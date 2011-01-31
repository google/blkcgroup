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
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
#   implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
#
# A general regression test for cgroup-based block layer isolation.

import os
import blkcgroup_test_lib


EXPERIMENTS = [
  # Experiments consist of a string and a number.
  #
  # The string specifies a set of workers (including the weights they should be
  # assigned).
  # The number specifies the amount of permitted variance from the requested DTF
  # for a test be be considered "passing".

  # Uniform worker experiments
  ('500 rdseq, 500 rdseq', 35),
  ('900 rdseq, 100 rdseq', 35),
  ('100 rdseq, 900 rdseq', 35),
  ('600 rdseq, 200 rdseq, 200 rdseq', 35),
  ('650 rdseq, 100 rdseq, 100 rdseq, 150 rdseq', 35),
  ('140 rdseq, 140 rdseq, 140 rdseq, 140 rdseq, 140 rdseq, 140 rdseq, 160 rdseq', 35),

  ('500 rdrand, 500 rdrand', 35),
  ('900 rdrand, 100 rdrand', 35),
  ('100 rdrand, 900 rdrand', 35),
  ('600 rdrand, 200 rdrand, 200 rdrand', 35),
  ('650 rdrand, 100 rdrand, 100 rdrand, 150 rdrand', 35),
  ('140 rdrand, 140 rdrand, 140 rdrand, 140 rdrand, 140 rdrand, 140 rdrand, 160 rdrand', 35),

  ('500 wrseq.buf*2, 500 wrseq.buf*2', 150),
  ('900 wrseq.buf*2, 100 wrseq.buf*2', 150),
  ('100 wrseq.buf*2, 900 wrseq.buf*2', 150),
  ('600 wrseq.buf*2, 200 wrseq.buf*2, 200 wrseq.buf*2', 150),
  ('650 wrseq.buf*2, 100 wrseq.buf*2, 100 wrseq.buf*2, 150 wrseq.buf*2', 150),
  ('140 wrseq.buf*2, 140 wrseq.buf*2, 140 wrseq.buf*2, 140 wrseq.buf*2, 140 wrseq.buf*2, 140 wrseq.buf*2, 160 wrseq.buf*2', 150),

  ('500 wrseq.dir, 500 wrseq.dir', 35),
  ('900 wrseq.dir, 100 wrseq.dir', 35),
  ('100 wrseq.dir, 900 wrseq.dir', 35),
  ('600 wrseq.dir, 200 wrseq.dir, 200 wrseq.dir', 35),
  ('650 wrseq.dir, 100 wrseq.dir, 100 wrseq.dir, 150 wrseq.dir', 35),
  ('140 wrseq.dir, 140 wrseq.dir, 140 wrseq.dir, 140 wrseq.dir, 140 wrseq.dir, 140 wrseq.dir, 160 wrseq.dir', 35),

  # Mixed worker experiments
  ('500 rdrand, 500 rdseq', 35),
  ('900 rdrand, 100 rdseq', 35),
  ('100 rdrand, 900 rdseq', 35),
  ('500 rdrand, 500 wrseq.buf*2', 150),
  ('900 rdrand, 100 wrseq.buf*2', 150),
  ('100 rdrand, 900 wrseq.buf*2', 150),
  ('500 rdrand, 500 wrseq.dir', 35),
  ('900 rdrand, 100 wrseq.dir', 35),
  ('100 rdrand, 900 wrseq.dir', 35)
]

test = blkcgroup_test_lib.test_harness('Regression test')
blkcgroup_test_lib.setup_logging(debug=False)

seq_read_mb = 1000
timeout = '%ds' % (seq_read_mb // 25)

test.run_experiments(experiments=EXPERIMENTS,
                     seq_read_mb=seq_read_mb,
                     workvol=os.getcwd(),
                     kill_slower=True,
                     timeout=timeout)
