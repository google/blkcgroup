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
# A regression test for the shared_sync_queues flag.

import os
import blkcgroup_test_lib


EXPERIMENTS = [
  ('140S rdseq*8, 140 rdseq*8, 140S rdseq*8, 140 rdseq*8, 140S rdseq*8, 140 rdseq*8, 160S rdseq*8', 35),
  ('140S rdrand*8, 140 rdrand*8, 140S rdrand*8, 140 rdrand*8, 140S rdrand*8, 140 rdrand*8, 160S rdrand*8', 35),
  ('140S wrseq.buf*8, 140 wrseq.buf*8, 140S wrseq.buf*8, 140S wrseq.buf*8, 140 wrseq.buf*8, 140S wrseq.buf*8, 160 wrseq.buf*8', 150),
  ('140S wrseq.dir*8, 140 wrseq.dir*8, 140S wrseq.dir*8, 140 wrseq.dir*8, 140S wrseq.dir*8, 140 wrseq.dir*8, 160S wrseq.dir*8', 35),
  ('500S rdrand*8, 500 wrseq.buf*8', 150),
  ('500 rdrand*8, 500S wrseq.dir*8', 35),
]

test = blkcgroup_test_lib.test_harness('Shared sync queues test')
blkcgroup_test_lib.setup_logging(debug=False)

seq_read_mb = 1000
timeout = '%ds' % (seq_read_mb // 25)

test.run_experiments(experiments=EXPERIMENTS,
                     seq_read_mb=seq_read_mb,
                     workvol=os.getcwd(),
                     kill_slower=True,
                     timeout=timeout)
