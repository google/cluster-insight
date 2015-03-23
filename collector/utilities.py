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

"""Common utility routines for the Castanet data collector.
"""
import copy
import datetime
import hashlib
import json
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

def one_string_arg(func):
  """A decorator for a function that should be given exactly one valid string.
  """
  def inner(arg1):
    assert valid_string(arg1)
    return func(arg1)

  return inner

def one_optional_string_arg(func):
  """A decorator for a function that should be given an optional valid string.
  """
  def inner(arg1=None):
    assert valid_optional_string(arg1)
    return func(arg1)

  return inner

def one_dictionary_arg(func):
  """A decorator for a function that should be given a dictionary argument.
  """
  def inner(arg1):
    assert isinstance(arg1, types.DictType)
    return func(arg1)

  return inner

def two_string_args(func):
  """A decorator for a function that should be given exactly two valid strings.
  """
  def inner(arg1, arg2):
    assert valid_string(arg1) and valid_string(arg2)
    return func(arg1, arg2)

  return inner

def one_string_one_optional_string_args(func):
  """A decorator for a function that should be given two string arguments.

  The first argument must be a valid string (see valid_string() above).
  The second argument must be an optional string (see valid_optional_string()
  above).
  """
  def inner(arg1, arg2=None):
    assert valid_string(arg1) and valid_optional_string(arg2)
    return func(arg1, arg2)

  return inner

def two_dict_args(func):
  """A decorator for a function that should be given two dictionary arguments.
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, types.DictType) and isinstance(arg2, types.DictType)
    return func(arg1, arg2)

  return inner

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


def timeless_json_hash(obj):
  """Compute the hash of 'obj' without continuously changing attributes.

  Returns:
  The SHA1 digest of the JSON representation of 'obj' after removing the
  'timestamp', 'lastProbeTime', and 'resourceVersion' attributes and their
  values. The values of these attributes change continously and they do not
  add much to the semantics of the object. Ignoring the values of these
  attributes prevent false positive indications that the object changed.
  The JSON representation lists all attributes in sorted order to ensure
  consistent hashing.
  """
  s = json.dumps(obj, sort_keys=True)
  m = hashlib.sha1()
  s = re.sub('"(timestamp|lastProbeTime)": "[-0-9:.TZ]+"', '', s)
  s = re.sub('"resourceVersion": [0-9]+', '', s)
  m.update(s)
  return m.digest()


def object_to_hex_id(obj):
  """Computes the short object ID (12 hexadecimal digits) for the given object.

  The short  ID is the contents of the "CONTAINER ID" column in the
  output of the "docker ps" command or the contents of the "IMAGE ID"
  column in the output of the "docker images" command.
  """
  assert isinstance(obj, types.DictType)
  assert isinstance(obj.get('Id'), types.StringTypes)
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
