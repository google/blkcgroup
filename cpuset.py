# Copyright 2011 Google Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


# A basic cpuset/cgroup container manager for limiting memory use during tests.

import glob, fcntl, logging, os, re
import error, utils

SUPER_ROOT = ''      # root of all containers or cgroups
NO_LIMIT = (1 << 63) - 1   # containername/memory.limit_in_bytes if no limit

super_root_path = ''    # usually '/dev/cgroup'; '/dev/cpuset' on 2.6.18
cpuset_prefix   = None  # usually 'cpuset.'; '' on 2.6.18
fake_numa_containers = False # container mem via numa=fake mem nodes, else pages
mem_isolation_on = False
node_mbytes = 0         # mbytes in one typical mem node
root_container_bytes = 0  # squishy limit on effective size of root container


def discover_container_style():
    """Fetch information about containers and cache in global state."""
    global super_root_path, cpuset_prefix
    global mem_isolation_on, fake_numa_containers
    global node_mbytes, root_container_bytes

    if super_root_path != '':
        return  # already looked up

    if os.path.exists('/dev/cgroup/tasks'):
        # running on 2.6.26 or later kernel with containers on:
        super_root_path = '/dev/cgroup'
        cpuset_prefix = 'cpuset.'
        if get_boot_numa():
            mem_isolation_on = fake_numa_containers = True
        else:  # memcg containers IFF compiled-in & mounted & non-fakenuma boot
            fake_numa_containers = False
            mem_isolation_on = os.path.exists(
                    '/dev/cgroup/memory.limit_in_bytes')
            # TODO: handle possibility of where memcg is mounted as its own
            #       cgroup hierarchy, separate from cpuset?

    else:
        # neither cpuset nor cgroup filesystem active:
        super_root_path = None
        cpuset_prefix = 'no_cpusets_or_cgroups_exist'
        mem_isolation_on = fake_numa_containers = False

    logging.debug('mem_isolation: %s', mem_isolation_on)
    logging.debug('fake_numa_containers: %s', fake_numa_containers)
    if fake_numa_containers:
        node_mbytes = int(mbytes_per_mem_node())

    elif mem_isolation_on:  # memcg-style containers
        # For now, limit total of all containers to using just 98% of system's
        # visible total ram, to avoid oom events at system level, and avoid
        # page reclaim overhead from going above kswapd highwater mark.
        system_visible_pages = utils.memtotal() >> 2
        usable_pages = int(system_visible_pages * 0.98)
        root_container_bytes = usable_pages << 12
        logging.debug('root_container_bytes: %s',
                      utils.human_format(root_container_bytes))


def need_mem_containers():
    """Raise an exception if memory-islation containers are not enabled."""
    discover_container_style()
    if not mem_isolation_on:
        raise error.Error('Memory isolation containers are not enabled')

def need_fake_numa():
    """Raise an exception if fake numa is not enabled."""
    discover_container_style()
    if not fake_numa_containers:
        raise error.Error('fake=numa is not enabled')


def full_path(container_name):
    """Get the full path to a container from its name."""
    discover_container_style()
    return os.path.join(super_root_path, container_name)


def unpath(container_path):
    return container_path[len(super_root_path)+1:]


def cpuset_attr(container_name, attr):
    discover_container_style()
    return os.path.join(super_root_path, container_name, cpuset_prefix+attr)


def blkio_attr(container_name, attr):
    discover_container_style()
    # current version assumes shared cgroup hierarchy
    return os.path.join(super_root_path, container_name, 'blkio.'+attr)


def tasks_path(container_name):
    return os.path.join(full_path(container_name), 'tasks')


def mems_path(container_name):
    return cpuset_attr(container_name, 'mems')


def memory_path(container_name):
    return os.path.join(super_root_path, container_name, 'memory')


def cpus_path(container_name):
    return cpuset_attr(container_name, 'cpus')


def container_exists(name):
    return name is not None and os.path.exists(tasks_path(name))


def move_tasks_into_container(name, tasks):
    task_file = tasks_path(name)
    for task in tasks:
        try:
            logging.debug('moving task %s into container "%s"', task, name)
            utils.write_one_line(task_file, task)
        except Exception:
            if utils.pid_is_alive(task):
                raise   # task exists but couldn't move it
            # task is gone or zombie so ignore this exception


def move_self_into_container(name):
    """Move the current process into the named container."""
    me = str(os.getpid())
    move_tasks_into_container(name, [me])
    logging.debug('running self (pid %s) in container "%s"', me, name)


def my_lock(lockname):
    """Create and take a file lock. Returns the file name."""
    # lockname is 'inner'
    lockdir = '/tmp'
    lockname = os.path.join(lockdir, '.cpuset.lock.'+lockname)
    lockfile = open(lockname, 'w')
    fcntl.flock(lockfile, fcntl.LOCK_EX)
    return lockfile


def my_unlock(lockfile):
    """Release a file lock, taking the file name."""
    fcntl.flock(lockfile, fcntl.LOCK_UN)
    lockfile.close()


def rangelist_to_set(rangelist):
    """Convert '1-3,7,9-12' to set(1,2,3,7,9,10,11,12)"""
    result = set()
    if not rangelist:
        return result
    for x in rangelist.split(','):
        if re.match(r'^(\d+)$', x):
            result.add(int(x))
            continue
        m = re.match(r'^(\d+)-(\d+)$', x)
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            result.update(set(range(start, end+1)))
            continue
        msg = 'Cannot understand data input: %s %s' % (x, rangelist)
        raise ValueError(msg)
    return result


def my_container_name():
    """Get current process's inherited or self-built container name.

    The container is within /dev/cpuset or /dev/cgroup, or
    '' for root container."""
    name = utils.read_one_line('/proc/%i/cpuset' % os.getpid())
    return name[1:]   # strip leading /


def get_mem_nodes(container_name):
    "Return mem nodes now available to a container, both exclusive & shared"""
    file_name = mems_path(container_name)
    if os.path.exists(file_name):
        return rangelist_to_set(utils.read_one_line(file_name))
    else:
        return set()


def _busy_mem_nodes(parent_container):
    """Get busy memory node information for children of the parent_container.

    Get set of numa memory nodes now used (exclusively or shared)
    by existing children of parent container"""
    busy = set()
    mem_files_pattern = os.path.join(full_path(parent_container),
                                     '*', cpuset_prefix+'mems')
    for mem_file in glob.glob(mem_files_pattern):
        child_container = os.path.dirname(mem_file)
        busy |= get_mem_nodes(child_container)
    return busy


def available_exclusive_mem_nodes(parent_container):
    """Get the memory nodes which can be allocated exclusively to children.

    Get subset of numa memory nodes of parent container which could
    be allocated exclusively to new child containers.
    This excludes nodes now allocated to existing children.
    """
    need_fake_numa()
    available = get_mem_nodes(parent_container)
    available -= _busy_mem_nodes(parent_container)
    return available


def node_avail_kbytes(node):
    """Get the number of available kilobytes for a node."""
    return node_mbytes << 10  # crude; fixed numa node size


def nodes_avail_mbytes(nodes):
    """Get the combined user+available size, in megabytes."""
    return sum(node_avail_kbytes(n) for n in nodes) // 1024


def container_bytes(name):
    """Get the memory limit for a given container, in bytes."""
    if fake_numa_containers:
        return nodes_avail_mbytes(get_mem_nodes(name)) << 20
    else:
        while True:
            file = memory_path(name) + '.limit_in_bytes'
            limit = int(utils.read_one_line(file))
            if limit < NO_LIMIT:
                return limit
            if name == SUPER_ROOT:
                return root_container_bytes
            name = os.path.dirname(name)


def container_mbytes(name):
    """Get the memory limit for a given container, in megabytes."""
    return container_bytes(name) >> 20


def mbytes_per_mem_node():
    """Get the mbyte size of the 'standard' fakenuma mem node, as a float.

    This assumes that all fakenuma mem noes are the same size.
    """
    numa = get_boot_numa()
    if numa.endswith('M'):
        return float(numa[:-1])  # mbyte size of fake nodes
    elif numa:
        nodecnt = int(numa)  # fake numa mem nodes for container isolation
    else:
        nodecnt = len(utils.numa_nodes())  # phys mem-controller nodes
    # Use guessed total physical mem size, not kernel's
    #   lesser 'available memory' after various system tables.
    return utils.rounded_memtotal() / (nodecnt * 1024.0)


def get_cpus(container_name):
    """Get the set of cpus in a container."""
    file_name = cpus_path(container_name)
    if os.path.exists(file_name):
        return rangelist_to_set(utils.read_one_line(file_name))
    else:
        return set()


def get_tasks(container_name):
    """Get the list of tasks in a container."""
    file_name = tasks_path(container_name)
    try:
        tasks = [x.rstrip() for x in open(file_name).readlines()]
    except IOError:
        if os.path.exists(file_name):
            raise
        tasks = []   # container doesn't exist anymore
    return tasks


def set_blkio_controls(container_name, device, blkio_shares):
    """Define all the blkio parameters.

    Set the blkio controls for one container, for selected disks
    writing directly to /dev/cgroup/container_name/blkio.weight_device

    Args:
        container_name: the name of the container where to update the values.
        device: the name of the device to set the blkio parameters on.
        blkio_shares = user specified share (100-1000) for the blkio subsystem.
    """
    # Setup path to blkio cgroup.
    weight_device = blkio_attr(container_name, 'weight_device')
    if not os.path.exists(weight_device):
        raise error.Error("Kernel predates blkio features or blkio "
                          "cgroup is mounted separately from cpusets")

    # Gather the "major:minor dtf" values.
    weight = blkio_shares
    disk_info = '%s %s' % (utils.get_device_id(device), weight)

    # Add entry to the cgroup.
    utils.write_one_line(weight_device, disk_info)

    logging.debug('set_blkio_controls of %s to %s',
                  container_name, disk_info)


def create_container_with_specific_mems_cpus(name, mems, cpus):
    need_fake_numa()
    os.mkdir(full_path(name))
    utils.write_one_line(cpuset_attr(name, 'mem_hardwall'), '1')
    utils.write_one_line(mems_path(name), ','.join(map(str, mems)))
    utils.write_one_line(cpus_path(name), ','.join(map(str, cpus)))
    logging.debug('container %s has %d cpus and %d nodes totalling %s bytes',
                  name, len(cpus), len(get_mem_nodes(name)),
                  utils.human_format(container_bytes(name)) )


def create_container_via_memcg(name, parent, bytes, cpus):
    # create container via direct memcg cgroup writes
    os.mkdir(full_path(name))
    nodes = utils.read_one_line(mems_path(parent))
    utils.write_one_line(mems_path(name), nodes)  # inherit parent's nodes
    utils.write_one_line(memory_path(name)+'.limit_in_bytes', str(bytes))
    utils.write_one_line(cpus_path(name), ','.join(map(str, cpus)))
    logging.debug('Created container %s directly via memcg,'
                  ' has %d cpus and %s bytes',
                  name, len(cpus), utils.human_format(container_bytes(name)))


def _create_fake_numa_container_directly(name, parent, mbytes, cpus):
    need_fake_numa()
    lockfile = my_lock('inner')   # serialize race between parallel tests
    try:
        # Pick specific mem nodes for new cpuset's exclusive use
        # For now, arbitrarily pick highest available node numbers
        needed_kbytes = mbytes * 1024
        nodes = sorted(list(available_exclusive_mem_nodes(parent)))
        kbytes = 0
        nodecnt = 0
        while kbytes < needed_kbytes and nodecnt < len(nodes):
            nodecnt += 1
            kbytes += node_avail_kbytes(nodes[-nodecnt])
        if kbytes < needed_kbytes:
            parent_mbytes = container_mbytes(parent)
            if mbytes > parent_mbytes:
                raise error.Error(
                      "New container's %d Mbytes exceeds "
                      "parent container's %d Mbyte size"
                      % (mbytes, parent_mbytes) )
            else:
                raise error.Error(
                      "Existing sibling containers hold "
                      "%d Mbytes needed by new container"
                      % ((needed_kbytes - kbytes)//1024) )
        mems = nodes[-nodecnt:]

        create_container_with_specific_mems_cpus(name, mems, cpus)
    finally:
        my_unlock(lockfile)


def create_container_directly(name, mbytes, cpus):
    parent = os.path.dirname(name)
    if fake_numa_containers:
        _create_fake_numa_container_directly(name, parent, mbytes, cpus)
    else:
        create_container_via_memcg(name, parent, mbytes<<20, cpus)


def create_container_with_mbytes_and_specific_cpus(device, name, mbytes,
                                                   cpus=None, root=SUPER_ROOT,
                                                   blkio_shares=None,
                                                   move_in=True, timeout=0):
        """Create a cpuset container and move job's current pid into it.
        Allocate the list "cpus" of cpus to that container

        Args:
            device = the device under test.
            name = arbitrary string tag
            mbytes = reqested memory for job in megabytes
            cpus = list of cpu indicies to associate with the cpuset
                defaults to all cpus avail with given root
            root = the parent cpuset to nest this new set within
                '': unnested top-level container
            blkio_shares = user specified share for the blkio subsystem
            move_in = True: Move current process into the new container now.
            timeout = must be 0: persist until explicitly deleted.

        Return:
            name: the name of the container.
        """
        if not blkio_shares:
            raise error.ValueError('blkio_shares not defined.')

        # Initialize memory container.
        need_mem_containers()
        if not container_exists(root):
            raise error.Error('Parent container "%s" does not exist' % root)
        if cpus is None:
            # default to biggest container we can make under root
            cpus = get_cpus(root)
        else:
            cpus = set(cpus)  # interface uses list
        if not cpus:
            raise error.Error('Creating container with no cpus')
        name = os.path.join(root, name)  # path relative to super_root
        if os.path.exists(full_path(name)):
            raise error.Error('Container %s already exists. '
                              'Try running test with -c which deletes '
                              'test state.' % name)
        create_container_directly(name, mbytes, cpus)

        # Initialize blkio container.
        set_blkio_controls(name, device, blkio_shares)

        # Move pid into container.
        if move_in:
            move_self_into_container(name)

        return name


def get_boot_numa():
    """Get boot-time numa=fake=xyz option for current boot.

    For example, numa=fake=nnn,  numa=fake=nnnM, or nothing
    """
    label = 'numa=fake='
    for arg in utils.read_one_line('/proc/cmdline').split():
        if arg.startswith(label):
            return arg[len(label):]
    return ''
