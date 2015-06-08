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

# This uses the official Python Docker image, which includes
# an onbuild trigger that automatically does the following:
#   - installs a Python 2.7.* environment
#   - pip installs all packages inside ./requirements.txt
#   - copies the files in . to /usr/src/app on the image
#   - makes /usr/src/app the working directory
#   - runs CMD within that directory

# You should login to the node (VM instance) of the Kubernetes master with the
# commands:
#   gcloud config set project PROJECT_ID
#   gcloud compute ssh MASTER_NODE_NAME
#
# You should then clone the Cluster-Insight GitHub repository to obtain the
# sources with the command:
#   git clone https://github.com/google/cluster-insight.git
#
# To build the image you should first change your location to the directory
# containing Dockerfile then build it.
#   cd cluster-insight/collector
#   sudo docker build -t kubernetes/cluster-insight .
# Check that you now have a new image called "kubernetes/cluster-insight":
#   sudo docker images

# You must configure the Cluster-Insight data collector as explained in the
# accompanying ../README.md file before running it.

# To run a container from this image in dev/test mode as the master:
# (Ctrl-C will stop and remove the container):
#   sudo docker run --rm --net=host -p 5555:5555 --name cluster-insight -e CLUSTER_INSIGHT_MODE=master kubernetes/cluster-insight python ./collector.py --debug
#
# To run a container from this image in detached production mode as the master:
#   sudo docker run -d --net=host -p 5555:5555 --name cluster-insight -e CLUSTER_INSIGHT_MODE=master kubernetes/cluster-insight
# (this assumes that the Web Server port specified in collector.py is 5555)
#
# To run a container from this image in detached production mode as a minion:
#   sudo docker run -d --net=host -p 4243:4243 --name cluster-insight -e CLUSTER_INSIGHT_MODE=minion -v /var/run/docker.sock:/var/run/docker.sock:ro kubernetes/cluster-insight 
# (this assumes that the docker port specified in docker_proxy.py is 4243)

# To check if the Cluster-Insight data collector is running:
#   sudo docker ps | grep cluster-insight

# To stop and remove the container:
#   sudo docker rm -f cluster-insight

# To remove the kubernetes/cluster-insight image:
#   sudo docker rmi kubernetes/cluster-insight


FROM python:2-onbuild
ENV CLUSTER_INSIGHT_MODE minion

CMD ["python", "./cluster_insight.py"]
