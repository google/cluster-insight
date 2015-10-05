# Cluster Insight: a context graph generator for Kubernetes clusters

Cluster Insight is a Kubernetes service that collects runtime metadata about resources in a Kubernetes cluster, and infers relationships between them to create a *context graph*.

A context graph is a point-in-time snapshot of the cluster’s state. Clients of the Cluster Insight service, such as user interfaces, can retrieve context graphs through the service's REST API. Each call may produce a different context graph, reflecting the inherent dynamicity in the Kubernetes cluster.

A context graph provides contextual information that can be combined with resource level monitoring data to enable visual navigation of the dynamic state of a Kubernetes cluster.

The nodes of the context graph are cluster resources (cluster, nodes, services, replication controllers, pods, containers, and images), and the edges are the inferred relationships (contains, runs, monitors, loadBalances, createdFrom).

## How to set up and access the service

Deploying Cluster Insight involves creating a service and a replication controller. The replication controller creates one pod, which contains one container. The container image is [here](https://registry.hub.docker.com/u/kubernetes/cluster-insight/) on Docker Hub.

### Preliminaries

In the following, we will assume that you have a Kubernetes cluster running and `kubectl` configured to talk to it. If you have set up the Kubernetes cluster from the command line with `gcloud container clusters create` or `kube-up.sh`, then `kubectl` will have been configured for you. If you have set it up from the Google Developers Console, you can configure `kubectl` by running `gcloud container clusters get-credentials`.

If you have several Kubernetes clusters configured, you can determine the corresponding *context names* with `kubectl config view`, and you can switch among them with `kubectl config use-context CONTEXT_NAME`.

### Setup

Assuming you have configured `kubectl` to talk to your Kubernetes cluster, deploying Cluster Insight is a simple matter of invoking `kubectl create`:

```
git clone https://github.com/google/cluster-insight --branch=v2
cd cluster-insight/install
kubectl create -f cluster-insight-service.yaml
kubectl create -f cluster-insight-controller.yaml
```

The Cluster Insight images on Docker Hub are tagged with their version, and the controller template in `cluster-insight-controller.yaml` references the latest released version. We will update the version tag in this file whenever we push a new released image to Docker Hub.

### Access

Cluster Insight provides detailed information about your cluster, including the values of environment variables, which many people use to inject secret credentials into containers. Access to its API needs to be restricted. An easy and safe way to access it is using `kubectl proxy`.

Cluster Insight makes its REST API available through the `cluster-insight` service in the `default` namespace, on the named port `cluster-insight`. With `kubectl proxy` running, the help page for the API will be available at the following URL:

* [http://localhost:8001/api/v1/proxy/namespaces/default/services/cluster-insight:cluster-insight](http://localhost:8001/api/v1/proxy/namespaces/default/services/cluster-insight:cluster-insight)

## Running Cluster Insight locally

It is easy to run Cluster Insight locally on your workstation for development purposes:

```
git clone https://github.com/google/cluster-insight --branch=v2
cd cluster-insight/collector

pip install -r requirements.txt

export KUBERNETES_API=http://localhost:8001/api/v1
python collector.py --debug --host=localhost
```

Running the `pip` and `python` commands above under [virtualenv](https://virtualenv.pypa.io/) is highly recommended, but not required.

Now the Cluster Insight help page will be available at [http://localhost:5555/](http://localhost:5555/), and if you have `kubectl proxy` running, the REST API will be operational.

## REST API

Cluster Insight makes available the following endpoints:

* `/` returns a help page with links to the following.
* `/cluster` returns a context graph. The format of the context graph is described below.
* `/cluster/resources` returns all of the resources (nodes), but not the relations (edges).
* `/cluster/resources/TYPE` returns the raw metadata for all cluster resources of type TYPE, where TYPE is `nodes`, `pods`, `services`, or `rcontrollers`.
* `/debug` returns a rendering of the current context graph in DOT format for debugging purposes.

In order to minimize the load on the Kubernetes API, the context graph is computed on demand from cached metadata describing the cluster resources. The cache is internal to the Cluster Insight service. Its update frequency is fixed in this release at once every 10 seconds. In a future release, the cache may update automatically in response to Kubernetes API events, ensuring that the resource data is always up to date.

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

The `properties` field in `resources` is the data returned by the Kubernetes API for the corresponding resource. The `annotations` field in `resources` and `relations` contains key-value pairs inserted by the Cluster Insight logic.

Resources and relations have a `timestamp` attribute, indicating when they were first observed or inferred, respectively. The `timestamp` value should remain constant as long as the corresponding resource or relation did not change substantially.

When comparing resource values, we compute the hash of the JSON representation after removing the attributes `timestamp`, `lastHeartbeatTime` and `resourceVersion`, because their values are ephemeral and do not indicate a substantial change in the corresponding resource. All data older than one hour is deleted automatically from the cache. The value of the `timestamp` attribute will therefore remain constant for at most one hour.

The entire context graph has a separate timestamp, which is the maximum of the timestamps of the resources and relations contained in the graph. If the timestamp of the entire context graph did not change, then there was
no substantial change in any of the resources and relations inside it.
