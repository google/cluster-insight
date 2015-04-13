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

"""Common utility routines for the Cluster-Insight data collector.
"""
import datetime
import hashlib
import json
import re
import types

# local imports
import global_state


# The format of node ID is:
# <host name>.c.<project_name>.internal
# The <project_name> may contain internal periods.
# If <project_name> contains periods, then we are interested only in the
# first component of the <project_name> up to the first period.
# For example:
# "k8s-guestbook-node-1.c.rising-apricot-840.internal"
# or
# "kubernetes-minion-dlc9.c.spartan-alcove-89517.google.com.internal".
NODE_ID_PATTERN = '^([^.]+)[.]c[.]([^.]+).*[.]internal$'


def valid_string(x):
  """Returns True iff 'x' is a non-empty string."""
  return isinstance(x, types.StringTypes) and x


def valid_optional_string(x):
  """Returns True iff is either None or a non-empty string."""
  return (x is None) or valid_string(x)


def valid_hex_id(x):
  """Returns True iff 'x' is a valid full-length hexadecimal ID."""
  return valid_string(x) and (len(x) >= 32) and re.match('^[0-9a-fA-F]+$', x)


def global_state_arg(func):
  """A decorator for a function that should be given a global state argument.
  """
  def inner(arg1):
    assert isinstance(arg1, global_state.GlobalState)
    return func(arg1)

  return inner


def one_string_arg(func):
  """A decorator for a function that should be given exactly one valid string.
  """
  def inner(arg1):
    assert valid_string(arg1)
    return func(arg1)

  return inner


def global_state_string_args(func):
  """A decorator for a function with a glonal state and one string argumensts.

  The string argument must be valid (see valid_string() above).
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_string(arg2)
    return func(arg1, arg2)

  return inner


def one_optional_string_arg(func):
  """A decorator for a function that should be given an optional valid string.
  """
  def inner(arg1=None):
    assert valid_optional_string(arg1)
    return func(arg1)

  return inner


def global_state_optional_string_args(func):
  """A decorator for a function with a global state and an optional string.

  If the string argument is defined, it must be valid
  (see valid_optional_string() above).
  """
  def inner(arg1, arg2=None):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_optional_string(arg2)
    return func(arg1, arg2)

  return inner


def global_state_dictionary_args(func):
  """A decorator for a function with a global state and a dictionary arguments.

  The dictionary argument must not be empty.

  Raises:
    AssertionError: if the run-time arguments are not a global state and
    a non-empty dictionary.

  Returns:
  A decorated function.
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, global_state.GlobalState)
    assert isinstance(arg2, types.DictType) and arg2
    return func(arg1, arg2)

  return inner


def two_string_args(func):
  """A decorator for a function with exactly two valid string arguments.
  """
  def inner(arg1, arg2):
    assert valid_string(arg1) and valid_string(arg2)
    return func(arg1, arg2)

  return inner


def global_state_string_string_args(func):
  """A decorator for a function with a global state and two string arguments.

  All string arguments must be valid strings (see valid_string() above).
  """
  def inner(arg1, arg2, arg3):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_string(arg2) and valid_string(arg3)
    return func(arg1, arg2, arg3)

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


def global_state_string_optional_string_args(func):
  """A decorator for a function that should be given two string arguments.

  The first argument must be a valid string (see valid_string() above).
  The second argument must be an optional string (see valid_optional_string()
  above).
  """
  def inner(arg1, arg2, arg3=None):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_string(arg2) and valid_optional_string(arg3)
    return func(arg1, arg2, arg3)

  return inner


def two_dict_args(func):
  """A decorator for a function that should be given two dictionary arguments.

  Both dictionaries must be not empty.

  Raises:
    AssertionError: if the run-time arguments are not two non-empty
    dictionaries.

  Returns:
  A decorated function.
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, types.DictType) and arg1
    assert isinstance(arg2, types.DictType) and arg2
    return func(arg1, arg2)

  return inner


def range_limit(x, low, high):
  """Limits the input value 'x' to the range [low, high].

  Args:
    x: the input value. should be compatible with the values of 'low' and
      'high'.
    low: low limit on the output value.
    high: high limit on the output value.

  Returns:
  If 'x' is less than 'low', returns 'low'.
  If 'x' is greater than 'high', returns 'high'.
  Otherwise, returns 'x'.
  """
  assert low <= high
  if x < low:
    return low
  elif x > high:
    return high
  else:
    return x


def wrap_object(obj, obj_type, obj_id, timestamp_seconds, label=None,
                alt_label=None):
  """Returns a dictionary containing the standard wrapper around 'obj'.
  """
  assert valid_string(obj_type) and valid_string(obj_id)
  assert isinstance(timestamp_seconds, types.FloatType)
  assert valid_optional_string(label)
  assert valid_optional_string(alt_label)

  wrapped_obj = {
      'id': obj_id, 'type': obj_type,
      'timestamp':
          datetime.datetime.fromtimestamp(timestamp_seconds).isoformat(),
      'properties': obj}

  wrapped_obj['annotations'] = {}
  wrapped_obj['annotations']['label'] = label if label is not None else obj_id
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

  Args:
    obj: any object. If the object does not have the expected type or structure,
      is_wrapped_object() will return False.
    expected_type: the expected value of obj['type'].

  Returns:
  True iff 'obj' is a wrapped object of the expected type.
  """
  assert valid_string(expected_type)
  return (valid_string(get_attribute(obj, ['id'])) and
          valid_string(get_attribute(obj, ['type'])) and
          (obj['type'] == expected_type) and
          valid_string(get_attribute(obj, ['timestamp'])) and
          isinstance(get_attribute(obj, ['properties']), types.DictType))


def timeless_json_hash(obj):
  """Compute the hash of 'obj' without continuously changing attributes.

  Args:
    obj: an object.

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

  Args:
    obj: a dictionary containing the 'Id' attribute.

  Returns:
  The short object ID (12 hexadecimal digits) of 'obj', which is the first
  12 characters of the obj['Id'] value.
  """
  id_value = get_attribute(obj, ['Id'])
  assert valid_string(id_value)
  assert re.match('^[0-9a-fA-F]+$', id_value) and (len(id_value) > 12)

  return id_value[:12]


def node_id_to_project_name(node_id):
  """Returns the project ID of the node ID.

  It assumes that the node's ID matches the pattern NODE_ID_PATTERN.
  See the comment describing NODE_ID_PATTERN for details and examples.

  Args:
    node_id: node identifier. Must not be empty.

  Returns:
  The project name.
  """
  m = re.match(NODE_ID_PATTERN, node_id)
  assert m
  return m.group(2)


def node_id_to_host_name(node_id):
  """Returns the host name part of the given node ID.

  It assumes that the node's ID matches the pattern NODE_ID_PATTERN.
  See the comment describing NODE_ID_PATTERN for details and examples.

  Args:
    node_id: node identifier. Must not be empty.

  Returns:
    The host name.
  """
  m = re.match(NODE_ID_PATTERN, node_id)
  assert m
  return m.group(1)


def get_attribute(obj, names_list):
  """Applies the attribute names in 'names_list' on 'obj' to get a value.

  get_attribute() is an extension of the get() function.
  If applies get() successively on a given initial object.
  If any of the intermediate attributes is missing or the object is no
  longer a dictionary, this function returns None.

  For example, calling get_attributes(container, ['Config', 'Image'])
  will attempt to fetch container['Config']['Image'] and return None
  if this attribute or any of its parents is not found.

  Returns:
  The attribute value or None if any of the intermediate values is not a
  dictionary of any of the attributes in 'names_list' was not found.
  """
  assert isinstance(names_list, types.ListType)
  v = obj
  for name in names_list:
    assert isinstance(name, types.StringTypes)
    if isinstance(v, types.DictType) and (name in v):
      v = v[name]
    else:
      return None

  return v
