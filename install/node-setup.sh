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

# This shell script sets up a minion node to run the Cluster-Insight data
# collector. You can run this script again to fetch the latest binary.
#
# This script should work on any VM running Linux, but it was tested only
# on Google Cloud Platform (GCP).
#
# If you cluster is running is on GCP, you should set up your GCP support tools
# (mainly the "gcloud" command) on your workstation, and then you can run
# it this way:
#
# cat node-setup.sh | gcloud compute ssh --project=PROJECT_NAME --zone=ZONE_NAME NODE_NAME
#
# However, most users will run the gcp-project-setup.sh script in this
# directory, which will call this script on all VMs (instances) of the
# project.
#
# The script will print "ALL DONE" if it completed the setup successfully.
# The script will print "FAILED" in case of a failure.
set +xv

# pull the latest Cluster-Insight container image from Docker Hub.
echo "pulling latest Cluster-Insight container image from Docker Hub"
sudo docker pull kubernetes/cluster-insight
if [[ $? != 0 ]]; then
  echo "FAILED to pull cluster-insight image from Docker Hub"
  exit 1
fi

echo "ALL DONE"
exit 0
