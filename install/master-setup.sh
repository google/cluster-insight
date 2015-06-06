#!/bin/sh
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

# This shell script sets up the master node to run the Cluster-Insight data
# collector. You can run this script again to fetch and start the latest
# binary. You should run this script after you run the script 'node-setup.sh'
# on all minion nodes before.
#
# This script should work on any VM running Linux, but it was tested only
# on Google Cloud Platform (GCP).
#
# If you cluster is running is on GCP, you should set up your GCP support tools
# (mainly the "gcloud" command) on your workstation, and then you can run
# it this way:
#
# cat master-setup.sh | sed 's/NUM_MINIONS/<#minion nodes>/' | gcloud compute ssh --project=PROJECT_NAME --zone=ZONE_NAME NODE_NAME
#
# *** IMPORTANT ***
# To set the number of minion nodes (NUM_MINIONS) you should change the
# string 'NUM_MINIONS' to the desired value before running this script.
# The example above does it with the 'sed' Unix command.
#
# However, most users will run the gcp-project-setup.sh script in this
# directory, which will call this script on all VMs (instances) of the
# project.
#
# The script will print "ALL DONE" if it completed the setup successfully.
# The script will print "FAILED" in case of a failure.
set +xv
IMAGE="kubernetes/cluster-insight"
REP_CONTROLLER="cluster-insight/collector/cluster-insight-controller.json"

# extract the "cluster-insight" repository to a temporary directory
TMP_DIR="/tmp/$$"
mkdir ${TMP_DIR}
if [[ $? != 0 ]]; then
  echo "FAILED to create temporary directory ${TMP_DIR}"
  exit 1
fi

cd ${TMP_DIR}
if [[ $? != 0 ]]; then
  echo "FAILED to change directory to ${TMP_DIR}"
  exit 1
fi

echo "clone the project source from GitHub to get ${REP_CONTROLLER}"
git clone https://github.com/google/cluster-insight.git
if [[ $? != 0 ]]; then
  echo "FAILED to clone the project source from GitHub"
  exit 1
fi

# pull the latest Cluster-Insight container image from Docker Hub.
echo "pulling latest Cluster-Insight container image from Docker Hub"
sudo docker pull ${IMAGE}
if [[ $? != 0 ]]; then
  echo "FAILED to pull ${IMAGE} image from Docker Hub"
  exit 1
fi

# stop the Cluster-Insight collector master if it is running.
MASTER_ID="$(sudo docker ps | fgrep ${IMAGE} | awk '{print $1}')"
if [[ "${MASTER_ID}" != "" ]]; then
  echo "stop the Cluster-Insight master (Docker ID=${MASTER_ID})"
  sudo docker stop ${MASTER_ID}
  if [[ $? != 0 ]]; then
    echo "FAILED to stop Cluster-Insight master"
    exit 1
  fi
  sudo docker rm ${MASTER_ID}
  if [[ $? != 0 ]]; then
    echo "FAILED to remove Cluster-Insight master"
    exit 1
  fi
fi

# stop the Cluster-Insight minion collectors.
echo "stop the Cluster-Insight replication controller and minions"
kubectl stop -f ${REP_CONTROLLER}
if [[ $? != 0 ]]; then
  echo "FAILED to stop the Cluster-Insight replication controller"
  exit 1
fi

# start and resize the Cluster-Insight minion collectors.
echo "start the Cluster-Insight replication controller on one minion"
kubectl create -f ${REP_CONTROLLER}
if [[ $? != 0 ]]; then
  echo "FAILED to create the Cluster-Insight replication controller"
  exit 1
fi

echo "resize the Cluster-Insight replication controller on NUM_MINIONS nodes"
kubectl resize rc cluster-insight-controller --replicas=NUM_MINIONS
if [[ $? != 0 ]]; then
  echo "FAILED to resize the Cluster-Insight replication controller"
  exit 1
fi

echo "verify that the replication controller has the correct # of replicas"
rc_output="$(kubectl get rc | fgrep ${IMAGE} | awk '{print $NF}')"
if [[ "${rc_output}" != "NUM_MINIONS" ]]; then
  echo "FAILED to create NUM_MINIONS replicas"
  exit 1
fi

# start the Cluster-Insight master collector.
echo "start the Cluster-Insight collector master"
sudo docker run -d --net=host -p 5555:5555 --name cluster-insight -e CLUSTER_INSIGHT_MODE=master ${IMAGE}
if [[ $? != 0 ]]; then
  echo "FAILED to start the Cluster-Insight master collector"
  exit 1
fi

# verify that the Cluster-Insight master is working.
sleep 5
echo "checking master health"
health="$(curl http://localhost:5555/healthz)"
if [[ "${health}" =~ "OK" ]]; then
  echo "master is alive"
else
  echo "FAILED to get master health response"
  echo 1
fi

# cleanup after successful operation.
cd
rm -fr ${TMP_DIR}

echo "ALL DONE"
exit 0
