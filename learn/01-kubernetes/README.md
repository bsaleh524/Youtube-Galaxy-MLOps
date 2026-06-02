# Module 01: Kubernetes

## What is Kubernetes?

Kubernetes (K8s) is a container orchestration system. It answers the question: *"I have a bunch of Docker containers — how do I run them reliably, scale them, and connect them together?"*

Without K8s, you run containers manually with `docker run`. That works for one or two containers on one machine. It breaks down when you have 10+ services, need automatic restarts on failure, want to roll out updates without downtime, or need to manage resources across a cluster of machines.

K8s solves all of that declaratively: you write YAML files describing what you *want* to exist, and K8s continuously works to make reality match your description.

---

## Core Concepts

### The Object Hierarchy

```
Cluster
└── Node (a physical or virtual machine)
    └── Pod (the smallest deployable unit — one or more containers)
        └── Container (a Docker container)
```

A **Pod** is not a container — it's a wrapper around one or more containers that share a network namespace (same IP address) and storage volumes. In practice, most Pods run a single container.

### Key Resource Types

**Deployment** — manages a set of identical Pods, ensures the right number are running, handles rolling updates.
```
Deployment (I want 3 copies of this Pod)
└── ReplicaSet (actually manages the 3 Pod instances)
    ├── Pod
    ├── Pod
    └── Pod
```

**Service** — a stable network endpoint that routes traffic to Pods. Pods come and go (they can be restarted, rescheduled), but a Service has a fixed DNS name and IP.
- `ClusterIP` — reachable only inside the cluster (default)
- `NodePort` — exposes on each Node's IP at a static port
- `LoadBalancer` — provisions an external load balancer (cloud providers)

**Ingress** — routes external HTTP/HTTPS traffic to Services based on hostname or URL path. Think of it as a smart reverse proxy / nginx config, but managed declaratively.

**Namespace** — a virtual cluster inside a cluster. Used to isolate environments (e.g., `dev`, `staging`, `prod` in the same cluster).

**PersistentVolume (PV) / PersistentVolumeClaim (PVC)** — storage that outlives a Pod. PVC is your request for storage ("I need 5GB"); PV is the actual storage that satisfies that request.

**ConfigMap / Secret** — inject configuration or sensitive values into Pods as environment variables or mounted files.

### Essential kubectl Commands

```bash
# Cluster info
kubectl cluster-info
kubectl get nodes

# Viewing resources
kubectl get pods                        # list pods in current namespace
kubectl get pods -n kube-system         # list in kube-system namespace
kubectl get pods --all-namespaces       # list everywhere
kubectl describe pod <name>             # detailed info + events
kubectl logs <pod-name>                 # stdout from container
kubectl logs <pod-name> -f              # follow/stream logs

# Working with resources
kubectl apply -f manifest.yaml          # create or update from file
kubectl delete -f manifest.yaml         # delete what the file describes
kubectl delete pod <name>               # delete a specific pod
kubectl exec -it <pod-name> -- bash     # shell into a running pod

# Port forwarding (access a service locally)
kubectl port-forward service/<name> 8080:80

# Check resource usage
kubectl top pods
kubectl top nodes
```

---

## Setup: k3d (k3s in Docker)

k3d runs a lightweight K8s cluster (k3s) inside Docker containers. No VM needed. Starts in seconds.

```bash
# Install k3d (macOS)
brew install k3d

# Install kubectl (if not already)
brew install kubectl

# Create a cluster named "galaxy-learn"
k3d cluster create galaxy-learn --port "8080:80@loadbalancer" --port "8443:443@loadbalancer"

# Verify
kubectl get nodes
# NAME                        STATUS   ROLES                  AGE
# k3d-galaxy-learn-server-0   Ready    control-plane,master   30s

# Delete when done
k3d cluster delete galaxy-learn
```

The `--port` flags map ports from your laptop (8080, 8443) into the cluster's load balancer, so you can reach Ingress resources from your browser.

---

## Exercise 1: Your First Pod

Create a pod that runs nginx, look inside it, then delete it.

**File: exercises/01-first-pod.yaml**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx-pod
  labels:
    app: nginx
spec:
  containers:
  - name: nginx
    image: nginx:alpine
    ports:
    - containerPort: 80
```

```bash
# Apply
kubectl apply -f exercises/01-first-pod.yaml

# Watch it become Ready
kubectl get pod nginx-pod -w

# Look at the details
kubectl describe pod nginx-pod

# Shell into it
kubectl exec -it nginx-pod -- sh
# Inside the container:
ls /etc/nginx/
exit

# Check logs
kubectl logs nginx-pod

# Clean up
kubectl delete pod nginx-pod
```

**What to notice:**
- The Pod goes through `Pending` → `ContainerCreating` → `Running`
- `kubectl describe` shows Events — this is your primary debugging tool
- Deleting a bare Pod is permanent; a Deployment would restart it

---

## Exercise 2: Deployment + Service

Bare Pods are fragile — if a node dies or you delete the pod, it's gone. Deployments add self-healing.

**File: exercises/02-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "50m"
          limits:
            memory: "128Mi"
            cpu: "100m"
```

**File: exercises/02-service.yaml**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-service
spec:
  selector:
    app: nginx         # Routes to Pods with this label
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
```

```bash
kubectl apply -f exercises/02-deployment.yaml
kubectl apply -f exercises/02-service.yaml

# See both pods running
kubectl get pods

# Delete one pod — watch K8s restart it
kubectl delete pod <one-of-the-pod-names>
kubectl get pods -w   # Watch the new one appear

# Access the service from your laptop
kubectl port-forward service/nginx-service 8888:80
# Open http://localhost:8888 in your browser

# Scale up
kubectl scale deployment nginx-deployment --replicas=4
kubectl get pods

# Clean up
kubectl delete deployment nginx-deployment
kubectl delete service nginx-service
```

**What to notice:**
- `resources.requests` is what K8s uses for scheduling (how much to reserve)
- `resources.limits` is the hard cap (container is OOM-killed if exceeded)
- The Service's `selector` must match the Pod's `labels` — this is how routing works

---

## Exercise 3: Namespaces

Namespaces partition the cluster. In the Galaxy project we'll use separate namespaces for different concerns (e.g., `galaxy-pipeline`, `galaxy-serving`).

```bash
# Create a namespace
kubectl create namespace galaxy-learn

# Deploy into that namespace
kubectl apply -f exercises/02-deployment.yaml -n galaxy-learn

# You need to specify -n to see it
kubectl get pods                         # nothing (default namespace)
kubectl get pods -n galaxy-learn         # your pod

# Set default namespace for this session
kubectl config set-context --current --namespace=galaxy-learn
kubectl get pods   # now shows galaxy-learn pods by default

# Reset
kubectl config set-context --current --namespace=default
kubectl delete namespace galaxy-learn    # deletes everything inside it
```

---

## Exercise 4: PersistentVolume

Pods are ephemeral — when they die, so does their filesystem. Use PVCs for data that should survive pod restarts. In the Galaxy project, MLflow stores experiment data and Weaviate stores its index on PVCs.

**File: exercises/04-pvc.yaml**
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

**File: exercises/04-pod-with-pvc.yaml**
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: pvc-demo
spec:
  containers:
  - name: writer
    image: busybox
    command: ["sh", "-c", "echo 'hello persistent world' > /data/test.txt && sleep 3600"]
    volumeMounts:
    - name: data-volume
      mountPath: /data
  volumes:
  - name: data-volume
    persistentVolumeClaim:
      claimName: data-pvc
```

```bash
kubectl apply -f exercises/04-pvc.yaml
kubectl apply -f exercises/04-pod-with-pvc.yaml

# Verify the file was written
kubectl exec pvc-demo -- cat /data/test.txt

# Delete the pod — the data persists in the PVC
kubectl delete pod pvc-demo

# Create a new pod that reads the same PVC
kubectl run reader --image=busybox --restart=Never \
  --overrides='{"spec":{"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"data-pvc"}}],"containers":[{"name":"reader","image":"busybox","command":["cat","/data/test.txt"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}]}}'

kubectl logs reader   # Should print: hello persistent world

# Clean up
kubectl delete pod reader
kubectl delete pvc data-pvc
```

---

## Exercise 5: Kubernetes Job (how training runs in Galaxy)

A **Job** runs a Pod to completion — unlike a Deployment which keeps it running forever. In the Galaxy project, the training pipeline runs as a Kubernetes Job submitted by Airflow.

**File: exercises/05-training-job.yaml**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-job-example
spec:
  template:
    spec:
      restartPolicy: Never      # Don't restart on failure — fail the job
      containers:
      - name: trainer
        image: python:3.11-slim
        command:
        - python
        - -c
        - |
          import time, random
          print("Starting training...")
          time.sleep(5)
          accuracy = random.uniform(0.85, 0.95)
          print(f"Training complete. Accuracy: {accuracy:.4f}")
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
  backoffLimit: 2               # Retry up to 2 times on failure
```

```bash
kubectl apply -f exercises/05-training-job.yaml

# Watch the job run
kubectl get jobs -w

# Get the pod name and check logs
kubectl get pods -l job-name=training-job-example
kubectl logs -l job-name=training-job-example

# Clean up
kubectl delete job training-job-example
```

**GPU resource request (for reference — only works with GPU nodes):**
```yaml
resources:
  limits:
    nvidia.com/gpu: 1    # Request one GPU
  requests:
    nvidia.com/gpu: 1
```
In the Galaxy project, the real training Job uses this on the desktop with k3d GPU passthrough. On the M1, this line is omitted and training falls back to CPU.

---

## Exercise 6: Helm (managing complex deployments)

Manually writing 10+ YAML files for a service like Airflow or Weaviate is impractical. Helm is a package manager for K8s — it bundles all the required resources into a **chart** with configurable **values**.

```bash
# Install Helm
brew install helm

# Add a chart repository (like pip index)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Search available charts
helm search repo bitnami/redis

# Install Redis (you'll use this for Feast's online store)
helm install my-redis bitnami/redis \
  --set auth.enabled=false \
  --set master.persistence.enabled=false

# Check what was created
kubectl get all -l app.kubernetes.io/instance=my-redis

# Connect to Redis
kubectl exec -it my-redis-master-0 -- redis-cli ping

# Customize with a values file
cat > my-values.yaml << 'EOF'
auth:
  enabled: false
master:
  persistence:
    enabled: false
  resources:
    requests:
      memory: 128Mi
      cpu: 50m
EOF

helm upgrade my-redis bitnami/redis -f my-values.yaml

# Uninstall
helm uninstall my-redis
```

**What Helm gives you:**
- One command to install a complex multi-resource service
- `values.yaml` to customize without touching the chart templates
- `helm upgrade` for updates, `helm rollback` for rollbacks
- `helm list` to see all installed releases

---

## How This Maps to the Galaxy Project

In the Galaxy project, every service runs in k3s:

| Concept | Galaxy usage |
|---|---|
| Deployment | Airflow, MLflow, FastAPI chatbot, Streamlit |
| Job | Training pipeline (GPU on desktop, CPU on M1) |
| Service | Internal routing (chatbot → weaviate, airflow → mlflow) |
| Ingress | `spookypharaoh.com` → Streamlit and FastAPI |
| PVC | MLflow experiment data, Weaviate index, Ollama model weights |
| Namespace | `galaxy-pipeline` (Airflow, MLflow) and `galaxy-serving` (Weaviate, chatbot, frontend) |
| Helm | Installing Airflow, Weaviate, cert-manager, Prometheus |
| ConfigMap | Non-secret configuration (MLflow tracking URI, Feast config) |
| Secret | API keys (Groq, Oracle credentials) |

You have two clusters:
- `galaxy-local` (k3d on your machine) — Airflow + MLflow + dev services
- `galaxy-prod` (k3s on Oracle Cloud) — Weaviate + chatbot + frontend

Same `kubectl` commands, same Helm charts, different contexts:
```bash
kubectl config use-context k3d-galaxy-local    # switch to local
kubectl config use-context galaxy-prod          # switch to Oracle
```

---

## Troubleshooting Cheat Sheet

```bash
# Pod won't start — check events
kubectl describe pod <name>

# Pod is running but wrong behavior — check logs
kubectl logs <name>
kubectl logs <name> --previous   # logs from the previous (crashed) container

# Can't reach a service — check endpoints
kubectl get endpoints <service-name>   # should list pod IPs, not be empty

# Resource issues — check node capacity
kubectl describe node <node-name>     # look at "Allocated resources"

# Nuclear option — see everything in a namespace
kubectl get all -n <namespace>
```
