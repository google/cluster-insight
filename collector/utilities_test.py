"""Tests for collector/utilities."""

# global imports
import datetime
import copy
import time
import unittest

# local imports
import utilities

class TestUtilities(unittest.TestCase):

  def test_timeless_json_hash(self):
    """Tests timeless_json_hash() with multiple similar objects."""
    a = { 'uid': 'A', 'creationTimestamp': '2015-02-20T21:39:34Z' }
    b1 = { 'uid': 'B', 'lastProbeTime': '2015-03-13T22:32:15Z' }
    b2 = { 'uid': 'B', 'lastProbeTime': datetime.datetime.now().isoformat() }
    wrapped_a1 = utilities.wrap_object(a, 'Node', 'aaa', time.time())
    wrapped_a2 = utilities.wrap_object(a, 'Node', 'aaa', time.time() + 100)
    now = time.time()
    wrapped_b1 = utilities.wrap_object(b1, 'Node', 'bbb', now)
    wrapped_b2 = utilities.wrap_object(b2, 'Node', 'bbb', now)
    wrapped_b3 = utilities.wrap_object(b2, 'Node', 'bbb', now + 100)

    self.assertEqual(utilities.timeless_json_hash(wrapped_a1),
                     utilities.timeless_json_hash(wrapped_a2))
    self.assertEqual(utilities.timeless_json_hash(wrapped_b1),
                     utilities.timeless_json_hash(wrapped_b2))
    self.assertEqual(utilities.timeless_json_hash(wrapped_b1),
                     utilities.timeless_json_hash(wrapped_b3))
    self.assertEqual(utilities.timeless_json_hash([wrapped_a1, wrapped_b3]),
                     utilities.timeless_json_hash([wrapped_a2, wrapped_b1]))
    self.assertTrue(utilities.timeless_json_hash(wrapped_a1) !=
                    utilities.timeless_json_hash(wrapped_b1))


if __name__ == '__main__':
  unittest.main()
