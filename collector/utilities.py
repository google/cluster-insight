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

"""Common utility routines for the Cluster-Insight data collector."""

import datetime
import hashlib
import json
import re
import types

# local imports
import global_state


def valid_string(x):
  """Returns True iff 'x' is a non-empty string."""
  return isinstance(x, types.StringTypes) and x


def valid_optional_string(x):
  """Returns True iff is either None or a non-empty string."""
  return (x is None) or valid_string(x)


def seconds_to_timestamp(seconds):
  """Converts a timestamp in seconds since the epoch to ISO 8601 format.

  Args:
    seconds: timestamp in seconds since the epoch.

  Returns:
  An ISO 8601 date/time value, which is YYYY-MM-DDTHH:MM:SS[.mmmmmm].
  """
  assert isinstance(seconds, (int, long, float))
  return datetime.datetime.fromtimestamp(seconds).isoformat()


def now():
  """Returns the current date/time in ISO 8601 format.

  Returns:
  An ISO 8601 date/time value, which is YYYY-MM-DDTHH:MM:SS[.mmmmmm].
  """
  return datetime.datetime.now().isoformat()


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
  """A decorator for a function with a global state and one string argument.

  The string argument must be valid (see valid_string() above).
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_string(arg2)
    return func(arg1, arg2)

  return inner


def global_state_dict_args(func):
  """A decorator for a function with a global state and a dictionary argument.

  The dictionary argument must not be empty.

  Raises:
    AssertionError: if the run-time arguments are not a global state and
    a non-empty dictionary.

  Returns:
  A decorated function.
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, global_state.GlobalState)
    assert isinstance(arg2, dict) and arg2
    return func(arg1, arg2)

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
    assert isinstance(arg1, dict) and arg1
    assert isinstance(arg2, dict) and arg2
    return func(arg1, arg2)

  return inner


def wrap_object(obj, obj_type, obj_id, timestamp, label=None,
                alt_label=None):
  """Returns a dictionary containing the standard wrapper around 'obj'.
  """
  assert valid_string(obj_type) and valid_string(obj_id)
  assert isinstance(timestamp, (float, str))
  assert valid_optional_string(label)
  assert valid_optional_string(alt_label)

  if not isinstance(timestamp, str):
    timestamp = seconds_to_timestamp(timestamp)

  wrapped_obj = {
      'id': obj_id, 'type': obj_type,
      'timestamp': timestamp,
      'properties': obj}

  wrapped_obj['annotations'] = {}
  wrapped_obj['annotations']['label'] = label if label is not None else obj_id
  if alt_label is not None:
    wrapped_obj['annotations']['alternateLabel'] = alt_label

  return wrapped_obj


def is_wrapped_object(obj, expected_type=None):
  """Returns True iff 'obj' is a wrapped object of the expected type.

  A wrapped object is the result of calling wrap_object() on a given object.
  Note that
  is_wrapped_object(wrap_object(obj, 'some_type', 'some_id', time.time()),
                    'some_type')
  is always true.

  Args:
    obj: any object. If the object does not have the expected type or structure,
      is_wrapped_object() will return False.
    expected_type: the expected value of obj['type'].
      If it is None, then any non-empty object type is accepted.

  Returns:
  True iff 'obj' is a wrapped object of the expected type.
  """
  assert valid_optional_string(expected_type)
  return (valid_string(get_attribute(obj, ['id'])) and
          valid_string(get_attribute(obj, ['type'])) and
          ((expected_type is None) or (obj['type'] == expected_type)) and
          valid_string(get_attribute(obj, ['timestamp'])) and
          isinstance(get_attribute(obj, ['properties']), dict))


def timeless_json_hash(obj):
  """Compute the hash of 'obj' without continuously changing attributes.

  Args:
    obj: an object.

  Returns:
  The SHA1 digest of the JSON representation of 'obj' after removing the
  'timestamp', 'lastHeartbeatTime', and 'resourceVersion' attributes and their
  values. The values of these attributes change continously and they do not
  add much to the semantics of the object. Ignoring the values of these
  attributes prevent false positive indications that the object changed.
  The JSON representation lists all attributes in sorted order to ensure
  consistent hashing.
  """
  s = json.dumps(obj, sort_keys=True)
  m = hashlib.sha1()
  s = re.sub(r'"(timestamp|lastHeartbeatTime)": "[-0-9:.TZ]+"', '', s)
  s = re.sub(r'"resourceVersion": "[0-9]+"', '', s)
  m.update(s)
  return m.digest()


def get_attribute(obj, names_list):
  """Applies the attribute names in 'names_list' on 'obj' to get a value.

  get_attribute() is an extension of the get() function.
  If applies get() successively on a given initial object.
  If any of the intermediate attributes is missing or the object is no
  longer a dictionary, this function returns None.

  For example, calling get_attributes(container, ['Config', 'Image'])
  will attempt to fetch container['Config']['Image'] and return None
  if this attribute or any of its parents is not found.

  Args:
    obj: the object to fetch the attributes from.
    names_list: a list of strings specifying the name of the attributes to
      fetch successively from 'obj'.

  Returns:
  The attribute value or None if any of the intermediate values is not a
  dictionary of any of the attributes in 'names_list' was not found.
  """
  assert isinstance(names_list, list)
  v = obj
  for name in names_list:
    assert isinstance(name, types.StringTypes)
    if isinstance(v, dict) and (name in v):
      v = v[name]
    else:
      return None

  return v


def make_response(value, attribute_name):
  """Makes the JSON response containing the given attribute name and value.

  Args:
    value: the value associated with 'attribute_name'.
    attribute_name: a string containing the attribute name.

  Returns:
    A dictionary containing a context-graph successful response with the given
    attribute name and value.
  """
  assert valid_string(attribute_name)
  # Compute the maximum timestamp of the values in the list 'value'.
  if (isinstance(value, list) and value and
      all([is_wrapped_object(x) for x in value])):
    ts = value[0]['timestamp']  # we know that the list is not empty
    for x in value:
      if x['timestamp'] > ts:
        ts = x['timestamp']
  else:
    # 'value' is not a list or it does not contain wrapped objects.
    ts = now()
  return {'success': True, 'timestamp': ts, attribute_name: value}


@one_string_arg
def make_error(error_message):
  """Makes the JSON response indicating an error.

  Args:
    error_message: a string containing the error message describing the
    failure.

  Returns:
    A dictionary containing an failed context-graph response with a given
    error message.
  """
  assert valid_string(error_message)
  return {'success': False,
          'timestamp': now(),
          'error_message': error_message}
