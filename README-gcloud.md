# Google Cloud Platform commands

This is a gcloud command line cheat-sheet for some of the operations you will
need for deploying the Cluster Insight service on GCP. It assumes that you have
downloaded and installed the Google Cloud SDK which includes the gcloud command
line tool.

Please follow the instructions in the README.md for installing the Cluster
Insight service. The commands listed in this document are for your reference only.

* Set the project and zone defaults for the "gcloud":
```
  gcloud config set project PROJECT_NAME
  gcloud config set compute/zone ZONE_NAME
```

* Find the names of all GCE instances (nodes) in your project - returns a
list of instances with their INSTANCE_NAME, External IP and Internal IP:
```
  gcloud compute instances list
```

* Login to an instance (node):
```
   gcloud compute ssh INSTANCE_NAME
```

* Create a firewall rule to allow external TCP traffic to port 5555 on an instance:
```
  gcloud compute firewall-rules create RULE_NAME \
      --allow tcp:5555 --network "default" --source-ranges "0.0.0.0/0" \
      --target-tags INSTANCE_NAME
```

* List all the firewall rules that are active:
```
     gcloud compute firewall-rules list
```
