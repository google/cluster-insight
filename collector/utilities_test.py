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

"""Tests for collector/utilities.py."""

# global imports
import json
import time
import types
import unittest

# local imports
import utilities

CONTAINER = {
    'annotations': {
        'label': 'php-redis/c6bf48e9b60c',
    },
    'id': 'k8s_php-redis.526c9b3e_guestbook-controller-14zj2_default',
    'properties': {
        'Id': 'deadbeef',
        'Image': '01234567',
        'Name': '/k8s_php-redis.526c9b3e_guestbook-controller-14zj2_default'
    },
    'timestamp': '2015-05-29T18:42:52.217499',
    'type': 'Container'
}

ANOTHER_CONTAINER = {
    'id': 'cluster-insight-deadbeef',
    'properties': {
        'Id': u'deadbeef',
        'Image': u'01234567',
        'Name': u'/cluster-insight'
    },
    'timestamp': '2015-05-29T18:42:52.217499',
    'type': 'Container'
}

PARENT_POD = {
    'annotations': {
        'label': 'guestbook-controller-14zj2'
    },
    'id': 'guestbook-controller-14zj2',
    'properties': {
        'status': {
            'containerStatuses': [
                {
                    'containerID': 'docker://deadbeef',
                    'image': 'brendanburns/php-redis',
                    'name': 'php-redis'
                }
            ],
            'hostIP': '104.154.34.132',
            'phase': 'Running',
            'podIP': '10.64.0.5'
        }
    },
    'timestamp': '2015-05-29T18:37:04.852412',
    'type': 'Pod'
}


class TestUtilities(unittest.TestCase):

  def test_node_id_to_host_name(self):
    """Tests node_id_to_host_name()."""
    self.assertEqual(
        'k8s-guestbook-node-1',
        utilities.node_id_to_host_name(
            'k8s-guestbook-node-1.c.rising-apricot-840.internal'))
    self.assertEqual(
        'k8s-guestbook-node-1',
        utilities.node_id_to_host_name('k8s-guestbook-node-1'))
    self.assertEqual(
        'kubernetes-minion-dlc9',
        utilities.node_id_to_host_name(
            'kubernetes-minion-dlc9.c.spartan-alcove-89517.google.com.'
            'internal'))
    self.assertEqual(
        'k8s-guestbook-node-1',
        utilities.node_id_to_host_name('Node:k8s-guestbook-node-1'))
    with self.assertRaises(AssertionError):
      utilities.node_id_to_host_name('')
    with self.assertRaises(ValueError):
      utilities.node_id_to_host_name('x.y.z.w')
    with self.assertRaises(ValueError):
      utilities.node_id_to_host_name('Node:x.y.z.w')
    with self.assertRaises(ValueError):
      utilities.node_id_to_host_name('Node:')

  def test_node_id_to_project_id(self):
    """Tests node_id_to_project_id()."""
    self.assertEqual(
        'rising-apricot-840',
        utilities.node_id_to_project_id(
            'k8s-guestbook-node-1.c.rising-apricot-840.internal'))
    self.assertEqual(
        'rising-apricot-840',
        utilities.node_id_to_project_id(
            'Node:k8s-guestbook-node-1.c.rising-apricot-840.internal'))
    self.assertEqual(
        '_unknown_',
        utilities.node_id_to_project_id('k8s-guestbook-node-1'))
    self.assertEqual(
        'spartan-alcove-89517',
        utilities.node_id_to_project_id(
            'kubernetes-minion-dlc9.c.spartan-alcove-89517.google.com.'
            'internal'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_project_id('x.y.z.w'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_project_id('Node:x.y.z.w'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_project_id('Node:'))
    with self.assertRaises(AssertionError):
      utilities.node_id_to_project_id('')

  def test_node_id_to_cluster_name(self):
    """Tests node_id_to_cluster_name()."""
    self.assertEqual(
        'guestbook',
        utilities.node_id_to_cluster_name(
            'k8s-guestbook-node-1.c.rising-apricot-840.internal'))
    self.assertEqual(
        'guestbook',
        utilities.node_id_to_cluster_name('k8s-guestbook-node-1'))
    self.assertEqual(
        'guestbook',
        utilities.node_id_to_cluster_name('Node:k8s-guestbook-node-1'))
    self.assertEqual(
        '_unknown_',
        utilities.node_id_to_cluster_name(
            'kubernetes-minion-dlc9.c.spartan-alcove-89517.google.com.'
            'internal'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_cluster_name('x.y.z.w'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_cluster_name('Node:x.y.z.w'))
    self.assertEqual(
        '_unknown_', utilities.node_id_to_cluster_name('Node:'))
    with self.assertRaises(AssertionError):
      utilities.node_id_to_cluster_name('')

  def test_container_to_pod(self):
    """Tests the operation of utilities.get_parent_pod_id()."""
    f = open('testdata/containers.output.json')
    containers_blob = json.loads(f.read())
    f.close()

    assert isinstance(containers_blob.get('resources'), types.ListType)
    pod_ids_list = []
    for container in containers_blob['resources']:
      pod_id = utilities.get_parent_pod_id(container)
      pod_ids_list.append(pod_id)

    # One of the contains has no parent pod.
    self.assertEqual(
        ['guestbook-controller-14zj2',
         'redis-master',
         'guestbook-controller-myab8',
         None,
         'redis-worker-controller-4qg33'],
        pod_ids_list)

  def test_timeless_json_hash(self):
    """Tests timeless_json_hash() with multiple similar and dissimilar objects.
    """
    a = {'uid': 'A', 'creationTimestamp': '2015-02-20T21:39:34Z'}

    # 'b1' and 'b2' differs just by the value of the 'lastHearbeatTime'
    # attribute.
    b1 = {'uid': 'B', 'lastHeartbeatTime': '2015-03-13T22:32:15Z'}
    b2 = {'uid': 'B', 'lastHeartbeatTime': utilities.now()}

    # 'c1' and 'c2' differs just by the value of the 'resourceVersion'
    # attribute.
    c1 = {'uid': 'C', 'resourceVersion': '13'}
    c2 = {'uid': 'C', 'resourceVersion': '42'}

    # 'wrapped_xxx' objects look like the objects we normally keep in the cache.
    # The difference between 'wrapped_a1' and 'wrapped_a2' is the value of the
    # 'timestamp' attribute.
    wrapped_a1 = utilities.wrap_object(a, 'Node', 'aaa', time.time())
    wrapped_a2 = utilities.wrap_object(a, 'Node', 'aaa', time.time() + 100)

    # The difference between the 'wrapped_b1', 'wrapped_b2' and 'wrapped_b3'
    # objects are the values of the 'timestamp' and 'lastHeartbeatTime'
    # attributes.
    now = time.time()
    wrapped_b1 = utilities.wrap_object(b1, 'Node', 'bbb', now)
    wrapped_b2 = utilities.wrap_object(b2, 'Node', 'bbb', now)
    wrapped_b3 = utilities.wrap_object(b2, 'Node', 'bbb', now + 100)

    # The difference between 'wrapped_c1' and 'wrapped_c2' objects are
    # the values of the 'timestamp' and 'resourceVersion' attributes.
    wrapped_c1 = utilities.wrap_object(c1, 'Node', 'bbb', now)
    wrapped_c2 = utilities.wrap_object(c2, 'Node', 'bbb', now + 100)

    self.assertEqual(utilities.timeless_json_hash(wrapped_a1),
                     utilities.timeless_json_hash(wrapped_a2))
    self.assertEqual(utilities.timeless_json_hash(wrapped_b1),
                     utilities.timeless_json_hash(wrapped_b2))
    self.assertEqual(utilities.timeless_json_hash(wrapped_b1),
                     utilities.timeless_json_hash(wrapped_b3))
    self.assertEqual(utilities.timeless_json_hash(wrapped_c1),
                     utilities.timeless_json_hash(wrapped_c2))

    # Verify that the hash values of lists of objects behaves as expected.
    self.assertEqual(utilities.timeless_json_hash([wrapped_a1, wrapped_b3]),
                     utilities.timeless_json_hash([wrapped_a2, wrapped_b1]))

    # Verify that the hash value of dissimilar objects is not equal.
    self.assertTrue(utilities.timeless_json_hash(wrapped_a1) !=
                    utilities.timeless_json_hash(wrapped_b1))

  def test_get_short_container_name(self):
    """Tests get_short_container_name()."""
    self.assertEqual(
        'php-redis',
        utilities.get_short_container_name(CONTAINER, PARENT_POD))

  def test_make_response(self):
    """Tests make_response()."""
    # The timestamp of the first response is the current time.
    start_time = utilities.now()
    resp = utilities.make_response([], 'resources')
    end_time = utilities.now()
    # Note that timless_json_hash() ignores the value of the timestamp.
    self.assertEqual(
        utilities.timeless_json_hash(
            {'success': True, 'timestamp': utilities.now(), 'resources': []}),
        utilities.timeless_json_hash(resp))
    self.assertTrue(start_time <= resp.get('timestamp') <= end_time)

    # The timestamp of the second response is the timestamp of the container.
    resp = utilities.make_response([CONTAINER], 'resources')
    self.assertEqual(
        utilities.timeless_json_hash(
            {'success': True, 'timestamp': utilities.now(), 'resources':
             [CONTAINER]}),
        utilities.timeless_json_hash(resp))
    self.assertEqual(CONTAINER['timestamp'], resp['timestamp'])

  def test_is_wrapped_object(self):
    """Tests is_wrapped_object()."""
    self.assertTrue(utilities.is_wrapped_object(CONTAINER, 'Container'))
    self.assertTrue(utilities.is_wrapped_object(CONTAINER))
    self.assertFalse(utilities.is_wrapped_object(CONTAINER, 'Pod'))

    self.assertTrue(utilities.is_wrapped_object(PARENT_POD, 'Pod'))
    self.assertTrue(utilities.is_wrapped_object(PARENT_POD))
    self.assertFalse(utilities.is_wrapped_object(PARENT_POD, 'Container'))

    self.assertFalse(utilities.is_wrapped_object({}))
    self.assertFalse(utilities.is_wrapped_object({}, 'Pod'))
    self.assertFalse(utilities.is_wrapped_object(None))
    self.assertFalse(utilities.is_wrapped_object('hello, world'))

  def test_contains_long_hex_number(self):
    """Tests contains_long_hex_number()."""
    self.assertFalse(utilities.contains_long_hex_number(''))
    self.assertFalse(utilities.contains_long_hex_number('cluster-insight'))
    self.assertFalse(utilities.contains_long_hex_number('abc-123'))
    self.assertFalse(utilities.contains_long_hex_number(u'hello01234567'))
    self.assertTrue(utilities.contains_long_hex_number(u'hello.01234567'))
    self.assertTrue(utilities.contains_long_hex_number(
        'k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_'
        'f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8'))

  def test_get_container_name(self):
    """Tests get_container_name()."""
    with self.assertRaises(AssertionError):
      utilities.get_container_name(None)
    with self.assertRaises(AssertionError):
      utilities.get_container_name({})
    self.assertEqual(
        'k8s_php-redis.526c9b3e_guestbook-controller-14zj2_default',
        utilities.get_container_name(CONTAINER))
    self.assertEqual(
        'cluster-insight',
        utilities.get_container_name(ANOTHER_CONTAINER))

  def test_container_id_to_fname(self):
    """Tests container_id_to_fname()."""
    self.assertEqual(
        'k8s-guestbook-node-3-container-8dcdfec8',
        utilities.container_id_to_fname(
            'k8s-guestbook-node-3.c.rising-apricot-840.internal',
            'container',
            'k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_'
            'f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8'))
    self.assertEqual(
        'k8s-guestbook-node-3-container-cluster-insight',
        utilities.container_id_to_fname(
            'k8s-guestbook-node-3.c.rising-apricot-840.internal',
            'container',
            'cluster-insight'))
    self.assertEqual(
        'k8s-guestbook-node-3-processes-8dcdfec8',
        utilities.container_id_to_fname(
            'k8s-guestbook-node-3',
            'processes',
            'k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_'
            'f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8'))


if __name__ == '__main__':
  unittest.main()
