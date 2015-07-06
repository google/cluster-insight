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

The raw context metadata is gathered from a Kubernetes master and the Docker
daemons of its nodes.

The context graph is computed by a pool of concurrent worker threads.
The purpose of the worker threads is to reduce the elapsed time by
performing independent operations concurrently.

We store the outstanding operations in a random order in the input
work queue in order to prevent long trains of accessess to the same
system component (such as the Kubernetes master or a Docker controller
on a minion node).

There is no need to verify the existence of attributes in all wrapped
objects (the output of utilities.wrap_object()), because we assume that
the object was already verified by the corresponding get_xxx() routine
in kubernetes.py or docker.py.

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
import Queue  # "Queue" was renamed "queue" in Python 3.
import re
import sys
import threading
import time
import types

# local imports
import collector_error
import constants
import docker
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
        'Process': 'gold',
        'Image': 'maroon'
    }
    self._context_resources = []
    self._context_relations = []
    self._version = None
    self._id_set = set()
    self._previous_relations_to_timestamps = {}
    self._current_relations_to_timestamps = {}

  def get_relations_to_timestamps(self):
    with self._lock:
      return self._current_relations_to_timestamps

  def set_relations_to_timestamps(self, d):
    assert isinstance(d, types.DictType)
    with self._lock:
      self._previous_relations_to_timestamps = d

  def add_resource(self, rid, annotations, rtype, timestamp, obj):
    """Adds a resource to the context graph."""
    assert utilities.valid_string(rid)
    assert utilities.valid_string(utilities.get_attribute(
        annotations, ['label']))
    assert utilities.valid_string(rtype)
    assert utilities.valid_string(timestamp)
    assert isinstance(obj, types.DictType)

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

      if self._version is not None:
        resource['annotations']['createdBy'] = self._version

      resource['properties'] = obj

      self._context_resources.append(resource)
      self._id_set.add(rid)

  def add_relation(self, source, target, kind, label=None, metadata=None):
    """Adds a relation to the context graph."""
    assert utilities.valid_string(source) and utilities.valid_string(target)
    assert utilities.valid_string(kind)
    assert utilities.valid_optional_string(label)
    assert (metadata is None) or isinstance(metadata, types.DictType)

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
      if self._version is not None:
        relation['annotations']['createdBy'] = self._version

      self._context_relations.append(relation)

  def set_version(self, version):
    assert utilities.valid_string(version)
    with self._lock:
      self._version = version

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
          'relations': self._context_relations
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

    We perfer the "alternateLabel" over "label" and a string not composed
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

  def dump(self, gs, output_format):
    """Returns the context graph in the specified format."""
    assert isinstance(gs, global_state.GlobalState)
    assert isinstance(output_format, types.StringTypes)

    if output_format == 'dot':
      return self.to_dot_graph()
    elif output_format == 'context_graph':
      return self.to_context_graph()
    elif output_format == 'resources':
      return self.to_context_resources()
    else:
      msg = 'invalid dump() output_format: %s' % output_format
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)


def _make_error(error_message):
  """Returns an error response in the Cluster-Insight context graph format.

  Args:
    error_message: the error message describing the failure.

  Returns:
    An error response in the cluster-insight context graph format.
  """
  assert isinstance(error_message, types.StringTypes) and error_message
  return {'success': False,
          'timestamp': utilities.now(),
          'error_message': error_message}


def _do_compute_node(gs, input_queue, cluster_guid, node, g):
  assert isinstance(gs, global_state.GlobalState)
  assert isinstance(input_queue, Queue.PriorityQueue)
  assert utilities.valid_string(cluster_guid)
  assert utilities.is_wrapped_object(node, 'Node')
  assert isinstance(g, ContextGraph)

  node_id = node['id']
  node_guid = 'Node:' + node_id
  g.add_resource(node_guid, node['annotations'], 'Node', node['timestamp'],
                 node['properties'])
  g.add_relation(cluster_guid, node_guid, 'contains')  # Cluster contains Node
  # Pods in a Node
  pod_ids = set()
  docker_hosts = set()

  # Process pods sequentially because calls to _do_compute_pod() do not call
  # lower-level services or wait.
  for pod in kubernetes.get_pods(gs, node_id):
    _do_compute_pod(gs, cluster_guid, node_guid, pod, g)
    pod_ids.add(pod['id'])
    # pod.properties.spec.nodeName may be missing if the pod is waiting.
    docker_host = utilities.get_attribute(
        pod, ['properties', 'spec', 'nodeName'])
    if utilities.valid_string(docker_host):
      docker_hosts.add(docker_host)

  # 'docker_hosts' should contain a single Docker host, because all of
  # the pods run in the same Node. However, if it is not the case, we
  # cannot fix the situation, so we just log an error message and continue.
  if len(docker_hosts) != 1:
    gs.logger_error(
        'corrupt pod data in node=%s: '
        '"docker_hosts" is empty or contains more than one entry: %s',
        node_guid, str(docker_hosts))

  # Process containers concurrently.
  for docker_host in docker_hosts:
    for container in docker.get_containers_with_metrics(gs, docker_host):
      parent_pod_id = utilities.get_parent_pod_id(container)
      if utilities.valid_string(parent_pod_id) and (parent_pod_id in pod_ids):
        # This container is contained in a pod.
        parent_guid = 'Pod:' + parent_pod_id
      else:
        # This container is not contained in a pod.
        parent_guid = node_guid

      # Do not compute the containers by worker threads in test mode
      # because the order of the output will be different than the golden
      # files due to the effects of queuing the work.
      if gs.get_testing():
        _do_compute_container(gs, docker_host, parent_guid, container, g)
      else:
        input_queue.put((
            gs.get_random_priority(),
            _do_compute_container,
            {'gs': gs, 'docker_host': docker_host, 'parent_guid': parent_guid,
             'container': container, 'g': g}))


def _do_compute_pod(gs, cluster_guid, node_guid, pod, g):
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(cluster_guid)
  assert utilities.valid_string(node_guid)
  assert utilities.is_wrapped_object(pod, 'Pod')
  assert isinstance(g, ContextGraph)

  pod_id = pod['id']
  pod_guid = 'Pod:' + pod_id
  g.add_resource(pod_guid, pod['annotations'], 'Pod', pod['timestamp'],
                 pod['properties'])

  # pod.properties.spec.nodeName may be missing if the pod is waiting
  # (not running yet).
  docker_host = utilities.get_attribute(
      pod, ['properties', 'spec', 'nodeName'])
  if utilities.valid_string(docker_host):
    # Pod is running.
    if node_guid == ('Node:' + docker_host):
      g.add_relation(node_guid, pod_guid, 'runs')  # Node runs Pod
    else:
      msg = ('Docker host (pod.properties.spec.nodeName)=%s '
             'not matching node ID=%s' % (docker_host, node_guid))
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)
  else:
    # Pod is not running.
    g.add_relation(cluster_guid, pod_guid, 'contains')  # Cluster contains Pod


def _do_compute_container(gs, docker_host, parent_guid, container, g):
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(docker_host)
  assert utilities.valid_string(parent_guid)
  assert utilities.is_wrapped_object(container, 'Container')
  assert isinstance(g, ContextGraph)

  container_id = container['id']
  container_guid = 'Container:' + container_id
  # TODO(vasbala): container_id is too verbose?
  g.add_resource(container_guid, container['annotations'],
                 'Container', container['timestamp'],
                 container['properties'])

  # The parent (Pod or Node) contains Container.
  g.add_relation(parent_guid, container_guid, 'contains')

  # Processes in a Container
  for process in docker.get_processes(gs, docker_host, container_id):
    process_id = process['id']
    process_guid = 'Process:' + process_id
    g.add_resource(process_guid, process['annotations'],
                   'Process', process['timestamp'], process['properties'])

    # Container contains Process
    g.add_relation(container_guid, process_guid, 'contains')

  image = docker.get_image(gs, docker_host, container)
  if image is None:
    # image not found
    return

  image_guid = 'Image:' + image['id']
  # Add the image to the graph only if we have not added it before.
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
    if not isinstance(selector, types.DictType):
      msg = 'Service id=%s has an invalid "selector" value' % service_id
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    for pod in kubernetes.get_selected_pods(gs, selector):
      pod_guid = 'Pod:' + pod['id']
      # Service loadBalances Pod
      g.add_relation(service_guid, pod_guid, 'loadBalances')
  else:
    gs.logger_error('Service id=%s has no "selector" attribute', service_id)


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
    if not isinstance(selector, types.DictType):
      msg = ('Rcontroller id=%s has an invalid "replicaSelector" value' %
             rcontroller_id)
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    for pod in kubernetes.get_selected_pods(gs, selector):
      pod_guid = 'Pod:' + pod['id']
      # Rcontroller monitors Pod
      g.add_relation(rcontroller_guid, pod_guid, 'monitors')
  else:
    gs.logger_error('Rcontroller id=%s has no "spec.selector" attribute',
                    rcontroller_id)


def _do_compute_master_pods(gs, cluster_guid, nodes_list, oldest_timestamp, g):
  """Adds pods running on the master node to the graph.

  These pods do not have a valid parent node, because the nodes list
  does not include the master node.

  This routine adds a dummy master node, and then adds the pods running
  on the master node to the graph. It does not add information about
  containers, processes, or images of these nodes, because there is no
  minion collector running on the master node.

  Note that in some configurations (for example, GKE), there is no
  master node.

  Args:
    gs: the global state.
    cluster_guid: the cluster's ID.
    nodes_list: a list of wrapped Node objects.
    oldest_timestamp: the timestamp of the oldest Node object.
    g: the context graph under construction.
  """
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(cluster_guid)
  assert isinstance(nodes_list, types.ListType)
  assert utilities.valid_string(oldest_timestamp)
  assert isinstance(g, ContextGraph)

  # Compute the set of known Node names.
  known_node_ids = set()
  project_id = '_unknown_'
  for node in nodes_list:
    assert utilities.is_wrapped_object(node, 'Node')
    known_node_ids.add(node['id'])
    project_id = utilities.node_id_to_project_id(node['id'])

  # Compute the set of Nodes referenced by pods but not in the known set.
  # The set of unknown node names may be empty.
  assert utilities.valid_string(project_id)
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

  # Process the pods in each of the missing nodes.
  for node_id in missing_node_ids:
    # Create a dummy node object just as a placeholder for metric
    # annotations.
    node = utilities.wrap_object(
        {}, 'Node', node_id, time.time(),
        label=utilities.node_id_to_host_name(node_id))

    # The project_id may be '_unknown_'. This is not a big
    # deal, since the aggregator knows the project ID.
    metrics.annotate_node(project_id, node)
    node_guid = 'Node:' + node_id
    g.add_resource(node_guid, node['annotations'], 'Node', oldest_timestamp, {})
    g.add_relation(cluster_guid, node_guid, 'contains')  # Cluster contains Node
    for pod in kubernetes.get_pods(gs, node_id):
      _do_compute_pod(gs, cluster_guid, node_guid, pod, g)


def _do_compute_graph(gs, input_queue, output_queue, output_format):
  """Returns the context graph in the specified format.

  Args:
    gs: the global state.
    input_queue: the input queue for the worker threads.
    output_queue: output queue containing exceptions data from the worker
        threads.
    output_format: one of 'graph', 'dot', 'context_graph', or 'resources'.

  Returns:
    A successful response in the specified format.

  Raises:
    CollectorError: inconsistent or invalid graph data.
  """
  assert isinstance(gs, global_state.GlobalState)
  assert isinstance(input_queue, Queue.PriorityQueue)
  assert isinstance(output_queue, Queue.Queue)
  assert utilities.valid_string(output_format)

  g = ContextGraph()
  try:
    version = docker.get_version(gs)
  except Exception as e:
    exc_type, value, _ = sys.exc_info()
    msg = ('get_version() failed with exception %s: %s' %
           (exc_type, value))
    gs.logger_error(msg)
    version = '_unknown_'

  g.set_version(version)
  g.set_relations_to_timestamps(gs.get_relations_to_timestamps())

  # Nodes
  nodes_list = kubernetes.get_nodes_with_metrics(gs)
  if not nodes_list:
    return g.dump(gs, output_format)

  # Find the timestamp of the oldest node. This will be the timestamp of
  # the cluster.
  oldest_timestamp = utilities.now()
  for node in nodes_list:
    assert utilities.is_wrapped_object(node, 'Node')
    # note: we cannot call min(oldest_timestamp, node['timestamp']) here
    # because min(string) returnes the smallest character in the string.
    if node['timestamp'] < oldest_timestamp:
      oldest_timestamp = node['timestamp']

  # Get the cluster name from the first node.
  # The cluster name is an approximation. It is not a big deal if it
  # is incorrect, since the aggregator knows the cluster name.
  cluster_name = utilities.node_id_to_cluster_name(nodes_list[0]['id'])
  cluster_guid = 'Cluster:' + cluster_name
  g.set_title(cluster_name)
  g.add_resource(cluster_guid, {'label': cluster_name}, 'Cluster',
                 oldest_timestamp, {})

  # Nodes
  for node in nodes_list:
    input_queue.put((
        gs.get_random_priority(),
        _do_compute_node,
        {'gs': gs, 'input_queue': input_queue, 'cluster_guid': cluster_guid,
         'node': node, 'g': g}))

  # Services
  for service in kubernetes.get_services(gs):
    input_queue.put((
        gs.get_random_priority(),
        _do_compute_service,
        {'gs': gs, 'cluster_guid': cluster_guid, 'service': service, 'g': g}))

  # ReplicationControllers
  rcontrollers_list = kubernetes.get_rcontrollers(gs)
  for rcontroller in rcontrollers_list:
    input_queue.put((
        gs.get_random_priority(),
        _do_compute_rcontroller,
        {'gs': gs, 'cluster_guid': cluster_guid, 'rcontroller': rcontroller,
         'g': g}))

  # Pods running on the master node.
  input_queue.put((
      gs.get_random_priority(),
      _do_compute_master_pods,
      {'gs': gs, 'cluster_guid': cluster_guid, 'nodes_list': nodes_list,
       'oldest_timestamp': oldest_timestamp, 'g': g}))

  # Wait until worker threads finished processing all outstanding requests.
  # Once we return from the join(), all output was generated already.
  input_queue.join()

  # Convert any exception caught by the worker threads to an exception
  # raised by the current thread.
  if not output_queue.empty():
    msg = output_queue.get_nowait()  # should not fail.
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  # Keep the relations_to_timestamps mapping for next call.
  gs.set_relations_to_timestamps(g.get_relations_to_timestamps())
  g.set_metadata({'timestamp': g.max_resources_and_relations_timestamp()})

  # Dump the resulting graph
  return g.dump(gs, output_format)


def worker(gs, input_queue, output_queue):
  """A worker thread that executes tasks from the input queue.

  The input queue contains tuples of the form:
  (function, keyword-args dictionary).
  All exceptions raised during the exection of the function are caught
  and a textual description of the execption is pushed at the end of the
  output queue. If the exection of the function does not raise any
  exception, then nothing is pushed at the end of the output queue.

  The worker thread pulls work from the input queue repeatedly.
  The worker thread exits only if the tuple it pulls from the input queue
  contains a function equivalent to None.

  The the entries in the input queue are kept in a random order to prevent
  long trains of accesses to the same minion node or to the Kubernetes
  master. Long trains of requests to the same system component are
  inherently sequential.

  Args:
    gs: global state.
    input_queue: input queue containing (priority, function, kwargs) tuples.
    output_queue: output queue containing exception information
  """
  assert isinstance(gs, global_state.GlobalState)
  assert isinstance(input_queue, Queue.PriorityQueue)
  assert isinstance(output_queue, Queue.Queue)

  while True:
    _, func, kwargs = input_queue.get()
    if func is None:
      break
    assert isinstance(kwargs, types.DictType)

    try:
      func(**kwargs)
    except collector_error.CollectorError as e:
      output_queue.put(str(e))
    except:
      msg = ('calling %s with arguments %s failed with exception %s' %
             (str(func), str(kwargs), sys.exc_info()[0]))
      gs.logger_error(msg)
      output_queue.put(msg)

    input_queue.task_done()


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
    input_queue = Queue.PriorityQueue()
    output_queue = Queue.Queue()

    # Compute the number of workers threads to create.
    if gs.get_testing():
      nworkers = 1
    elif gs.get_num_workers() > 0:
      # no range restrictions.
      nworkers = gs.get_num_workers()
    else:
      # get_nodes() may trigger an exception. It will be handled by
      # the exception handler in the caller of this routine.
      nworkers = len(kubernetes.get_nodes(gs))
      # The number of workers must be in the range
      # [constants.MIN_CONCURRENT_WORKERS, constants.MAX_CONCURRENT_WORKERS].
      nworkers = utilities.range_limit(
          nworkers,
          constants.MIN_CONCURRENT_WORKERS, constants.MAX_CONCURRENT_WORKERS)

    # Start worker threads
    gs.logger_info('creating %d worker threads', nworkers)
    worker_threads = []
    for _ in range(nworkers):
      t = threading.Thread(target=worker, args=(gs, input_queue, output_queue))
      t.daemon = True
      t.start()
      worker_threads.append(t)

    # Compute the graph
    try:
      result = _do_compute_graph(gs, input_queue, output_queue, output_format)
    finally:
      # Cleanup: signal all worker threads to stop and wait for them to
      # terminate. If we do not stop the threads they may run forever
      # and constitute a memory leak.
      for _ in worker_threads:
        input_queue.put((0, None, None))

      for t in worker_threads:
        t.join()

  return result
