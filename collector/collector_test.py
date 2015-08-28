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

"""Tests for collector/collector.py."""

# global imports
import json
import os
import re
import time
import types
import unittest

# local imports
import collector
import global_state
import utilities


# A regular expression that matches the 'timestamp' attribute and value
# in JSON data.
TIMESTAMP_REGEXP = r'"timestamp": "[-0-9:.TZ]+"'


class TestCollector(unittest.TestCase):
  """Test harness."""

  def setUp(self):
    os.environ['KUBERNETES_SERVICE_HOST'] = 'localhost'
    os.environ['KUBERNETES_SERVICE_PORT'] = '443'
    gs = global_state.GlobalState()
    gs.init_caches_and_synchronization()
    collector.app.context_graph_global_state = gs
    collector.app.testing = True
    self.app = collector.app.test_client()

  def compare_to_golden(self, ret_value, fname):
    """Compares the returned value to the golden (expected) value.

    The golden value is read from the file
    'testdata/<last element of fname>.output.json'.
    All timestamp attributes and their values are removed from the returned
    value and the golden value prior to comparing them.

    Args:
      ret_value: JSON output from the server.
      fname: the middle part of the file name containing the golden
        (expected) output from the server.
    Raises:
      AssertError if the sanitized golden data differs from the sanitized
      return value.
    """
    assert isinstance(ret_value, types.StringTypes)
    assert isinstance(fname, types.StringTypes)

    # Read the golden data (expected value).
    golden_fname = 'testdata/' + fname + '.output.json'
    f = open(golden_fname, 'r')
    golden_data = f.read()
    f.close()

    # Remove all timestamps from golden data and returned value.
    sanitized_golden_data = re.sub(TIMESTAMP_REGEXP, '', golden_data)
    sanitized_ret_value = re.sub(TIMESTAMP_REGEXP, '', ret_value)

    # Strip whitespaces of the sanitized strings, and replace multiple
    # whitespaces by a single space
    sanitized_golden_data = re.sub(r'\s+', ' ', sanitized_golden_data.strip())
    sanitized_ret_value = re.sub(r'\s+', ' ', sanitized_ret_value.strip())

    # Find the index of the first discrepancy between 'sanitized_golden_data'
    # and 'sanitized_ret_value'. If they are equal, the index will point at
    # the position after the last character in both strings.
    # DO NOT replace this code with:
    # self.assertEqual(sanitized_golden_data, sanitized_ret_value)
    # The current code prints the tail of the mismatched data, which helps
    # the human developer identify and comprehend the discrepancies.
    i = 0
    while (i < len(sanitized_golden_data)) and (i < len(sanitized_ret_value)):
      if sanitized_golden_data[i] != sanitized_ret_value[i]:
        break
      i += 1

    # The sanitized golden data must equal the sanitized
    # return value.
    self.assertEqual(sanitized_golden_data[i:], sanitized_ret_value[i:])

  def test_regexp(self):
    """Tests the TIMESTAMP_REGEXP against various timestamp formats."""
    self.assertEqual(
        '{}',
        re.sub(TIMESTAMP_REGEXP, '',
               '{"timestamp": "2015-03-17T02:00:41.918629"}'))
    self.assertEqual(
        '{}',
        re.sub(TIMESTAMP_REGEXP, '', '{"timestamp": "2015-02-23T03:13:29Z"}'))

  def test_home(self):
    ret_value = self.app.get('/')
    self.assertTrue('Returns this help message' in ret_value.data)

  def test_nodes(self):
    ret_value = self.app.get('/cluster/resources/nodes')
    self.compare_to_golden(ret_value.data, 'nodes')

  def test_pods(self):
    ret_value = self.app.get('/cluster/resources/pods')
    self.compare_to_golden(ret_value.data, 'pods')

  def test_services(self):
    ret_value = self.app.get('/cluster/resources/services')
    self.compare_to_golden(ret_value.data, 'services')

  def test_rcontrollers(self):
    ret_value = self.app.get('/cluster/resources/rcontrollers')
    self.compare_to_golden(ret_value.data, 'replicationcontrollers')

  def count_resources(self, output, type_name):
    assert isinstance(output, dict)
    assert isinstance(type_name, types.StringTypes)
    if not isinstance(output.get('resources'), list):
      return 0

    n = 0
    for r in output.get('resources'):
      assert utilities.is_wrapped_object(r)
      if r.get('type') == type_name:
        n += 1

    return n

  def count_relations(self, output, type_name,
                      source_type=None, target_type=None):
    """Count relations of the specified type (e.g., "contains").

    If the source type and/or target type is specified (e.g., "Node", "Pod",
    etc.), count only relations that additionally match that constraint.
    """
    assert isinstance(output, dict)
    assert isinstance(type_name, types.StringTypes)
    if not isinstance(output.get('relations'), list):
      return 0

    n = 0
    for r in output.get('relations'):
      assert isinstance(r, dict)
      if r['type'] != type_name:
        continue
      if source_type and r['source'].split(':')[0] != source_type:
        continue
      if target_type and r['target'].split(':')[0] != target_type:
        continue
      n += 1

    return n

  def verify_resources(self, result, start_time, end_time):
    assert isinstance(result, dict)
    assert utilities.valid_string(start_time)
    assert utilities.valid_string(end_time)
    self.assertEqual(1, self.count_resources(result, 'Cluster'))
    self.assertEqual(5, self.count_resources(result, 'Node'))
    self.assertEqual(6, self.count_resources(result, 'Service'))
    # TODO(eran): the pods count does not include the pods running in the
    # master. Fix the count once we include pods that run in the master node.
    self.assertEqual(14, self.count_resources(result, 'Pod'))
    self.assertEqual(16, self.count_resources(result, 'Container'))
    self.assertEqual(10, self.count_resources(result, 'Image'))
    self.assertEqual(3, self.count_resources(result, 'ReplicationController'))

    # Verify that all resources are valid wrapped objects.
    assert isinstance(result.get('resources'), list)
    for r in result['resources']:
      # all resources must be valid.
      assert utilities.is_wrapped_object(r)
      assert start_time <= r['timestamp'] <= end_time

  def test_resources(self):
    """Test the '/resources' endpoint."""
    start_time = utilities.now()
    ret_value = self.app.get('/cluster/resources')
    end_time = utilities.now()
    result = json.loads(ret_value.data)
    self.verify_resources(result, start_time, end_time)

    self.assertEqual(0, self.count_relations(result, 'contains'))
    self.assertEqual(0, self.count_relations(result, 'createdFrom'))
    self.assertEqual(0, self.count_relations(result, 'loadBalances'))
    self.assertEqual(0, self.count_relations(result, 'monitors'))
    self.assertEqual(0, self.count_relations(result, 'runs'))

    # The overall timestamp must be in the expected range.
    self.assertTrue(utilities.valid_string(result.get('timestamp')))
    self.assertTrue(start_time <= result['timestamp'] <= end_time)

  def test_cluster(self):
    """Test the '/cluster' endpoint."""
    start_time = utilities.now()
    end_time = None
    for _ in range(2):
      # Exercise the collector. Read data from golden files and compute
      # a context graph.
      # The second iteration should read from the cache.
      ret_value = self.app.get('/cluster')
      if end_time is None:
        end_time = utilities.now()
      result = json.loads(ret_value.data)
      # The timestamps of the second iteration should be the same as in the
      # first iteration, because the data of the 2nd iteration should be
      # fetched from the cache, and it did not change.
      # Even if fetching the data caused an explicit reading from the files
      # in the second iteration, the data did not change, so it should keep
      # its original timestamp.
      self.verify_resources(result, start_time, end_time)

      self.assertEqual(5, self.count_relations(
          result, 'contains', 'Cluster', 'Node'))
      self.assertEqual(6, self.count_relations(
          result, 'contains', 'Cluster', 'Service'))
      self.assertEqual(3, self.count_relations(
          result, 'contains', 'Cluster', 'ReplicationController'))
      self.assertEqual(16, self.count_relations(
          result, 'contains', 'Pod', 'Container'))

      self.assertEqual(30, self.count_relations(result, 'contains'))
      self.assertEqual(16, self.count_relations(result, 'createdFrom'))
      self.assertEqual(7, self.count_relations(result, 'loadBalances'))
      self.assertEqual(6, self.count_relations(result, 'monitors'))
      self.assertEqual(14, self.count_relations(result, 'runs'))

      # Verify that all relations contain a timestamp in the range
      # [start_time, end_time].
      self.assertTrue(isinstance(result.get('relations'), list))
      for r in result['relations']:
        self.assertTrue(isinstance(r, dict))
        timestamp = r.get('timestamp')
        self.assertTrue(utilities.valid_string(timestamp))
        self.assertTrue(start_time <= timestamp <= end_time)

      # The overall timestamp must be in the expected range.
      self.assertTrue(utilities.valid_string(result.get('timestamp')))
      self.assertTrue(start_time <= result['timestamp'] <= end_time)

      # Wait a little to ensure that the current time is greater than
      # end_time
      time.sleep(1)
      self.assertTrue(utilities.now() > end_time)

    # Change the timestamp of the nodes in the cache.
    timestamp_before_update = utilities.now()
    gs = collector.app.context_graph_global_state
    nodes, timestamp_seconds = gs.get_nodes_cache().lookup('')
    self.assertTrue(isinstance(nodes, list))
    self.assertTrue(start_time <=
                    utilities.seconds_to_timestamp(timestamp_seconds) <=
                    end_time)
    # Change the first node to force the timestamp in the cache to change.
    # We have to change both the properties of the first node and its
    # timestamp, so the cache will store the new value (including the new
    # timestamp).
    self.assertTrue(len(nodes) >= 1)
    self.assertTrue(utilities.is_wrapped_object(nodes[0], 'Node'))
    nodes[0]['properties']['newAttribute123'] = 'the quick brown fox jumps over'
    nodes[0]['timestamp'] = utilities.now()
    gs.get_nodes_cache().update('', nodes)
    timestamp_after_update = utilities.now()
    _, timestamp_seconds = gs.get_nodes_cache().lookup('')
    self.assertTrue(timestamp_before_update <=
                    utilities.seconds_to_timestamp(timestamp_seconds) <=
                    timestamp_after_update)

    # Build the context graph again.
    ret_value = self.app.get('/cluster')
    result = json.loads(ret_value.data)
    self.verify_resources(result, start_time, timestamp_after_update)

    # Verify that all relations contain a timestamp in the range
    # [start_time, end_time].
    self.assertTrue(isinstance(result.get('relations'), list))
    for r in result['relations']:
      self.assertTrue(isinstance(r, dict))
      timestamp = r.get('timestamp')
      self.assertTrue(utilities.valid_string(timestamp))
      self.assertTrue(start_time <= timestamp <= end_time)

    # The overall timestamp must be in the expected range.
    self.assertTrue(utilities.valid_string(result.get('timestamp')))
    self.assertTrue(timestamp_before_update <= result['timestamp'] <=
                    timestamp_after_update)

  def test_debug(self):
    """Test the '/debug' endpoint."""
    ret_value = self.app.get('/debug')
    self.compare_to_golden(ret_value.data, 'debug')

  def verify_empty_elapsed(self):
    """Verify that '/elapsed' endoint returns an empty list of elapsed times.
    """
    ret_value = self.app.get('/elapsed')
    result = json.loads(ret_value.data)
    self.assertTrue(result.get('success'))
    elapsed = result.get('elapsed')
    self.assertTrue(isinstance(elapsed, dict))
    self.assertEqual(0, elapsed.get('count'))
    self.assertTrue(elapsed.get('min') is None)
    self.assertTrue(elapsed.get('max') is None)
    self.assertTrue(elapsed.get('average') is None)
    self.assertTrue(isinstance(elapsed.get('items'), list))
    self.assertEqual([], elapsed.get('items'))

  def test_elapsed(self):
    """Test the '/elapsed' endpoint with and without calls to Kubernetes.
    """
    self.verify_empty_elapsed()

    # Issue a few requests to Kubernetes.
    self.app.get('/cluster/resources/nodes')
    self.app.get('/cluster/resources/services')
    self.app.get('/cluster/resources/rcontrollers')

    # Now we should have a few elapsed time records.
    ret_value = self.app.get('/elapsed')
    result = json.loads(ret_value.data)
    self.assertTrue(result.get('success'))
    elapsed = result.get('elapsed')
    self.assertTrue(isinstance(elapsed, dict))
    self.assertEqual(3, elapsed.get('count'))
    self.assertTrue(elapsed.get('min') > 0)
    self.assertTrue(elapsed.get('max') > 0)
    self.assertTrue(elapsed.get('min') <= elapsed.get('average') <=
                    elapsed.get('max'))
    self.assertTrue(isinstance(elapsed.get('items'), list))
    self.assertEqual(3, len(elapsed.get('items')))

    # The next call to '/elapsed' should return an empty list
    self.verify_empty_elapsed()

  def test_healthz(self):
    """Test the '/healthz' endpoint."""
    ret_value = self.app.get('/healthz')
    result = json.loads(ret_value.data)
    self.assertTrue(result.get('success'))
    health = result.get('health')
    self.assertTrue(isinstance(health, types.StringTypes))
    self.assertEqual('OK', health)


if __name__ == '__main__':
  unittest.main()

