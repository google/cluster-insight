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

The Cluster Insight service is a self-contained Docker image. It runs in two
modes: in the "master" mode it collects data from Kubernetes and from the
Docker daemons running on the minion modes. In the "minion" mode it acts
as a proxy for the local Docker daemon. The Cluster-Insight "master" should
run on the Kubernetes master, whereas the Cluster-Insight "minion" should run
on every Kubernetes minion node in the cluster.
The provided installation script will configure, install, and run the
Cluster-Insight service on any Kubernetes cluster.
The Cluster-Insight service does not require any change to the Docker
daemon configuration or require restarting the Docker daemons.

### Easy installation: run the `gcp-project-setup.sh` script

The `gcp-project-setup.sh` script will configure, install, and run the
Cluster-Insight service
on the given Kubernetes cluster running on GCP. You should run the script
on your workstation. To run the script, follow the instruction below.
If you run the script, then you can skip the rest of this section.
* Clone the Cluster-Insight sources from Github into a local directory
  `./cluster-insight` with the command
  `git clone https://github.com/google/cluster-insight.git` .
* Run the installation script with the command
  `cd ./cluster-insight/install; ./gcp-project-setup.sh PROJECT_ID`.
  The script will fetch the latest version of the Cluster-Insight container
  from Docker Hub.
  The script will print "SCRIPT ALL DONE" if it completed the operation
  sucessfully.
* Note: the installation script may take up to a minute per node in case
  that the Cluster-Insight or its libraries are not pre-loaded on the
  node. Also, creating the firewall rule may take up to a minute.


### Manual installation (for example, on AWS)

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
  Note the terminating period which is a part of the command.
* Verify that the new image is available by the command: `sudo docker images`.
  You should see an image named `kubernetes/cluster-insight`.

To install and activate this service, follow these instructions:

To set up the minion nodes, do the following on every minion node:
  * Pull the Cluster-Insight binary from Docker Hub or compile it from
    the sources in every minion node. To pull the pre-built binary image from
    Docker Hub use the following command:
   `sudo docker pull kubernetes/cluster-insight`.
  * To compile the binary from the source code, follow the instruction
    above for compiling the binary on the master node.
  * *IMPORTANT:* You must have the same binary image of the Cluster-Insight
    service
    in each minion node prior to starting the Cluster-Insight service.
    You can do it by either fetching the image from Docker Hub or compiling
    it from the latest sources. See above.

Perform the following on the master node to complete the set up of the minion nodes:
  * Clone the Cluster-Insight sources from Github into a local directory
    if you have not done so already. See above for the command.
  * Run cluster-insight in "minion" mode on all the minions to enable access
    to the docker daemon on port 4243. We provide a script for a replication
    controller, so this is easy to set up. Run the following `kubectl`
    commands on the master host to set this up:
    * `kubectl create -f cluster-insight/collector/cluster-insight-controller.json`
    * `kubectl resize rc cluster-insight-controller --replicas=<num-minions>`
    * Here `<num-minions>` is the number of minion nodes in your cluster. Since the container binds to a specific port on the host, this will ensure that exactly one cluster-insight container runs on each minion.
    * All the minion nodes will have a cluster-insight container node running on them, and will provide limited read access to their docker daemon via port 4243. Try this out by running the following command based on the internal-ip of one of your minions: `curl http://<minion-node-internal-ip>:4243/containers/json`. 

To set up the Cluster-Insight service on master node, do the following:
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
     `sudo docker run -d --net=host -p 5555:5555 --name cluster-insight -e CLUSTER_INSIGHT_MODE=master  kubernetes/cluster-insight`.
   * The Cluster-Insight service should now be listening for REST
     API requests on port 5555 in the Kubernetes master. Check this by typing:
     `sudo docker ps` - you should see a running container with the name
     cluster-insight.
   * To start the Cluster-Insight service in debug mode, append the `-d` or
     `--debug` flags to the end of the command line like this:
     `sudo docker run -d --net=host -p 5555:5555 --name cluster-insight -e CLUSTER_INSIGHT_MODE=master kubernetes/cluster-insight python ./collector.py --debug`.
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

The Cluster-Insight service runs in "master" mode on the Kubernetes master
node, and accesses the Docker daemons on all of the minion nodes via the
Cluster-Insight service which runs in "minion" mode and acts as a proxy to
the Docker daemons.
The "master" Cluster-Insight service listens for external HTTP requests to
its REST endpoint on port 5555 of the master node, as shown in the figure
below.
The "minion" Cluste-Insight service listens for requests on port 4243 and
relays them to the local Docker daemon via a Unix-domain socket.
Note that the Unix-domain socket is the default way of communicating with
the Docker daemon.

![alt text](cluster-insight-architecture.png "cluster-insight service setup")


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

