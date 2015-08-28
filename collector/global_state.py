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

"""Keeps global system state to be used by concurrent threads."""

import collections
import Queue  # "Queue" was renamed "queue" in Python 3.
import thread
import threading

# local imports
import constants
import simple_cache
import utilities


ElapsedRecord = collections.namedtuple(
    'ElapsedRecord',
    ['start_time', 'what', 'thread_identifier', 'elapsed_seconds'])


class GlobalState(object):
  """Keeps global state to be used by concurrent threads.

  Concurrent threads cannot use the Flask 'app' and 'current_app' variables
  for accessing global state because these variables are operational only
  inside the threads managed directly by Flask.

  You should initialize the GlobalState object before any access it.
  Since GlobalState is a read-only object after initialization, it is
  thread safe.
  """

  def __init__(self):
    """Initialize internal state."""
    # pointers to various caches.
    self._nodes_cache = None
    self._pods_cache = None
    self._services_cache = None
    self._rcontrollers_cache = None

    # pointers to synchronization constructs.
    self._bounded_semaphore = None

    # Elapsed time queue containing ElapsedRecord items.
    self._elapsed_queue = Queue.Queue()  # a FIFO queue

    # pointers to shared dictionaries.
    self._relations_lock = threading.Lock()
    self._relations_to_timestamps = {}

  def init_caches_and_synchronization(self):
    """Initializes all caches."""
    self._nodes_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)
    self._pods_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)
    self._services_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)
    self._rcontrollers_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)

    self._bounded_semaphore = threading.BoundedSemaphore(
        constants.MAX_CONCURRENT_COMPUTE_GRAPH)

  def get_nodes_cache(self):
    return self._nodes_cache

  def get_pods_cache(self):
    return self._pods_cache

  def get_services_cache(self):
    return self._services_cache

  def get_rcontrollers_cache(self):
    return self._rcontrollers_cache

  def get_bounded_semaphore(self):
    return self._bounded_semaphore

  def get_relations_to_timestamps(self):
    with self._relations_lock:
      return self._relations_to_timestamps

  def set_relations_to_timestamps(self, v):
    assert isinstance(v, dict)
    with self._relations_lock:
      self._relations_to_timestamps = v

  def add_elapsed(self, start_time, url_or_fname, elapsed_seconds):
    """Append an ElapsedRecord of an access operation to the elapsed time queue.

    Keep at most constants.MAX_ELAPSED_QUEUE_SIZE elements in the elapsed
    time queue.

    Args:
      start_time: the timestamp at the start of the operation.
      url_or_fname: the URL or file name of the operation.
      elapsed_seconds: the elapsed time of the operation.
    """
    assert isinstance(start_time, float)
    assert utilities.valid_string(url_or_fname)
    assert isinstance(elapsed_seconds, float)

    # If the queue is too large, remove some items until it contains less
    # than constants.MAX_ELAPSED_QUEUE_SIZE elements.
    while self._elapsed_queue.qsize() >= constants.MAX_ELAPSED_QUEUE_SIZE:
      try:
        self._elapsed_queue.get(block=False)
      except Queue.Empty:
        # self._elapsed_queue.get() may raise the EMPTY exception if the
        # queue becomes empty (for example, due to concurrent access).
        break

    self._elapsed_queue.put(
        ElapsedRecord(start_time=start_time, what=url_or_fname,
                      thread_identifier=thread.get_ident(),
                      elapsed_seconds=elapsed_seconds))

  def get_elapsed(self):
    """Returns a list of all queued elapsed time records and clears the queue.

    Returns:
    An empty list if the elapsed time queue is empty.
    Otherwise, a list of ElapsedRecord in the order that they appear
    in the queue.
    """
    result = []
    while not self._elapsed_queue.empty():
      try:
        result.append(self._elapsed_queue.get(block=False))
      except Queue.Empty:
        # self._elapsed_queue.get() may raise the Empty exception if the
        # queue becomes empty (for example, due to concurrent access).
        break

    return result
