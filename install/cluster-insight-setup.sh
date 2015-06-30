#!/bin/bash
#
# Copyright 2015 The cluster-insight Authors. All Rights Reserved
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

# This shell script sets up the cluster-insight datacollector. You can run 
# it again to fetch and start the latest binary.
#
# This script should work on any machine running Linux or MacOSX, but it 
# was tested only on Ubunto 14.04 and MacOSC Yosemite. It should correctly 
# configure any Kubernetes cluster, but it was tested only with clusters 
# running on Google Cloud Platform (GCP) and vagrant running Ubuntu 14.04.
#
# *** IMPORTANT ***
# This script must be run from directory where you cloned the cluster-insight
# repository, so ./cluster-insight/install/cluster-insight-setup.sh is
# the path to the installation script.
# 
# To explicitly set the number of minions, you should set the environment
# variable NUM_MINIONS. The default is to set NUM_MINIONS to the number
# of nodes in your cluster as reported by Kubernetes.
#
# You may specify an explicit path to Kubernetes binaries, which is an optional
# parameter of this script.
#
# This script will restart the cluster-insight collector using the latest
# container pulled from Docker Hub. If you want to restart the collector
# using the latest binary from each instance (for example, when you build
# the container from the sources), you should run this script in debug mode
# by specifying the "-d" or "--debug" as the first argument of this script.
#
# The script will print "ALL DONE" if it completed the setup successfully.
# The script will print "FAILED" in case of a failure.

set -o nounset
set -o pipefail

readonly SERVICE_NAME="cluster-insight"
readonly SERVICE_PORT="cluster-insight"
readonly SERVICE_PATH="$(pwd)/${SERVICE_NAME}"

readonly INSTALL_PATH="${SERVICE_PATH}/install"

readonly MINION_CONTROLLER_NAME="${SERVICE_NAME}-minion-controller-v1"
readonly MASTER_CONTROLLER_NAME="${SERVICE_NAME}-master-controller-v1"
readonly NUM_MASTERS=1
readonly SERVICE_FILE="${INSTALL_PATH}/${SERVICE_NAME}-service.yaml"
readonly DOCKER_IMAGE="kubernetes/${SERVICE_NAME}"

function run_command() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: run_command cmd arg1 arg2 arg3 ..."
    exit 1
  fi
  "$@"
  if [[ $? -ne 0 ]]; then
    echo "FAILED to execute: $@"
    exit 1
  fi
}

function stop_kubernetes_service() {
  if [[ $# -ne 2 ]]; then
    echo "Wrong number of arguments to stop_kubernetes_service: $#."
    exit 1
  fi

  local svc_output="$(${KUBECTL} get service | fgrep ${1})"
  if [[ -n "${svc_output}" ]] ; then
    echo "Stopping service ${1}."
    run_command "${KUBECTL}" stop -f "${2}"
  else
    echo "The service ${1} is not running"
  fi
}

function stop_kubernetes_rc() {
  if [[ $# -ne 2 ]]; then
    echo "Wrong number of arguments to stop_kubernetes_rc: $#."
    exit 1
  fi

  local rc_output="$(${KUBECTL} get rc | fgrep ${1})"
  if [[ -n "${rc_output}" ]] ; then
    echo "Stopping replication controller ${1}."
    run_command "${KUBECTL}" stop -f "${2}"
  else
    echo "Replication controller ${1} is not running."
  fi
}

function start_kubernetes_service() {
  if [[ $# -ne 2 ]]; then
    echo "Wrong number of arguments to stop_kubernetes_rc: $#."
    exit 1
  fi

  echo "Starting service ${1}."
  run_command "${KUBECTL}" create -f "${2}"

  svc_output="$(${KUBECTL} get service | fgrep ${1})"
  if [[ -z "${svc_output}" ]] ; then
    echo "FAILED to start service ${1}."
    exit 1
  fi
}

function start_kubernetes_rc() {
  if [[ $# -ne 3 ]]; then
    echo "Wrong number of arguments to stop_kubernetes_rc: $#."
    exit 1
  fi

  echo "Starting replication controller ${1}."
  run_command "${KUBECTL}" create -f "${2}"

  rc_output="$(${KUBECTL} get rc | fgrep ${1})"
  if [[ -z "${rc_output}" ]]; then
    echo "FAILED to create replication controller ${1}."
    exit 1
  fi

  # scale the cluster-insight minion controller.
  echo "Scaling replication controller ${1} to ${3} replicas."
  # The "kubectl scale" command is implemented in newer versions of
  # Kubernetes.
  "${KUBECTL}" scale rc "${1}" --replicas="${3}"
  if [[ $? -ne 0 ]]; then
    # The "kubectl resize" command is implemented in older versions of
    # Kubernetes.
    run_command "${KUBECTL}" resize rc "${1}" --replicas="${3}"
  fi
}

function launch_kubectl_proxy() {
  local pid
  for port in $(seq 8001 65535); do 
    # Start the proxy in the background on port ${port}
    # The proxy will terminate if this port is already in use.
    "${KUBECTL}" proxy --port="${port}" > /dev/null 2>&1 & 
    pid=$!
    sleep 1
    if [[ -n $(ps -p "${pid}" -o pid | fgrep -v PID) ]] ; then 
      # The proxy is running.
      KUBECTL_PORT=${port}
      return 0
    fi
  done

  # Failed to find a port.
  KUBECTL_PORT=0
  return 1
}

function verify_service_health() {
  if [[ $# -ne 1 ]]; then
    echo "Usage: verify_service_health KUBECTL_PORT"
    exit 1
  fi
  for i in $(seq 1 60); do
    health="$(curl http://localhost:${1}/api/v1beta3/proxy/namespaces/default/services/${SERVICE_NAME}:${SERVICE_PORT}/healthz 2>/dev/null)"
    if [[ "${health}" =~ "OK" ]]; then
      return 0
    fi
    sleep 1
  done 
  return 1
}

if [[ ("${1:-}" == "--debug") || ("${1:-}" == "-d") ]]; then
  # Run in debug mode.
  # Use the debug version of the master and minion template files.
  echo "run in debug mode"
  readonly MASTER_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-master-controller-debug.yaml"
  readonly MINION_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-minion-controller-debug.yaml"
  shift
else
  # Run in production mode.
  # Use the production version of the master and minion template files.
  echo "run in production mode"
  readonly MASTER_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-master-controller.yaml"
  readonly MINION_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-minion-controller.yaml"
fi

if [[ $# -ge 1 ]]; then
  KUBE_ROOT="$1"
  readonly KUBECTL="${KUBE_ROOT}/cluster/kubectl.sh"
else
  readonly KUBECTL="kubectl"
fi

if [[ -z "$(which ${KUBECTL})" ]]; then
  echo "could not find the kubectl executable at ${KUBECTL}"
  echo "usage: $0 [-d|--debug] [path/to/kubernetes]"
  exit 1
fi

# stop the cluster-insight service and replication controllers.
stop_kubernetes_service "${SERVICE_NAME}" "${SERVICE_FILE}"
stop_kubernetes_rc "${MASTER_CONTROLLER_NAME}" "${MASTER_CONTROLLER_FILE}"
stop_kubernetes_rc "${MINION_CONTROLLER_NAME}" "${MINION_CONTROLLER_FILE}"

# compute the number of minions if not supplied by the caller.
if [[ -z "${NUM_MINIONS:-}" ]]; then
  NUM_MINIONS="$(${KUBECTL} get nodes | fgrep -v STATUS | wc -l)"
  if [[ "${NUM_MINIONS}" < 1 ]]; then
    echo "SCRIPT FAILED"
    echo "Kubernetes is not running"
    exit 1
  fi
fi

#start the cluster-insight replication controllers and service.
start_kubernetes_rc "${MINION_CONTROLLER_NAME}" "${MINION_CONTROLLER_FILE}" "${NUM_MINIONS:-1}"
start_kubernetes_rc "${MASTER_CONTROLLER_NAME}" "${MASTER_CONTROLLER_FILE}" "${NUM_MASTERS:-1}"
start_kubernetes_service "${SERVICE_NAME}" "${SERVICE_FILE}"


# verify that the cluster-insight service is healthy.
echo "Verifying service health."

KUBECTL_PORT=0
launch_kubectl_proxy || {
  echo "FAILED to launch ${KUBECTL} proxy."
  exit 1
}

echo "${KUBECTL} proxy is running on port ${KUBECTL_PORT}"

verify_service_health ${KUBECTL_PORT} || {
  echo "FAILED to get service health response."
  exit 1
}

echo "Service ${SERVICE_NAME} ALL DONE."
exit 0
