#!/usr/bin/env python
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


""" Collects config metadata from multiple places and computes a graph from it.
"""

import datetime
import flask
from flask_cors import CORS
import logging
import sys
import time
import types

# local imports
import collector_error
import config
import constants
import docker
import kubernetes
import simple_cache
import utilities

app = flask.Flask(__name__)

# enable cross-origin resource sharing (CORS) HTTP headers on all routes
cors = CORS(app)

def valid_id(x):
  """Returns True when 'x' a valid resource identifier.
  A valid resource identifier is either None (which means you refer to every
  resource) or a non-empty string.
  """
  return utilities.valid_optional_string(x)

def make_response(value, attribute_name):
  """Makes the JSON response containing the given attribute name and value.
  """
  assert utilities.valid_string(attribute_name)
  return { 'success': True,
           'timestamp': datetime.datetime.now().isoformat(),
           attribute_name: value }

def make_error(error_message):
  """Makes the JSON response indicating an error.
  """
  assert utilities.valid_string(error_message)
  return { 'success': False,
           'timestamp': datetime.datetime.now().isoformat(),
           'error_message': error_message }

@app.route('/', methods=['GET'])
def help():
  return flask.send_from_directory('static', 'help.html')

@app.route('/cluster/resources/nodes', methods=['GET'])
def get_nodes():
  try:
    nodes_list = kubernetes.get_nodes()
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_nodes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(nodes_list, 'resources'))

@app.route('/cluster/resources/services', methods=['GET'])
def get_services():
  try:
    services_list = kubernetes.get_services()
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
  try:
    rcontrollers_list = kubernetes.get_rcontrollers()
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
  url = flask.url_for('get_pods')

  try:
    pods_list = kubernetes.get_pods(None)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_pods() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(pods_list, 'resources'))


@app.route('/cluster/resources/containers', methods=['GET'])
def get_containers():
  url = flask.url_for('get_containers')
  try:
    for node in kubernetes.get_nodes():
      # The node_id is the Docker host name.
      docker_host = node['id']
      containers = docker.get_containers(docker_host)

  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'get_containers() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(containers, 'resources'))


@app.route('/cluster/resources/processes', methods=['GET'])
def get_processes(node_id=None, pod_id=None, container_id=None):
  url = flask.url_for('get_processes')
  processes = []

  try:
    for node in kubernetes.get_nodes():
      node_id = node['id']
      docker_host = node_id
      for container in docker.get_containers(docker_host):
        container_id = container['id']
        processes.extend(docker.get_processes(docker_host, container_id))

  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'get_processes() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(processes, 'resources'))

@app.route('/cluster/resources/images', methods=['GET'])
def get_images():
  url = flask.url_for('get_images')
  images_list = []

  try:
    for node in kubernetes.get_nodes():
      images_list.extend(docker.get_images(node['id']))

  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = 'kubernetes.get_images() failed with exception %s' % sys.exc_info()[0]
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

  return flask.jsonify(make_response(images_list, 'resources'))


@app.route('/graph', methods=['GET'])
def get_graph():
  try:
    return flask.jsonify(config.compute_graph('graph'))
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"graph\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


@app.route('/debug', methods=['GET'])
def get_debug():
  try:
    return config.compute_graph('dot')
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"dot\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))

@app.route('/cluster/resources', methods=['GET'])
def get_resources():
  try:
    response = config.compute_graph('resources')
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
  try:
    response = config.compute_graph('cluster')
    return flask.jsonify(response)
  except collector_error.CollectorError as e:
    return flask.jsonify(make_error(str(e)))
  except:
    msg = ('compute_graph(\"cluster\") failed with exception %s' %
           sys.exc_info()[0])
    app.logger.exception(msg)
    return flask.jsonify(make_error(msg))


# Start the web server on port DATA_COLLECTOR_PORT and listen on all external
# IPs associated with this host.
if __name__ == '__main__':
  try:
    port = int(sys.argv[1])
  except:
    port = constants.DATA_COLLECTOR_PORT

  app.logger.setLevel(logging.DEBUG)

  # keep global caches in the 'app' object because Flask allocates all other
  # objects in thread-local memory.
  app._nodes_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._pods_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._services_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._rcontrollers_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._containers_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._images_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)
  app._processes_cache = simple_cache.SimpleCache(
      constants.MAX_CACHED_DATA_AGE_SECONDS)

  app.run(host='0.0.0.0', port=port, debug=True)
