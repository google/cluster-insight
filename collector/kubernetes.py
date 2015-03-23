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


"""
Collects config metadata from Kubernetes. Assumes the Kubernetes REST API
is accessible via the url defined by KUBERNETES_API.
"""

from flask import current_app
import json
import requests
import sys
import time
import types

# local imports
import collector_error
import utilities

## Kubernetes APIs

KUBERNETES_API = "http://127.0.0.1:8080/api/v1beta1"

@utilities.one_string_arg
def fetch_data(url):
  """Fetch the named URL from Kubernetes (in production) or a file (in a test).
  """
  if current_app.config.get('TESTING'):
    # Read the data from a file.
    url_elements = url.split('/')
    fname = 'testdata/' + url_elements[-1] + '.json'
    return json.loads(open(fname, 'r').read())
  else:
    # Send the request to Kubernetes
    return requests.get(url).json()


def get_nodes():
  """ Gets the list of all nodes in the current cluster.

  Returns:
    list of wrapped node objects.
    Each element in the list is the result of
    utilities.wrap_object(node, 'Node', ...)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  nodes, timestamp_seconds = current_app._nodes_cache.lookup('')
  if timestamp_seconds is not None:
    current_app.logger.info('get_nodes() cache hit returns %d nodes',
                            len(nodes))
    return nodes

  nodes = []
  url = '{kubernetes}/nodes'.format(kubernetes=KUBERNETES_API)
  try:
    result = fetch_data(url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  for node in result['items']:
    nodes.append(utilities.wrap_object(
            node, 'Node', node['id'], now,
            utilities.node_id_to_host_name(node['id'])))

  ret_value = current_app._nodes_cache.update('', nodes, now)
  current_app.logger.info('get_nodes() returns %d nodes', len(nodes))
  return ret_value


@utilities.one_optional_string_arg
def get_pods(node_id=None):
  """Gets the list of all pods in the given node or in the cluster.

  When 'node_id' is None, it returns the list of pods in the cluster.
  When 'node_id' is a non-empty string, it returns the list of pods in that
  node.

  Returns:
    list of wrapped pod objects.
    Each element in the list is the result of
    utilities.wrap_object(pod, 'Pod', ...)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  pods_label = '' if node_id is None else node_id
  pods, timestamp_seconds = current_app._pods_cache.lookup(pods_label)
  if timestamp_seconds is not None:
    current_app.logger.info('get_pods(pods_label=%s) cache hit returns %d pods',
                            pods_label, len(pods))
    return pods

  pods = []
  url = "{kubernetes}/pods".format(kubernetes=KUBERNETES_API)
  try:
    result = fetch_data(url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  for pod in result['items']:
    wrapped_pod = utilities.wrap_object(pod, 'Pod', pod['id'], now)
    if node_id:
      if pod['currentState']['host'] == node_id:
        pods.append(wrapped_pod)
    else:
      pods.append(wrapped_pod)

  ret_value = current_app._pods_cache.update(pods_label, pods, now)
  current_app.logger.info('get_pods(node_id=%s) returns %d pods',
                          pods_label, len(pods))
  return ret_value


@utilities.two_dict_args
def matching_labels(pod, selector):
  """Returns True iff the the pod's labels contain the selector's labels.
  """
  assert utilities.is_wrapped_object(pod, 'Pod')
  if not isinstance(pod['properties']['labels'], types.DictType):
    return False
  selector_view = selector.viewitems()
  pod_labels_view = pod['properties']['labels'].viewitems()
  return len(selector_view & pod_labels_view) == len(selector_view)


@utilities.one_dictionary_arg
def get_selected_pods(selector):
  """Gets the list of pods in the current cluster matching 'selector'.

  Returns:
    list of wrapped pod objects.
    Each element in the list is the result of
    utilities.wrap_object(pod, 'Pod', ...)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  try:
    all_pods = get_pods()
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  pods = []
  # select the pods with the matching labels.
  for pod in all_pods:
    if matching_labels(pod, selector):
      pods.append(pod)

  current_app.logger.info('get_selected_pods(labels=%s) returns %d pods',
                          str(selector), len(pods))
  return pods


@utilities.one_string_arg
def get_pod_host(pod_id):
  """Gets the host name associated with the given pod.

  Returns:
    If the pod was found, returns the associated host name.
    If the pod was not found, returns an empty string.

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  current_app.logger.info('calling get_pod_host(pod_id=%s)', pod_id)
  for pod in get_pods():
    if pod['id'] == pod_id:
      return pod['properties']['currentState']['host']

  # Could not find pod.
  return ''


def get_services():
  """Gets the list of services in the current cluster.

  Returns:
    list of wrapped service objects.
    Each element in the list is the result of
    utilities.wrap_object(rcontroller, 'Service', ...)

    (list_of_services, timestamp_in_seconds)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  services, timestamp_seconds = current_app._services_cache.lookup('')
  if timestamp_seconds is not None:
    current_app.logger.info('get_services() cache hit returns %d services',
                            len(services))
    return services

  services = []
  url = "{kubernetes}/services".format(kubernetes=KUBERNETES_API)
  try:
    result = fetch_data(url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  for service in result['items']:
    services.append(utilities.wrap_object(
            service, 'Service', service['id'], now))

  ret_value = current_app._services_cache.update('', services, now)
  current_app.logger.info('get_services() returns %d services', len(services))
  return ret_value


def get_rcontrollers():
  """Gets the list of replication controllers in the current cluster.

  Returns:
    list of wrapped replication controller objects.
    Each element in the list is the result of
    utilities.wrap_object(rcontroller, 'ReplicationController', ...)

  Raises:
    CollectorError in case of failure to fetch data from Kubernetes.
    Other exceptions may be raised due to exectution errors.
  """
  rcontrollers, timestamp_seconds = current_app._rcontrollers_cache.lookup('')
  if timestamp_seconds is not None:
    current_app.logger.info(
        'get_rcontrollers() cache hit returns %d rcontrollers',
        len(rcontrollers))
    return rcontrollers

  rcontrollers = []
  url = "{kubernetes}/replicationControllers".format(kubernetes=KUBERNETES_API)
  try:
    result = fetch_data(url)
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  for rcontroller in result['items']:
    rcontrollers.append(utilities.wrap_object(
            rcontroller, 'ReplicationController', rcontroller['id'], now))

  ret_value = current_app._rcontrollers_cache.update('', rcontrollers, now)
  current_app.logger.info('get_rcontrollers() returns %d rcontrollers',
                          len(rcontrollers))
  return ret_value
