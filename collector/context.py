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


"""Computes a context graph from raw context metadata.

The raw context metadata is gathered from the Kubernetes API.

There is no need to verify the existence of attributes in all wrapped
objects (the output of utilities.wrap_object()), because we assume that
the object was already verified by the corresponding get_xxx() routine
in kubernetes.py.

The get_xxx() routine should have skipped any invalid object and not
return it to the caller.

Usage:

import context
import global_state
gs = global_state.GlobalState()
# initialize the global state in 'gs'.
# select the desired output format.
context.compute_graph(gs, output_format)
"""

import copy
import re
import threading
import time
import types

from flask import current_app as app

import collector_error
import global_state
import kubernetes
import metrics
import utilities


class ContextGraph(object):
  """Maintains the context graph and outputs it.

  This class is thread-safe.
  """

  def __init__(self):
    self._lock = threading.Lock()
    self._graph_metadata = None
    self._graph_title = None
    # Set the color lookup table of various resources.
    self._graph_color = {
        'Cluster': 'black',
        'Node': 'red',
        'Service': 'darkgreen',
        'ReplicationController': 'purple',
        'Pod': 'blue',
        'Container': 'green',
        'Image': 'maroon'
    }
    self._context_resources = []
    self._context_relations = []
    self._id_set = set()
    self._previous_relations_to_timestamps = {}
    self._current_relations_to_timestamps = {}

  def get_relations_to_timestamps(self):
    with self._lock:
      return self._current_relations_to_timestamps

  def set_relations_to_timestamps(self, d):
    assert isinstance(d, dict)
    with self._lock:
      self._previous_relations_to_timestamps = d

  def add_resource(self, rid, annotations, rtype, timestamp, obj):
    """Adds a resource to the context graph."""
    assert utilities.valid_string(rid)
    assert utilities.valid_string(utilities.get_attribute(
        annotations, ['label']))
    assert utilities.valid_string(rtype)
    assert utilities.valid_string(timestamp)
    assert isinstance(obj, dict)

    with self._lock:
      # It is possible that the same resource is referenced by more than one
      # parent. In this case the resource is added only once.
      if rid in self._id_set:
        return

      # Add the resource to the context graph data structure.
      resource = {
          'id': rid,
          'type': rtype,
          'timestamp': timestamp,
          'annotations': copy.deepcopy(annotations)
      }

      resource['properties'] = obj

      self._context_resources.append(resource)
      self._id_set.add(rid)

  def add_relation(self, source, target, kind, label=None, metadata=None):
    """Adds a relation to the context graph."""
    assert utilities.valid_string(source) and utilities.valid_string(target)
    assert utilities.valid_string(kind)
    assert utilities.valid_optional_string(label)
    assert (metadata is None) or isinstance(metadata, dict)

    with self._lock:
      # The timestamp of the relation should be inherited from the previous
      # context graph.
      key = (source, target, kind)
      timestamp = self._previous_relations_to_timestamps.get(key)
      if not utilities.valid_string(timestamp):
        timestamp = utilities.now()

      # Add the relation to the context graph data structure.
      relation = {
          'source': source,
          'target': target,
          'type': kind,
          'timestamp': timestamp
      }
      self._current_relations_to_timestamps[key] = timestamp

      # Add annotations as needed.
      relation['annotations'] = {}
      if metadata is not None:
        relation['annotations']['metadata'] = copy.deep_copy(metadata)
      relation['annotations']['label'] = label if label is not None else kind

      self._context_relations.append(relation)

  def set_title(self, title):
    """Sets the title of the context graph."""
    with self._lock:
      self._graph_title = title

  def set_metadata(self, metadata):
    """Sets the metadata of the context graph."""
    with self._lock:
      self._graph_metadata = metadata

  def max_resources_and_relations_timestamp(self):
    """Computes the maximal timestamp of all resources and relations.

    Must be called while holding self._lock.
    If there are no resources and no relations, return the current time.

    Returns:
    Maximum timestamp of all resources and relations.
    """
    max_timestamp = None
    for r in self._context_resources:
      if (max_timestamp is None) or (r['timestamp'] > max_timestamp):
        max_timestamp = r['timestamp']

    for r in self._context_relations:
      if (max_timestamp is None) or (r['timestamp'] > max_timestamp):
        max_timestamp = r['timestamp']

    return utilities.now() if max_timestamp is None else max_timestamp

  def to_context_graph(self):
    """Returns the context graph in cluster-insight context graph format."""
    # return graph in Cluster-Insight context graph format.
    with self._lock:
      context_graph = {
          'success': True,
          'timestamp': self.max_resources_and_relations_timestamp(),
          'resources': self._context_resources,
          'relations': self._context_relations,
      }
      return context_graph

  def to_context_resources(self):
    """Returns just the resources in Cluster-Insight context graph format."""
    with self._lock:
      resources = {
          'success': True,
          'timestamp': self.max_resources_and_relations_timestamp(),
          'resources': self._context_resources,
      }
      return resources

  def best_label(self, obj):
    """Returns the best human-readable label of the given object.

    We prefer the "alternateLabel" over "label" and a string not composed
    of only hexadecimal digits over hexadecimal digits.

    This function must be called when self._lock is held.

    Args:
      obj: a dictionary containing an "annotations" attribute. The value
        of this attribute should be a dictionary, which may contain
        "alternateLabel" and "Label" attributes.

    Returns:
    The best human-readable label.
    """
    alt_label = utilities.get_attribute(obj, ['annotations', 'alternateLabel'])
    label = utilities.get_attribute(obj, ['annotations', 'label'])
    if (utilities.valid_string(alt_label) and
        re.search('[^0-9a-fA-F]', alt_label)):
      return alt_label
    elif utilities.valid_string(label) and re.search('[^0-9a-fA-F]', label):
      return label
    elif utilities.valid_string(alt_label):
      return alt_label
    elif utilities.valid_string(label):
      return label
    else:
      # should not arrive here.
      return '<unknown>'

  def to_dot_graph(self, show_node_labels=True):
    """Returns the context graph in DOT graph format."""
    with self._lock:
      if show_node_labels:
        resource_list = [
            '"{0}"[label="{1}",color={2}]'.format(
                res['id'],
                res['type'] + ':' + self.best_label(res),
                self._graph_color.get(res['type']) or 'black')
            for res in self._context_resources]
      else:
        resource_list = [
            '"{0}"[label="",fillcolor={1},style=filled]'.format(
                res['id'],
                self._graph_color.get(res['type']) or 'black')
            for res in self._context_resources]
      relation_list = [
          '"{0}"->"{1}"[label="{2}"]'.format(
              rel['source'], rel['target'], self.best_label(rel))
          for rel in self._context_relations]
      graph_items = resource_list + relation_list
      graph_data = 'digraph{' + ';'.join(graph_items) + '}'
      return graph_data

  def dump(self, output_format):
    """Returns the context graph in the specified format."""
    assert isinstance(output_format, types.StringTypes)

    self._context_resources.sort(key=lambda x: x['id'])
    self._context_relations.sort(key=lambda x: (x['source'], x['target']))

    if output_format == 'dot':
      return self.to_dot_graph()
    elif output_format == 'context_graph':
      return self.to_context_graph()
    elif output_format == 'resources':
      return self.to_context_resources()
    else:
      msg = 'invalid dump() output_format: %s' % output_format
      app.logger.error(msg)
      raise collector_error.CollectorError(msg)


def _do_compute_node(cluster_guid, node, g):
  assert utilities.valid_string(cluster_guid)
  assert utilities.is_wrapped_object(node, 'Node')
  assert isinstance(g, ContextGraph)

  node_id = node['id']
  node_guid = 'Node:' + node_id
  g.add_resource(node_guid, node['annotations'], 'Node', node['timestamp'],
                 node['properties'])
  g.add_relation(cluster_guid, node_guid, 'contains')  # Cluster contains Node


def _do_compute_pod(cluster_guid, pod, g):
  assert utilities.valid_string(cluster_guid)
  assert utilities.is_wrapped_object(pod, 'Pod')
  assert isinstance(g, ContextGraph)

  pod_id = pod['id']
  pod_guid = 'Pod:' + pod_id
  g.add_resource(pod_guid, pod['annotations'], 'Pod', pod['timestamp'],
                 pod['properties'])

  # pod.properties.spec.nodeName may be missing if the pod is waiting
  # (not running yet).
  node_id = utilities.get_attribute(pod, ['properties', 'spec', 'nodeName'])
  if utilities.valid_string(node_id):
    # Pod is running.
    node_guid = 'Node:' + node_id
    g.add_relation(node_guid, pod_guid, 'runs')  # Node runs Pod
  else:
    # Pod is not running.
    g.add_relation(cluster_guid, pod_guid, 'contains')  # Cluster contains Pod

  for container in kubernetes.get_containers_from_pod(pod):
    metrics.annotate_container(container, pod)
    _do_compute_container(pod_guid, container, g)


def _do_compute_container(parent_guid, container, g):
  assert utilities.valid_string(parent_guid)
  assert utilities.is_wrapped_object(container, 'Container')
  assert isinstance(g, ContextGraph)

  container_id = container['id']
  container_guid = 'Container:' + container_id
  # TODO(vasbala): container_id is too verbose?
  g.add_resource(container_guid, container['annotations'],
                 'Container', container['timestamp'],
                 container['properties'])

  # The parent Pod contains Container.
  g.add_relation(parent_guid, container_guid, 'contains')

  image = kubernetes.get_image_from_container(container)
  image_guid = 'Image:' + image['id']

  # Add the image to the graph only if we have not added it before.
  #
  # Different containers might reference the same image using different
  # names. Unfortunately, only the first name encountered is recorded.
  # TODO(rimey): Record the other names as well, and choose the primary
  # name deterministically.
  g.add_resource(image_guid, image['annotations'], 'Image',
                 image['timestamp'], image['properties'])

  # Container createdFrom Image
  g.add_relation(container_guid, image_guid, 'createdFrom')


def _do_compute_service(gs, cluster_guid, service, g):
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(cluster_guid)
  assert utilities.is_wrapped_object(service, 'Service')
  assert isinstance(g, ContextGraph)

  service_id = service['id']
  service_guid = 'Service:' + service_id
  g.add_resource(service_guid, service['annotations'], 'Service',
                 service['timestamp'], service['properties'])

  # Cluster contains Service.
  g.add_relation(cluster_guid, service_guid, 'contains')

  # Pods load balanced by this service (use the service['spec', 'selector']
  # key/value pairs to find matching Pods)
  selector = utilities.get_attribute(
      service, ['properties', 'spec', 'selector'])
  if selector:
    if not isinstance(selector, dict):
      msg = 'Service id=%s has an invalid "selector" value' % service_id
      app.logger.error(msg)
      raise collector_error.CollectorError(msg)

    for pod in kubernetes.get_selected_pods(gs, selector):
      pod_guid = 'Pod:' + pod['id']
      # Service loadBalances Pod
      g.add_relation(service_guid, pod_guid, 'loadBalances')


def _do_compute_rcontroller(gs, cluster_guid, rcontroller, g):
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(cluster_guid)
  assert utilities.is_wrapped_object(rcontroller, 'ReplicationController')
  assert isinstance(g, ContextGraph)

  rcontroller_id = rcontroller['id']
  rcontroller_guid = 'ReplicationController:' + rcontroller_id
  g.add_resource(rcontroller_guid, rcontroller['annotations'],
                 'ReplicationController',
                 rcontroller['timestamp'], rcontroller['properties'])

  # Cluster contains Rcontroller
  g.add_relation(cluster_guid, rcontroller_guid, 'contains')

  # Pods that are monitored by this replication controller.
  # Use the rcontroller['spec']['selector'] key/value pairs to find matching
  # pods.
  selector = utilities.get_attribute(
      rcontroller, ['properties', 'spec', 'selector'])
  if selector:
    if not isinstance(selector, dict):
      msg = ('Rcontroller id=%s has an invalid "replicaSelector" value' %
             rcontroller_id)
      app.logger.error(msg)
      raise collector_error.CollectorError(msg)

    for pod in kubernetes.get_selected_pods(gs, selector):
      pod_guid = 'Pod:' + pod['id']
      # Rcontroller monitors Pod
      g.add_relation(rcontroller_guid, pod_guid, 'monitors')
  else:
    app.logger.error('Rcontroller id=%s has no "spec.selector" attribute',
                     rcontroller_id)


def _do_compute_other_nodes(gs, cluster_guid, nodes_list, oldest_timestamp, g):
  """Adds nodes not in the node list but running pods to the graph.

  This handles the case when there are pods running on the master node,
  in which case we add a dummy node representing the master to the graph.
  The nodes list does not include the master.

  Args:
    gs: the global state.
    cluster_guid: the cluster's ID.
    nodes_list: a list of wrapped Node objects.
    oldest_timestamp: the timestamp of the oldest Node object.
    g: the context graph under construction.
  """
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(cluster_guid)
  assert isinstance(nodes_list, list)
  assert utilities.valid_string(oldest_timestamp)
  assert isinstance(g, ContextGraph)

  # Compute the set of known Node names.
  known_node_ids = set()
  for node in nodes_list:
    assert utilities.is_wrapped_object(node, 'Node')
    known_node_ids.add(node['id'])

  # Compute the set of Nodes referenced by pods but not in the known set.
  # The set of unknown node names may be empty.
  missing_node_ids = set()
  for pod in kubernetes.get_pods(gs):
    assert utilities.is_wrapped_object(pod, 'Pod')
    # pod.properties.spec.nodeName may be missing if the pod is waiting.
    parent_node_id = utilities.get_attribute(
        pod, ['properties', 'spec', 'nodeName'])
    if not utilities.valid_string(parent_node_id):
      continue

    if parent_node_id in known_node_ids:
      continue

    # Found a pod that does not belong to any of the known nodes.
    missing_node_ids.add(parent_node_id)

  # Process the missing nodes.
  for node_id in missing_node_ids:
    # Create a dummy node object just as a placeholder for metric
    # annotations.
    node = utilities.wrap_object({}, 'Node', node_id, time.time())

    metrics.annotate_node(node)
    node_guid = 'Node:' + node_id
    g.add_resource(node_guid, node['annotations'], 'Node', oldest_timestamp, {})
    g.add_relation(cluster_guid, node_guid, 'contains')  # Cluster contains Node


def _do_compute_graph(gs, output_format):
  """Returns the context graph in the specified format.

  Args:
    gs: the global state.
    output_format: one of 'dot', 'context_graph', or 'resources'.

  Returns:
    A successful response in the specified format.

  Raises:
    CollectorError: inconsistent or invalid graph data.
  """
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(output_format)

  g = ContextGraph()
  g.set_relations_to_timestamps(gs.get_relations_to_timestamps())

  # Nodes
  nodes_list = kubernetes.get_nodes_with_metrics(gs)
  if not nodes_list:
    return g.dump(output_format)

  # Find the timestamp of the oldest node. This will be the timestamp of
  # the cluster.
  oldest_timestamp = utilities.now()
  for node in nodes_list:
    assert utilities.is_wrapped_object(node, 'Node')
    # note: we cannot call min(oldest_timestamp, node['timestamp']) here
    # because min(string) returnes the smallest character in the string.
    if node['timestamp'] < oldest_timestamp:
      oldest_timestamp = node['timestamp']

  # The cluster name may be available through the Kubernetes API someday.
  # TODO(rimey): Determine the cluster name.
  cluster_name = '_unknown_'
  cluster_guid = 'Cluster:' + cluster_name
  g.set_title(cluster_name)
  g.add_resource(cluster_guid, {'label': cluster_name}, 'Cluster',
                 oldest_timestamp, {})

  # Nodes
  for node in nodes_list:
    _do_compute_node(cluster_guid, node, g)

  # Pods
  for pod in kubernetes.get_pods(gs):
    _do_compute_pod(cluster_guid, pod, g)

  # Services
  for service in kubernetes.get_services(gs):
    _do_compute_service(gs, cluster_guid, service, g)

  # ReplicationControllers
  for rcontroller in kubernetes.get_rcontrollers(gs):
    _do_compute_rcontroller(gs, cluster_guid, rcontroller, g)

  # Other nodes, not on the list, such as the Kubernetes master.
  _do_compute_other_nodes(gs, cluster_guid, nodes_list, oldest_timestamp, g)

  # Keep the relations_to_timestamps mapping for next call.
  gs.set_relations_to_timestamps(g.get_relations_to_timestamps())
  g.set_metadata({'timestamp': g.max_resources_and_relations_timestamp()})

  # Dump the resulting graph
  return g.dump(output_format)


@utilities.global_state_string_args
def compute_graph(gs, output_format):
  """Collects raw information and computes the context graph.

  The number of concurrent calls to compute_graph() is limited by
  the bounded semaphore gs.get_bounded_semaphore().

  Args:
    gs: global state.
    output_format: one of 'graph', 'dot', 'context_graph', or 'resources'.

  Returns:
  The context graph in the specified format.
  """
  with gs.get_bounded_semaphore():
    return _do_compute_graph(gs, output_format)
