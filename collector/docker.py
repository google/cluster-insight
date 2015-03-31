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


"""Collects context metadata from Docker.

Assumes the Docker daemon's remote API is enabled on port 4243 on the Docker
host.
"""

import json
import re
import sys
import time
import types

from flask import current_app
import requests

# local imports
import collector_error
import kubernetes
import utilities

## Docker APIs


# No decorator for this function signature.
def fetch_data(url, base_name, expect_missing=False):
  """Fetch the named URL from Kubernetes (in production) or a file (in a test).

  The production/test mode is determined by the existence of the
  attribute 'TESTING' in 'current_app.config'.

  The input is always JSON. It is converted to an internal representation
  by this routine.

  Args:
    url: the URL to fetch the data from when running in production.
    base_name: fetch the data from the file 'testdata/' + base_name + '.json'
      when running in test mode.
    expect_missing: if True, then do not die in test mode when the test file
      is missing. Just raise ValueError. If False and the test file is not
      found in test mode, raise CollectorError.

  Returns:
  The data after converting it from JSON.

  Raises:
  ValueError: when 'expect_missing' is True and failed to open the file.
  CollectorError: if any other exception occured or 'expect_missing' is False.
  other exceptions which may be raised by fetching the URL in production mode.
  """
  assert isinstance(url, types.StringTypes)
  assert isinstance(base_name, types.StringTypes)
  if current_app.config.get('TESTING'):
    # Read the data from a file.
    fname = 'testdata/' + base_name + '.json'
    try:
      f = open(fname, 'r')
      v = json.loads(f.read())
      f.close()
      return v
    except IOError:
      # File not found
      if expect_missing:
        raise ValueError
      else:
        msg = 'failed to read %s' % fname
        current_app.logger.exception(msg)
        raise collector_error.CollectorError(msg)
    except:
      msg = 'reading %s failed with exception %s' % (fname, sys.exc_info()[0])
      current_app.logger.exception(msg)
      raise collector_error.CollectorError(msg)
  else:
    # Send the request to Kubernetes
    return requests.get(url).json()


@utilities.two_string_args
def _inspect_container(docker_host, container_id):
  """Fetch detailed information about the given container in the given host.

  Args:
    docker_host: Docker host name. Must not be empty.
    container_id: container ID. Must not be empty.

  Returns:
    (container_information, timestamp_in_seconds) if the container was found.
    (None, None) if the container was not found.

  Raises:
    CollectorError in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  url = 'http://{docker_host}:4243/containers/{container_id}/json'.format(
      docker_host=docker_host, container_id=container_id)
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'container_id' is:
  # k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8
  # Use just the tail of the container ID after the last '-' sign.
  fname = '{host}-container-{id}'.format(
      host=docker_host.split('.')[0], id=container_id.split('-')[-1])
  try:
    result = fetch_data(url, fname, expect_missing=True)
  except ValueError:
    # TODO(vasbala): this container does not exist anymore.
    # What should we do here?
    return (None, time.time())
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  # Sort the "Env" attribute because it tends to contain elements in
  # a different order each time you fetch the container information.
  if isinstance(utilities.get_attribute(result, ['Config', 'Env']),
                types.ListType):
    # Sort the contents of the 'Env' list in place.
    result['Config']['Env'].sort()

  return (result, time.time())


@utilities.one_string_one_optional_string_args
def get_containers(docker_host, pod_id=None):
  """Gets the list of all containers in the 'docker_host' and 'pod_id'.

  An undedined 'pod_id' indicates getting the containers in all pods of
  this 'docker_host'.

  Args:
    docker_host: the Docker host running the containers.
    pod_id: The pod running the containers. If None, then fetch pods from all
      pods in thos Docker host.

  Returns:
    list of wrapped container objects.
    Each element in the list is the result of
    utilities.wrap_object(container, 'Container', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  if pod_id is None:
    containers_label = docker_host
  else:
    containers_label = '%s/%s' % (docker_host, pod_id)

  containers, timestamp = current_app.context_graph_containers_cache.lookup(
      containers_label)
  if timestamp is not None:
    current_app.logger.info(
        'get_containers(docker_host=%s, pod_id=%s) cache hit returns '
        '%d containers', docker_host, pod_id, len(containers))
    return containers

  url = 'http://{docker_host}:4243/containers/json'.format(
      docker_host=docker_host)
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  fname = '{host}-containers'.format(host=docker_host.split('.')[0])
  try:
    containers_list = fetch_data(url, fname)
  except collector_error.CollectorError:
    raise
  except:
    msg = ('fetching %s or %s failed with exception %s' %
           (url, fname, sys.exc_info()[0]))
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  containers = []
  timestamps = []
  for container_info in containers_list:
    # NOTE: container 'Name' is stable across container re-starts whereas
    # container 'Id' is not.
    # This may be because Kubernertes assigns the Name while Docker assigns
    # the Id (?)
    # The container Name is the only element of the array 'Names' -
    # why is Names an array here?
    # skip the leading / in the Name
    if not isinstance(container_info.get('Names'), types.ListType):
      msg = 'invalid containers data format. docker_host=%s' % docker_host
      current_app.logger.exception(msg)
      raise collector_error.CollectorError(msg)

    assert container_info['Names'][0][0] == '/'
    container_id = container_info['Names'][0][1:]
    container, ts = _inspect_container(docker_host, container_id)
    if container is None:
      continue
    if container['Name'] != ('/' + container_id):
      msg = ('container %s\'s Name attribute is %s; expecting %s' %
             (container_id, container['Name'], '/' + container_id))
      current_app.logger.exception(msg)
      raise collector_error.CollectorError(msg)

    container_label = utilities.object_to_hex_id(container)
    wrapped_container = utilities.wrap_object(
        container, 'Container', container_id, ts, label=container_label)
    if pod_id:
      # container['Config']['Hostname'] is the name of the pod (not the host).
      if pod_id == container['Config']['Hostname']:
        containers.append(wrapped_container)
        timestamps.append(ts)
    else:
      containers.append(wrapped_container)
      timestamps.append(ts)

  ret_value = current_app.context_graph_containers_cache.update(
      containers_label, containers,
      min(timestamps) if timestamps else time.time())
  current_app.logger.info(
      'get_containers(docker_host=%s, pod_id=%s) returns %d containers',
      docker_host, pod_id, len(containers))
  return ret_value


@utilities.two_string_args
def get_one_container(docker_host, container_id):
  """Gets the given container that runs in the given Docker host.

  Args:
    docker_host: the Docker host running the container. Must not be empty.
    container_id: the container ID. Must not be empty.

  Returns:
  The wrapped container object if it was found.
  The wrapped container object is the result of
  utilities.wrap_object(container, 'Container', ...)
  None is the container is not found.

  Raises:
  Passes through all exceptions from lower-level routines.
  May raise exceptions due to run-time errors.
  """
  for container in get_containers(docker_host):
    if container['id'] == container_id:
      return container

  return None


@utilities.two_string_args
def invalid_processes(url):
  """Raise the CollectorError exception because the response is invalid.

  Args:
    url: the source of the invalid data is this URL.

  Raises:
    CollectorError: always raises this exception.
  """
  msg = 'process information from URL %s is invalid' % url
  current_app.logger.exception(msg)
  raise collector_error.CollectorError(msg)


@utilities.two_string_args
def get_processes(docker_host, container_id):
  """Gets the list of all processes in the 'docker_host' and 'container_id'.

  If the container is not found, returns an empty list of processes.

  Args:
    docker_host: the Docker host running the container.
    container_id: the container running the processes.

  Returns:
    list of wrapped process objects.
    Each element in the list is the result of
    utilities.wrap_object(process, 'Process', ...)

  Raises:
    CollectorError in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  processes_label = '%s/%s' % (docker_host, container_id)
  processes, timestamp_secs = current_app.context_graph_processes_cache.lookup(
      processes_label)
  if timestamp_secs is not None:
    current_app.logger.info(
        'get_processes(docker_host=%s, container_id=%s) cache hit',
        docker_host, container_id)
    return processes

  container = get_one_container(docker_host, container_id)
  if container is not None:
    container_label = container['annotations']['label']
  else:
    # Parent container not found. Container might have crashed while we were
    # looking for it.
    return []

  # NOTE: there is no trailing /json in this URL - this looks like a bug in the
  # Docker API
  url = ('http://{docker_host}:4243/containers/{container_id}/top?'
         'ps_args=aux'.format(docker_host=docker_host,
                              container_id=container_id))
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'container_id' is:
  # k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8
  # Use just the tail of the container ID after the last '-' sign.
  fname = '{host}-processes-{id}'.format(
      host=docker_host.split('.')[0], id=container_id.split('-')[-1])

  try:
    # TODO(vasbala): what should we do in cases where the container is gone
    # (and replaced by a different one)?
    result = fetch_data(url, fname, expect_missing=True)
  except ValueError:
     # this container does not exist anymore
    return []
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  if not isinstance(utilities.get_attribute(result, ['Titles']),
                    types.ListType):
    invalid_processes(url)
  if not isinstance(utilities.get_attribute(result, ['Processes']),
                    types.ListType):
    invalid_processes(url)

  pstats = result['Titles']
  processes = []
  now = time.time()
  for pvalues in result['Processes']:
    process = {}
    if not isinstance(pvalues, types.ListType):
      invalid_processes(url)
    if len(pstats) != len(pvalues):
      invalid_processes(url)
    for pstat, pvalue in zip(pstats, pvalues):
      process[pstat] = pvalue

    # Prefix with container Id to ensure uniqueness across the whole graph.
    process_id = '%s/%s' % (container_label, process['PID'])
    processes.append(utilities.wrap_object(
        process, 'Process', process_id, now, label=process['PID']))

  ret_value = current_app.context_graph_processes_cache.update(
      processes_label, processes, now)
  current_app.logger.info(
      'get_processes(docker_host=%s, container_id=%s) returns %d processes',
      docker_host, container_id, len(processes))
  return ret_value


@utilities.two_string_args
def get_image(docker_host, image_id):
  """Gets the information of the given image in the given host.

  Args:
    docker_host: Docker host name. Must not be empty.
    image_id: Image ID. Must not be empty. Must be a symbolic name of the image
      (not a long hexadecimal string).

  Returns:
    If image was found, returns the wrapped image object, which is the result of
    utilities.wrap_object(image, 'Image', ...)
    If the image was not found, returns None.

  Raises:
    CollectorError in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  # 'image_id' should be a symbolic name and not a very long hexadecimal string.
  assert not utilities.valid_hex_id(image_id)
  cache_key = '%s|%s' % (docker_host, image_id)
  image, timestamp_secs = current_app.context_graph_images_cache.lookup(
      cache_key)
  if timestamp_secs is not None:
    current_app.logger.info('get_image(docker_host=%s, image_id=%s) cache hit',
                            docker_host, image_id)
    return image

  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'image_id' is:
  # brendanburns/php-redis
  # We convert embedded '/' and ':' characters to '-' to avoid interference with
  # the directory structure or file system.
  url = 'http://{docker_host}:4243/images/{image_id}/json'.format(
      docker_host=docker_host, image_id=image_id)
  fname = '{host}-image-{id}'.format(
      host=docker_host.split('.')[0],
      id=image_id.replace('/', '-').replace(':', '-'))

  try:
    image = fetch_data(url, fname, expect_missing=True)
  except ValueError:
    # image not found.
    return None
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  # compute the two labels of the image.
  # The first is a 12-digit hexadecimal number shown by "docker images".
  # The second is the symbolic name of the image.
  image_hex_label = utilities.object_to_hex_id(image)
  image_name_label = image_id

  wrapped_image = utilities.wrap_object(
      image, 'Image', '%s/%s' % (docker_host, image_hex_label), now,
      label=image_hex_label, alt_label=image_name_label)

  ret_value = current_app.context_graph_images_cache.update(
      cache_key, wrapped_image, now)
  current_app.logger.info('get_image(docker_host=%s, image_id=%s)',
                          docker_host, image_id)
  return ret_value


@utilities.one_string_arg
def get_images(docker_host):
  """Gets the list of all images in 'docker_host'.

  Args:
    docker_host: Docker host name. Must not be empty.

  Returns:
    list of wrapped image objects.
    Each element in the list is the result of
    utilities.wrap_object(image, 'Image', ...)

  Raises:
    CollectorError in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  # The images are already cached by get_image(), so there is no need to
  # check the cache on entry to this method.

  # docker_host is the same as node_id
  images = []
  for pod in kubernetes.get_pods(docker_host):
    pod_id = pod['id']
    assert pod['properties']['currentState']['host'] == docker_host

    # Containers in a Pod
    for container in get_containers(docker_host, pod_id):
      # Image from which this Container was created
      if (('properties' not in container) or
          ('Config' not in container['properties']) or
          ('Image' not in container['properties']['Config'])):
        # Image ID not found
        continue

      image_id = container['properties']['Config']['Image']
      image = get_image(docker_host, image_id)
      if image is not None:
        images.append(image)

  current_app.logger.info('get_images(docker_host=%s) returns %d images',
                          docker_host, len(images))
  return images


def get_version():
  """Returns a human-readable information of the currently running image.

  Returns:
  A string of the form:
  <symbolic container name> <container hex ID> <creation date and time>

  Raises:
    CollectorError: in case of any error to compute the running image information.
  """
  if current_app.config.get('TESTING'):
    fname = 'testdata/proc-self-cgroup.txt'
  else:
    fname = '/proc/self/cgroup'

  try:
    f = open(fname, 'r')
    cgroup = f.read()
    f.close()
  except IOError:
    # file not found
    msg = 'failed to open or read %s' % fname
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)
  except:
    msg = 'reading %s failed with exception %s' % (fname, sys.exc_info()[0])
    current_app.logger.exception(msg)
    raise collector_error.CollectorError(msg)

  # The file must contain an entry for 'cpu:/docker/...'.
  m = re.search(r'\b[0-9]+:cpu:/docker/([0-9a-fA-F]+)\b', cgroup)
  if not m:
    msg = 'could not find an entry for "cpu:/docker/..." in %s' % fname
    current_app.logger.error(msg)
    raise collector_error.CollectorError(msg)

  hex_container_id = m.group(1)
  # inspect the running container.
  url = 'http://localhost:4243/containers/' + hex_container_id + '/json'
  container = fetch_data(url, 'container-' + hex_container_id[:12])

  # Fetch the image symbolic name and hex ID from the container information.
  symbolic_image_id = utilities.get_attribute(container, ['Config', 'Image'])
  hex_image_id = utilities.get_attribute(container, ['Image'])

  # Verify the image symbolic name and the image hex ID.
  if not (utilities.valid_string(symbolic_image_id) and
          not utilities.valid_hex_id(symbolic_image_id) and
          utilities.valid_hex_id(hex_image_id)):
    msg = 'could not find or invalid image information in container %s' % url
    current_app.logger.error(msg)
    raise collector_error.CollectorError(msg)

  # Fetch image information.
  url = 'http://localhost:4243/images/' + hex_image_id + '/json'
  image = fetch_data(url, 'image-' + hex_image_id[:12])

  # Fetch the image creation timestamp.
  created = utilities.get_attribute(image, ['Created'])
  if not utilities.valid_string(created):
    msg = 'could not find image creation timestamp in %s' % url
    current_app.logger.error(msg)
    raise collector_error.CollectorError(msg)

  # Remove the trailing subsecond part of the creation timestamp.
  created = re.sub(r'\.[0-9]+Z$', '', created)

  ret_val = '%s %s %s' % (symbolic_image_id, hex_image_id[:12], created)
  current_app.logger.info('get_version() returns: %s', ret_val)
  return ret_val
