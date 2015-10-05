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

"""CollectorError is raised by run-time errors in the data collector.

CollectorError is a user-defined exception for handling run-time
errors in the data collector.

Typical usage:
try:
  result_list = requests.get(url).json()
except Exception:
  msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
  current_app.logger.exception(msg)
  raise CollectorError(s)
"""

import types


class CollectorError(Exception):

  def __init__(self, message):
    Exception.__init__(self)
    assert isinstance(message, types.StringTypes)
    self._message = message

  def __str__(self):
    return repr(self._message)
