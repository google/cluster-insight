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


"""Select the module to run specified by CLUSTER_INSIGHT_MODE env. variable."""

import os

import collector
import collector_error
import constants
import docker_proxy

if __name__ == '__main__':
  mode = os.environ.get('CLUSTER_INSIGHT_MODE')

  if mode == constants.MODE_MASTER:
    collector.main()
  elif mode == constants.MODE_MINION:
    docker_proxy.main()
  else:
    raise collector_error.CollectorError(
        'CLUSTER_INSIGHT_MODE environment variable is %s. Valid values are %s '
        'or %s' % (mode, constants.MODE_MINION, constants.MODE_MASTER))
