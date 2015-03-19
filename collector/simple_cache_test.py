#!/usr/bin/env python
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

"""Tests for collector/simple_cache.py """

# global imports

import datetime
import time
import types
import unittest

# local imports
import simple_cache


MAX_DATA_AGE_SECONDS = 10
DATA_CLEANUP_AGE_SECONDS = 100
KEY = 'abc123'
BLOB_ID_EMPTY = { 'id': '' }
BLOB_ID_KEY = { 'id': KEY }

class TestSimpleCache(unittest.TestCase):

  def setUp(self):
    self._cache = simple_cache.SimpleCache(
        MAX_DATA_AGE_SECONDS, DATA_CLEANUP_AGE_SECONDS)

  def test_basic(self):
    now = time.time()
    # Verify that the cache is empty
    self.assertEqual(0, self._cache.size())
    value, timestamp = self._cache.lookup('', now)
    self.assertTrue((value is None) and (timestamp is None))
    value, timestamp = self._cache.lookup(KEY, now)
    self.assertTrue((value is None) and (timestamp is None))

    # Insert two elements into the cache and fetch them.
    self._cache.update('', BLOB_ID_EMPTY, now)
    self._cache.update(KEY, BLOB_ID_KEY, now)
    self.assertEqual(2, self._cache.size())
    value, timestamp = self._cache.lookup('', now + 1)
    self.assertEqual(str(value), str(BLOB_ID_EMPTY))
    self.assertEqual(now, timestamp)
    value, timestamp = self._cache.lookup(KEY, now + 1)
    self.assertEqual(str(value), str(BLOB_ID_KEY))
    self.assertEqual(now, timestamp)

    # Wait a long time and fetch the elements. It should fail.
    value, timestamp = self._cache.lookup('', now + MAX_DATA_AGE_SECONDS + 1)
    self.assertTrue((value is None) and (timestamp is None))
    value, timestamp = self._cache.lookup(KEY, now + MAX_DATA_AGE_SECONDS + 1)
    self.assertTrue((value is None) and (timestamp is None))

    # Update one element. Now you can fetch this element and not the other.
    self._cache.update('', BLOB_ID_EMPTY, now + MAX_DATA_AGE_SECONDS + 2)
    self.assertEqual(2, self._cache.size())
    value, timestamp = self._cache.lookup('', now + MAX_DATA_AGE_SECONDS + 3)
    self.assertEqual(str(value), str(BLOB_ID_EMPTY))
    self.assertEqual(now + MAX_DATA_AGE_SECONDS + 2, timestamp)
    value, timestamp = self._cache.lookup(KEY, now + MAX_DATA_AGE_SECONDS + 3)
    self.assertTrue((value is None) and (timestamp is None))


  def make_blob(self, id):
    """Makes a blob containing the ID ("id%d" % i).
    """
    assert isinstance(id, types.IntType)
    return { 'id': 'id%d' % id }


  def test_cleanup(self):
    """Verify that objects older than DATA_CLEANUP_AGE_SECONDS are cleaned.
    """
    start_time = time.time()
    now = start_time
    for i in range(2 * DATA_CLEANUP_AGE_SECONDS):
      self._cache.update('id%d' % i, self.make_blob(i), now)
      # Since the objects are added one per second, the cache can never hold
      # more than DATA_CLEANUP_AGE_SECONDS objects. Once the oldest object
      # reaches this threshold, it is removed as part of the update() operation.
      self.assertEqual(min(i + 1, DATA_CLEANUP_AGE_SECONDS),
                       self._cache.size())
      now += 1

    # You can access only the MAX_DATA_AGE_SECONDS most recent items in the
    # cache.
    for i in range(2 * DATA_CLEANUP_AGE_SECONDS):
      value, timestamp = self._cache.lookup('id%d' % i, now)
      if i > (2 * DATA_CLEANUP_AGE_SECONDS) - MAX_DATA_AGE_SECONDS:
        self.assertEqual(str(self.make_blob(i)), str(value))
        self.assertEqual(start_time + i, timestamp)
      else:
        self.assertTrue((value is None) and (timestamp is None))


  def make_fancy_blob(self, id, timestamp_seconds, value):
    """Makes a blob containing "id", "timestamp" and "value" attributes.
    """
    assert isinstance(id, types.StringTypes)
    assert isinstance(timestamp_seconds, types.FloatType)
    return { 'id': id,
             'timestamp':
               datetime.datetime.fromtimestamp(timestamp_seconds).isoformat(),
             'value': value }


  def test_update(self):
    """Verify that updating an object with equivalent/non-equivalent objects.

    A equivalent object is identical to the first object after removal of the
    'timestamp' attribute.
    """
    start_time = time.time()
    now = start_time
    first_blob_a = None

    for i in range(2 * MAX_DATA_AGE_SECONDS):
      blob_a = self.make_fancy_blob('a', now, 0)
      if first_blob_a is None:
        first_blob_a = blob_a
      ret_value = self._cache.update('a', blob_a, now)
      # The return value should be the first blob_a value, because all
      # stored values should be identical after removal of the 'timestamp'
      # attribute.
      self.assertEqual(str(first_blob_a), str(ret_value))

      blob_b = self.make_fancy_blob('b', now, i)
      ret_value = self._cache.update('b', blob_b, now)
      # The return value should be the latest blob_b value, because all
      # stored values are not identical after removal of the 'timestamp'
      # attribute.
      self.assertEqual(str(blob_b), str(ret_value))

      # The lookup value of 'a' is the first 'blob_a', because all
      # versions of this blob are identical after removal of the 'timestamp'
      # value.
      value, timestamp = self._cache.lookup('a', now + 0.5)
      self.assertEqual(str(first_blob_a), str(value))
      self.assertEqual(now, timestamp)

      # The lookup value of 'b' is the latest 'blob_b', because all
      # versions of this blob are different after removal of the 'timestamp'
      # value.
      value, timestamp = self._cache.lookup('b', now + 0.5)
      self.assertEqual(str(blob_b), str(value))
      self.assertEqual(now, timestamp)

      now += 1


if __name__ == '__main__':
    unittest.main()
