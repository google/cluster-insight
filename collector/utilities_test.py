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

import time
import unittest

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


if __name__ == '__main__':
  unittest.main()
