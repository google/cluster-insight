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


import argparse
import datetime
import flask
from flask_cors import CORS
import json
import logging
import requests_unixsocket
import sys
import types

import constants

app = flask.Flask(__name__)
logger = logging.getLogger(__name__)


# enable cross-origin resource sharing (CORS) HTTP headers on all routes
cors = CORS(app)

# Start unix socket session
session = requests_unixsocket.Session()

# Constant pointing to the url for the docker unix socket
LOCAL_DOCKER_HOST= 'http+unix://%2Fvar%2Frun%2Fdocker.sock'


def make_error(error_message):
  """Returns a JSON response indicating an error."""
  assert isinstance(error_message, types.StringTypes) and error_message
  result = {
      'success': False,
      'timestamp': datetime.datetime.now().isoformat(),
      'error_message': error_message
  }
  return result


def get_response(api):
  """This method passes the API call to the docker unix host, 
  and returns the json response."""
  logger.info('Getting response for API: %s', api)
  try:
    r = session.get('{docker_host}{url}'.format(
  	  docker_host=LOCAL_DOCKER_HOST, url=api))
    if r.status_code != 200:
      logger.info('%d', r.status_code)
      raise Exception('Error accessing %s API', api)

    else:
      return flask.make_response(json.dumps(r.json()), 
		      r.status_code, 
  		      {'Content-Type': 'application/json'})
  except Exception as e:
    logger.error(e, exc_info=True)
    exc_type, value, _ = sys.exc_info()
    return flask.jsonify(make_error(
	    'Failed to retrieve %s with exception %s: %s' 
	    % (api, exc_type, value)))



# Calls to support 
# 1. /containers/{container_id}/json
# 2. /containers/json
# 3. /containers/{container_id}/top?ps_args=aux
# 4. /containers/{image_id}/json

@app.route('/containers/json', methods=['GET'])
def get_all_containers():
  return get_response('/containers/json')

@app.route('/containers/<container_id>/json', methods=['GET'])
def get_one_container(container_id):
  return get_response('/containers/{cid}/json'.format(cid=container_id))

@app.route('/containers/<image_id>/json', methods=['GET'])
def get_one_image(image_id):
  return get_response('/containers/{iid}/json'.format(iid=image_id))

@app.route('/containers/<container_id>/top', methods=['GET'])
def get_one_container_processes(container_id):
  qargs = flask.request.args.to_dict() if flask.request.args else {}
  if qargs.get('ps_args') != 'aux' or len(qargs.keys()) > 1:
    return flask.jsonify(make_error(
	    'For /container/{container_id}/top, the only allowed arg is ps_args=aux.'
	    '%s is not allowed' % (qargs)))

  return get_response('/containers/{cid}/top?ps_args=aux'.format(cid=container_id))


# Starts the web server and listen on all external IPs associated with this
# host.
def main():
  parser = argparse.ArgumentParser(description='Cluster-Insight docker data collector')
  parser.add_argument('-d', '--debug', action='store_true',
                      help='enable debug mode')
  parser.add_argument('--docker_port', action='store', type=int,
                      default=constants.DOCKER_PORT,
                      help=('Docker port number [default=%d]' %
                            constants.DOCKER_PORT))

  args = parser.parse_args()
  app.logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
  app.run(host='0.0.0.0', port=args.docker_port, debug=args.debug)


if __name__ == '__main__':
  main()
