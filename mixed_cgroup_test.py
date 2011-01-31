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

import os
import blkcgroup_test_lib

PRE_EXPERIMENT_FILENAME='pre-experiment.txt'
POST_EXPERIMENT_FILENAME='post-experiment.txt'

def print_container_data(cgroup_names, filename):
    """Print blkio statistics for our control groups."""
    for cgroup in cgroup_names:
        os.system('for file in `ls /dev/cgroup/%(c)s/blkio.*`; '
            'do echo $file >> %(f)s; cat $file >> %(f)s; echo >> %(f)s;done'
            % {'c': cgroup, 'f': filename})


def pre_experiment(cgroup_names):
    print_container_data(cgroup_names, PRE_EXPERIMENT_FILENAME)


def post_experiment(cgroup_names):
    print_container_data(cgroup_names, POST_EXPERIMENT_FILENAME)


def delete_if_exists(filename):
    if os.path.exists(filename):
        os.unlink(filename)



EXPERIMENTS = [
    ('600 rdrand, 400 wrseq.dir', 35),
]

test = blkcgroup_test_lib.test_harness('Single mixed cgroup test')
blkcgroup_test_lib.setup_logging(debug=False)

seq_read_mb = 1000
timeout = '%ds' % (seq_read_mb // 25)


delete_if_exists(PRE_EXPERIMENT_FILENAME)
delete_if_exists(POST_EXPERIMENT_FILENAME)


test.run_experiments(experiments=EXPERIMENTS,
                     seq_read_mb=seq_read_mb,
                     workvol=os.getcwd(),
                     kill_slower=True,
                     timeout=timeout,
                     pre_experiment_cb=pre_experiment,
                     post_experiment_cb=post_experiment)
