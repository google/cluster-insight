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

#
# Setup Cluster-Insight in a given project.
# You should run this script only once per project.
# It will set up all instances (VMs) that belong to this project.
# If you run this script more than once, it will do nothing (idempotent).
#
# The script will print "SCRIPT ALL DONE" if it configured all instances
# successfully. This includes the case that nothing was done.
#
# The script will print "SCRIPT FAILED" if it failed to configure any node.
#
# You should run this script from your workstation after setting up your GCP
# project.
#
# Usage:
#  ./project_setup PROJECT_NAME

SCRIPT_NAME="./node-setup.sh"

if [ $# -ne 1 ]; then
  echo "SCRIPT FAILED"
  echo "usage: $0 PROJECT_NAME"
  exit 1
fi

readonly PROJECT_NAME="$1"

if [ \! -r "${SCRIPT_NAME}" ]; then
  echo "SCRIPT FAILED"
  echo "cannot read script ${SCRIPT_NAME}"
  exit 1
fi

# The 'nodes_and_zones' array will contain pairs of (node, zone) strings.
# The node name will appear in the even elements of the array, and the
# corresponding zone name will appear in the following odd element.
declare -a nodes_and_zones
count=0
for name in $(gcloud compute --project="${PROJECT_NAME}" instances list |
              fgrep RUNNING | awk '{print $1, $2}'); do
  nodes_and_zones[${count}]="${name}"
  count=$((count+1))
done

if [[ ${count} == 0 ]]; then
  echo "SCRIPT FAILED"
  echo "No instances found in project ${PROJECT_NAME}"
  exit 1
fi

all_done_count=0
nothing_done_count=0
failure_count=0
i=0

while [[ ${i} -lt ${count} ]]; do
  instance_name="${nodes_and_zones[${i}]}"
  zone_name="${nodes_and_zones[$((i+1))]}"
  echo "setup: project=${PROJECT_NAME} zone=${zone_name} instance=${instance_name}"
  output="$(cat ${SCRIPT_NAME} | gcloud compute ssh --project=${PROJECT_NAME} --zone=${zone_name} ${instance_name})"
  if [[ "${output}" =~ "ALL DONE" ]]; then
    all_done_count=$((all_done_count+1))
    echo "ALL DONE"
  elif [[ "${output}" =~ "NOTHING DONE" ]]; then
    echo "NOTHING DONE"
    nothing_done_count=$((nothing_done_count+1))
  else
    echo "FAILED"
    failure_count=$((failure_count+1))
    echo "${output}"
  fi
  i=$((i+2))
done 

echo "all_done_count=${all_done_count}"
echo "nothing_done_count=${nothing_done_count}"
echo "failure_count=${failure_count}"

if [[ ${failure_count} -gt 0 ]]; then
  echo "SCRIPT FAILED"
  exit 1
fi

if [[ (${all_done_count} -le 0) && (${nothing_done_count} -le 0) ]]; then
  echo "SCRIPT FAILED"
  echo "internal error: invalid counter values"
  exit 1
fi

echo "SCRIPT ALL DONE"
exit 0
