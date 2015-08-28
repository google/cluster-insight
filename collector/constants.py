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

"""Common constants for the Cluster-Insight data collector."""

# The Cluster-Insight data collector listens on this port for requests.
DATA_COLLECTOR_PORT = 5555

# The cache will keep data for at most this many seconds.
MAX_CACHED_DATA_AGE_SECONDS = 10

# Delete data that was last updated more than this many seconds ago from the
# cache.
CACHE_DATA_CLEANUP_AGE_SECONDS = 3600  # one hour

# Maximum number of active context.compute_graph() calls.
MAX_CONCURRENT_COMPUTE_GRAPH = 2

# Maximum number of elapsed time records in the elapsed time queue.
MAX_ELAPSED_QUEUE_SIZE = 1000
