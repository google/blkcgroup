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

EXPERIMENTS = [
    ('600 (500 rdrand, 500 rdrand), 400 rdrand', 35),
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
