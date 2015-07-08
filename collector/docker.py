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
import os
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
  start_time = time.time()
  if gs.get_testing():
    # Read the data from a file.
    fname = 'testdata/' + base_name + '.input.json'
    try:
      f = open(fname, 'r')
      v = json.loads(f.read())
      f.close()
      gs.add_elapsed(start_time, fname, time.time() - start_time)
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
    v = requests.get(url).json()
    gs.add_elapsed(start_time, url, time.time() - start_time)
    return v


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
  fname = utilities.container_id_to_fname(
      docker_host, 'container', container_id)
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

  if not isinstance(result, types.DictType):
    msg = 'fetching %s returns invalid data' % url
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

  if not isinstance(containers_list, types.ListType):
    msg = 'invalid response from fetching %s' % url
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
      msg = ('missing or invalid "Name" attribute in container %s' %
             container_id)
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    if container['Name'] != ('/' + container_id):
      msg = ('container %s\'s Name attribute is "%s"; expecting "%s"' %
             (container_id, container['Name'], '/' + container_id))
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    # The 'container_id' is most often unique, because it contains long
    # unique hex numbers. However, in some cases the 'container_id' is simply
    # the image name, such as "cluster-insight". In this case 'container_id'
    # is not unique in the context graph, so we make it unique by appending
    # the a prefix of the Docker ID of the container.
    hex_id = utilities.object_to_hex_id(container)
    if hex_id is None:
      msg = 'Could not compute short hex ID of container %s' % container_id
      gs.logger_error(msg)
      raise collector_error.CollectorError(msg)

    if utilities.contains_long_hex_number(container_id):
      short_label = hex_id
      unique_id = container_id
    else:
      # The short label is descriptive when 'container_id' does not contain
      # long hex numbers.
      short_label = container_id
      unique_id = '{container_id}-{hex_id}'.format(
          container_id=container_id, hex_id=hex_id)

    wrapped_container = utilities.wrap_object(
        container, 'Container', unique_id, ts, label=short_label)
    containers.append(wrapped_container)
    timestamps.append(ts)

    # If the container's label does not contain long hex fields, it is
    # good enough. It should not be replaced with anything else.
    if not utilities.contains_long_hex_number(short_label):
      continue

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
                                                 hex_id)

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
        pod, ['properties', 'spec', 'nodeName'])
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
      metrics.annotate_container_error(container, msg)
      continue

    if parent_pod_id not in pod_id_to_pod:
      msg = ('could not locate parent pod %s for container %s' %
             (parent_pod_id, container['id']))
      metrics.annotate_container_error(container, msg)
      continue

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
  -or-
  cluster-insight-9c1e7820fd4c
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

  container_name = utilities.get_container_name(container)
  if not utilities.valid_string(container_name):
    msg = 'Invalid container "Name" attribute in container %s' % container_id
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  # NOTE: there is no trailing /json in this URL - this looks like a bug in the
  # Docker API
  # Note that the {container_id} in the URL must be the internal container
  # name in container['properties']['Name'][1:]
  # and not the container name in container['id'] which may contain an extra
  # suffix.
  url = ('http://{docker_host}:{port}/containers/{container_name}/top?'
         'ps_args=aux'.format(docker_host=docker_host,
                              port=gs.get_docker_port(),
                              container_name=container_name))
  fname = utilities.container_id_to_fname(
      docker_host, 'processes', container_name)

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


@utilities.global_state_string_dict_args
def get_image(gs, docker_host, container):
  """Gets the information of the given image in the given host.

  Args:
    gs: global state.
    docker_host: Docker host name. Must not be empty.
    container: the container which runs the image.

  Returns:
    If image was found, returns the wrapped image object, which is the result of
    utilities.wrap_object(image, 'Image', ...)
    If the image was not found, returns None.

  Raises:
    CollectorError: in case of failure to fetch data from Docker.
    ValueError: in case the container does not contain a valid image ID.
    Other exceptions may be raised due to exectution errors.
  """
  assert utilities.is_wrapped_object(container, 'Container')
  # The 'image_id' should be a long hexadecimal string.
  image_id = utilities.get_attribute(container, ['properties', 'Image'])
  if not utilities.valid_hex_id(image_id):
    msg = 'missing or invalid image ID in container ID=%s' % container['id']
    gs.logger_error(msg)
    raise ValueError(msg)

  # The 'image_name' should be a symbolic name (not a hexadecimal string).
  image_name = utilities.get_attribute(
      container, ['properties', 'Config', 'Image'])

  if ((not utilities.valid_string(image_name)) or
      utilities.valid_hex_id(image_name)):
    msg = 'missing or invalid image name in container ID=%s' % container['id']
    gs.logger_error(msg)
    raise ValueError(msg)

  cache_key = '%s|%s' % (docker_host, image_id)
  image, timestamp_secs = gs.get_images_cache().lookup(cache_key)
  if timestamp_secs is not None:
    gs.logger_info('get_image(docker_host=%s, image_id=%s) cache hit',
                   docker_host, image_id)
    return image

  # A typical value of 'docker_host' is:
  # k8s-guestbook-node-3.c.rising-apricot-840.internal
  # Use only the first period-seperated element for the test file name.
  # The typical value of 'image_name' is:
  # brendanburns/php-redis
  # We convert embedded '/' and ':' characters to '-' to avoid interference with
  # the directory structure or file system.
  url = 'http://{docker_host}:{port}/images/{image_id}/json'.format(
      docker_host=docker_host, port=gs.get_docker_port(), image_id=image_id)
  fname = '{host}-image-{id}'.format(
      host=docker_host.split('.')[0],
      id=image_name.replace('/', '-').replace(':', '-'))

  try:
    image = fetch_data(gs, url, fname, expect_missing=True)
  except ValueError:
    # image not found.
    msg = 'image not found for image_id: %s' % image_id
    gs.logger_info(msg)
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

  wrapped_image = utilities.wrap_object(
      image, 'Image', full_hex_label, now,
      label=short_hex_label, alt_label=image_name)

  ret_value = gs.get_images_cache().update(cache_key, wrapped_image, now)
  gs.logger_info('get_image(docker_host=%s, image_id=%s, image_name=%s)',
                 docker_host, image_id, image_name)
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
    image = get_image(gs, docker_host, container)
    if (image is not None) and (image['id'] not in image_id_set):
      images_list.append(image)
      image_id_set.add(image['id'])

  gs.logger_info('get_images(docker_host=%s) returns %d images',
                 docker_host, len(images_list))
  return images_list


@utilities.global_state_string_args
def get_minion_status(gs, docker_host):
  """Returns the status of the collector minion running on 'docker_host'.

  Args:
    gs: global state.
    docker_host: Docker host name. Must not be empty.

  Returns:
  'OK': the collector minion is active.
  'ERROR': the collecor minion is inactive or an error occured while
    communicating with it.
  """
  try:
    containers_list = get_containers(gs, docker_host)
  except:
    gs.logger_error('failed to communicate with collector minion on %s',
                    docker_host)
    return 'ERROR'

  # In testing mode, an empty containers list is also considered an error.
  if gs.get_testing() and (not containers_list):
    return 'ERROR'
  return 'OK'


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

  # The file must contain an entry for '\d+:cpu:/...'.
  m = re.search(r'\b\d+:cpu:/([0-9a-fA-F]+)\b', cgroup)
  if not m:
    msg = 'could not find an entry for "cpu:/docker/..." in %s' % fname
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  hex_container_id = m.group(1)
  if gs.get_testing():
    # This pod name is guaranteed to match a pod in the testdata directory.
    my_pod_name = 'kube-dns-bqw5e'
  else:
    my_pod_name = os.uname()[1]
  assert utilities.valid_string(my_pod_name)

  # Find my node name from my pod.
  my_node_name = None
  for pod in kubernetes.get_pods(gs):
    assert utilities.is_wrapped_object(pod, 'Pod')
    if pod['id'] == my_pod_name:
      my_node_name = utilities.get_attribute(
          pod, ['properties', 'spec', 'nodeName'])
      break

  if not utilities.valid_string(my_node_name):
    msg = ('could not find pod %s or this pod does not contain a valid '
           'node name' % my_pod_name)
    gs.logger_error(msg)
    raise collector_error.CollectorError(msg)

  # inspect the running container.
  # Must specify an explicit host name (not "localhost").
  url = 'http://{host}:{port}/containers/{container_id}/json'.format(
      host=my_node_name, port=gs.get_docker_port(),
      container_id=hex_container_id)
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
  # Must specify an explicit host name (not "localhost").
  url = 'http://{host}:{port}/images/{image_id}/json'.format(
      host=my_node_name, port=gs.get_docker_port(),
      image_id=hex_image_id)
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
