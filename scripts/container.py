#!/usr/bin/python

import os
import sys
import errno


class Container(object):
  CGROUP_MNT = '/dev/cgroup'

  def __init__(self, name, split_hierarchies=False):
    self.path = os.path.join(Container.CGROUP_MNT, name)
    self.split_hierarchies = split_hierarchies;
    if split_hierarchies:
      self.io_path = os.path.join(Container.CGROUP_MNT, 'io', name)
      self.cpuset_path = os.path.join(Container.CGROUP_MNT, 'cpuset', name)
      self.blkio_prefix = 'io'
    else:
      self.io_path = self.path
      self.cpuset_path = self.path
      self.blkio_prefix = 'blkio'

  def create(self):
    try:
      if self.split_hierarchies:
        os.mkdir(self.io_path)
        os.mkdir(self.cpuset_path)
      else:
        os.mkdir(self.path)
    except OSError, e:
      raise

  def delete(self):
    try:
      if self.split_hierarchies:
        os.rmdir(self.cpuset_path)
        os.rmdir(self.io_path)
      else:
        os.rmdir(self.path)
    except OSError, e:
      raise

  def parse_mems(self, strmems):
    mems = set()
    ranges = strmems.split(',')
    for range_ in ranges:
      if '-' in range_:
        begin, end = range_.split('-')
        mems |= set(range(int(begin), int(end)+1))
      else:
        mems.add(int(range_))

    return mems

  def set_io_weight(self, weight):
    service_level = open(os.path.join(self.io_path, 'blkio.weight'), 'w')
    service_level.write('%d' % weight)
    service_level.close()

  def set_io_service_level(self, device, svc_class, share):
    service_level = open(os.path.join(self.io_path, self.blkio_prefix + '.io_service_level'), 'w', buffering=0)
    service_level.write('%s %d 0 %d\n' % (device, svc_class, share))
    service_level.close()

  def set_mems(self, nodes):
    mems = open(os.path.join(self.cpuset_path, 'cpuset.mems'), 'w')
    mems.write(','.join([str(node) for node in nodes]) + '\n')
    mems.close()

  def set_cpus(self, cpuset_cpus):
    cpus = open(os.path.join(self.cpuset_path, 'cpuset.cpus'), 'w')
    # allow all cpus for now
    cpus.write('0')
    cpus.close()

  def create_device_value_dict(self, lines):
    """
       Parse the output into a dict with the strucure { 'device' => 'value' ... }
       Example { 'sda' => '5000' }
    """
    ret = {}
    for i in lines:
      parts = i.split()
      ret[parts[0]] = parts[1]
    return ret

  def create_device_cat_value_dict(self, lines):
    """
       Parse the output into a multi-level dictionary with the structure:
       { 'device' => { 'category' => 'value' ... } ... }
       Example: { 'sda' => { 'Sync' => '100', 'Async' => '200' } }
    """
    ret = {}
    for i in lines:
      parts = i.split()
      device = parts[0]
      if device != 'Total':
        # Put in an empty dict on the first iteration.
        if device not in ret:
          ret[device] = {}

        cat_val_dict = ret[device]
        cat_val_dict[parts[1]] = parts[2]

    return ret

  def get_io_avg_queue_size_self(self):
    lines = open(os.path.join(self.io_path,
                              'io.avg_queue_size_self'), 'r').readlines()
    return self.create_device_value_dict(lines)

  def get_io_queued_self(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_queued_self'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_serviced(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_serviced'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_serviced_bytes(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_service_bytes'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_service_time(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_service_time'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_timeslice_used(self):
    lines = open(os.path.join(self.io_path,
                              'io.timeslice_used'), 'r').readlines()
    return self.create_device_value_dict(lines)

  def get_io_wait_time(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_wait_time'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_wait_time_self(self):
    lines = open(os.path.join(self.io_path,
                              'io.wait_time_self'), 'r').readlines()
    return self.create_device_value_dict(lines)

  def get_io_idle_time(self):
    lines = open(os.path.join(self.io_path,
                             'io.idle_time'), 'r').readlines()
    return self.create_device_value_dict(lines)

  def get_io_sectors(self):
    lines = open(os.path.join(self.io_path,
                             'io.sectors'), 'r').readlines()
    return self.create_device_value_dict(lines)

  def get_io_preempt_count_self(self):
    lines = open(os.path.join(self.io_path,
                              'io.preempt_count_self'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_preempt_throttle_self(self):
    lines = open(os.path.join(self.io_path,
                              'io.preempt_throttle_self'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def get_io_merged(self):
    lines = open(os.path.join(self.io_path,
                              'io.io_merged'), 'r').readlines()
    return self.create_device_cat_value_dict(lines)

  def reset_all(self):
    open(os.path.join(self.io_path, 'io.avg_queue_size_self'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_queued_self'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_serviced'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_service_bytes'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_service_time'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.timeslice_used'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_wait_time'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.wait_time_self'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.idle_time'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.sectors'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.preempt_count_self'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.preempt_throttle_self'), 'w').write('0')
    open(os.path.join(self.io_path, 'io.io_merged'), 'w').write('0')

  def get_mems(self):
    return self.parse_mems(open(os.path.join(self.cpuset_path, 'cpuset.mems'), 'r').read())

  def swallow_pid(self, pid):
    if self.split_hierarchies:
      open(os.path.join(self.io_path, 'tasks'), 'w', buffering=0).write('%d\n' % pid)
      open(os.path.join(self.cpuset_path, 'tasks'), 'w', buffering=0).write('%d\n' % pid)
    else:
      open(os.path.join(self.path, 'tasks'), 'w').write('%d\n' % pid)

  def empty_container(self, container_path):
    lines = open(os.path.join(container_path, 'tasks')).read().split('\n')
    root_tasks = open(os.path.join(CGROUP_MNT, 'tasks'), 'wb')
    for line in lines:
      root_tasks.write(line)

  def empty_container(self):
    if self.split_hierarchies:
      self.empty_container(self.cpuset_path)
      self.empty_container(self.io_path)
    else:
      self.empty_container(self.path)

