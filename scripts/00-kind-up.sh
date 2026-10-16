#!/usr/bin/env bash
# Create the local kind cluster (skip this on a real cluster).
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kind kubectl docker

if kind get clusters | grep -qx "$CLUSTER_NAME"; then
  log "kind cluster '$CLUSTER_NAME' already exists"
else
  log "Creating kind cluster '$CLUSTER_NAME'"
  kind create cluster --name "$CLUSTER_NAME" --config "$ROOT/kind/kind-config.yaml"
fi
kubectl get nodes
