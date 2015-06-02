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


"""Chooses which top level module to run, based on the mode passed in
"""

import argparse
import os

import collector
import constants
import docker_proxy

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Cluster-Insight data collector')
  parser.add_argument('-d', '--debug', action='store_true',
                      help='enable debug mode')
  parser.add_argument('-p', '--port', action='store', type=int,
                      default=constants.DATA_COLLECTOR_PORT,
                      help=('data collector port number [default=%d]' %
                            constants.DATA_COLLECTOR_PORT))
  parser.add_argument('--docker_port', action='store', type=int,
                      default=constants.DOCKER_PORT,
                      help=('Docker port number [default=%d]' %
                            constants.DOCKER_PORT))
  parser.add_argument('-w', '--workers', action='store', type=int,
                      default=0,
                      help=('number of concurrent workers. A zero or a '
                            'negative value denotes an automatic calculation '
                            'of this number. [default=0]'))

  mode = os.environ.get('CLUSTER_INSIGHT_MODE')

  if mode == constants.MODE_MASTER:
    collector.main()
  elif mode == constants.MODE_MINION:
    docker_proxy.main()
  else:
    raise Exception('Mode is %s. It can only be one of %s, and %s' 
		    % (mode, constants.MODE_MINION, constants.MODE_MASTER))

