# Cluster Insight: a context graph generator for Kubernetes clusters

Cluster Insight is a user-installable service that collects runtime metadata
about resources in a Kubernetes managed cluster, and infers relationships
between those resources to create a *context graph*. The nodes of the context
graph are cluster resources (e.g. nodes, pods, services,
replication-controllers, containers, processes, and images), and the edges are
inferred relationships between those resources (e.g. contains, runs, monitors,
loadBalances, createdFrom).

The context graph represents a point-in-time snapshot of the cluster’s state.
Subsequent snapshots may produce different context graphs, reflecting the
inherent dynamicity in the Kubernetes cluster.

Clients of the Cluster-Insight service, such as UIs, can retrieve context graph
snapshots through a REST API. The context graph provides valuable contextual
data that can be combined with resource level monitoring data to enable
enhanced visual navigation of the dynamic state of a Kubernetes cluster.


## How to install and activate this service

The Cluster Insight service expects to run on the Kubernetes master node, and
can be deployed from a self-contained Docker image, built offline from the
source code.

You can either install a pre-built image or build a Docker image from the
source code.
To build a Docker image from the source code, follow these instructions:

* Login to the master host.
* Check if the Docker service is running: `sudo docker ps`. If this gives
  an error, you must install and start the Docker service on this machine
  with the command: `sudo service docker start` .
* Clone the Cluster-Insight sources from Github into a local directory
  `./cluster-insight` with the command
  `git clone https://github.com/google/cluster-insight.git` .
* Change directory to `./cluster-insight/collector` .
* Run: `sudo docker build -t kubernetes/cluster-insight . `
* Check for the image: `sudo docker images`. You should see an image named
  `kubernetes/cluster-insight`.

To install and activate this service, follow these instructions:

* Enable port 4243 of the Docker daemons running on the master and minion nodes.
  The easiest way to do so is by running the the installation script
  `cluster-insight/install/project-setup.sh` by the following instructions:
* Clone the Cluster-Insight sources from Github into a local directory
  `./cluster-insight` with the command
  `git clone https://github.com/google/cluster-insight.git`
  if you have not done so already.
* Change directory to `./cluster-insight/collector`. 
* Run the script `./project-setup.sh PROJECT_NAME`.
* If the script ends with the message `SCRIPT ALL DONE` then the one-time setup
  of port 4243 is complete. You can skip the following two steps.
* If the script ends with the message `SCRIPT FAILED` or with another error,
  you will have to perform the following operations by hand.
* On each of the Kubernetes minion node and the Kubernetes master node
  do the following:
   * Login to the minion/master host.
   * Edit the file /etc/default/docker, and replace the line `DOCKER_OPTS=`
     with the line: `DOCKER_OPTS='-H tcp://0.0.0.0:4243 -H unix:///var/run/docker.sock'`
   * Restart the Docker daemon: `sudo service docker restart`

* On the Kubernetes master do the following:
   * Login to the master host.
   * Check if the Docker service is running: `sudo docker ps`. If this gives
     an error, you must install and start the Docker service on this machine
     with the command: `sudo service docker start` .
   * Download or build the Docker image `kubernetes/cluster-insight`:
       * If you want to use a pre-built image, use `sudo docker pull kubernetes/cluster-insight`
         to download it from Docker Hub.
       * If you want to build the Docker image from the sources, please
         follow the instructions above.
       * In both cases, you should be able to see the
         `kubernetes/cluster-insight` in the list of images reported by
         `sudo docker images`.

   * Start the Cluster-Insight service like this:
     `sudo docker run -d --net=host -p 5555:5555 --name cluster-insight kubernetes/cluster-insight`.
   * The Cluster-Insight service should now be listening for REST
     API requests on port 5555 in the Kubernetes master. Check this by typing:
     `sudo docker ps` - you should see a running container with the name
     cluster-insight.
   * To start the Cluster-Insight service in debug mode, append the `-d` or
     `--debug` flags to the end of the command line like this:
     `sudo docker run -d --net=host -p 5555:5555 --name cluster-insight kubernetes/cluster-insight python ./collector.py --debug`.
     Please excercise caution when enabling the debug mode, because it enables
     a significant security hole. Any user who triggers a failure in the
     Cluster-Insight service will have unrestricted access to the debugger
     and will be able to issue arbitrary commands.

* If you plan to access this service externally over HTTP, you must create a
  firewall rule on your platform to enable HTTP access to port 5555 on the
  Kubernetes master host.
   * On the Google Cloud Platform, you can do this using the gcloud command
     line tool: `gcloud compute firewall-rules create FIREWALL_RULE_NAME --allow tcp:5555 --network "default" --source-ranges "0.0.0.0/0" --target-tags KUBERNETES_MASTER_NAME`.
     For example: 
     `gcloud compute firewall-rules create cluster-insight-collector --allow tcp:5555 --network "default" --source-ranges "0.0.0.0/0" --target-tags k8s-guestbook-master`.


## Data collection details

The Cluster Insight service runs on the Kubernetes master node, and accesses
the Docker daemons on all of the minion nodes via port 4243 on each minion node.
It also accesses the Docker daemon on the master node via port 4243.
In addition, it listens for external HTTP requests to its REST endpoint on port
5555 of the master node, as shown in the figure below:

![alt text](kubernetes-setup.png "cluster-insight service setup")


## REST API

These are the APIs that clients of Cluster Insight can use to get the context
graph snapshot and raw resource-specific metadata:

* `/cluster` - returns a context graph snapshot with a timestamp. The context
  graph is a JSON document consisting of `resources` and `relations` keys. The
  format of this JSON document is described later.
* `/cluster/resources/TYPE` - returns the raw metadata for cluster resources
  of type TYPE, where TYPE must be one of {Node, Pod, Service,
  ReplicationController, Container, Image, Process}.
* `/debug` - returns a rendering of the context graph in DOT format for
  debugging purposes.
* `/version` - returns the name of the currently running Docker image,
  the image identifier, and its compilation date.

In order to minimize monitoring overhead on the Kubernetes cluster, the context
graph is computed from cached metadata about the cluster resources. The cache
is internal to the Cluster Insight service, and its update frequency is fixed
in this release (10 seconds). In a future release, the cache will update
automatically in response to Kubernetes API events, ensuring that the resource
data is always up to date. The context graph is computed on demand using the
resource metadata from the cache.

## Context graph format

The context graph is a JSON document with the following format:
```js
{
  "timestamp": SNAPSHOT-TIME,
  "resources" : [
    {
      "id" : RESOURCE-ID,
      "type" : RESOURCE-TYPE,
      "timestamp" : WHEN-OBSERVED,
      "properties" : RESOURCE-METADATA,
      "annotations" : {
        "label" : RESOURCE-LABEL
      }
    },
    ...
  ],
  "relations" : [
    {
      "type" : RELATION-TYPE,
      "timestamp" : WHEN-INFERRED,
      "source" : RESOURCE-ID,
      "target" : RESOURCE-ID,
      "annotations" : {
        "label" : RELATION-LABEL
      }
    },
    ...
  ]
}
```

The `properties` field in the resource is the observed runtime data for the
corresponding resource that was collected from the Kubernetes master or
the Docker daemons on its minion nodes.
The observed data is immutable.
The `annotations` field in resources and relations contains key-value pairs
inserted by the Cluster-Insight logic.

Each of the resources and relations has a `timestamp` field, indicating when
it was observed or inferred, respectively. The entire context graph has a
separate timestamp indiciating when the graph was computed from the resource
metadata.
