#/usr/bin/end python

"""
Computes a config graph from raw config metadata gathered from
a Kubernetes master and the Docker daemons of its nodes.
"""

from flask import current_app

import copy
import datetime
import requests
import logging
import re
import time
import types

# local imports
import collector_error
import constants
import docker
import kubernetes
import utilities

class ConfigGraph:

  def __init__(self):
    self._graph_resources = []
    self._graph_relations = []
    self._graph_metadata = None
    self._graph_title = None
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
    self._cluster_resources = []
    self._cluster_relations = []

  def add_resource(self, rid, rlabel, rtype, timestamp, obj=None):
    assert utilities.valid_string(rid) and utilities.valid_string(rlabel)
    assert utilities.valid_string(rtype)
    assert utilities.valid_string(timestamp)

    # Add the resource to the JSON-graph data structure.
    resource = {
      'id' : rid,
      'label' : rlabel,
      'type' : rtype,
    }

    # Do not add a 'metadata' attribute if its value is None.
    if obj is not None:
      resource['metadata'] = obj

    self._graph_resources.append(resource)

    # Add the resource to the cluster data structure.
    resource = {
      'id' : rid,
      'type' : rtype,
      'timestamp' : timestamp,
    }

    # Do not add a 'metadata' attribute if its value is None.
    resource['annotations'] = { 'label': rlabel }
    if obj is not None:
      resource['properties'] = obj

    self._cluster_resources.append(resource)

  def add_relation(self, source, target, kind, label=None, metadata=None):
    assert utilities.valid_string(source) and utilities.valid_string(target)
    assert utilities.valid_string(kind)
    assert utilities.valid_optional_string(label)
    assert (metadata is None) or isinstance(metadata, types.DictType)

    # Add the relation to the JSON-graph data structure.
    relation = {
      'source' : source,
      'target' : target,
      'relation' : kind,
      'label' : label if label is not None else kind,
    }

    # Do not add a 'metadata' attribute if its value is None.
    if metadata is not None:
      relation['metadata'] = metadata
    self._graph_relations.append(relation)

    # Add the relation to the cluster data structure.
    if kind == 'contains':
      relation = {
        'source' : target,
        'target' : source,
        'type' : 'memberOf',
    }
    else:
      relation = {
        'source' : source,
        'target' : target,
        'type' : kind,
    }

    # Add annotations as needed.
    if metadata is not None:
      relation['annotations'] = metadata

    if label is not None:
      if 'annotations' not in relation:
        relation['annotations'] = {}
      relation['annotations']['label'] = label

    self._cluster_relations.append(relation)

  def set_title(self, title):
    self._graph_title = title

  def set_metadata(self, metadata):
    self._graph_metadata = metadata

  def to_json_graph(self):
    # return graph in JSON-graph format
    json_graph = {
      'graph' : {
        'directed' : True,
        'label' : self._graph_title,
        'metadata' : self._graph_metadata,
        'nodes' : self._graph_resources,
        'edges' : self._graph_relations
      }
    }
    return json_graph

  def to_cluster_insight(self):
    # return graph in Cluster-Insight data collector format.
    cluster = {
        'success': True,
        'timestamp': datetime.datetime.now().isoformat(),
        'resources': self._cluster_resources,
        'relations': self._cluster_relations
    }
    return cluster

  def to_cluster_resources(self):
    # return just the resources in Cluster-Insight data collector format.
    resources = {
        'success': True,
        'timestamp': datetime.datetime.now().isoformat(),
        'resources': self._cluster_resources,
    }
    return resources

  def to_dot_graph(self, show_node_labels=True):
    # return graph in Dot format
    if show_node_labels:
      resource_list = ['"{0}"[label="{1}",color={2}]'.format(
                        res['id'], res['type'] + ':' + res['label'],
                        self._graph_color.get(res['type']) or 'black')
                      for res in self._graph_resources]
    else:
      resource_list = ['"{0}"[label="",fillcolor={1},style=filled]'.format(
                        res['id'],
                        self._graph_color.get(res['type']) or 'black')
                      for res in self._graph_resources]
    relation_list = ['"{0}"->"{1}"[label="{2}"]'.format(
                      rel['source'], rel['target'], rel['label'])
                     for rel in self._graph_relations]
    graph_items = resource_list + relation_list
    graph_data = 'digraph{' + ';'.join(graph_items) + '}'
    return graph_data

  def dump(self, output_format):
    if output_format == 'graph':
      return self.to_json_graph()
    elif output_format == 'dot':
      return self.to_dot_graph()
    elif output_format == 'cluster':
      return self.to_cluster_insight()
    elif output_format == 'resources':
      return self.to_cluster_resources()
    else:
      msg = 'invalid dump() output_format: %s' % output_format
      current_app.logger.exception(msg)
      raise collector_error.CollectorError(msg)

def _make_error(error_message):
  assert isinstance(error_message, types.StringTypes) and error_message
  return { '_success': False,
           '_timestamp': datetime.datetime.now().isoformat(),
           '_error_message': error_message }

def _do_compute_graph(output_format):
  G = ConfigGraph()
  G.set_metadata({'timestamp' : datetime.datetime.now().isoformat()})

  # Nodes
  nodes_list = kubernetes.get_nodes()
  if not nodes_list:
    return G.dump(output_format)

  # Get the project name from the first node.
  project_id = utilities.node_id_to_project_name(nodes_list[0]['id'])

  # TODO(vasbala): how do we get the name of this Kubernetes cluster?
  cluster_id = project_id
  cluster_guid = 'Cluster:' + cluster_id
  G.set_title(cluster_id)
  G.add_resource(cluster_guid, cluster_id, 'Cluster',
                 nodes_list[0]['timestamp'])

  for node in nodes_list:
    node_id = node['id']
    node_label = node['annotations']['label']
    node_guid = 'Node:' + node_id
    G.add_resource(node_guid, node_label, 'Node', node['timestamp'],
                   node['properties'])
    G.add_relation(cluster_guid, node_guid, 'contains') # Cluster contains Node
    # Pods in a Node
    for pod in kubernetes.get_pods(node_id):
      pod_id = pod['id']
      pod_guid = 'Pod:' + pod_id
      docker_host = pod['properties']['currentState']['host']
      G.add_resource(pod_guid, pod_id, 'Pod', pod['timestamp'],
                     pod['properties'])
      G.add_relation(node_guid, pod_guid, 'contains') # Node contains Pod
      # Containers in a Pod
      for container in docker.get_containers(docker_host, pod_id):
        container_id = container['id']
        container_guid = 'Container:' + container_id
        # TODO(vasbala): container_id is too verbose?
        G.add_resource(container_guid, container['annotations']['label'],
                       'Container', container['timestamp'],
                       container['properties'])
        # Pod contains Container
        G.add_relation(pod_guid, container_guid, 'contains')
        # Processes in a Container
        for process in docker.get_processes(docker_host, container_id):
          process_id = process['id']
          process_guid = 'Process:' + process_id
          G.add_resource(process_guid, process['annotations']['label'],
                         'Process', process['timestamp'], process['properties'])
          # Container contains Process
          G.add_relation(container_guid, process_guid, 'contains')
        # Image from which this Container was created
        image_id = container['properties']['Config']['Image']
        image = docker.get_image(docker_host, image_id)
        if image is None:
          # image not found
          continue
        image_guid = 'Image:' + image['id']
        G.add_resource(image_guid, image['annotations']['label'], 'Image',
                       image['timestamp'], image['properties'])
        # Container createdFrom Image
        G.add_relation(container_guid, image_guid, 'createdFrom')

  # Services
  for service in kubernetes.get_services():
    service_id = service['id']
    service_guid = 'Service:' + service_id
    G.add_resource(service_guid, service_id, 'Service',
                   service['timestamp'], service['properties'])
    # Cluster contains Service.
    G.add_relation(cluster_guid, service_guid, 'contains')
    # Pods load balanced by this Service (use the service['labels']
    # key/value pairs to find matching Pods)
    selector = service['properties'].get('labels')
    if selector:
      for pod in kubernetes.get_selected_pods(selector):
        pod_guid = 'Pod:' + pod['id']
        # Service loadBalances Pod
        G.add_relation(service_guid, pod_guid, 'loadBalances')
    else:
      current_app.logger.error('Service id=%s has no "labels" key', service_id)

  # ReplicationControllers
  rcontrollers_list = kubernetes.get_rcontrollers()
  for rcontroller in rcontrollers_list:
    rcontroller_id = rcontroller['id']
    rcontroller_guid = 'ReplicationController:' + rcontroller_id
    G.add_resource(rcontroller_guid, rcontroller_id, 'ReplicationController',
                   rcontroller['timestamp'], rcontroller['properties'])
    # Cluster contains Rcontroller
    G.add_relation(cluster_guid, rcontroller_guid, 'contains')
    # Pods that are monitored by this Rcontroller (use the rcontroller['labels']
    # key/value pairs to find matching pods)
    selector = rcontroller['properties'].get('labels')
    if selector:
      for pod in kubernetes.get_selected_pods(selector):
        pod_guid = 'Pod:' + pod['id']
        # Rcontroller monitors Pod
        G.add_relation(rcontroller_guid, pod_guid, 'monitors')
    else:
      current_app.logger.error('Rcontroller id=%s has no "labels" key',
                               rcontroller_id)

  # Dump the resulting graph
  return G.dump(output_format)


def compute_graph(output_format):
  return _do_compute_graph(output_format)
