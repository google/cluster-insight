# Troubleshooting guide for the Cluster-Insight server

## The server does not respond
1.  Verify that the server is running.
    1. Login to the master node.
    0. Try to access the Cluster-Insight server from the local machine with
      the command: `curl http://localhost:5555`.
      If you get the HTML contents of the Cluster-Insight's home page,
      the the server is functional. Follow the instructions below for other
      causes for the problem.
    2. List the running containers with the command:
       `sudo docker ps`.
    3. If the `sudo docker ps` command failed, you will need to restart Docker
       with the command: `sudo service docker start`.
    4. If the container `kubernetes/cluster-insight` is not listed in the
       output of `sudo docker ps`, you will have to start it.
       Please follow the instructions in the [README](README.md) file.
       You may need to
       delete a previous dead container with the same name if the `docker run`
       command fails.
    5. If the container `kubernetes/cluster-insight` is listed as running,
       then it is probably stuck.
       Read its log by the command:
       `sudo docker logs -f CONTAINER_ID` .
       Pay attention to the messages at the tail of the log.
       The CONTAINER_ID is a 12-digit hexadecimal number. It is
       listed in the first column of the output of `sudo docker ps`.
    6. Stop and delete the running container with:
       `sudo docker rm -f CONTAINER_ID`.
    7. Start the Cluster-Insight service. Please follow the instructions in
       the [README](README.md) file.
    8. Verify that the Cluster-Insight server is operational by accessing
       it. See item (ii) above.

2.  Did the IP address of the master node change?
    If you are using an IP address to access the Cluster-Insight server, then
    your access will fail if the master gets assigned a new IP address.
    Reinstalling the master node will change its static IP address.

    List the IP address of the master by visiting the developer's console
    or by the following command:
    `gcloud compute --project=PROJECT_ID instances list`.
    If the IP address changed, use the new one in your browser.

3.  Is the firewall rule correct?
    If you have used this Cluster-Insight server in the past, it is unlikely
    that the firewall rule got corrupt.

    List the firewall rules of the cluster on GCP with:
    `gcloud compute --project=PROJECT_ID firewall-rules list`
    You should find a rule called `cluster-insight-controller` that opens port
    5555 on the master node to all incoming TCP traffic.
    The output of the `gcloud compute firewall-rules list` command should
    contain a line similar to:
    `cluster-insight-collector default 0.0.0.0/0 tcp:5555 kubernetes-master`.
    If you cannot find such line, you have to create the missing firewall
    rule. Please follow the instructions in the [README](README.md) file.

## The server fails with CollectorError exception

The most common cause of this exception is a failure to communicate with
the Docker daemons in the minion nodes. To verify that this is indeed the
case, you should access the endpoints which show only Kubernetes data
(`/cluster/resources/nodes`, `/cluster/resources/pods`,
`/cluster/resources/services`, `/cluster/resources/rcontrollers`)
and the endpoints which show only Docker data
(`/cluster/resources/containers`, `/cluster/resources/processes`,
`/cluster/resources/images`).
If only the endpoints which show Docker data fail, then the problem is with
the Docker daemons or the Cluster-Insight minions that proxy the requests to
the Docker daemons.

To fix the problem on the minion nodes, follow these instructions:

1. Get the name of the failed minion from the error message that is shown
   by the CollectorError exception.

2. Login to that minion node.

3. Verify that Docker is running on this node by the command:
   `sudo docker ps`. If this command fails, you should restart the Docker
   daemon by the command: `sudo service docker restart`.

4. Verify that the Cluster-Insight minion is running by the command:
   `sudo docker ps`. You should find a line containing the
   `kubernetes/cluster-insight:latest` image name. 

5. If the Cluster-Insight minion is not running, it is extremely strange,
   because the Cluster-Insight minions are controlled by a replication
   controller. Follow the instructions in the [README](README.md) file
   to reinstall the Cluster-Insight service.

6. Verify that the Cluster-Insight minion and the Docker daemon respond as
   expected by running the command:
   `curl http://localhost:4243/containers/json`.
   You should see some JSON output.

7. If the above `curl` command fails, you should follow the instructions in
   the [README](README.md) file to reinstall the Cluster-Insight service.

## The server fails with a different run-time failure
This may be caused by a genuine bug.

1.  Read the log of the running Cluster-Insight server and look for additional
    information about the failure. Follow these instructions:
    1. Login to the master node running the Cluster-Insight server.
    2. Find the container ID of the Cluster-Insight server with the command:
       `sudo docker ps`
    3. Read the logs of the Cluster-Insight server with the command:
       `sudo docker logs -f CONTAINER_ID` .

2.  If the logs of the currently running server do not contain useful
    information,
    you should restart the Cluster-Insight server in debug mode.
    Please follow the instructions in the [README](README.md) file to do so.

3.  Try to trigger the same error.

4.  Read the logs and collect all relevant error messages.

5.  Open a new issue on Github and include all relevant information in the
    description of the issue. 
