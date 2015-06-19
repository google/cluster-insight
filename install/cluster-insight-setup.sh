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
# This script must be run from the Kubernetes base directory.
# 
# To set the number of minions, you should set the env var NUM_MINIONS 
# or pass the number of minions as a parameter.
#
# The script will print "ALL DONE" if it completed the setup successfully.
# The script will print "FAILED" in case of a failure.

set -o errexit
set -o nounset
set -o pipefail

# Create a temporary directory for the project repository.
TMP_DIR="/tmp/$$"

SERVICE_NAME="cluster-insight"
SERVICE_PORT="cluster-insight"
SERVICE_PATH="${TMP_DIR}/${SERVICE_NAME}"

INSTALL_PATH="${SERVICE_PATH}/install"

MINION_CONTROLLER_NAME="${SERVICE_NAME}-minion-controller-v1"
MINION_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-minion-controller.yaml"

MASTER_CONTROLLER_NAME="${SERVICE_NAME}-master-controller-v1"
MASTER_CONTROLLER_FILE="${INSTALL_PATH}/${SERVICE_NAME}-master-controller.yaml"
NUM_MASTERS=1

SERVICE_FILE="${INSTALL_PATH}/${SERVICE_NAME}-service.yaml"

DOCKER_IMAGE="kubernetes/${SERVICE_NAME}"

if [[ -z "${KUBE_ROOT:-}" ]]; then
  if [[ $# -ge 1 ]]; then
    KUBE_ROOT="$1"
  else
    KUBE_ROOT="$(pwd)"
  fi
fi

KUBECTL="${KUBE_ROOT}/cluster/kubectl.sh"
if [[ -z "$(which ${KUBECTL})" ]]; then
  echo "usage: $0 path/to/kubernetes"
  exit 1
fi

function stop_kubernetes_service() {
  if [[ $# -ne 2 ]]; then
    echo "Wrong number of arguments to stop_kubernetes_service: $#."
    exit 1
  fi

  local svc_output="$(${KUBECTL} get service | fgrep ${1})"
  if [[ -n "${svc_output}" ]] ; then
    echo "Stopping service ${1}."
    "${KUBECTL}" stop -f "${2}" > /dev/null 2>&1
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
    "${KUBECTL}" stop -f "${2}" > /dev/null 2>&1
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
  "${KUBECTL}" create -f "${2}" > /dev/null 2>&1

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
  "${KUBECTL}" create -f "${2}" > /dev/null 2>&1

  rc_output="$(${KUBECTL} get rc | fgrep ${1})"
  if [[ -z "${rc_output}" ]]; then
    echo "FAILED to create replication controller ${1}."
    exit 1
  fi

  # scale the cluster-insight minion controller.
  echo "Scaling replication controller ${1} to ${3} replicas."
  "${KUBECTL}" scale rc "${1}" --replicas="${3}" > /dev/null 2>&1
}

function clean_up_directory() {
  rm -rf "${TMP_DIR}"
}

trap clean_up_directory SIGINT SIGTERM SIGHUP EXIT
mkdir -p "${TMP_DIR}"

# Extract the project repository to the temporary directory.
echo "Cloning the Github project repository into ${SERVICE_PATH}."
git clone "https://github.com/google/${SERVICE_NAME}.git" "${SERVICE_PATH}"

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

KUBECTL_PORT=8001
KUBECTL_PID=$$

function clean_up_processes() {
  kill `ps ax | fgrep "kubectl proxy --port=${KUBECTL_PORT}" | awk '{ print $1 }'` > /dev/null 2>&1
  clean_up_directory
}

function launch_kubectl_proxy() {
  for KUBECTL_PORT in `seq 8001 65535`; do 
    "${KUBECTL}" proxy --port="${KUBECTL_PORT}" > /dev/null 2>&1 & 
    KUBECTL_PID=$!
    sleep 1
    if [[ -n `ps -p "${KUBECTL_PID}" -o pid | fgrep -v PID` ]] ; then 
      trap clean_up_processes SIGINT SIGTERM SIGHUP EXIT
      return 0
    fi
    port=$((${KUBECTL_PORT} + 1))
  done
  return 1
}

# verify that the cluster-insight service is healthy.
echo "Verifying service health."

launch_kubectl_proxy || {
  echo "FAILED to run ${KUBECTL} proxy."
  exit 1
}

function verify_service_health() {
  for i in `seq 1 60`; do
    health="$(curl http://localhost:${KUBECTL_PORT}/api/v1/proxy/namespaces/default/services/${SERVICE_NAME}:${SERVICE_PORT}/healthz 2>/dev/null)"
    if [[ "${health}" =~ "OK" ]]; then
      return 0
    fi
    sleep 1
  done 
  return 1
}

verify_service_health || {
  echo "FAILED to get service health response."
  exit 1
}

echo "Service ${SERVICE_NAME} setup complete."
exit 0
