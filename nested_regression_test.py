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
#   Tests that cgroup hierarchies are scheduled properly. Basically just
#   runs the mixed cgroup tests in separate containers with weights similar
#   to what we expect to see in production.
#
#   It also verfies that groups with prio do not overrun their dtf.

import os
import blkcgroup_test_lib

EXPERIMENTS = [
    ('600 (500 rdrand, 500 rdrand), 400 rdrand', 35),
    ('900 (900 rdrand, 100 rdrand), 100 (900 rdrand, 100 rdrand)', 35),
    ('500 rdrand, 100 (100 rdrand, 100 rdrand, 100 rdrand)', 35),
    ('500 rdrand, 100 (100 rdrand, 100 rdrand, 100 rdrand), 100 rdrand', 35),

    # Mixed worker experiments borrowed from regression_test.py and run in
    # 2 containers, '500 (test), 100 (test)'.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq)', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq)', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq)', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2)', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2)', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2)', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir)', 150),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir)', 150),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir)', 150),

    # Same experiments as above but run in 3 containers, '500 (test), 100 (test) 100 rdrand'.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100 rdrand', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100 rdrand', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100 rdrand', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100 rdrand', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100 rdrand', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100 rdrand', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100 rdrand', 150),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100 rdrand', 150),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100 rdrand', 150),

    # Same experiments as above but run in 3 containers, '500 (test), 100 (test) 100 rdseq'.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100 rdseq', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100 rdseq', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100 rdseq', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100 rdseq', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100 rdseq', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100 rdseq', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100 rdseq', 150),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100 rdseq', 150),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100 rdseq', 150),

    # Same experiments as above but run in 3 containers, '500 (test), 100 (test) 100 wrseq.dir'.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100 wrseq.dir', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100 wrseq.dir', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100 wrseq.dir', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100 wrseq.dir', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100 wrseq.dir', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100 wrseq.dir', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100 wrseq.dir', 150),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100 wrseq.dir', 150),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100 wrseq.dir', 150),

    # Same experiments as above but run in 3 containers, '500 (test), 100 (test) 100 wrseq.buf*2'.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100 wrseq.buf*2', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100 wrseq.buf*2', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100 wrseq.buf*2', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100 wrseq.buf*2', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100 wrseq.buf*2', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100 wrseq.buf*2', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100 wrseq.buf*2', 150),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100 wrseq.buf*2', 150),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100 wrseq.buf*2', 150),

    # Same experiments as above but run in 3 containers, '500p (test), 100 (test)'.
    # The goal here is not to verify the actual preemption but to check that the
    # groups still respect their weights even when they are high priority.
    ('500p (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq)', 35),
    ('500p (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq)', 35),
    ('500p (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq)', 35),
    ('500p (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2)', 150),
    ('500p (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2)', 150),
    ('500p (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2)', 150),
    ('500p (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir)', 150),
    ('500p (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir)', 150),
    ('500p (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir)', 150),

    # Same experiments as above, but this time give priority to one of the workers
    # in one of the cgroups.
    ('500 (500p rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq)', 35),
    ('500 (900p rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq)', 35),
    ('500 (100p rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq)', 35),
    ('500 (500p rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2)', 150),
    ('500 (900p rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2)', 150),
    ('500 (100p rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2)', 150),
    ('500 (500p rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir)', 150),
    ('500 (900p rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir)', 150),
    ('500 (100p rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir)', 150),

    # Run the io_load worker with prio in read & write mode.
    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100p io_load_read*2', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100p io_load_read*2', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100p io_load_read*2', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100p io_load_read*2', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100p io_load_read*2', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100p io_load_read*2', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100p io_load_read*2', 35),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100p io_load_read*2', 35),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100p io_load_read*2', 35),

    ('500 (500 rdrand, 500 rdseq), 100 (500 rdrand, 500 rdseq), 100p io_load_write*2', 35),
    ('500 (900 rdrand, 100 rdseq), 100 (900 rdrand, 100 rdseq), 100p io_load_write*2', 35),
    ('500 (100 rdrand, 900 rdseq), 100 (100 rdrand, 900 rdseq), 100p io_load_write*2', 35),
    ('500 (500 rdrand, 500 wrseq.buf*2), 100 (500 rdrand, 500 wrseq.buf*2), 100p io_load_write*2', 150),
    ('500 (900 rdrand, 100 wrseq.buf*2), 100 (900 rdrand, 100 wrseq.buf*2), 100p io_load_write*2', 150),
    ('500 (100 rdrand, 900 wrseq.buf*2), 100 (100 rdrand, 900 wrseq.buf*2), 100p io_load_write*2', 150),
    ('500 (500 rdrand, 500 wrseq.dir), 100 (500 rdrand, 500 wrseq.dir), 100p io_load_write*2', 35),
    ('500 (900 rdrand, 100 wrseq.dir), 100 (900 rdrand, 100 wrseq.dir), 100p io_load_write*2', 35),
    ('500 (100 rdrand, 900 wrseq.dir), 100 (100 rdrand, 900 wrseq.dir), 100p io_load_write*2', 35)
]

test = blkcgroup_test_lib.test_harness('Single mixed cgroup test')
blkcgroup_test_lib.setup_logging(debug=True)

seq_read_mb = 1500
timeout = '%ds' % (seq_read_mb // 25)


test.run_experiments(experiments=EXPERIMENTS,
                     seq_read_mb=seq_read_mb,
                     workvol=os.getcwd(),
                     kill_slower=True,
                     timeout=timeout)
