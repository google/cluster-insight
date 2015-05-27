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
# <host name>.c.<project ID>.internal
# The <project ID> may contain internal periods.
# If <project ID> contains periods, then we are interested only in the
# first component of the <project ID> up to the first period.
# For example:
# "k8s-guestbook-node-1.c.rising-apricot-840.internal"
# or
# "kubernetes-minion-dlc9.c.spartan-alcove-89517.google.com.internal".
# or
# "kubernetes-minion-mmj2.c.nth-segment-93514.google.com.internal"
# Note that the actual project name may include a "google.com" prefix.
# For example: google.com:nth-segment-93514
# Thus the project name matched by this pattern just an approximation of the
# correct project name.
NODE_ID_PATTERN = '^([^.]+)[.]c[.]([^.]+).*[.]internal$'

# Some host names may contain the cluster name, but not all.
# Host names that contain cluster names have the following format:
# ks8-<cluster name>-<suffix>
# For example:
# "k8s-guestbook-node-1.c.rising-apricot-840.internal"
# The above pattern does not match cluster names that contain internal
# dashes. Thus the cluster name matched by this pattern may be inaccurate.
HOST_NAME_PATTERN = '^k8s-([^-]+)-.*'


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
  """A decorator for a function with a global state and one string argument.

  The string argument must be valid (see valid_string() above).
  """
  def inner(arg1, arg2):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_string(arg2)
    return func(arg1, arg2)

  return inner


def one_optional_string_arg(func):
  """A decorator for a function with an optional string argument.

  If the string argument is defined, it must be valid
  (see valid_optional_string() above).
  """
  def inner(arg1=None):
    assert valid_optional_string(arg1)
    return func(arg1)

  return inner


def global_state_optional_string_args(func):
  """A decorator for a function with a global state and an optional string arg.

  If the string argument is defined, it must be valid
  (see valid_optional_string() above).
  """
  def inner(arg1, arg2=None):
    assert isinstance(arg1, global_state.GlobalState)
    assert valid_optional_string(arg2)
    return func(arg1, arg2)

  return inner


def global_state_dictionary_args(func):
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


def global_state_two_string_args(func):
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

  The short ID is the contents of the "CONTAINER ID" column in the
  output of the "docker ps" command or the contents of the "IMAGE ID"
  column in the output of the "docker images" command.

  Args:
    obj: a dictionary containing the 'Id' attribute.

  Returns:
  The short object ID (12 hexadecimal digits) of 'obj', which is the first
  12 characters of the obj['Id'] value.
  If the short object ID could not be computed, returns None.
  """
  id_value = get_attribute(obj, ['Id'])
  if not valid_string(id_value):
    return None
  if not re.match('^[0-9a-fA-F]+$', id_value):
    return None
  if len(id_value) < 12:
    return None

  return id_value[:12]


def node_id_to_project_id(node_id):
  """Returns the project ID of the node ID.

  It assumes that the node's ID matches the pattern NODE_ID_PATTERN.
  See the comment describing NODE_ID_PATTERN for details and examples.
  If the node's ID does not match NODE_ID_PATTERN, return '_unknown_'.

  Args:
    node_id: node identifier. Must not be empty.

  Returns:
  The project ID or '_unknown_'.
  """
  m = re.match(NODE_ID_PATTERN, node_id)
  if m:
    return m.group(2)
  else:
    return '_unknown_'


def node_id_to_host_name(node_id):
  """Returns the host name part of the given node ID.

  It assumes that the node's ID matches the pattern NODE_ID_PATTERN or
  if the node ID does not contain any dots, return the node ID.
  See the comment describing NODE_ID_PATTERN for details and examples.

  Args:
    node_id: node identifier. Must not be empty.

  Returns:
    The host name.

  Raises:
    ValueError: failed to parse the node ID.
  """
  if valid_string(node_id) and node_id.find('.') < 0:
    return node_id

  m = re.match(NODE_ID_PATTERN, node_id)
  if m:
    return m.group(1)
  else:
    raise ValueError('Cannot parse node ID to obtain host name: %s' % node_id)


def node_id_to_cluster_name(node_id):
  """Returns the cluster name part of the given node ID.

  It assumes that the node's ID matches the pattern HOST_NAME_PATTERN.
  See the comment describing HOST_NAME_PATTERN for details and examples.
  If the node ID does not match the pattern, return '_unknown_'.

  Args:
    node_id: node identifier. Must not be empty.

  Returns:
    The cluster name or '_unknown_'.
  """
  m = re.match(HOST_NAME_PATTERN, node_id)
  if m:
    return m.group(1)
  else:
    return '_unknown_'


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
  assert isinstance(names_list, types.ListType)
  v = obj
  for name in names_list:
    assert isinstance(name, types.StringTypes)
    if isinstance(v, types.DictType) and (name in v):
      v = v[name]
    else:
      return None

  return v


def get_parent_pod_id(container):
  """Returns the parent pod ID of a given container.

  In most cases, the attribute container['properties']['Config']['Hostname']
  contains the pod ID. However, if the name is too long, it is truncated.

  The current convention of container names is that the pod name appears
  inside the container name before the "_default_" or ".default." substring.
  If the pod name extracted from the container name is longer than the pod
  name in the 'Hostname' attribute, we use the longer name.

  Typical pod names are:
  guestbook-controller-hh2gd
  monitoring-heapster-controller-hquxc
  fluentd-to-elasticsearch-kubernetes-minion-a7lt.c.gce-monitoring.internal

  Typical container names are:
  k8s_heapster.59702a6a_monitoring-heapster-controller-hquxc_default_9cc2c9ac-dd5a-11e4-8a61-42010af0c46c_5193f65d
  k8s_fluentd-es.2a803504_fluentd-to-elasticsearch-kubernetes-minion-a7lt.c.gce-monitoring.internal_default_c5973403e9c9de201f684c38aa8a7588_4dfe38b6
  k8s_php-redis.b317029a_guestbook-controller-hh2gd.default.api_f991f13c-b949-11e4-8246-42010af0c3dd_eb67684a

  Args:
    container: a wrapped container object.

  Returns:
  The parent pod's ID or None if parent pod ID could not be found.
  """
  assert is_wrapped_object(container, 'Container')

  pod_name = get_attribute(
      container, ['properties', 'Config', 'Hostname'])
  if not valid_string(pod_name):
    return None

  # Try to extract a longer pod name from the container name.
  start_index = container['id'].find('_' + pod_name)
  if start_index < 0:
    return None
  end_index = container['id'].find('_default_', start_index + len(pod_name))
  if end_index < 0:
    end_index = container['id'].find('.default.', start_index + len(pod_name))
  if end_index < 0:
    return None
  return container['id'][start_index + 1: end_index]


@two_dict_args
def get_short_container_name(container, parent_pod):
  """Returns the short container name of 'container'.

  The short container name is the key of the value identifying the container.
  For example, the short name of the container is "cassandra" and its
  Docker ID is the hexadecimal string after "docker://".
  "info": {
    "cassandra": {
      "containerID": "docker://325316d8009...",
      "image": "kubernetes/cassandra:v2",
      "imageID": ...
    }
  }

  Args:
    container: the container to be named.
    parent_pod: the container's parent pod.

  Returns:
  The short container name if one was found or None if no short container
  was found.
  """
  assert is_wrapped_object(container, 'Container')
  assert is_wrapped_object(parent_pod, 'Pod')

  info_dict = get_attribute(parent_pod, ['properties', 'currentState', 'info'])
  if not isinstance(info_dict, types.DictType):
    return None

  expected_id = get_attribute(container, ['properties', 'Id'])
  if not valid_string(expected_id):
    return None
  docker_id = 'docker://' + expected_id

  # Search the container ID in the pod's properties.currentState.info
  # dictionary.
  for key, value in info_dict.iteritems():
    assert valid_string(key)
    container_id = get_attribute(value, ['containerID'])
    if valid_string(container_id) and container_id == docker_id:
      return key

  return None
