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
NO_LIMIT = (1 << 63) - 1   # containername/memory/memory.limit_in_bytes

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

    if os.path.exists('/dev/cgroup/tasks') or \
       os.path.exists('/dev/cgroup/cpuset/tasks'):
        # running on 2.6.26 or later kernel with containers on:
        super_root_path = '/dev/cgroup'
        cpuset_prefix = 'cpuset.'
        if get_boot_numa():
            mem_isolation_on = False
            fake_numa_containers = True
        else:  # memcg containers IFF compiled-in & mounted & non-fakenuma boot
            fake_numa_containers = False
            mem_isolation_on = os.path.exists(
                    '/dev/cgroup/memory/memory.limit_in_bytes')
    else:
        # neither cpuset nor cgroup filesystem active:
        super_root_path = None
        cpuset_prefix = 'no_cpusets_or_cgroups_exist'
        mem_isolation_on = fake_numa_containers = False

    logging.debug('mem_isolation: %s', mem_isolation_on)
    logging.debug('fake_numa_containers: %s', fake_numa_containers)

    # Get the total available memory depending on memory isolation scheme.
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


def is_memcg():
    """Return True/False depending on the memory isolation scheme is memcg."""
    discover_container_style()
    if mem_isolation_on:
        return True
    else:
        return False


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


def cpuset_attr(container_name, attr):
    discover_container_style()
    return os.path.join(super_root_path, container_name, cpuset_prefix+attr)


def blkio_attr(container_name, attr):
    discover_container_style()
    # current version assumes shared cgroup hierarchy
    return os.path.join(super_root_path, container_name, 'io.'+attr)


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


def set_blkio_controls(container_name, device,
                       weight, priority, shared_sync_queues):
    """Define all the blkio parameters.

    Set the blkio controls for one container, for selected disks
    writing directly to /dev/cgroup/container_name/blkio.weight_device

    Args:
        container_name = the name of the container where to update the values.
        device = the name of the device to set the blkio parameters on.
        weight = user specified weight (100-1000) for the blkio subsystem.
        priority = 0-2, the I/O priority (0 is best effort, 1 is prio, 2 is
          idle)
        shared_sync_queues = if true, uses per-cgroup sync queues, otherwise
          uses per-task sync queues.
    """
    # Setup path to blkio cgroup.
    weight_device = blkio_attr(container_name, 'io_service_level')
    logging.info('weight device: ' + weight_device)
    if not os.path.exists(weight_device):
        raise error.Error("Kernel predates blkio features or blkio "
                          "cgroup is mounted separately from cpusets")

    # Set the service level for the device.
    disk_info = '%s %d 0 %s' % (device, priority, weight / 10)
    utils.write_one_line(weight_device, disk_info)

    logging.debug('set io_service_level of %s to %s',
                  container_name, disk_info)

    shared_sync_queues_device = blkio_attr(container_name, 'shared_sync_queues')
    if not os.path.exists(shared_sync_queues_device):
        # This is not fatal, just ignore the value of the flag
        logging.warn("Kernel predates shared sync queues")
        return

    logging.info('shared sync queues device: ' + shared_sync_queues_device)
    shared_sync_queues_str = "%d" % shared_sync_queues
    utils.write_one_line(shared_sync_queues_device, "%d" % shared_sync_queues)

    logging.debug('set shared_sync_queues of %s to %s',
                  container_name, shared_sync_queues_str)


def _create_fakenuma_container(name, mems):
    # Ensure that fakenuma is enabled.
    need_fake_numa()

    container_path = full_path(name)
    if os.path.exists(container_path):
        logging.debug('Container %s already exists. Updating current values.',
                      container_path)
    else:
        raise error.Error('Container: %s does not exist.', container_path)

    utils.write_one_line(cpuset_attr(name, 'mem_hardwall'), '1')
    utils.write_one_line(mems_path(name), ','.join(map(str, mems)))
    logging.debug('Created memory container %s (fakenuma) with %d nodes '
                  'equalling %sBytes.', name, len(get_mem_nodes(name)),
                  utils.human_format(container_bytes(name)))


def _create_memcg_container(name, req_bytes):
    # Ensure that memory isolation (memcg) is enabled.
    need_mem_containers()

    # Create & initialize the memory container.
    os.mkdir(full_path(name))
    utils.write_one_line(memory_path(name)+'.limit_in_bytes', str(req_bytes))
    logging.debug('Created memory container %s (memcg) with %sBytes.',
                  name, utils.human_format(container_bytes(name)))


def _create_cpuset_container(name, cpus):
    # Create & initialize the cpu container.
    cpuset_path = full_path(os.path.join("cpuset", os.path.basename(name)))
    os.mkdir(full_path(cpuset_path))
    utils.write_one_line(cpus_path(cpuset_path), ','.join(map(str, cpus)))
    logging.debug('Created cpuset container %s with %s cpus.', 
                  name, len(cpus))


def _create_fake_numa_container_directly(name, parent, mbytes):
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

        _create_fakenuma_container(name, mems)
    finally:
        my_unlock(lockfile)


def create_container_directly(name, mbytes):
    parent = os.path.dirname(name)
    if fake_numa_containers:
        _create_fake_numa_container_directly(name, parent, mbytes)
    else:
        _create_memcg_container(name, mbytes<<20)


def create_container_memory(name, mbytes, root=SUPER_ROOT):
    """Create a memory container and move job's current pid into it.

    Args:
        name = arbitrary string tag
        mbytes = reqested memory for job in megabytes
        root = the parent cpuset to nest this new set within
            '': unnested top-level container
    Return:
        name: the name of the container.
    """
    discover_container_style()

    if fake_numa_containers:
        # Fake numa.
        croot = os.path.join('cpuset', root)
    else:
        # Memcg.
        croot = os.path.join('memory', root)

    if not container_exists(croot):
        raise error.Error('Parent container "%s" does not exist' % root)

    cname = os.path.join(croot, name)  # path relative to super_root

    # Create the containers.
    create_container_directly(cname, mbytes)

    return os.path.join(root, name)


def create_container_cpuset(name, cpus=None, root=SUPER_ROOT):
    """Create a cpuset container and move job's current pid into it.
    Allocate the list "cpus" of cpus to that container

    Args:
        name = arbitrary string tag
        cpus = list of cpu indicies to associate with the cpuset
            defaults to all cpus avail with given root
        root = the parent cpuset to nest this new set within
            '': unnested top-level container
    Return:
        name: the name of the container.
    """
    croot = os.path.join('cpuset', root)

    if not container_exists(croot):
        raise error.Error('Parent container "%s" does not exist' % root)

    if cpus is None:
        # Use all the cpus present on system.
        cpus = get_cpus(croot)
    else:
        cpus = set(cpus)  # interface uses list
    if not cpus:
        raise error.Error('Creating container with no cpus')

    cname = os.path.join(croot, name)  # path relative to super_root
    if os.path.exists(full_path(cname)):
        raise error.Error('Container %s already exists. '
                          'Try running test with -c which deletes '
                          'test state.' % name)

    # Create the containers.
    _create_cpuset_container(cname, cpus)

    return os.path.join(root, name)


def create_container_blkio(device, name, root=SUPER_ROOT,
                           weight=None, priority=None,
                           shared_sync_queues=None):
    """Create a cpuset container and move job's current pid into it.
    Allocate the list "cpus" of cpus to that container

    Args:
        device = the device under test.
        name = arbitrary string tag
        root = the parent cpuset to nest this new set within
            '': unnested top-level container
        weight = user specified weight for the blkio subsystem
        priority = 0-2, the I/O priority (0 is best effort, 1 is prio, 2 is
          idle)
        shared_sync_queues = if true, uses per-cgroup sync queues, otherwise
          uses per-task sync queues.
    Return:
        name: the name of the container.
    """
    if weight is None:
        raise ValueError('weight not defined.')

    if priority is None:
        raise ValueError('priority not defined.')

    if shared_sync_queues is None:
        raise ValueError('shared_sync_queues not defined.')

    croot = os.path.join('io', root)

    cname = os.path.join(croot, name)  # path relative to super_root
    if os.path.exists(full_path(cname)):
        raise error.Error('Container %s already exists. '
                          'Try running test with -c which deletes '
                          'test state.' % cname)

    os.mkdir(full_path(cname))

    # Initialize blkio container.
    set_blkio_controls(cname, device,
                       weight, priority, shared_sync_queues)

    return os.path.join(root, name)


def get_boot_numa():
    """Get boot-time numa=fake=xyz option for current boot.

    For example, numa=fake=nnn,  numa=fake=nnnM, or nothing
    """
    label = 'numa=fake='
    for arg in utils.read_one_line('/proc/cmdline').split():
        if arg.startswith(label):
            return arg[len(label):]
    return ''
