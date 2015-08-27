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


"""Runs the cluster insight data collector.

Collects context metadata from the Kubernetes API and computes a graph from it.
"""

import argparse
import sys

import flask
from flask_cors import CORS

# local imports
import collector_error
import constants
import context
import global_state
import kubernetes
import utilities

app = flask.Flask(__name__)

# enable cross-origin resource sharing (CORS) HTTP headers on all routes
cors = CORS(app)


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

  return flask.jsonify(utilities.make_response(rcontrollers_list, 'resources'))


@app.route('/cluster/resources/pods', methods=['GET'])
def get_pods():
  """Computes the response of the '/cluster/resources/pods' endpoint.

  Returns:
    The pods of the context graph.
  """
  gs = app.context_graph_global_state
  try:
    pods_list = kubernetes.get_pods(gs)
  except collector_error.CollectorError as e:
    return flask.jsonify(utilities.make_error(str(e)))

  return flask.jsonify(utilities.make_response(pods_list, 'resources'))


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


@app.route('/elapsed', methods=['GET'])
def get_elapsed():
  """Computes the response of the '/elapsed' endpoint.

  Returns:
  A successful response containing the list of elapsed time records of the
  most recent Kubernetes API invocations since the previous call to the
  '/elapsed' endpoint. Never returns more than constants.MAX_ELAPSED_QUEUE_SIZE
  elapsed time records.
  """
  gs = app.context_graph_global_state
  result = return_elapsed(gs)
  return flask.jsonify(utilities.make_response(result, 'elapsed'))


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
  args = parser.parse_args()

  g_state = global_state.GlobalState()
  g_state.init_caches_and_synchronization()
  app.context_graph_global_state = g_state

  app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
  main()
