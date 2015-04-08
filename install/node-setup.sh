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

# This shell script sets up a node to run the Cluster-Insight data
# collector. You need to run this script once after you set up your project.
# Running this script again will cause no trouble (idempotent operation).
# This script recognizes the different configuration files in master and
# minion nodes and updates them accordingly.
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
# The script will print "NOTHING DONE" if the node was already set up.
# The script will print "FAILED" in case of a failure.
set +xv
readonly CONFIG_FILE="/etc/default/docker"

# Expected values.
readonly EXPECTED_1ST_LINE_INITIAL='DOCKER_OPTS=""'
readonly EXPECTED_1ST_LINE_FINAL='DOCKER_OPTS="-H tcp://0.0.0.0:4243 -H unix:///var/run/docker.sock"'
readonly EXPECTED_BODY_LINE='DOCKER_OPTS='
readonly EXPECTED_LAST_LINE='DOCKER_NOFILE=1000000'
readonly EXPECTED_MIN_LINES=4
readonly EXPECTED_MAX_LINES=10

# Derived values from configuration file.
readonly CONFIG_LINES=$(cat ${CONFIG_FILE} | wc -l)
readonly FIRST_LINE="$(head -n 1 ${CONFIG_FILE})"
readonly MATCHING_LINES=$(fgrep "${EXPECTED_BODY_LINE}" ${CONFIG_FILE} | wc -l)
readonly LAST_LINE="$(tail -n 1 ${CONFIG_FILE})"

if [[ ${CONFIG_LINES} -lt ${EXPECTED_MIN_LINES} ]]; then
  echo "FAILED: configuration file is too short"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ ${CONFIG_LINES} -gt ${EXPECTED_MAX_LINES} ]]; then
  echo "FAILED: configuration file is too long"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ ${MATCHING_LINES} -lt 2 ]]; then
  echo "FAILED: configuration file does not contain expected pattern"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ "${LAST_LINE}" != "${EXPECTED_LAST_LINE}" ]]; then
  echo "FAILED: conifiguration file does not end as expected"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ "${FIRST_LINE}" == "${EXPECTED_1ST_LINE_FINAL}" ]]; then
  echo "NOTHING DONE"
  exit 0
fi
  
if [[ "${FIRST_LINE}" != "${EXPECTED_1ST_LINE_INITIAL}" ]]; then
  echo "FAILED: unexpected first line"
  cat ${CONFIG_FILE}
  exit 1
fi

# Create the new configuration contents.
readonly NEW_CONFIG="/tmp/$$"
echo "${EXPECTED_1ST_LINE_FINAL}" > ${NEW_CONFIG}
tail -n +2 ${CONFIG_FILE} >> ${NEW_CONFIG}

if [[ $(cat ${NEW_CONFIG} | wc -l) != ${CONFIG_LINES} ]]; then
  echo "FAILED: internal error"
  cat ${NEW_CONFIG}
  rm -f ${NEW_CONFIG}
  exit 1
fi

# Rewrite the first line.
sudo cp -f ${NEW_CONFIG} ${CONFIG_FILE}
if [[ $? != 0 ]]; then
  echo "FAILED: writing ${CONFIG_FILE} failed."
  rm -fr ${NEW_CONFIG}
  exit 1
fi

# cleanup
rm -fr ${NEW_CONFIG}

# Verify that the new configuration file is not corrupt.
if [[ $(cat ${CONFIG_FILE} | wc -l) != ${CONFIG_LINES} ]]; then
  echo "FAILED: unexpected final value of configuration file: length"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ "$(head -n 1 ${CONFIG_FILE})" != "${EXPECTED_1ST_LINE_FINAL}" ]]; then
  echo "FAILED: unexpected final value of configuration file: first line"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ $(fgrep "${EXPECTED_BODY_LINE}" ${CONFIG_FILE} | wc -l) != \
      ${MATCHING_LINES} ]]; then
  echo "FAILED: unexpected final value of configuration file: body lines"
  cat ${CONFIG_FILE}
  exit 1
fi

if [[ "$(tail -n 1 ${CONFIG_FILE})" != "${EXPECTED_LAST_LINE}" ]]; then
  echo "FAILED: unexpected final value of configuration file: last line"
  cat ${CONFIG_FILE}
  exit 1
fi

# Restart the Docker service.
sudo service docker restart
if [[ $? != 0 ]]; then
  echo "FAILED to restart Docker"
  exit 1
fi

echo "ALL DONE"
exit 0
