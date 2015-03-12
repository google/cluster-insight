# Castanet Project, Google NY

# This uses the official Python Docker image, which includes
# an onbuild trigger that automatically does the following:
#   - installs a Python 2.7.* environment
#   - pip installs all packages inside ./requirements.txt
#   - copies the files in . to /usr/src/app on the image
#   - makes /usr/src/app the working directory
#   - runs CMD within that directory

# To build the Docker image on your Kubernetes master node, you first have to
# copy the source files to that node. You can do it with the following commands:
#   cd <your P4 directory home>/experimental/castanet
#   gcloud config set project PROJECT_NAME
#   gcloud compute copy-files collector MASTER_NODE_NAME:~/
#
# This command will copy the files under the "collector" subdirectory (recursively)
# to your home directory in the specified node (VM instance).
#
# You should login to the node (VM instance) of the Kubernetes master where you
# copied the source files to with the command:
#   gcloud compute ssh MASTER_NODE_NAME
# For example:
#   gcloud compute ssh k8s-guestbook-master
#
# To build the image (you must do this within this directory containing Dockerfile):
#   sudo docker build -t IMAGE-NAME .
# Check that you now have a new image called IMAGE-NAME:
#   sudo docker images

# NOTE: You must copy the image castanet/collector into the Kubernetes Master, before trying to run it.
# The logic will try to connect to the Kubernetes master via localhost:8080, and it will crash if it
# cannot find it there. See the accompanying README.md file for instructions on how to deploy this.

# To run a container from this image in dev/test mode (Ctl-C will stop and remove the container):
#   sudo docker run --rm --net=host -p 5555:5555 --name castanet-collector castanet/collector
# To run a container from this image in detached production mode:
#   sudo docker run -d --net=host -p 5555:5555 --name castanet-collector castanet/collector
# (this assumes that the Web Server port specified in collector.py is 5555)

# To check if the container is running:
#   sudo docker ps | grep castanet-collector

# To stop and remove the container:
#   sudo docker rm -f castanet-collector

# To remove the castanet/collector image:
#   sudo docker rmi castanet/collector


FROM python:2-onbuild

EXPOSE 5555

CMD ["python", "./collector.py"]
