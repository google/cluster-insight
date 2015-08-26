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

FROM python:2-onbuild

CMD ["python", "./collector.py"]
