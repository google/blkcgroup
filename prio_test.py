#!/usr/bin/python
#
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
#
#
# A fairly minimal test to run a test experiment with two workers:
#   - A random read worker, with 60% dtf
#   - A sequential writer (direct writes), with 40% dtf
#
# This test also serves to show off how methods can be hooked in before and
# after an experiment to retrieve container statistics for debugging.

import logging
import os
import blkcgroup_test_lib

def dump_wait_histo(container, worker, device):
    for line in container['blkio_cgroup'].get_attr('io_wait_time_histo'):
        parts = line.split()
        # Line format is
        # device direction <10ms 10-20 20-50 50-100 100-200 200-500...
        if parts[0] == device:
            int_parts = map(int, parts[2:])
            total = reduce(lambda x, y: x+y, int_parts)
            if total == 0:
                continue
            over_50 = total - int_parts[0] - int_parts[1] - int_parts[2]
            over_100 = over_50 - int_parts[3]

            mode = parts[1]
            logging.info('container %s %s %s wait: %f%% > 50ms, %f%% > 100ms' %
                         (container['name'], worker, mode,
                          over_50 * 100.0 / total, over_100 * 100.0 / total))


def dump_preempt_count_stats(container, worker, device):
    for line in container['blkio_cgroup'].get_attr('preempt_count_self'):
        parts = line.split()
        if parts[0] == device:
            logging.info('container %s %s: preempt count %s' %
                         (container['name'], worker, line))


def dump_preempt_throttle_stats(container, worker, device):
    for line in container['blkio_cgroup'].get_attr('preempt_throttle_self'):
        parts = line.split()
        if parts[0] == device:
            logging.info('container %s %s: preempt throttle %s' %
                         (container['name'], worker, line))



def dump_exp_stats(tree, device):
    """Log the percentage of requests that waited 50ms, and 100ms"""
    for container in tree:
        worker = ''
        if container['worker']:
            worker = '(%s)' % container['worker']
        dump_wait_histo(container, worker, device)
        dump_preempt_count_stats(container, worker, device)
        dump_preempt_throttle_stats(container, worker, device)

        dump_exp_stats(container['nest'], device)



EXPERIMENTS = [
    # Basic proportion testing.
    ('450p io_load_read, 50 rdrand.delay2', 35)
]

test = blkcgroup_test_lib.test_harness('Priority testing',
                                       post_experiment_cb=dump_exp_stats)
blkcgroup_test_lib.setup_logging(debug=False)

seq_read_mb = 1500
timeout = '60s'


test.run_experiments(experiments=EXPERIMENTS,
                     seq_read_mb=seq_read_mb,
                     workvol=os.getcwd(),
                     kill_slower=True,
                     timeout=timeout)
