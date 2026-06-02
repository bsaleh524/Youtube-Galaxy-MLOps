#!/bin/bash
# Start the local k3d cluster for the Galaxy project.
# Reads COMPUTE_BACKEND from env (default: cpu).
#
# Usage:
#   ./scripts/start_local.sh               # CPU mode (M1 or any machine)
#   COMPUTE_BACKEND=gpu ./scripts/start_local.sh   # GPU mode (desktop with 3080)

set -euo pipefail

COMPUTE_BACKEND=${COMPUTE_BACKEND:-cpu}
LLM_BACKEND=${LLM_BACKEND:-groq}
CLUSTER_NAME="galaxy-local"

echo "=== Galaxy MLOps Local Cluster ==="
echo "COMPUTE_BACKEND : $COMPUTE_BACKEND"
echo "LLM_BACKEND     : $LLM_BACKEND"
echo ""

# Check dependencies
for cmd in k3d kubectl helm; do
    command -v $cmd >/dev/null 2>&1 || { echo "ERROR: $cmd not found. Install it first."; exit 1; }
done

# Check if cluster already exists
if k3d cluster list | grep -q "^$CLUSTER_NAME "; then
    echo "Cluster '$CLUSTER_NAME' already exists. Skipping creation."
    echo "  To recreate: k3d cluster delete $CLUSTER_NAME && $0"
else
    echo "Creating k3d cluster with k3d-${COMPUTE_BACKEND}.yaml..."
    k3d cluster create -c "k3d-${COMPUTE_BACKEND}.yaml"
fi

# Switch kubectl context
kubectl config use-context "k3d-${CLUSTER_NAME}"

echo ""
echo "Creating namespaces..."
kubectl apply -f k8s/namespaces.yaml

echo ""
echo "Installing nginx-ingress..."
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx --force-update >/dev/null
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace kube-system \
  --values k8s/ingress/nginx-values.yaml \
  --wait

echo ""
echo "Installing cert-manager..."
helm repo add jetstack https://charts.jetstack.io --force-update >/dev/null
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace kube-system \
  --set installCRDs=true \
  --wait

echo ""
echo "=== Cluster ready! ==="
echo ""
echo "Next steps:"
echo "  make install-mlflow     → deploy MLflow"
echo "  make install-weaviate   → deploy Weaviate"
echo "  make install-redis      → deploy Redis (for Feast)"
echo "  make install-airflow    → deploy Airflow"
if [ "$COMPUTE_BACKEND" = "gpu" ]; then
    echo "  make install-ollama     → deploy Ollama (GPU mode)"
fi
echo ""
echo "Access services:"
echo "  make forward-airflow    → http://localhost:8080"
echo "  make forward-mlflow     → http://localhost:5000"
