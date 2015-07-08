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

"""Common constants for the Cluster-Insight data collector.
"""

# The Cluster-Insight data collector listens on this port for requests.
DATA_COLLECTOR_PORT = 5555

# The Docker controller listens on this port in the master and minion nodes.
DOCKER_PORT = 4243

# The cache will keep data for at most this many seconds.
MAX_CACHED_DATA_AGE_SECONDS = 10

# Delete data that was last updated more than this many seconds ago from the
# cache.
CACHE_DATA_CLEANUP_AGE_SECONDS = 3600  # one hour

# Low and high bounds of the number of concurrent worker threads that
# fetch information from the backend.
# The number of workers threads may either be set by a flag or set to be
# the number of nodes in the cluster.
MIN_CONCURRENT_WORKERS = 2
MAX_CONCURRENT_WORKERS = 10

# Maximum number of active context.compute_graph() calls.
# These calls are executed by concurrent worker threads, so they may generate
# heavy load on the backend.
MAX_CONCURRENT_COMPUTE_GRAPH = 2

MODE_MINION = 'minion'
MODE_MASTER = 'master'

# Maximum number of elapsed time records in the elapsed time queue.
MAX_ELAPSED_QUEUE_SIZE = 1000
