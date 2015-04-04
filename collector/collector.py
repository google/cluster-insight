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


"""Collects context metadata from multiple places and computes a graph from it.
"""

import argparse
import datetime
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


def make_response(value, attribute_name):
  """Makes the JSON response containing the given attribute name and value.

  Args:
    value: the value associated with 'attribute_name'.
    attribute_name: a string containing the attribute name.

  Returns:
    A dictionary containing a context-graph successful response with the given
    attribute name and value.
  """
  assert utilities.valid_string(attribute_name)
  return {'success': True,
          'timestamp': datetime.datetime.now().isoformat(),
          attribute_name: value}


def make_error(error_message):
  """Makes the JSON response indicating an error.

  Args:
    error_message: a string containing the error message describing the
    failure.

  Returns:
    A dictionary containing an failed context-graph response with a given
    error message.
  """
  assert utilities.valid_string(error_message)
  return {'success': False,
          'timestamp': datetime.datetime.now().isoformat(),
          'error_message': error_message}


@app.route('/', methods=['GET'])
def home():
  """Returns the home.html contents for all accesses to the '/' URI.

  Returns:
    The home page of the Cluster-Insight data collector.
  """
  return flask.send_from_directory('static', 'home.html')


@app.route('/cluster/resources/nodes', methods=['GET'])
def get_nodes():
  """Computes the response of accessing the '/cluster/resources/nodes' URI.

  Returns:
    The nodes of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    nodes_list = kubernetes.get_nodes(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_nodes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(nodes_list, 'resources'))


@app.route('/cluster/resources/services', methods=['GET'])
def get_services():
  """Computes the response of accessing the '/cluster/resources/services' URI.

  Returns:
    The services of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    services_list = kubernetes.get_services(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('kubernetes.get_services() failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(services_list, 'resources'))


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
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('kubernetes.get_rcontrollers() failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(rcontrollers_list, 'resources'))


@app.route('/cluster/resources/pods', methods=['GET'])
def get_pods():
  """Computes the response of accessing the '/cluster/resources/pods' URI.

  Returns:
    The pods of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    pods_list = kubernetes.get_pods(gs, None)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_pods() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(pods_list, 'resources'))


@app.route('/cluster/resources/containers', methods=['GET'])
def get_containers():
  """Computes the response of accessing the '/cluster/resources/containers' URI.

  Returns:
    The containers of the context graph.
  """
  containers = []

  gs = app.context_graph_global_state
  try:
    for node in kubernetes.get_nodes(gs):
      # The node_id is the Docker host name.
      docker_host = node['id']
      containers.extend(docker.get_containers(gs, docker_host))

  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'get_containers() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(containers, 'resources'))


@app.route('/cluster/resources/processes', methods=['GET'])
def get_processes():
  """Computes the response of accessing the '/cluster/resources/processes' URI.

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
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'get_processes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(processes, 'resources'))


@app.route('/cluster/resources/images', methods=['GET'])
def get_images():
  """Computes the response of accessing the '/cluster/resources/images' URI.

  Returns:
    The images of the context graph.
  """
  images_list = []
  gs = app.context_graph_global_state

  try:
    for node in kubernetes.get_nodes(gs):
      images_list.extend(docker.get_images(gs, node['id']))

  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_images() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(images_list, 'resources'))


@app.route('/debug', methods=['GET'])
def get_debug():
  """Computes the response of accessing the '/cluster/resources/debug' URI.

  Returns:
    The DOT graph depicting the context graph.
  """
  gs = app.context_graph_global_state
  try:
    return context.compute_graph(gs, 'dot')
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"dot\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


@app.route('/cluster/resources', methods=['GET'])
def get_resources():
  """Computes the response of accessing the '/cluster/resources' URI.

  Returns:
    The 'resources' section of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    response = context.compute_graph(gs, 'resources')
    return flask.jsonify(response)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"resources\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


@app.route('/cluster', methods=['GET'])
def get_cluster():
  """Computes the response of accessing the '/cluster' URI.

  Returns:
    The entire context graph.
  """
  gs = app.context_graph_global_state
  try:
    response = context.compute_graph(gs, 'context_graph')
    return flask.jsonify(response)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"context_graph\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


@app.route('/version', methods=['GET'])
def get_version():
  """Computes the response of accessing the '/version' URI.

  Returns:
    The value of the docker.get_version() or an error message.
  """
  gs = app.context_graph_global_state
  try:
    version = docker.get_version(gs)
    return flask.jsonify(make_response(version, 'version'))
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('get_version() failed with exception %s' % sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


# Starts the web server and listen on all external IPs associated with this
# host.
if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Cluster-Insight data collector')
  parser.add_argument('-d', '--debug', action='store_true',
                      help='enable debug mode')
  parser.add_argument('-p', '--port', action='store', type=int,
                      default=constants.DATA_COLLECTOR_PORT,
                      help=('data collector port number [default=%d]' %
                            constants.DATA_COLLECTOR_PORT))
  parser.add_argument('--docker_port', action='store', type=int,
                      default=constants.DOCKER_PORT,
                      help=('Docker port number [default=%d]' %
                            constants.DOCKER_PORT))
  args = parser.parse_args()

  app.logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
  app.context_graph_docker_port = args.docker_port
  g_state = global_state.GlobalState()
  g_state.init_caches()
  g_state.set_logger(app.logger)
  app.context_graph_global_state = g_state

  app.run(host='0.0.0.0', port=args.port, debug=args.debug)
