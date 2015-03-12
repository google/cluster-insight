"""Common utility routines for the Castanet data collector.
"""

import datetime
import re
import types

# local imports
import constants


def valid_string(x):
  """Returns True iff 'x' is a non-empty string."""
  return isinstance(x, types.StringTypes) and x


def valid_optional_string(x):
  """Returns True iff is either None or a non-empty string."""
  return (x is None) or valid_string(x)


def wrap_object(obj, obj_type, obj_id, timestamp_seconds, label=None,
                alt_label=None):
  """Returns a dictionary containing the standard wrapper around 'obj'.
  """
  assert valid_string(obj_type) and valid_string(obj_id)
  assert isinstance(timestamp_seconds, types.FloatType)
  assert valid_optional_string(label)
  assert valid_optional_string(alt_label)

  wrapped_obj = {
      'id' : obj_id, 'type' : obj_type,
      'timestamp' :
           datetime.datetime.fromtimestamp(timestamp_seconds).isoformat(),
      'properties' : obj }
  if (label is not None) or (alt_label is not None):
    wrapped_obj['annotations'] = {}
    if label is not None:
      wrapped_obj['annotations']['label'] = label
    if alt_label is not None:
      wrapped_obj['annotations']['alternateLabel'] = alt_label

  return wrapped_obj


def is_wrapped_object(obj, expected_type):
  """Returns True iff 'obj' is a wrapped object of the expected type.

  A wraped object is the result of caling wrap_objected() on a given object.
  Note that
  is_wrapped_object(wrap_object('some_type', 'some_id', time.time(), obj),
                    'some_type')
  is always true.
  """
  assert valid_string(expected_type)
  return (isinstance(obj, types.DictType) and
          ('id' in obj) and valid_string(obj['id']) and
          ('type' in obj) and (obj['type'] == expected_type) and
          ('timestamp' in obj) and valid_string(obj['timestamp']) and
          ('properties' in obj))


def object_to_hex_id(obj):
  """Computes the short object ID (12 hexadecimal digits) for the given object.

  The short  ID is the contents of the "CONTAINER ID" column in the
  output of the "docker ps" command or the contents of the "IMAGE ID"
  column in the output of the "docker images" command.
  """
  assert isinstance(obj, types.DictType) and ('Id' in obj)
  id = obj['Id']
  assert re.match('^[0-9a-f]+$', id) and (len(id) > 12)

  return id[:12]


def _node_id_helper(node_id, id_field):
  """Returns the given field in the given node ID.

  It assumes that the node's ID has the format:split
  <host_name>.c.<project_name>.internal

  For example, the node ID of the first slave node in a cluster is:
  "k8s-guestbook-node-1.c.rising-apricot-840.internal"
  """
  assert valid_string(node_id)
  assert isinstance(id_field, types.IntType)
  assert (id_field >= 0) and (id_field <= 3)
  elements = node_id.split('.')
  assert len(elements) == 4
  assert elements[1] == 'c'
  assert elements[-1] == 'internal'
  assert elements[id_field]

  return elements[id_field]

def node_id_to_project_name(node_id):
  """Returns the project ID of the node ID.

  It assumes that the node's ID has the format:
  <host_name>.c.<project_name>.internal

  For example, the node ID of the first slave node in a cluster is:
  "k8s-guestbook-node-1.c.rising-apricot-840.internal"
  """
  return _node_id_helper(node_id, 2)


def node_id_to_host_name(node_id):
  """Returns the host name part of the given node ID.

  It assumes that the node's ID has the format:
  <host_name>.c.<project_name>.internal

  For example, the node ID of the first slave node in a cluster is:
  "k8s-guestbook-node-1.c.rising-apricot-840.internal"
  """
  return _node_id_helper(node_id, 0)
