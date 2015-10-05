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

"""Tests for collector/simple_cache.py."""

# global imports

import json
import sys
import time
import types
import unittest

# local imports
import simple_cache
import utilities


# Global constants
MAX_DATA_AGE_SECONDS = 10
DATA_CLEANUP_AGE_SECONDS = 100
KEY = 'abc123'
BLOB_ID_EMPTY = {'id': ''}
BLOB_ID_KEY = {'id': KEY}


class TestSimpleCache(unittest.TestCase):

  def setUp(self):
    self._cache = simple_cache.SimpleCache(
        MAX_DATA_AGE_SECONDS, DATA_CLEANUP_AGE_SECONDS)

    # The contents of the _forever_cache never expires.
    self._forever_cache = simple_cache.SimpleCache(sys.maxint, sys.maxint)

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
    self.assertEqual(str(BLOB_ID_EMPTY), str(value))
    self.assertEqual(now, timestamp)
    value, timestamp = self._cache.lookup(KEY, now + 1)
    self.assertEqual(str(BLOB_ID_KEY), str(value))
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
    self.assertEqual(str(BLOB_ID_EMPTY), str(value))
    # The creation timestamp of BLOB_ID_EMPTY did not change, because we
    # stored exactly the same value there.
    self.assertEqual(now, timestamp)
    value, timestamp = self._cache.lookup(KEY, now + MAX_DATA_AGE_SECONDS + 3)
    self.assertTrue((value is None) and (timestamp is None))

    # Update one element again with a different value. The creation time
    # should change as well.
    self._cache.update('', BLOB_ID_KEY, now + MAX_DATA_AGE_SECONDS + 4)
    self.assertEqual(2, self._cache.size())
    value, timestamp = self._cache.lookup('', now + MAX_DATA_AGE_SECONDS + 5)
    self.assertEqual(str(BLOB_ID_KEY), str(value))
    self.assertEqual(now + MAX_DATA_AGE_SECONDS + 4, timestamp)
    value, timestamp = self._cache.lookup(KEY, now + MAX_DATA_AGE_SECONDS + 5)
    self.assertTrue((value is None) and (timestamp is None))

  def make_blob(self, i):
    """Makes a blob containing the ID ("id%d" % i).

    Args:
      i: the numeric part of the identifier.

    Returns:
    The string 'id' followed by the string representation of the number 'i'.
    """
    assert isinstance(i, int)
    return {'id': 'id%d' % i}

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
      if i > ((2 * DATA_CLEANUP_AGE_SECONDS) - MAX_DATA_AGE_SECONDS):
        self.assertEqual(str(self.make_blob(i)), str(value))
        self.assertEqual(start_time + i, timestamp)
      else:
        self.assertTrue((value is None) and (timestamp is None))

  def make_fancy_blob(self, name, timestamp_seconds, value):
    """Makes a blob containing "name", "timestamp" and "value" attributes.

    Args:
      name: the name of this object (the value of the 'id' attribute).
      timestamp_seconds: a timestamp in seconds.
      value: a value of any type.

    Returns:
    A dictionary containing 'id', 'timestamp', and 'value' key/value pairs.
    """
    assert isinstance(name, types.StringTypes)
    assert isinstance(timestamp_seconds, float)
    return {'id': name,
            'timestamp': utilities.seconds_to_timestamp(timestamp_seconds),
            'value': value}

  def test_update(self):
    """Verify that updating an object with equivalent/non-equivalent objects.

    A equivalent object is identical to the first object after removal of the
    'timestamp' attribute.
    """
    start_time = time.time()
    now = start_time
    expected_blob_a = None
    expected_blob_a_timestamp = None

    for i in range(2 * DATA_CLEANUP_AGE_SECONDS):
      blob_a = self.make_fancy_blob('a', now, 0)
      if (i % DATA_CLEANUP_AGE_SECONDS) == 0:
        # store new data every DATA_CLEANUP_AGE_SECONDS seconds.
        # intermediate updates are ignored because the 'a' blob is the same.
        expected_blob_a = blob_a
        expected_blob_a_timestamp = now

      ret_value = self._cache.update('a', blob_a, now)
      # The return value should be the 'expected_blob_a', because all
      # stored values should be identical after removal of the 'timestamp'
      # attribute. A new value is stored after data cleanup, which occurs
      # in the 'DATA_CLEANUP_AGE_SECONDS' iteration.
      self.assertEqual(str(expected_blob_a), str(ret_value))

      blob_b = self.make_fancy_blob('b', now, i)
      ret_value = self._cache.update('b', blob_b, now)
      # The return value should be the latest blob_b value, because all
      # stored values are not identical after removal of the 'timestamp'
      # attribute.
      self.assertEqual(str(blob_b), str(ret_value))

      # The lookup value of 'a' is 'expected_blob_a', because all
      # versions of this blob are identical after removal of the 'timestamp'
      # value.
      value, timestamp = self._cache.lookup('a', now + 0.5)
      self.assertEqual(str(expected_blob_a), str(value))
      self.assertEqual(expected_blob_a_timestamp, timestamp)

      # The lookup value of 'b' is the latest 'blob_b', because all
      # versions of this blob are different after removal of the 'timestamp'
      # value.
      value, timestamp = self._cache.lookup('b', now + 0.5)
      self.assertEqual(str(blob_b), str(value))
      self.assertEqual(now, timestamp)

      now += 1.001

  def test_forever(self):
    """Verify that data entered into the 'forever_cache' remains there forever.
    """
    now = time.time()
    # Verify that the cache is empty
    self.assertEqual(0, self._forever_cache.size())
    value, timestamp = self._forever_cache.lookup('', now)
    self.assertTrue((value is None) and (timestamp is None))
    value, timestamp = self._forever_cache.lookup(KEY, now)
    self.assertTrue((value is None) and (timestamp is None))

    # Insert an element into the cache. It should stay there forever.
    self._forever_cache.update(KEY, BLOB_ID_KEY, now)
    update_time = now
    self.assertEqual(1, self._forever_cache.size())

    for _ in range(2 * MAX_DATA_AGE_SECONDS):
      now += 1
      value, timestamp = self._forever_cache.lookup(KEY, now)
      self.assertEqual(str(value), str(BLOB_ID_KEY))
      self.assertEqual(update_time, timestamp)

  def make_same_node(self, seconds):
    """Makes the same wrapped node object with the given timestamp.

    Args:
      seconds: timestamp in seconds since the epoch.

    Returns:
    A wrapped Node object with the given 'timestamp' and 'lastHeartbeatTime'.
    """
    assert isinstance(seconds, (int, long, float))
    return utilities.wrap_object(
        {'uid': KEY,
         'lastHeartbeatTime': utilities.seconds_to_timestamp(seconds)},
        'Node', KEY, seconds)

  def test_continuous_access_same_object(self):
    """Verify continuous access of the same object."""
    start_timestamp = time.time()
    last_update_seconds = None
    last_update_value = None
    for i in range(2 * DATA_CLEANUP_AGE_SECONDS):
      now = start_timestamp + (i * 1.001)
      value, ts = self._cache.lookup(KEY, now)
      if ((i % MAX_DATA_AGE_SECONDS) == 0 or
          (i % DATA_CLEANUP_AGE_SECONDS) == 0):
        # expect a cache miss
        self.assertTrue(value is None and ts is None)
        new_value = self.make_same_node(now)
        if (i % DATA_CLEANUP_AGE_SECONDS) == 0:
          # only the value stored every DATA_CLEANUP_AGE_SECONDS seconds
          # is kept in the cache. Other values are essentially the same
          # as the current contents of the cache, so they are not kept.
          last_update_value = new_value
          last_update_seconds = now
        ret_value = self._cache.update(KEY, new_value, now)
        self.assertEqual(json.dumps(last_update_value, sort_keys=True),
                         json.dumps(ret_value, sort_keys=True))
      else:
        # expect a cache hit
        self.assertFalse(last_update_seconds is None)
        self.assertFalse(value is None)
        self.assertEqual(json.dumps(last_update_value, sort_keys=True),
                         json.dumps(value, sort_keys=True))
        self.assertEqual(last_update_seconds, ts)

  def make_different_node(self, seconds):
    """Makes the a different wrapped node object with the given timestamp.

    Args:
      seconds: timestamp in seconds since the epoch.

    Returns:
    A wrapped Node object with the given 'timestamp' and 'creationTimestamp'.
    """
    assert isinstance(seconds, (int, long, float))
    return utilities.wrap_object(
        {'uid': KEY,
         'creationTimestamp': utilities.seconds_to_timestamp(seconds)},
        'Node', KEY, seconds)


if __name__ == '__main__':
  unittest.main()
