#!/usr/bin/python
#
# Copyright 2015 The Cluster-Insight Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for collector/global_state.py."""

# global imports
import thread
import time
import unittest

# local imports
import global_state


class TestGlobalState(unittest.TestCase):

  def setUp(self):
    self._state = global_state.GlobalState()
    self._state.init_caches_and_synchronization()

  def test_elapsed(self):
    result = self._state.get_elapsed()
    self.assertTrue(isinstance(result, list))
    self.assertEqual([], result)

    now = time.time()
    self._state.add_elapsed(now, 'abc', 13.4)

    # expect to get a list of one elapsed time records.
    result = self._state.get_elapsed()
    self.assertTrue(isinstance(result, list))
    self.assertEqual(1, len(result))
    self.assertEqual(now, result[0].start_time)
    self.assertEqual('abc', result[0].what)
    self.assertEqual(13.4, result[0].elapsed_seconds)
    self.assertEqual(thread.get_ident(), result[0].thread_identifier)

    # Calling get_elapsed() should clear the list of elapsed times.
    result = self._state.get_elapsed()
    self.assertTrue(isinstance(result, list))
    self.assertEqual([], result)


if __name__ == '__main__':
  unittest.main()
