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


# Utility functions for managing control groups.
# Assumes many cgroup subsystems share a single hierarchy and mount point,
#   and other subsystems each have their own hierarchy and mount point.
# This grouping of subsystems is learned, not hard-coded.
# Most subsystem tests will work with both joint and separate hierarchies,


import logging, os
import error, utils

# Global cache of all the cgroups and their associated mount points.
cached_mounts = {}


def mount_point(subsystem):
    """Get mount point for the cgroup hierarchy handling a particular subsystem.
    """
    if subsystem not in cached_mounts:
        cached_mounts[subsystem] = ''
        for mounts in open('/proc/mounts').readlines():
            name, mount_pt, fs, options, junk = mounts.split(None, 4)
            if (fs == 'cgroup' and subsystem in options.split(',')  or
                fs == 'cpuset' == subsystem):
                    cached_mounts[subsystem] = mount_pt
                    break

    if cached_mounts[subsystem] == '':
        # Error out if no mount_point found.
        raise error.Error('Could not find an associated mount point for '
                          'subsystem: %s' % subsystem)

    return cached_mounts[subsystem]


def my_container():
    """Get current task's cgroup names, across all cgroup hierarchies."""
    container = {}  # maps cgroup-subsystems to mount-relative cgroup paths
    filename = '/proc/self/cgroup'
    if os.path.exists(filename):
        for hierarchy in open(filename).readlines():
            # eg 'number:oom,blockio,net,cpuacct,cpu,cpuset:/sys'
            junknum, subsystems, cgroup_name = hierarchy.split(':')
            cgroup_name = cgroup_name[1:-1]  # strip leading / and newline
            for subsystem in subsystems.split(','):
                container[subsystem] = cgroup_name
    else:
        filename = '/proc/self/cpuset'
        cgroup_name = utils.read_one_line(filename)[1:]  # strip leading /
        container['cpuset'] = cgroup_name
    return container


def my_cgroup_name(subsystem):
    """Get current task's current cgroup handling a particular subsystem."""
    container = my_container()
    if subsystem in container:
        return container[subsystem]
    else:
        raise error.Error('Kernel does not support cgroup subsystem %s'
                          % subsystem)


def root_cgroup(subsystem):
    """Get an accessor to the root cgroup, with no subsystem."""
    return cgroup(subsystem, '')


def cgroup(subsystem, name):
    """Get a cgroup accessor for the subsystem for cgroup name."""
    path = os.path.join(mount_point(subsystem), name)
    return cgroup_accessor(subsystem, path)


def cgroup_path(subsystem, name=None):
    if not name:
        name = my_cgroup_name(subsystem)
    return os.path.join(mount_point(subsystem), name)


def subsystem_prefix(subsystem):
    """Get qualifier for subsystem's attribute names."""
    filename = os.path.join(mount_point('cpuset'), 'cpus')
    if subsystem == 'cpuset' and os.path.exists(filename):
        return ''  # old non-cgroup style
    return subsystem + '.'


class cgroup_accessor(object):
    """An accessor for data related to a cgroup.

    This class controls getting and putting attributes, and cgroup creation and
    destruction. This is the recommended abstraction for modifying cgroup
    settings.
    """

    def __init__(self, subsystem, path):
        mount = mount_point(subsystem)
        self.subsystem = subsystem
        self.path = path
        self.name = path[len(mount)+1:]
        self.cpuset_hierarchy = mount == mount_point('cpuset')
        self.subsystem_prefix = subsystem_prefix(subsystem)


    def parent(self):
        """Get the parent of this cgroup."""
        return cgroup_accessor(self.subsystem, os.path.dirname(self.path))


    def child(self, name):
        """Get the child of this cgroup that has the requested name."""
        return cgroup_accessor(self.subsystem, os.path.join(self.path, name))


    def _attr_file(self, attr, prefix):
        """Get the name of the file that stores the given attribute."""
        if prefix == 'default':
            prefix = self.subsystem_prefix
        return os.path.join(self.path, prefix+attr)


    def get_attr(self, attr, prefix='default'):
        """Get the value of a given cgorup attribute."""
        filename = self._attr_file(attr, prefix)
        return [value.rstrip() for value in open(filename).readlines()]


    def put_attr(self, attr, values, prefix='default'):
        """Set the value of a given cgorup attribute."""
        filename = self._attr_file(attr, prefix)
        for value in values:
            utils.write_one_line(filename, value)


    def get_tasks(self):
        """Get the value of the 'tasks' cgorup attribute."""
        return self.get_attr('tasks', '')


    def put_tasks(self, tasks):
        """Set the value of the 'tasks' cgroup attribute.

        This requires special handling because only one task can be added
        through the file interface at a time.

        Raises an exception if the task cannot be moved.
        """
        for task in tasks:
            try:
                self.put_attr('tasks', [task], '')
            except Exception:
                if utils.pid_is_alive(task):
                    raise   # task exists but couldn't move it
                # task is gone or zombie so ignore this exception
        # also removes tasks from their current cgroup in same hierarchy
        logging.debug('Running pid %s in cgroup %s', ','.join(tasks), self.path)


    def move_my_task_here(self):
        """Move the current task to this cgroup.

        Raises an exception if the task cannot be moved.
        """
        self.put_tasks([str(os.getpid())])


    def release(self):
        """Destroy this cgroup.

        Destroy the cgroup and transfers all surviving tasks to this cgroup's
        parent.
        """
        if os.path.exists(self.path):
            # Transfer any survivor tasks (e.g. me) to parent
            self.parent().put_tasks(self.get_tasks())

            # remove the now-empty outermost cgroup of this subtree
            os.rmdir(self.path)
            logging.debug('Deleted cgroup %s', self.path)
