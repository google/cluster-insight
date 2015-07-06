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

"""Tests for collector/docker_proxy.py."""

# global imports
import json
import logging
import types
import unittest

import flask
import requests

# local imports
import docker_proxy
import simple_cache


# A large number of seconds, which is much larger than the expected run time
# of this test.
MAX_SECONDS = 1000


class TestDockerProxy(unittest.TestCase):
  """Test harness."""

  def setUp(self):
    self.app = docker_proxy.app.test_client()
    docker_proxy.app.logger.setLevel(logging.DEBUG)
    docker_proxy.app.proxy_containers_cache = simple_cache.SimpleCache(
        MAX_SECONDS, MAX_SECONDS)
    docker_proxy.app.proxy_is_testing_mode = True

  def compare_to_golden(self, resp, fname):
    """Compares the returned value to the golden (expected) value.

    The golden value is read from the file
    'testdata/localhost.<fname>'.

    Args:
      resp: the response from the server.
      fname: the middle part of the file name containing the golden
        (expected) output from the server.
    Raises:
      AssertError if the sanitized golden data differs from the sanitized
      return value.
    """
    assert isinstance(resp, flask.Response)
    assert isinstance(fname, types.StringTypes)

    # Verify response headers and status code.
    self.assertEqual('application/json', resp.headers.get('Content-Type'))
    self.assertEqual(requests.codes.ok, resp.status_code)

    # The data is normalized by converting it to JSON and then printing it
    # with sorted attribute names.
    ret_value = json.dumps(json.loads(resp.get_data()), sort_keys=True)

    # Read the golden data (expected value).
    golden_fname = 'testdata/localhost.' + fname
    f = open(golden_fname, 'r')
    golden_data = json.dumps(json.loads(f.read()), sort_keys=True)
    f.close()

    # Find the index of the first discrepancy between 'golden_data'
    # and 'ret_value'. If they are equal, the index will point at
    # the position after the last character in both strings.
    # DO NOT replace this code with:
    # self.assertEqual(golden_data, ret_value)
    # The current code prints the tail of the mismatched data, which helps
    # the human developer identify and comprehend the discrepancies.
    i = 0
    while (i < len(golden_data)) and (i < len(ret_value)):
      if golden_data[i] != ret_value[i]:
        break
      i += 1

    # The golden data must equal the return value.
    self.assertEqual(golden_data[i:], ret_value[i:])

  def test_containers(self):
    ret_value = self.app.get('/containers/json')
    self.compare_to_golden(ret_value, 'containers.json')

  def test_one_container(self):
    ret_value = self.app.get('/containers/deadbeef/json')
    self.compare_to_golden(ret_value, 'containers.deadbeef.json')

  def test_one_image(self):
    ret_value = self.app.get('/images/abcdef/json')
    self.compare_to_golden(ret_value, 'images.abcdef.json')

  def test_processes(self):
    ret_value = self.app.get('/containers/0123456789/top?ps_args=aux')
    self.compare_to_golden(ret_value,
                           'containers.0123456789.top.ps_args.aux')

  def test_version(self):
    """Test the '/version' endpoint."""
    ret_value = self.app.get('/version')
    self.assertEqual('{"version": "unknown for now"}', ret_value.data)


if __name__ == '__main__':
  unittest.main()
