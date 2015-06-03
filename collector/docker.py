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

Assumes the Docker daemon's remote API is enabled on port
global_state.get_docker_port() on the Docker host in the master and
minion nodes.
"""

import json
import re
import sys
import time
import types

import requests

# local imports
import collector_error
import global_state
import kubernetes
import metrics
import utilities

## Docker APIs


# No decorator for this function signature.
def fetch_data(gs, url, base_name, expect_missing=False):
  """Fetch the named URL from Kubernetes (in production) or a file (in a test).

  The input is always JSON. It is converted to an internal representation
  by this routine.

  Args:
    gs: global state.
    url: the URL to fetch the data from when running in production.
    base_name: fetch the data from the file
      'testdata/' + base_name + '.input.json'
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
  assert isinstance(gs, global_state.GlobalState)
  assert isinstance(url, types.StringTypes)
  assert isinstance(base_name, types.StringTypes)
  if gs.get_testing():
    # Read the data from a file.
    fname = 'testdata/' + base_name + '.input.json'
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
        gs.logger_exception(msg)
        raise collector_error.CollectorError(msg)
    except:
      msg = 'reading %s failed with exception %s' % (fname, sys.exc_info()[0])
      gs.logger_exception(msg)
      raise collector_error.CollectorError(msg)
  else:
    # Send the request to Kubernetes
    return requests.get(url).json()


@utilities.global_state_two_string_args
def _inspect_container(gs, docker_host, container_id):
  """Fetch detailed information about the given container in the given host.

  Args:
    gs: global state.
    docker_host: Docker host name. Must not be empty.
    container_id: container ID. Must not be empty.

  Returns:
    (container_information, timestamp_in_seconds) if the container was found.
    (None, None) if the container was not found.

  Raises:
    CollectorError in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  url = 'http://{docker_host}:{port}/containers/{container_id}/json'.format(
      docker_host=docker_host, port=gs.get_docker_port(),
      container_id=container_id)
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'container_id' is:
  # k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8
  # Use just the tail of the container ID after the last '_' sign.
  fname = '{host}-container-{id}'.format(
      host=docker_host.split('.')[0], id=container_id.split('_')[-1])
  try:
    result = fetch_data(gs, url, fname, expect_missing=True)
  except ValueError:
    # TODO(vasbala): this container does not exist anymore.
    # What should we do here?
    return (None, time.time())
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  # Sort the "Env" attribute because it tends to contain elements in
  # a different order each time you fetch the container information.
  if isinstance(utilities.get_attribute(result, ['Config', 'Env']),
                types.ListType):
    # Sort the contents of the 'Env' list in place.
    result['Config']['Env'].sort()

  return (result, time.time())


@utilities.global_state_string_args
def get_containers(gs, docker_host):
  """Gets the list of all containers in 'docker_host'.

  Args:
    gs: global state.
    docker_host: the Docker host running the containers.

  Returns:
    list of wrapped container objects.
    Each element in the list is the result of
    utilities.wrap_object(container, 'Container', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  containers, timestamp = gs.get_containers_cache().lookup(docker_host)
  if timestamp is not None:
    gs.logger_info(
        'get_containers(docker_host=%s) cache hit returns '
        '%d containers', docker_host, len(containers))
    return containers

  url = 'http://{docker_host}:{port}/containers/json'.format(
      docker_host=docker_host, port=gs.get_docker_port())
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  fname = '{host}-containers'.format(host=docker_host.split('.')[0])
  try:
    containers_list = fetch_data(gs, url, fname)
  except collector_error.CollectorError:
    raise
  except:
    msg = ('fetching %s or %s failed with exception %s' %
           (url, fname, sys.exc_info()[0]))
    gs.logger_exception(msg)
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
    if not (isinstance(container_info.get('Names'), types.ListType) and
            container_info['Names'] and
            utilities.valid_string(container_info['Names'][0]) and
            container_info['Names'][0][0] == '/'):
      msg = 'invalid containers data format. docker_host=%s' % docker_host
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    container_id = container_info['Names'][0][1:]
    container, ts = _inspect_container(gs, docker_host, container_id)
    if container is None:
      continue

    if not utilities.valid_string(container.get('Name')):
      msg = ('missing or invalid Name attribute in container %s' %
             container_id)
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    if container['Name'] != ('/' + container_id):
      msg = ('container %s\'s Name attribute is "%s"; expecting "%s"' %
             (container_id, container['Name'], '/' + container_id))
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    short_hex_id = utilities.object_to_hex_id(container)
    if short_hex_id is None:
      msg = 'Could not compute short hex ID of container %s' % container_id
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    wrapped_container = utilities.wrap_object(
        container, 'Container', container_id, ts, label=short_hex_id)
    containers.append(wrapped_container)
    timestamps.append(ts)

    # Modify the container's label after the wrapped container was added
    # to the containers list.
    # Compute the container's short name to create a better container label:
    # short_container_name/short_hex_id.
    # For example: "cassandra/d85b599c17d8".
    parent_pod_id = utilities.get_parent_pod_id(wrapped_container)
    if parent_pod_id is None:
      continue
    parent_pod = kubernetes.get_one_pod(gs, docker_host, parent_pod_id)
    if parent_pod is None:
      continue
    short_container_name = utilities.get_short_container_name(
        wrapped_container, parent_pod)
    if not utilities.valid_string(short_container_name):
      continue
    wrapped_container['annotations']['label'] = (short_container_name + '/' +
                                                 short_hex_id)

  ret_value = gs.get_containers_cache().update(
      docker_host, containers,
      min(timestamps) if timestamps else time.time())
  gs.logger_info(
      'get_containers(docker_host=%s) returns %d containers',
      docker_host, len(containers))
  return ret_value


@utilities.global_state_string_args
def get_containers_with_metrics(gs, docker_host):
  """Gets the list of all containers in 'docker_host' with metric annotations.

  Args:
    gs: global state.
    docker_host: the Docker host running the containers.

  Returns:
    list of wrapped container objects.
    Each element in the list is the result of
    utilities.wrap_object(container, 'Container', ...)

  Raises:
    CollectorError: in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  # Create a lookup table from pod IDs to pods.
  # This lookup table is needed when annotating containers with
  # metrics. Also compute the project's name.
  containers_list = get_containers(gs, docker_host)
  if not containers_list:
    return []

  pod_id_to_pod = {}
  project_id = '_unknown_'

  # Populate the pod ID to pod lookup table.
  # Compute the project_id from the name of the first pod.
  for pod in kubernetes.get_pods(gs, docker_host):
    assert utilities.is_wrapped_object(pod, 'Pod')
    pod_id_to_pod[pod['id']] = pod
    if project_id != '_unknown_':
      continue
    pod_hostname = utilities.get_attribute(
        pod, ['properties', 'spec', 'host'])
    if utilities.valid_string(pod_hostname):
      project_id = utilities.node_id_to_project_id(pod_hostname)

  # We know that there are containers in this docker_host.
  if not pod_id_to_pod:
    # there are no pods in this docker_host.
    msg = 'Docker host %s has containers but no pods' % docker_host
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  # Annotate the containers with their metrics.
  for container in containers_list:
    assert utilities.is_wrapped_object(container, 'Container')

    parent_pod_id = utilities.get_parent_pod_id(container)
    if not utilities.valid_string(parent_pod_id):
      msg = ('missing or invalid parent pod ID in container %s' %
             container['id'])
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    if parent_pod_id not in pod_id_to_pod:
      msg = ('could not locate parent pod %s for container %s' %
             (parent_pod_id, container['id']))
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    # Note that the project ID may be '_unknown_'.
    # This is not a big deal, because the aggregator knows the project ID.
    metrics.annotate_container(
        project_id, container, pod_id_to_pod[parent_pod_id])

  return containers_list


@utilities.global_state_two_string_args
def get_one_container(gs, docker_host, container_id):
  """Gets the given container that runs in the given Docker host.

  Note that the 'container_id' is the value in container['id'].
  It is a symbolic name, such as:
  k8s_POD.cc4afd21_kibana-logging-controller-fn98y_default_06b28f3f-dd5a-11e4-8a61-42010af0c46c_a1a2515e
  This should not be confused with the Docker ID of the container, which
  is a long hexadecimal string. It is stored in container['properties']['Id'].

  Args:
    gs: global state.
    docker_host: the Docker host running the container. Must not be empty.
    container_id: the container ID (in the wrapped object). Must not be empty.

  Returns:
  The wrapped container object if it was found.
  The wrapped container object is the result of
  utilities.wrap_object(container, 'Container', ...)
  None is the container is not found.

  Raises:
  Passes through all exceptions from lower-level routines.
  May raise exceptions due to run-time errors.
  """
  for container in get_containers(gs, docker_host):
    if container['id'] == container_id:
      return container

  return None


@utilities.global_state_string_args
def invalid_processes(gs, url):
  """Raise the CollectorError exception because the response is invalid.

  Args:
    gs: global state.
    url: the source of the invalid data is this URL.

  Raises:
    CollectorError: always raises this exception.
  """
  msg = 'process information from URL %s is invalid' % url
  gs.logger_error(msg)
  raise collector_error.CollectorError(msg)


@utilities.global_state_two_string_args
def get_processes(gs, docker_host, container_id):
  """Gets the list of all processes in the 'docker_host' and 'container_id'.

  If the container is not found, returns an empty list of processes.

  Args:
    gs: global state.
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
  processes, timestamp_secs = gs.get_processes_cache().lookup(
      processes_label)
  if timestamp_secs is not None:
    gs.logger_info(
        'get_processes(docker_host=%s, container_id=%s) cache hit',
        docker_host, container_id)
    return processes

  container = get_one_container(gs, docker_host, container_id)
  if container is not None:
    assert utilities.is_wrapped_object(container, 'Container')
    container_short_hex_id = utilities.object_to_hex_id(container['properties'])
    assert utilities.valid_string(container_short_hex_id)
  else:
    # Parent container not found. Container might have crashed while we were
    # looking for it.
    return []

  # NOTE: there is no trailing /json in this URL - this looks like a bug in the
  # Docker API
  url = ('http://{docker_host}:{port}/containers/{container_id}/top?'
         'ps_args=aux'.format(docker_host=docker_host,
                              port=gs.get_docker_port(),
                              container_id=container_id))
  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'container_id' is:
  # k8s_php-redis.b317029a_guestbook-controller-ls6k1.default.api_f991d53e-b949-11e4-8246-42010af0c3dd_8dcdfec8
  # Use just the tail of the container ID after the last '_' sign.
  fname = '{host}-processes-{id}'.format(
      host=docker_host.split('.')[0], id=container_id.split('_')[-1])

  try:
    # TODO(vasbala): what should we do in cases where the container is gone
    # (and replaced by a different one)?
    result = fetch_data(gs, url, fname, expect_missing=True)
  except ValueError:
     # this container does not exist anymore
    return []
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  if not isinstance(utilities.get_attribute(result, ['Titles']),
                    types.ListType):
    invalid_processes(gs, url)
  if not isinstance(utilities.get_attribute(result, ['Processes']),
                    types.ListType):
    invalid_processes(gs, url)

  pstats = result['Titles']
  processes = []
  now = time.time()
  for pvalues in result['Processes']:
    process = {}
    if not isinstance(pvalues, types.ListType):
      invalid_processes(gs, url)
    if len(pstats) != len(pvalues):
      invalid_processes(gs, url)
    for pstat, pvalue in zip(pstats, pvalues):
      process[pstat] = pvalue

    # Prefix with container Id to ensure uniqueness across the whole graph.
    process_id = '%s/%s' % (container_short_hex_id, process['PID'])
    processes.append(utilities.wrap_object(
        process, 'Process', process_id, now, label=process['PID']))

  ret_value = gs.get_processes_cache().update(
      processes_label, processes, now)
  gs.logger_info(
      'get_processes(docker_host=%s, container_id=%s) returns %d processes',
      docker_host, container_id, len(processes))
  return ret_value


@utilities.global_state_two_string_args
def get_image(gs, docker_host, image_id):
  """Gets the information of the given image in the given host.

  Args:
    gs: global state.
    docker_host: Docker host name. Must not be empty.
    image_id: Image ID. Must not be empty. Must be a symbolic name of the image
      (not a long hexadecimal string).

  Returns:
    If image was found, returns the wrapped image object, which is the result of
    utilities.wrap_object(image, 'Image', ...)
    If the image was not found, returns None.

  Raises:
    CollectorError: in case of failure to fetch data from Docker.
    Other exceptions may be raised due to exectution errors.
  """
  # 'image_id' should be a symbolic name and not a very long hexadecimal string.
  assert not utilities.valid_hex_id(image_id)
  cache_key = '%s|%s' % (docker_host, image_id)
  image, timestamp_secs = gs.get_images_cache().lookup(cache_key)
  if timestamp_secs is not None:
    gs.logger_info('get_image(docker_host=%s, image_id=%s) cache hit',
                   docker_host, image_id)
    return image

  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'image_id' is:
  # brendanburns/php-redis
  # We convert embedded '/' and ':' characters to '-' to avoid interference with
  # the directory structure or file system.
  url = 'http://{docker_host}:{port}/images/{image_id}/json'.format(
      docker_host=docker_host, port=gs.get_docker_port(), image_id=image_id)
  fname = '{host}-image-{id}'.format(
      host=docker_host.split('.')[0],
      id=image_id.replace('/', '-').replace(':', '-'))

  try:
    image = fetch_data(gs, url, fname, expect_missing=True)
  except ValueError:
    # image not found.
    return None
  except collector_error.CollectorError:
    raise
  except:
    msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  now = time.time()
  # compute the two labels of the image.
  # The first is a 12-digit hexadecimal number shown by "docker images".
  # The second is the symbolic name of the image.
  full_hex_label = image.get('Id')
  if not (isinstance(full_hex_label, types.StringTypes) and full_hex_label):
    msg = 'Image id=%s has an invalid "Id" attribute value' % image_id
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  short_hex_label = utilities.object_to_hex_id(image)
  if short_hex_label is None:
    msg = 'Could not compute short hex ID of image %s' % image_id
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  image_name_label = image_id

  wrapped_image = utilities.wrap_object(
      image, 'Image', full_hex_label, now,
      label=short_hex_label, alt_label=image_name_label)

  ret_value = gs.get_images_cache().update(cache_key, wrapped_image, now)
  gs.logger_info('get_image(docker_host=%s, image_id=%s)',
                 docker_host, image_id)
  return ret_value


@utilities.global_state_string_args
def get_images(gs, docker_host):
  """Gets the list of all images in 'docker_host'.

  Args:
    gs: global state.
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
  images_list = []
  image_id_set = set()

  # All containers in this 'docker_host'.
  for container in get_containers(gs, docker_host):
    # Image from which this Container was created
    image_id = utilities.get_attribute(
        container, ['properties', 'Config', 'Image'])
    if not utilities.valid_string(image_id):
      # Image ID not found
      continue

    image = get_image(gs, docker_host, image_id)
    if (image is not None) and (image['id'] not in image_id_set):
      images_list.append(image)
      image_id_set.add(image['id'])

  gs.logger_info('get_images(docker_host=%s) returns %d images',
                 docker_host, len(images_list))
  return images_list


@utilities.global_state_arg
def get_version(gs):
  """Returns a human-readable information of the currently running image.

  Args:
    gs: global state.

  Returns:
  A string of the form:
  <symbolic container name> <container hex ID> <creation date and time>

  Raises:
    CollectorError: in case of any error to compute the running image
      information.
  """
  #TODO(EranGabber): Edit this code to get the version from one of the minions.
  # Return unknown for now, so we don't have to access the docker API on master.
  return '_unknown_'
  
  """
  version, timestamp_secs = gs.get_version_cache().lookup('')
  if timestamp_secs is not None:
    assert utilities.valid_string(version)
    gs.logger_info('get_version() cache hit')
    return version

  if gs.get_testing():
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
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)
  except:
    msg = 'reading %s failed with exception %s' % (fname, sys.exc_info()[0])
    gs.logger_exception(msg)
    raise collector_error.CollectorError(msg)

  # The file must contain an entry for 'cpu:/docker/...'.
  m = re.search(r'\b[0-9]+:cpu:/docker/([0-9a-fA-F]+)\b', cgroup)
  if not m:
    msg = 'could not find an entry for "cpu:/docker/..." in %s' % fname
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  hex_container_id = m.group(1)
  # inspect the running container.
  url = 'http://localhost:{port}/containers/{container_id}/json'.format(
      port=gs.get_docker_port(), container_id=hex_container_id)
  container = fetch_data(gs, url, 'container-' + hex_container_id[:12])

  # Fetch the image symbolic name and hex ID from the container information.
  symbolic_image_id = utilities.get_attribute(container, ['Config', 'Image'])
  hex_image_id = utilities.get_attribute(container, ['Image'])

  # Verify the image symbolic name and the image hex ID.
  if not (utilities.valid_string(symbolic_image_id) and
          not utilities.valid_hex_id(symbolic_image_id) and
          utilities.valid_hex_id(hex_image_id)):
    msg = 'could not find or invalid image information in container %s' % url
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  # Fetch image information.
  url = 'http://localhost:{port}/images/{image_id}/json'.format(
      port=gs.get_docker_port(), image_id=hex_image_id)
  image = fetch_data(gs, url, 'image-' + hex_image_id[:12])

  # Fetch the image creation timestamp.
  created = utilities.get_attribute(image, ['Created'])
  if not utilities.valid_string(created):
    msg = 'could not find image creation timestamp in %s' % url
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  # Remove the trailing subsecond part of the creation timestamp.
  created = re.sub(r'\.[0-9]+Z$', '', created)

  version = '%s %s %s' % (symbolic_image_id, hex_image_id[:12], created)
  ret_value = gs.get_version_cache().update('', version)
  gs.logger_info('get_version() returns: %s', ret_value)
  return ret_value
  """
