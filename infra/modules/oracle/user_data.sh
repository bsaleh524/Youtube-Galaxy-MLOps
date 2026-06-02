#!/bin/bash
set -euo pipefail

# k3s bootstrap script — runs once on first boot via cloud-init

apt-get update -y
apt-get install -y curl git

# Install k3s (no traefik — we use nginx-ingress via Helm)
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -

# Allow the ubuntu user to run kubectl without sudo
mkdir -p /home/ubuntu/.kube
cp /etc/rancher/k3s/k3s.yaml /home/ubuntu/.kube/config
chown ubuntu:ubuntu /home/ubuntu/.kube/config
chmod 600 /home/ubuntu/.kube/config
# Replace 127.0.0.1 with the public IP so external kubectl works
PUBLIC_IP=$(curl -s http://169.254.169.254/opc/v1/instance/ | python3 -c "import sys,json; print(json.load(sys.stdin)['hostname'])" 2>/dev/null || curl -s ifconfig.me)
sed -i "s/127.0.0.1/$PUBLIC_IP/g" /home/ubuntu/.kube/config

# Install Helm
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Add common Helm repos
sudo -u ubuntu helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
sudo -u ubuntu helm repo add jetstack https://charts.jetstack.io
sudo -u ubuntu helm repo add weaviate https://weaviate.github.io/weaviate-helm
sudo -u ubuntu helm repo add bitnami https://charts.bitnami.com/bitnami
sudo -u ubuntu helm repo update

echo "Bootstrap complete. k3s is running."
echo "Get your kubeconfig from: /home/ubuntu/.kube/config"
