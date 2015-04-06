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

"""Keeps global system state to be used by concurrent threads.
"""
import threading
import types

# local imports
import constants
import simple_cache


class GlobalState(object):
  """Keeps global state to be used by concurrent threads.

  Concurrent threads cannot use the Flask 'app' and 'current_app' variables
  for accessing global state because these variables are operational only
  inside the threads managed directly by Flask.

  You should initialize the GlobalState object before any access it.
  Since GlobalState is a read-only object after initialization, it is
  thread safe.

  The only locking provided by GlobalState is for concurrent logging
  operations. It is neede because GlobalState typically keeps a reference
  to Flask's logger. I have no idea whether the Flask logger supports
  concurrent operations.

  Direct logging via the 'logging' package does not seem to work under
  Flask.
  """

  def __init__(self):
    """Initialize internal state."""
    self._testing = False
    self._docker_port = None

    # '_logger_lock' protects concurrent logging operations.
    self._logger_lock = threading.Lock()
    self._logger = None

    # pointers to various caches.
    self._nodes_cache = None
    self._pods_cache = None
    self._services_cache = None
    self._rcontrollers_cache = None
    self._containers_cache = None
    self._images_cache = None
    self._processes_cache = None

  def init_caches(self):
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
    self._containers_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)
    self._images_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)
    self._processes_cache = simple_cache.SimpleCache(
        constants.MAX_CACHED_DATA_AGE_SECONDS,
        constants.CACHE_DATA_CLEANUP_AGE_SECONDS)

  def get_nodes_cache(self):
    return self._nodes_cache

  def get_pods_cache(self):
    return self._pods_cache

  def get_services_cache(self):
    return self._services_cache

  def get_rcontrollers_cache(self):
    return self._rcontrollers_cache

  def get_containers_cache(self):
    return self._containers_cache

  def get_images_cache(self):
    return self._images_cache

  def get_processes_cache(self):
    return self._processes_cache

  def set_testing(self, testing):
    self._testing = testing

  def get_testing(self):
    return self._testing

  def set_docker_port(self, port):
    assert isinstance(port, types.IntType) and port > 0
    self._docker_port = port

  def get_docker_port(self):
    return self._docker_port

  def set_logger(self, logger):
    with self._logger_lock:
      self._logger = logger

  def logger_debug(self, *args):
    with self._logger_lock:
      self._logger.debug(*args)

  def logger_info(self, *args):
    with self._logger_lock:
      self._logger.info(*args)

  def logger_warning(self, *args):
    with self._logger_lock:
      self._logger.warning(*args)

  def logger_error(self, *args):
    with self._logger_lock:
      self._logger.error(*args)

  def logger_fatal(self, *args):
    with self._logger_lock:
      self._logger.fatal(*args)

  def logger_exception(self, *args):
    with self._logger_lock:
      self._logger.exception(*args)
