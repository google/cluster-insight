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

"""A cache of recent values of objects.

SimpleCache stores a dictionary from object labels to object values and their
most recent update time.

The lookup() method returns the most recent value associated with the given
label if the value is defined and it was updated less than _max_data_age_seconds
ago. If no such value exists or it is too old, lookup() will fail.

The update() method stores a value associated with the given label in the cache.
The value's update time is the current wallclock time.

Old data is removed from the cache as a side effect of calling the update()
operation. There is no cleanup as the result of the lookup() to avoid slowing
down cache hits. In this way ephemeral data does not stay in the cache
indefinitely as long as new data is inserted into the cache.

This class is thread-safe.

Usage:
  cache = SimpleCache(MAX_DATA_AGE_SECONDS)

  def get_value(label):
    value, timestamp_seconds = cache.lookup(label)
    if timestamp_seconds is not None:
      # handle cache hit
    else:
      # handle cache miss; usually fetch data from source
      value = fetch_data()
      cache.update(label, value, timestamp_now)

    return value
"""
import collections
import copy
import time
import threading
import types

class SimpleCache:
  """
  Attributes:
    _lock: a lock protecting access to the data.
    _max_data_age_seconds: data older than this many seconds will not be
                           returned.
    _label_to_tuple: a lookup table from label to a named tuple
      (timestamp, value), where 'timestamp' is the time the data was last
      updated. 'value' is a deep copy of the data.
    _namedtuple: a named tuple containing a 'timestamp' and 'value' fields.
  """

  def __init__(self, max_data_age_seconds):
    assert (isinstance(max_data_age_seconds, types.IntType) or
            isinstance(max_data_age_seconds, types.LongType) or
            isinstance(max_data_age_seconds, types.FloatType))
    assert max_data_age_seconds >= 0
    self._lock = threading.Lock()
    self._max_data_age_seconds = max_data_age_seconds
    self._label_to_tuple = {}
    self._namedtuple = collections.namedtuple('Tuple', ['timestamp', 'value'])

  def _cleanup(self):
    """Removes all data older than _max_data_age_seconds from the cache.

    This routine prevents the accumulation of stale ephemeral data.
    Such data usually has a unique label.

    This method must be called when '_lock' is held.
    """
    threshold = time.time() - self._max_data_age_seconds
    # Scan the cache using a list of keys instead of iterating on the cache
    # directly because we are deleting elements from the cache while iterating.
    for key in self._label_to_tuple.keys():
      if self._label_to_tuple[key].timestamp <= threshold:
        # delete current entry from the cache
        del self._label_to_tuple[key]

  def lookup(self, label):
    """Lookup the data with the given label in the cache.

    The label must be a string. It can be empty.

    Returns:
    When the given label has recent data in the cache (less than
    self._max_data_age_seconds seconds old), returns a tuple
    (value, timestamp_of_cached_data).
    When the given label was not found in the cahce or its data is too old,
    returns the tuple (None, None).
    """
    assert isinstance(label, types.StringTypes)

    self._lock.acquire()
    if (label in self._label_to_tuple) and (time.time() <
        (self._label_to_tuple[label].timestamp + self._max_data_age_seconds)):
      # a cache hit
      assert self._label_to_tuple[label].value is not None
      value, timestamp = (copy.deepcopy(self._label_to_tuple[label].value),
                          self._label_to_tuple[label].timestamp)

    else:
      value, timestamp = (None, None)

    self._lock.release()
    return (value, timestamp)

  def update(self, label, value, timestamp_seconds=None):
    """Stores the given value and timestamp for the given label.

    'label' must be a string. It can be empty. 'value' must not be None.
    If 'timestamp_seconds' is None, then the timestamp associated with 'value'
    is the current wallclock time. If 'timestamp_seconds' is not None, then
    this timestamp is stored with 'value'.
    The cache keeps a deep copy of 'value', so the caller may change 'value'
    afterwards.
    """
    assert isinstance(label, types.StringTypes)
    assert value is not None
    assert (timestamp_seconds is None) or isinstance(timestamp_seconds,
                                                     types.FloatType)

    self._lock.acquire()
    # Cleanup only when inserting new values into the cache in order to
    # avoid penalizing the cache hit operation.
    self._cleanup()
    self._label_to_tuple[label] = self._namedtuple(
        timestamp=time.time() if timestamp_seconds is None
                  else timestamp_seconds,
        value=copy.deepcopy(value))
    self._lock.release()
