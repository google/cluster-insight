This is a Docker-ized version of the Castanet data collector service for
getting the config graph of a Kubernetes cluster.

### Instructions to deploy this service on GCP (Google Cloud Platform):

1. Find the Kubernetes master and minion nodes:
    * Determine your Kubernetes project Id from the Google Developers Console.
    * Set the default project ID for the following ```gcloud``` commands with:
      ```gcloud config set project YOUR-KUBERNETES-PROJECT-ID```.
    * Set the default zone for the following ```gcloud``` commands with:
      ```gcloud config set compute/zone ZONE-NAME```.
    * List the name of GCE instances with the command:
      ```gcloud compute instances list```.
    * The Kubernetes master will have the suffix "...-master" and the minion
      nodes will have the suffix "...-node-N".

1. On each of the N minion nodes, enable the Docker REST API on port 4243:
    * SSH into the node: ```gcloud compute ssh KUBERNETES_MINION_NODE```.
    * Edit /etc/default/docker with ```sudo vi /etc/default/docker```
      (or another editor) and change the first line from ```DOCKER_OPTS=''```
      to:
      ```DOCKER_OPTS='-H tcp://0.0.0.0:4243 -H unix:///var/run/docker.sock'```.
    * Restart the Docker service: ```sudo service docker restart```.
    * Verify that Docker is running in this node by running the command:
```
  sudo docker ps
```

1. Set up the Castanet data collector service on the Kubernetes master:
    * SSH into the master: ```gcloud compute ssh KUBERNETES_MASTER```.
    * Start the Docker service if it is NOT already running:
      ```sudo service docker start```.
    * Download the Castanet Docker image from Docker Hub:
      ```sudo docker pull vasbala/castanet```. Alternatively,
      if you want to build this Docker image from source, see instructions below.
    * Start the container:
      ```sudo docker run -d --net=host -p 5555:5555 --name castanet-collector vasbala/castanet```
    * Check that you have the "castanet-collector" container running:
      ```sudo docker ps | grep castanet-collector```

1. Create a firewall rule to allow external HTTP traffic to the Castanet data
   collection service, which listens on port 5555 in
   the Kubernetes master. For example on GCP you can do this via:
```
  gcloud compute firewall-rules create "castanet-collector" --allow tcp:5555 --network "default" --source-ranges "0.0.0.0/0" --target-tags KUBERNETES_MASTER
```
   where KUBERNETES\_MASTER is the Kubernetes master mode name
   (e.g. k8s-guestbook-master).

1. Access the Castanet service from a browser to see the top-level help page:
   * Find the external IP address of the Kubernetes master by typing
     ```gcloud compute instances list```
     and noting the EXTERNAL\_IP for the KUBERNETES\_MASTER instance.
   * From a browser go to the URL ```http://EXTERNAL_IP:5555```. You should see
     a top level API help page.
   * This page will list all REST API targets supported by the
     data collector service. The most useful one is the /graph API, which returns
     a snapshot of the current configuration graph for the entire Kubernetes
     cluster.


### How to build the Castanet collector Docker image from source:

1. Download the source from GitHub: ```git clone https://github.com/kraken-people/castanet.git```

1. cd into ./collector

1. Build the Docker image within the /collector directory:
   ```sudo docker build -t vasbala/castanet .``` (don't forget the trailing ".")

1. You should now have a local Docker image named vasbala/castanet: ```sudo docker images```.

1. Follow the instructions above on how to deploy the container in a Kubernetes cluster,
   skipping the step to "Download the Castanet Docker image from Docker Hub".
