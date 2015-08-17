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


"""Routines for collecting context metadata from Kubernetes.

This module assumes that the Kubernete REST API
is accessible via the URL defined by KUBERNETES_API.
"""

import json
import os
import sys
import time
import types

import requests

# local imports
import collector_error
import metrics
import utilities


## Kubernetes APIs

KUBERNETES_API = 'https://%s:%s/api/v1'


def get_kubernetes_base_url():
  """Returns the base URL for the Kubernetes master.

  Uses the environment variables for the kubernetes service.

  Additionally, the environment variable KUBERNETES_API can be used
  to override the returned URL.

  Returns:
    The base URL for the Kubernetes master, including the API prefix.

  Raises:
    CollectorError: if the environment variable KUBERNETES_SERVICE_HOST
    or KUBERNETES_SERVICE_PORT is not defined or empty.
  """
  try:
    return os.environ['KUBERNETES_API']
  except KeyError:
    pass

  service_host = os.environ.get('KUBERNETES_SERVICE_HOST')
  if not service_host:
    raise collector_error.CollectorError(
        'KUBERNETES_SERVICE_HOST environment variable is not set')

  service_port = os.environ.get('KUBERNETES_SERVICE_PORT')
  if not service_port:
    raise collector_error.CollectorError(
        'KUBERNETES_SERVICE_PORT environment variable is not set')

  return KUBERNETES_API % (service_host, service_port)


KUBERNETES_BEARER_TOKEN = ''
KUBERNETES_BEARER_TOKEN_FILE = (
    '/var/run/secrets/kubernetes.io/serviceaccount/token')


def get_kubernetes_bearer_token():
  """Reads the bearer token required to call the Kubernetes master from a file.

  The file is installed in every container within a Kubernetes pod by the
  Kubelet. The path to the file is documented at
  https://github.com/GoogleCloudPlatform/kubernetes/blob/master/docs/accessing-the-cluster.md.

  Returns:
    The contents of the token file as a string for use in the Authorization
    header as a bearer token: 'Authorization: Bearer <token>'

  Raises:
    IOError: if cannot open the token file.
    CollectorError: if the file is empty.
  """
  # TODO(eran): add a lock around the global KUBERNETES_BEARER_TOKEN.
  global KUBERNETES_BEARER_TOKEN
  if not KUBERNETES_BEARER_TOKEN:
    with open(KUBERNETES_BEARER_TOKEN_FILE, 'r') as token_file:
      KUBERNETES_BEARER_TOKEN = token_file.read()
    if not KUBERNETES_BEARER_TOKEN:
      raise collector_error.CollectorError(
          'Cannot read Kubernetes bearer token from %s' %
          KUBERNETES_BEARER_TOKEN_FILE)

  return KUBERNETES_BEARER_TOKEN


def get_kubernetes_headers():
  try:
    return {'Authorization': 'Bearer %s' % (get_kubernetes_bearer_token())}
  except IOError:
    return {}


@utilities.global_state_string_args
def fetch_data(gs, url):
  """Fetches a URL from Kubernetes (production) or reads it from a file (test).

  The file name is derived from the URL in the following way:
  The file name is 'testdata/' + last element of the URL + '.input.json'.

  For example, if the URL is 'https://host:port/api/v1beta3/path/to/resource',
  then the file name is 'testdata/resource.input.json'.

  The input is always JSON. It is converted to an internal representation
  by this routine.

  Args:
   gs: global state.
   url: the URL to fetch from Kubernetes in production.

  Returns:
    The contents of the URL (in production) or the contents of the file
    (in a test).

  Raises:
    IOError: if cannot open the test file.
    ValueError: if cannot convert the contents of the file to JSON.
    Other exceptions may be raised as the result of attempting to
    fetch the URL.
  """
  start_time = time.time()
  if gs.get_testing():
    # Read the data from a file.
    url_elements = url.split('/')
    fname = 'testdata/' + url_elements[-1] + '.input.json'
    v = json.loads(open(fname, 'r').read())
    gs.add_elapsed(start_time, fname, time.time() - start_time)
    return v
  else:
    # Send the request to Kubernetes
    headers = get_kubernetes_headers()
    v = requests.get(url, headers=headers, verify=False).json()
    gs.add_elapsed(start_time, url, time.time() - start_time)
    return v


@utilities.global_state_arg
def get_nodes(gs):
  """Gets the list of all nodes in the current cluster.

  Args:
    gs: global state.

  Returns:
    list of wrapped node objects.
    Each element in the list is the result of
    utilities.wrap_object(node, 'Node', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  nodes, timestamp_secs = gs.get_nodes_cache().lookup('')
  if timestamp_secs is not None:
    gs.logger_info('get_nodes() cache hit returns %d nodes', len(nodes))
    return nodes

  nodes = []
  url = get_kubernetes_base_url() + '/nodes'
  try:
    result = fetch_data(gs, url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  if not (isinstance(result, types.DictType) and 'items' in result):
    msg = 'invalid result when fetching %s' % url
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  for node in result['items']:
    name = utilities.get_attribute(node, ['metadata', 'name'])
    if not utilities.valid_string(name):
      # an invalid node without a valid node ID value.
      continue
    wrapped_node = utilities.wrap_object(
        node, 'Node', name, now,
        label=utilities.node_id_to_host_name(name))
    nodes.append(wrapped_node)

  ret_value = gs.get_nodes_cache().update('', nodes, now)
  gs.logger_info('get_nodes() returns %d nodes', len(nodes))
  return ret_value


@utilities.global_state_arg
def get_nodes_with_metrics(gs):
  """Gets the list of all nodes in the current cluster with their metrics.

  Args:
    gs: global state.

  Returns:
    list of wrapped node objects.
    Each element in the list is the result of
    utilities.wrap_object(node, 'Node', ...)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  nodes_list = get_nodes(gs)

  for node in nodes_list:
    assert utilities.is_wrapped_object(node, 'Node')
    project_id = utilities.node_id_to_project_id(node['id'])
    # The project_id may be '_unknown_'. This is not a big
    # deal, since the aggregator knows the project ID.
    metrics.annotate_node(project_id, node)

  return nodes_list


@utilities.global_state_optional_string_args
def get_pods(gs, node_id=None):
  """Gets the list of all pods in the given node or in the cluster.

  When 'node_id' is None, it returns the list of pods in the cluster.
  When 'node_id' is a non-empty string, it returns the list of pods in that
  node.

  Args:
    gs: global state.
    node_id: the parent node of the pods or None.

  Returns:
    list of wrapped pod objects.
    Each element in the list is the result of
    utilities.wrap_object(pod, 'Pod', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  pods_label = '' if node_id is None else node_id
  pods, timestamp_secs = gs.get_pods_cache().lookup(pods_label)
  if timestamp_secs is not None:
    gs.logger_info('get_pods(pods_label=%s) cache hit returns %d pods',
                   pods_label, len(pods))
    return pods

  pods = []
  url = get_kubernetes_base_url() + '/pods'
  try:
    result = fetch_data(gs, url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  if not (isinstance(result, types.DictType) and 'items' in result):
    msg = 'invalid result when fetching %s' % url
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  for pod in result['items']:
    name = utilities.get_attribute(pod, ['metadata', 'name'])
    if not utilities.valid_string(name):
      # an invalid pod without a valid pod ID value.
      continue
    wrapped_pod = utilities.wrap_object(pod, 'Pod', name, now)
    if node_id:
      # pod['spec']['nodeName'] may be missing if the pod
      # is in "Waiting" status.
      if utilities.get_attribute(pod, ['spec', 'nodeName']) == node_id:
        pods.append(wrapped_pod)
    else:
      # append pod to output if 'node_id' is not specified.
      pods.append(wrapped_pod)

  ret_value = gs.get_pods_cache().update(pods_label, pods, now)
  gs.logger_info('get_pods(node_id=%s) returns %d pods', pods_label, len(pods))
  return ret_value


@utilities.global_state_two_string_args
def get_one_pod(gs, node_id, pod_id):
  """Gets the pod with the given pod_id in the given node_id.

  Args:
    gs: global state.
    node_id: the parent node of requested pod.
    pod_id: the ID of the requested pod.

  Returns:
    If the pod was found, returns the wrapped pod object, which is the result
    of utilities.wrap_object(pod, 'Pod', ...).
    If the pod was not found, returns None.

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  for pod in get_pods(gs, node_id):
    assert utilities.is_wrapped_object(pod, 'Pod')
    if pod['id'] == pod_id:
      return pod

  return None


@utilities.two_dict_args
def matching_labels(pod, selector):
  """Compares the key/vale pairs in 'selector' with the pod's label.

  The pod is considered to be matching the 'selector' iff
  all of the key/value pairs in 'selector' appear in the pod's "labels"
  value.

  Args:
    pod: the pod to be compared with 'selector'.
    selector: a dictionary of key/value pairs.

  Returns:
    True iff the pod's label matches the key/value pairs in 'selector'.
  """
  pod_labels = utilities.get_attribute(
      pod, ['properties', 'metadata', 'labels'])
  if not isinstance(pod_labels, types.DictType):
    return False
  selector_view = selector.viewitems()
  pod_labels_view = pod_labels.viewitems()
  return len(selector_view & pod_labels_view) == len(selector_view)


@utilities.global_state_dict_args
def get_selected_pods(gs, selector):
  """Gets the list of pods in the current cluster matching 'selector'.

  The matching pods must contain all of the key/value pairs in 'selector'.

  Args:
    gs: global state.
    selector: a dictionary of key/value pairs describing the labels of
      the matching pods.

  Returns:
    list of wrapped pod objects.
    Each element in the list is the result of
    utilities.wrap_object(pod, 'Pod', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  try:
    all_pods = get_pods(gs)
  except collector_error.CollectorError:
    raise
  except:
    msg = 'get_pods() failed with exception %s' % sys.exc_info()[0]
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  pods = []
  # select the pods with the matching labels.
  for pod in all_pods:
    if matching_labels(pod, selector):
      pods.append(pod)

  gs.logger_info('get_selected_pods(labels=%s) returns %d pods',
                 str(selector), len(pods))
  return pods


@utilities.global_state_string_args
def get_pod_host(gs, pod_id):
  """Gets the host name associated with the given pod.

  Args:
    gs: global state.
    pod_id: the pod name.

  Returns:
    If the pod was found, returns the associated host name.
    If the pod was not found, returns an empty string.

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  gs.logger_info('calling get_pod_host(pod_id=%s)', pod_id)
  for pod in get_pods(gs):
    if not utilities.valid_string(pod.get('id')):
      # Found an invalid pod without a pod ID.
      continue

    pod_host = utilities.get_attribute(pod, ['properties', 'spec', 'nodeName'])
    if pod['id'] == pod_id and utilities.valid_string(pod_host):
      # 'pod_host' may be missing if the pod is in "Waiting" state.
      return pod_host

  # Could not find pod.
  return ''


@utilities.global_state_arg
def get_services(gs):
  """Gets the list of services in the current cluster.

  Args:
    gs: global state.

  Returns:
    list of wrapped service objects.
    Each element in the list is the result of
    utilities.wrap_object(service, 'Service', ...)

    (list_of_services, timestamp_in_seconds)

  Raises:
    CollectorError: in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  services, timestamp_secs = gs.get_services_cache().lookup('')
  if timestamp_secs is not None:
    gs.logger_info('get_services() cache hit returns %d services',
                   len(services))
    return services

  services = []
  url = get_kubernetes_base_url() + '/services'
  try:
    result = fetch_data(gs, url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  if not (isinstance(result, types.DictType) and 'items' in result):
    msg = 'invalid result when fetching %s' % url
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  for service in result['items']:
    name = utilities.get_attribute(service, ['metadata', 'name'])
    if not utilities.valid_string(name):
      # an invalid service without a valid service ID.
      continue
    services.append(
        utilities.wrap_object(service, 'Service', name, now))

  ret_value = gs.get_services_cache().update('', services, now)
  gs.logger_info('get_services() returns %d services', len(services))
  return ret_value


@utilities.global_state_arg
def get_rcontrollers(gs):
  """Gets the list of replication controllers in the current cluster.

  Args:
    gs: global state.

  Returns:
    list of wrapped replication controller objects.
    Each element in the list is the result of
    utilities.wrap_object(rcontroller, 'ReplicationController', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  rcontrollers, ts = gs.get_rcontrollers_cache().lookup('')
  if ts is not None:
    gs.logger_info(
        'get_rcontrollers() cache hit returns %d rcontrollers',
        len(rcontrollers))
    return rcontrollers

  rcontrollers = []
  url = get_kubernetes_base_url() + '/replicationcontrollers'

  try:
    result = fetch_data(gs, url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  if not (isinstance(result, types.DictType) and 'items' in result):
    msg = 'invalid result when fetching %s' % url
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  for rcontroller in result['items']:
    name = utilities.get_attribute(rcontroller, ['metadata', 'name'])
    if not utilities.valid_string(name):
      # an invalid replication controller without a valid rcontroller ID.
      continue

    rcontrollers.append(utilities.wrap_object(
        rcontroller, 'ReplicationController', name, now))

  ret_value = gs.get_rcontrollers_cache().update('', rcontrollers, now)
  gs.logger_info(
      'get_rcontrollers() returns %d rcontrollers', len(rcontrollers))
  return ret_value
