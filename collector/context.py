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
import datetime
import Queue  # "Queue" was renamed "queue" in Python 3.
import re
import sys
import threading
import types

# local imports
import collector_error
import constants
import docker
import global_state
import kubernetes
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

  def add_resource(self, rid, annotations, rtype, timestamp, obj=None):
    """Adds a resource to the context graph."""
    assert utilities.valid_string(rid)
    assert utilities.valid_string(utilities.get_attribute(
        annotations, ['label']))
    assert utilities.valid_string(rtype)
    assert utilities.valid_string(timestamp)

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

      # Do not add a 'metadata' attribute if its value is None.
      if obj is not None:
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
      # Add the relation to the context graph data structure.
      relation = {
          'source': source,
          'target': target,
          'type': kind,
      }

      # Add annotations as needed.
      relation['annotations'] = {}
      if metadata is not None:
        relation['annotations']['metadata'] = metadata

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

  def to_context_graph(self):
    """Returns the context graph in cluster-insight context graph format."""
    # return graph in Cluster-Insight context graph format.
    with self._lock:
      context_graph = {
          'success': True,
          'timestamp': datetime.datetime.now().isoformat(),
          'resources': self._context_resources,
          'relations': self._context_relations
      }
      return context_graph

  def to_context_resources(self):
    """Returns just the resources in Cluster-Insight context graph format."""
    with self._lock:
      resources = {
          'success': True,
          'timestamp': datetime.datetime.now().isoformat(),
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
  return {'_success': False,
          '_timestamp': datetime.datetime.now().isoformat(),
          '_error_message': error_message}


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
  # Do not compute the pods by worker threads in test mode because the order
  # of the output will be different than the golden files due to the effects
  # of queuing the work.
  for pod in kubernetes.get_pods(gs, node_id):
    if gs.get_testing():
      _do_compute_pod(gs, input_queue, node_guid, pod, g)
    else:
      input_queue.put((
          gs.get_random_priority(),
          _do_compute_pod,
          {'gs': gs, 'input_queue': input_queue, 'node_guid': node_guid,
           'pod': pod, 'g': g}))


def _container_in_pod(gs, container, pod):
  """Returns True when 'container' is a part of 'pod'.

  In most cases, the attribute container['properties']['Config']['Hostname']
  contains the pod ID. However, if the name is too long, it is truncated.

  The current convention of container names is that the pod name appears
  inside the container name before the "_default_" substring.
  If the pod name extracted from the container name is longer than the pod
  name in the 'Hostname' attribute, we use the longer name.

  Typical pod names are:
  monitoring-heapster-controller-hquxc
  fluentd-to-elasticsearch-kubernetes-minion-a7lt.c.gce-monitoring.internal

  Typical container names are:
  k8s_heapster.59702a6a_monitoring-heapster-controller-hquxc_default_9cc2c9ac-dd5a-11e4-8a61-42010af0c46c_5193f65d
  k8s_fluentd-es.2a803504_fluentd-to-elasticsearch-kubernetes-minion-a7lt.c.gce-monitoring.internal_default_c5973403e9c9de201f684c38aa8a7588_4dfe38b6

  Args:
    gs: global state.
    container: a wrapped container object.
    pod: a wrapped pod object.

  Raises:
    CollectorError: if the 'container' or the 'pod' are missing essential
    attributes.

  Returns:
  True iff container 'container' is a part of 'pod'.
  """
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.is_wrapped_object(container, 'Container')
  assert utilities.is_wrapped_object(pod, 'Pod')

  pod_name = utilities.get_attribute(
      container, ['properties', 'Config', 'Hostname'])
  if not utilities.valid_string(pod_name):
    msg = 'could not find Hostname in container %s' % container['id']
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  if pod_name == pod['id']:
    return True

  # Try to extract a longer pod name from the container name.
  start_index = container['id'].find('_' + pod_name)
  if start_index < 0:
    return False
  end_index = container['id'].find('_default_', start_index + len(pod_name))
  if end_index < 0:
    return False
  pod_name = container['id'][start_index + 1: end_index]

  return pod_name == pod['id']


def _do_compute_pod(gs, input_queue, node_guid, pod, g):
  assert isinstance(gs, global_state.GlobalState)
  assert isinstance(input_queue, Queue.PriorityQueue)
  assert utilities.valid_string(node_guid)
  assert utilities.is_wrapped_object(pod, 'Pod')
  assert isinstance(g, ContextGraph)

  pod_id = pod['id']
  pod_guid = 'Pod:' + pod_id
  docker_host = utilities.get_attribute(
      pod, ['properties', 'currentState', 'host'])
  if not utilities.valid_string(docker_host):
    msg = ('Docker host (pod["properties"]["currentState"]["host"]) '
           'not found in pod ID %s' % pod_id)
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  g.add_resource(pod_guid, pod['annotations'], 'Pod', pod['timestamp'],
                 pod['properties'])
  g.add_relation(node_guid, pod_guid, 'runs')  # Node runs Pod

  # Containers in a Pod
  for container in docker.get_containers(gs, docker_host):
    if not _container_in_pod(gs, container, pod):
      continue

    # Do not compute the containers by worker threads in test mode because the
    # order of the output will be different than the golden files due to the
    # effects of queuing the work.
    if gs.get_testing():
      _do_compute_container(gs, docker_host, pod_guid, container, g)
    else:
      input_queue.put((
          gs.get_random_priority(),
          _do_compute_container,
          {'gs': gs, 'docker_host': docker_host, 'pod_guid': pod_guid,
           'container': container, 'g': g}))


def _do_compute_container(gs, docker_host, pod_guid, container, g):
  assert isinstance(gs, global_state.GlobalState)
  assert utilities.valid_string(docker_host)
  assert utilities.valid_string(pod_guid)
  assert utilities.is_wrapped_object(container, 'Container')
  assert isinstance(g, ContextGraph)

  container_id = container['id']
  container_guid = 'Container:' + container_id
  # TODO(vasbala): container_id is too verbose?
  g.add_resource(container_guid, container['annotations'],
                 'Container', container['timestamp'],
                 container['properties'])

  # Pod contains Container
  g.add_relation(pod_guid, container_guid, 'contains')

  # Processes in a Container
  for process in docker.get_processes(gs, docker_host, container_id):
    process_id = process['id']
    process_guid = 'Process:' + process_id
    g.add_resource(process_guid, process['annotations'],
                   'Process', process['timestamp'], process['properties'])

    # Container contains Process
    g.add_relation(container_guid, process_guid, 'contains')

  # Image from which this Container was created
  image_id = utilities.get_attribute(
      container, ['properties', 'Config', 'Image'])
  if not utilities.valid_string(image_id):
    # Image ID not found
    return
  image = docker.get_image(gs, docker_host, image_id)
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

  # Pods load balanced by this Service (use the service['labels']
  # key/value pairs to find matching Pods)
  selector = utilities.get_attribute(service, ['properties', 'selector'])
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

  # Pods that are monitored by this Rcontroller (use the rcontroller['labels']
  # key/value pairs to find matching pods)
  selector = utilities.get_attribute(
      rcontroller, ['properties', 'desiredState', 'replicaSelector'])
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
    gs.logger_error('Rcontroller id=%s has no "replicaSelector" attribute',
                    rcontroller_id)


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
  g.set_version(docker.get_version(gs))
  g.set_metadata({'timestamp': datetime.datetime.now().isoformat()})

  # Nodes
  nodes_list = kubernetes.get_nodes(gs)
  if not nodes_list:
    return g.dump(gs, output_format)

  # Get the project name from the first node.
  project_id = utilities.node_id_to_project_name(nodes_list[0]['id'])

  # TODO(vasbala): how do we get the name of this Kubernetes cluster?
  cluster_id = project_id
  cluster_guid = 'Cluster:' + cluster_id
  g.set_title(cluster_id)
  g.add_resource(cluster_guid, {'label': cluster_id}, 'Cluster',
                 nodes_list[0]['timestamp'])

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

  # Wait until worker threads finished processing all outstanding requests.
  # Once we return from the join(), all output was generated already.
  input_queue.join()

  # Convert any exception caught by the worker threads to an exception
  # raised by the current thread.
  if not output_queue.empty():
    msg = output_queue.get_nowait()  # should not fail.
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

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
