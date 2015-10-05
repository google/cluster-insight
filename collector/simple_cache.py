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

"""A cache of recent values of objects.

SimpleCache stores a dictionary from object labels to the tuple
(update_time, create_time, value)

The lookup() method returns the value associated with the given
label and its creation time if the value is defined and it was most recently
updated less than _max_data_age_seconds ago. If no such value exists or it is
too old, lookup() will fail.
Note that lookup() success depends on the last update time and not on the
data's creation time.

The update() method stores a value associated with the given label in the cache.
The value's most recent update time is passed as a parameter. If the given label
existed before and the associated value without its 'timestamp' attribute did
not change, then the data stored in the cache will not change. Only the most
recent update time will be changed in the cache. Otherwise the value, the most
recent update time and the creation time will be changed.

In other words, the creation time is updated whenever the value is also changed
in the cache. Calling update() always changes the update time, but it may
not change the value or the creation time.

Old data is removed from the cache as a side effect of calling the update()
operation. Old data is removed when it was created more than
DATA_CLEANUP_AGE_SECONDS seconds ago.
There is no cleanup as the result of the lookup() to avoid slowing
down cache hits. In this way ephemeral data does not stay in the cache
indefinitely as long as new data is inserted into the cache.

This class is thread-safe.

Usage:
  cache = SimpleCache(MAX_DATA_AGE_SECONDS, DATA_CLEANUP_AGE_SECONDS)

  def get_value(label):
    value, timestamp_seconds = cache.lookup(label)
    if timestamp_seconds is not None:
      # handle cache hit
    else:
      # handle cache miss; usually fetch data from source
      value = fetch_data()
      timestamp_now = time.time()
      cache.update(label, value, timestamp_now)

    return value
"""

import collections
import copy
import threading
import time
import types

# local import
import utilities


class SimpleCache(object):
  """A cache of named objects with specified freshness and cleanup times.

  Attributes:
    _lock: a lock protecting access to the data.
    _max_data_age_seconds: data older than this many seconds will not be
      returned.
    _data_cleanup_age_seconds: data older than this many seconds will be cleaned
      from the cache.
    _label_to_tuple: a lookup table from label to a named tuple
      (update_timestamp, value), where 'update_timestamp' is
      the time the data was last updated. 'value' is a deep copy of the data.
    _namedtuple: a named tuple containing a 'update_timestamp' and 'value'
      fields.
  """

  def __init__(self, max_data_age_seconds, data_cleanup_age_seconds):
    assert (isinstance(max_data_age_seconds, int) or
            isinstance(max_data_age_seconds, long) or
            isinstance(max_data_age_seconds, float))
    assert (isinstance(data_cleanup_age_seconds, int) or
            isinstance(data_cleanup_age_seconds, long) or
            isinstance(data_cleanup_age_seconds, float))
    assert max_data_age_seconds >= 0
    assert data_cleanup_age_seconds >= 0
    assert data_cleanup_age_seconds >= max_data_age_seconds
    self._lock = threading.Lock()
    self._max_data_age_seconds = max_data_age_seconds
    self._data_cleanup_age_seconds = data_cleanup_age_seconds
    self._label_to_tuple = {}
    self._namedtuple = collections.namedtuple(
        'Tuple', ['create_timestamp', 'update_timestamp', 'value'])

  def _cleanup(self, now):
    """Removes all data older than _data_cleanup_age_seconds from the cache.

    This routine prevents the accumulation of stale ephemeral data.
    Such data usually has a unique label.

    This method must be called when '_lock' is held.

    Args:
      now: current time in seconds since the Epoch.
    """
    assert isinstance(now, float)
    threshold = now - self._data_cleanup_age_seconds
    # Scan the cache using a list of keys instead of iterating on the cache
    # directly because we are deleting elements from the cache while iterating.
    for key in self._label_to_tuple.keys():
      if self._label_to_tuple[key].create_timestamp <= threshold:
        # delete current entry from the cache
        del self._label_to_tuple[key]

  def lookup(self, label, now=None):
    """Lookup the data with the given label in the cache.

    Args:
      label: the label of the data. must be a string. may be empty.
      now: current time in seconds. If 'now' is None, the cached entry is
        compared with the current wallclock time. Otherwise the cached entry
        is compared with the value of 'now'.

    Returns:
    When the given label has recent data in the cache ('update_timestamp'
    less than self._max_data_age_seconds seconds old), returns a tuple
    (deep copy of cached value, create_timestamp_of_cached_data).
    When the given label was not found in the cache or its data is too old,
    returns the tuple (None, None).
    """
    assert isinstance(label, types.StringTypes)
    assert (now is None) or isinstance(now, float)

    self._lock.acquire()
    ts_seconds = time.time() if now is None else now
    if ((label in self._label_to_tuple) and
        (ts_seconds < (self._label_to_tuple[label].update_timestamp +
                       self._max_data_age_seconds))):
      # a cache hit
      assert self._label_to_tuple[label].value is not None
      value, timestamp = (copy.deepcopy(self._label_to_tuple[label].value),
                          self._label_to_tuple[label].create_timestamp)

    else:
      value, timestamp = (None, None)

    self._lock.release()
    return (value, timestamp)

  def update(self, label, value, update_timestamp=None):
    """Stores the given value and timestamp for the given label.

    Args:
      label: the value's label. It must be a string. It can be empty.
      value: the value stored in the cache. Must not be None.
      update_timestamp: the timestamp in seconds of the value.
        If 'update_timestamp' is None, then the update timestamp associated
        with 'value' is the current wallclock time. If 'update_timestamp'
        is not None, then this timestamp is stored with 'value'.

    If 'value' is the same as the current value associated with the label
    after removal of 'timestamp' attributes, then the cached value is not
    changed.
    The cache keeps a deep copy of 'value', so the caller may change 'value'
    afterwards.

    Returns:
    The values that was stored in the cache. If the value stored in the cache
    was not changed, then the returned value is the deep copy of the old cached
    value.
    Otherwise the returned value is 'value'.

    In any case, the caller may modify 'value' or the returned value after
    this method returns.
    """
    assert isinstance(label, types.StringTypes)
    assert value is not None
    assert ((update_timestamp is None) or
            isinstance(update_timestamp, float))

    self._lock.acquire()
    # Cleanup only when inserting new values into the cache in order to
    # avoid penalizing the cache hit operation.
    ts = time.time() if update_timestamp is None else update_timestamp
    self._cleanup(ts)
    if ((label in self._label_to_tuple) and
        (utilities.timeless_json_hash(value) ==
         utilities.timeless_json_hash(self._label_to_tuple[label].value))):
      # cannot update just one field in a named tuple.
      create_ts = self._label_to_tuple[label].create_timestamp
      update_value = self._label_to_tuple[label].value
      ret_value = copy.deepcopy(update_value)
    else:
      create_ts = ts
      update_value = copy.deepcopy(value)
      ret_value = value

    # cannot update just one field in a named tuple.
    self._label_to_tuple[label] = self._namedtuple(
        update_timestamp=ts, create_timestamp=create_ts, value=update_value)
    self._lock.release()
    return ret_value

  def size(self):
    """Returns the number of entries in the cache.

    Note that you may lookup only recent entries in the cache
    (see the explanation of the lookup() function), even when the
    cache contains additional older entries.

    Returns:
    Number of entries in the cache.
    """
    self._lock.acquire()
    n = len(self._label_to_tuple)
    self._lock.release()
    return n


