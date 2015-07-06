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


"""Runs the cluster insight data collector in minion mode.

The minion data collector is a simple proxy with a cache for container data.
The cache is needed to avoid reading container information from the local
Docker daemon due to infrequent enormous containers. Such containers may
have more than 8MB of data, which may take up to a second to read from the
local Docker daemon. We found that all enormous containers are caused by the
ExecIDs attribute, which may contain more than 100,000 hex strings. We remove
this attribute to reduce the response time of the Cluster-Insight collector.

The containers cache is prefilled when the minion starts and it is refreshed
periodically every MAX_CONTAINER_AGE_SECONDS seconds, so all accesses to
container information will hit the cache.
"""

import argparse
import json
import logging
import re
import sys
import threading
import time
import types

import flask
from flask_cors import CORS
import requests
import requests_unixsocket

import constants
import simple_cache
import utilities


app = flask.Flask(__name__)

# enable cross-origin resource sharing (CORS) HTTP headers on all routes
cors = CORS(app)

# Start unix socket session
session = requests_unixsocket.Session()

# Constant pointing to the url for the docker unix socket
LOCAL_DOCKER_HOST = 'http+unix://%2Fvar%2Frun%2Fdocker.sock'

# Replace the value of this attribute with a placeholder to reduce the
# size of the JSON response by a few MB.
OVERSIZE_ATTRIBUTE = 'ExecIDs'

# Maximal age of container information in seconds in the cache.
MAX_CONTAINER_AGE_SECONDS = 60 * 60  # an hour
MAX_CLEANUP_AGE_SECONDS = 10 * MAX_CONTAINER_AGE_SECONDS  # ten hours


def fetch(req):
  """Fetch the output of the specified request from the Docker's socket.

  Args:
    req: the request to be sent to the Docker daemon.

  Returns:
  The contents of the JSON response.

  Raises:
    IOError: the Unix domain socket returns a code other than OK (200).
  """
  assert utilities.valid_string(req)
  assert req[0] == '/'
  if app.proxy_is_testing_mode:
    fname = 'testdata/localhost' + re.sub(r'[^a-zA-Z0-9_.-]', '.', req)
    app.logger.info('reading req %s from %s', req, fname)
    f = open(fname, 'r')
    result = json.loads(f.read())
    f.close()
    return result

  r = session.get(
      '{docker_host}{url}'.format(docker_host=LOCAL_DOCKER_HOST, url=req))

  if r.status_code != requests.codes.ok:
    msg = 'Accessing %s API returns an error code %d' % (req, r.status_code)
    app.logger.error(msg)
    raise IOError(msg)

  else:
    return r.json()


def cleanup(result):
  """Removes the attribute OVERSIZE_ATTRIBUTE from 'result'."""
  value = utilities.get_attribute(result, [OVERSIZE_ATTRIBUTE])
  if isinstance(value, types.ListType) and value:
    result[OVERSIZE_ATTRIBUTE] = 'omitted list of %d elements' % len(value)


def get_response(req, cache=None):
  """Send request 'req' to the Docker unix socket and returns the response."""
  if cache:
    value, _ = cache.lookup(req)
    if value is not None:
      app.logger.info('cache hit for request=%s', req)
      return flask.make_response(
          value, requests.codes.ok, {'Content-Type': 'application/json'})

  try:
    result = fetch(req)
    cleanup(result)
    output = json.dumps(result)
    if cache:
      app.logger.info('caching result of request=%s', req)
      cache.update(req, output)

    return flask.make_response(
        output,
        requests.codes.ok,
        {'Content-Type': 'application/json'})

  except:
    exc_type, value, _ = sys.exc_info()
    msg = ('Failed to retrieve %s with exception %s: %s' %
           (req, exc_type, value))
    app.logger.error(msg)
    return flask.jsonify(utilities.make_error(msg))


def fill_cache(cache):
  """Fill the 'cache' with information about all containers in this host.

  This routine should be called on startup and periodically every
  MAX_CONTAINER_AGE_SECONDS seconds.

  fill_cache() cannot call get_response() because get_response() must be
  called only from a running Flask application.
  fill_cache() is called from the main program before starting the Flask
  application.

  This routine cannot call app.logger.xxx() because it is not running
  as part of the application. It may also run before the application is
  initialized.

  Args:
    cache: the containers cache.
  """
  assert cache is not None
  try:
    containers_list = fetch('/containers/json')

  except ValueError:
    app.logger.error('invalid response format from "/containers/json"')
    return

  except:
    exc_type, value, _ = sys.exc_info()
    msg = ('Failed to fetch /containers/json with exception %s: %s' %
           (exc_type, value))
    app.logger.error(msg)
    return

  if not isinstance(containers_list, types.ListType):
    app.logger.error('invalid response format from "/containers/json"')
    return

  for container_info in containers_list:
    # skip the leading / in the "Name" attribute of the container information.
    if not (isinstance(container_info.get('Names'), types.ListType) and
            container_info['Names'] and
            utilities.valid_string(container_info['Names'][0]) and
            container_info['Names'][0][0] == '/'):
      app.logger.error('invalid containers data format')
      return

    container_id = container_info['Names'][0][1:]
    req = '/containers/{cid}/json'.format(cid=container_id)
    try:
      result = fetch(req)
      cleanup(result)
      cache.update(req, json.dumps(result))
      app.logger.info('caching result of request=%s', req)

    except:
      exc_type, value, _ = sys.exc_info()
      msg = ('Failed to fetch %s with exception %s: %s' %
             (req, exc_type, value))
      app.logger.error(msg)


def worker(cache):
  """A periodic worker task that refreshes the containers cache."""
  assert cache is not None

  while True:
    fill_cache(cache)
    time.sleep(MAX_CONTAINER_AGE_SECONDS)


# Support the following calls and nothing else:
# 1. /containers/{container_id}/json
# 2. /containers/json
# 3. /containers/{container_id}/top?ps_args=aux
# 4. /images/{image_id}/json
# 5. /version


@app.route('/containers/json', methods=['GET'])
def get_all_containers():
  return get_response('/containers/json')


@app.route('/containers/<container_id>/json', methods=['GET'])
def get_one_container(container_id):
  return get_response('/containers/{cid}/json'.format(cid=container_id),
                      app.proxy_containers_cache)


@app.route('/images/<image_id>/json', methods=['GET'])
def get_one_image(image_id):
  return get_response('/images/{iid}/json'.format(iid=image_id))


@app.route('/containers/<container_id>/top', methods=['GET'])
def get_one_container_processes(container_id):
  qargs = flask.request.args.to_dict() if flask.request.args else {}
  if len(qargs) != 1 or qargs.get('ps_args') != 'aux':
    return flask.jsonify(utilities.make_error(
        'For /container/{container_id}/top, the sole mandatory arg is '
        'ps_args=aux. %s is not allowed' % (qargs)))

  return get_response(
      '/containers/{cid}/top?ps_args=aux'.format(cid=container_id))


@app.route('/version', methods=['GET'])
def get_version():
  return flask.make_response(
      '{"version": "unknown for now"}',
      requests.codes.ok, {'Content-Type': 'application/json'})


# Starts the web server and listen on all external IPs associated with this
# host.
def main():
  parser = argparse.ArgumentParser(
      description='Cluster-Insight docker data collector')
  parser.add_argument('-d', '--debug', action='store_true',
                      help='enable debug mode')
  parser.add_argument('--docker_port', action='store', type=int,
                      default=constants.DOCKER_PORT,
                      help=('Docker port number [default=%d]' %
                            constants.DOCKER_PORT))

  args = parser.parse_args()
  app.logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
  app.proxy_containers_cache = simple_cache.SimpleCache(
      MAX_CONTAINER_AGE_SECONDS, MAX_CLEANUP_AGE_SECONDS)
  app.proxy_is_testing_mode = False
  t = threading.Thread(target=worker, args=(app.proxy_containers_cache,))
  t.daemon = True
  t.start()
  app.run(host='0.0.0.0', port=args.docker_port, debug=args.debug)


if __name__ == '__main__':
  main()
