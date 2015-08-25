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


"""Runs the cluster insight data collector in master mode.

Collects context metadata from multiple places and computes a graph from it.
"""

import argparse
import logging
import sys

import flask
from flask_cors import CORS

# local imports
import collector_error
import constants
import context
import docker
import global_state
import kubernetes
import utilities

app = flask.Flask(__name__)

# enable cross-origin resource sharing (CORS) HTTP headers on all routes
cors = CORS(app)


def valid_id(x):
  """Tests whether 'x' a valid resource identifier.

  A valid resource identifier is either None (which means you refer to every
  resource) or a non-empty string.

  Args:
    x: a resource identifier or None.

  Returns:
    True iff 'x' is a valid resource identifier.
  """
  return utilities.valid_optional_string(x)


def return_elapsed(gs):
  """Returns a description of the elapsed time of recent operations.

  Args:
    gs: global state.

  Returns:
  A dictionary containing the count, minimum elapsed time,
  maximum elapsed time, average elapsed time, and list of elapsed time
  records.
  """
  assert isinstance(gs, global_state.GlobalState)
  elapsed_list = []
  elapsed_sum = 0.0
  elapsed_min = None
  elapsed_max = None
  for elapsed_record in gs.get_elapsed():
    duration = elapsed_record.elapsed_seconds
    elapsed_list.append(
        {'start_time': utilities.seconds_to_timestamp(
            elapsed_record.start_time),
         'what': elapsed_record.what,
         'threadIdentifier': elapsed_record.thread_identifier,
         'elapsed_seconds': duration})
    elapsed_sum += duration
    if (elapsed_min is None) or (elapsed_max is None):
      elapsed_min = duration
      elapsed_max = duration
    else:
      elapsed_min = min(elapsed_min, duration)
      elapsed_max = max(elapsed_max, duration)

  return {'count': len(elapsed_list),
          'min': elapsed_min,
          'max': elapsed_max,
          'average': elapsed_sum / len(elapsed_list) if elapsed_list else None,
          'items': elapsed_list}


@app.route('/', methods=['GET'])
def home():
  """Returns the response of the '/' endpoint.

  Returns:
    The home page of the Cluster-Insight data collector.
  """
  return flask.send_from_directory('static', 'home.html')


@app.route('/cluster/resources/nodes', methods=['GET'])
def get_nodes():
  """Computes the response of the '/cluster/resources/nodes' endpoint.

  Returns:
    The nodes of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    nodes_list = kubernetes.get_nodes_with_metrics(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'kubernetes.get_nodes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(nodes_list, 'resources'))


@app.route('/cluster/resources/services', methods=['GET'])
def get_services():
  """Computes the response of the '/cluster/resources/services' endpoint.

  Returns:
    The services of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    services_list = kubernetes.get_services(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = ('kubernetes.get_services() failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(services_list, 'resources'))


@app.route('/cluster/resources/rcontrollers', methods=['GET'])
def get_rcontrollers():
  """Computes the response of accessing the '/cluster/resources/rcontrollers'.

  Returns:
    The replication controllers of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    rcontrollers_list = kubernetes.get_rcontrollers(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = ('kubernetes.get_rcontrollers() failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(rcontrollers_list, 'resources'))


@app.route('/cluster/resources/pods', methods=['GET'])
def get_pods():
  """Computes the response of the '/cluster/resources/pods' endpoint.

  Returns:
    The pods of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    pods_list = kubernetes.get_pods(gs, None)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'kubernetes.get_pods() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(pods_list, 'resources'))


@app.route('/cluster/resources/containers', methods=['GET'])
def get_containers():
  """Computes the response of the '/cluster/resources/containers' endpoint.

  Returns:
    The containers of the context graph.
  """
  containers = []

  gs = app.context_graph_global_state
  try:
    for node in kubernetes.get_nodes(gs):
      # The node_id is the Docker host name.
      docker_host = node['id']
      containers.extend(docker.get_containers_with_metrics(gs, docker_host))

  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'get_containers() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(containers, 'resources'))


@app.route('/cluster/resources/processes', methods=['GET'])
def get_processes():
  """Computes the response of the '/cluster/resources/processes' endpoint.

  Returns:
    The processes of the context graph.
  """
  processes = []

  gs = app.context_graph_global_state
  try:
    for node in kubernetes.get_nodes(gs):
      node_id = node['id']
      docker_host = node_id
      for container in docker.get_containers(gs, docker_host):
        container_id = container['id']
        processes.extend(docker.get_processes(gs, docker_host, container_id))

  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'get_processes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(processes, 'resources'))


@app.route('/cluster/resources/images', methods=['GET'])
def get_images():
  """Computes the response of the '/cluster/resources/images' endpoint.

  Returns:
    The images of the context graph.
  """
  gs = app.context_graph_global_state

  # A dictionary from Image ID to wrapped image objects.
  # If an image appears more than once, keep only its latest value.
  images_dict = {}

  try:
    for node in kubernetes.get_nodes(gs):
      for image in docker.get_images(gs, node['id']):
        images_dict[image['id']] = image

  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'kubernetes.get_images() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  # The images list is sorted by increasing identifiers.
  images_list = [images_dict[key] for key in sorted(images_dict.keys())]
  return flask.jsonify(utilities.make_response(images_list, 'resources'))


@app.route('/debug', methods=['GET'])
def get_debug():
  """Computes the response of the '/cluster/resources/debug' endpoint.

  Returns:
    The DOT graph depicting the context graph.
  """
  gs = app.context_graph_global_state
  try:
    return context.compute_graph(gs, 'dot')
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = ('compute_graph(\"dot\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))


@app.route('/cluster/resources', methods=['GET'])
def get_resources():
  """Computes the response of the '/cluster/resources' endpoint.

  Returns:
    The 'resources' section of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    response = context.compute_graph(gs, 'resources')
    return flask.jsonify(response)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = ('compute_graph(\"resources\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))


@app.route('/cluster', methods=['GET'])
def get_cluster():
  """Computes the response of the '/cluster' endpoint.

  Returns:
    The entire context graph.
  """
  gs = app.context_graph_global_state
  try:
    response = context.compute_graph(gs, 'context_graph')
    return flask.jsonify(response)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = ('compute_graph(\"context_graph\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))


@app.route('/version', methods=['GET'])
def get_version():
  """Computes the response of the '/version' endpoint.

  Returns:
    The value of the docker.get_version() or an error message.
  """
  gs = app.context_graph_global_state
  try:
    version = docker.get_version(gs)
    return flask.jsonify(utilities.make_response(version, 'version'))
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'get_version() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))


@app.route('/minions_status', methods=['GET'])
def get_minions():
  """Computes the response of the '/minions_status' endpoint.

  Returns:
  A dictionary from node names to the status of their minion collectors
  or an error message.
  """
  gs = app.context_graph_global_state
  minions_status = {}
  try:
    for node in kubernetes.get_nodes(gs):
      assert utilities.is_wrapped_object(node, 'Node')
      docker_host = node['id']
      minions_status[docker_host] = docker.get_minion_status(gs, docker_host)

  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))
  except:
    msg = 'get_minions_status() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))

  return flask.jsonify(utilities.make_response(minions_status, 'minionsStatus'))


@app.route('/elapsed', methods=['GET'])
def get_elapsed():
  """Computes the response of the '/elapsed' endpoint.

  Returns:
  A successful response containing the list of elapsed time records of the
  most recent Kubernetes and Docker access operations since the previous
  call to the '/elapsed' endpoint. Never returns more than
  constants.MAX_ELAPSED_QUEUE_SIZE elapsed time records.
  """
  gs = app.context_graph_global_state
  try:
    result = return_elapsed(gs)
    return flask.jsonify(utilities.make_response(result, 'elapsed'))
  except:
    msg = 'get_elapsed() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(utilities.make_error(msg))


@app.route('/healthz', methods=['GET'])
def get_health():
  """Computes the response of the '/healthz' endpoint.

  Returns:
  A successful response containing the attribute 'health' and the value 'OK'.
  """
  return flask.jsonify(utilities.make_response('OK', 'health'))


def main():
  """Starts the web server."""
  parser = argparse.ArgumentParser(description='Cluster-Insight data collector')
  parser.add_argument('-d', '--debug', action='store_true',
                      help='enable debug mode')
  parser.add_argument('--host', action='store', type=str,
                      default='0.0.0.0',
                      help='hostname to listen on [default=all interfaces]')
  parser.add_argument('-p', '--port', action='store', type=int,
                      default=constants.DATA_COLLECTOR_PORT,
                      help='data collector port number [default=%(default)d]')
  parser.add_argument('--docker_port', action='store', type=int,
                      default=constants.DOCKER_PORT,
                      help='Docker port number [default=%(default)d]')
  parser.add_argument('-w', '--workers', action='store', type=int,
                      default=0,
                      help=('number of concurrent workers. A zero or a '
                            'negative value denotes an automatic calculation '
                            'of this number. [default=%(default)d]'))
  args = parser.parse_args()

  app.logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
  g_state = global_state.GlobalState()
  g_state.init_caches_and_synchronization()
  g_state.set_logger(app.logger)
  g_state.set_docker_port(args.docker_port)
  g_state.set_num_workers(args.workers)
  app.context_graph_global_state = g_state

  app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
  main()
