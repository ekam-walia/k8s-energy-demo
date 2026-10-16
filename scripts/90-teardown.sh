#!/usr/bin/env bash
# Remove the demo. On kind this deletes the whole cluster; on a real cluster it removes only what we installed.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl

if command -v kind >/dev/null 2>&1 && kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  log "Deleting kind cluster '$CLUSTER_NAME'"
  kind delete cluster --name "$CLUSTER_NAME"
else
  log "Removing demo, Kepler and monitoring from the current cluster"
  kubectl delete namespace demo --ignore-not-found
  helm uninstall kepler -n kepler 2>/dev/null || true
  helm uninstall "$MONITORING_RELEASE" -n monitoring 2>/dev/null || true
  kubectl delete namespace kepler monitoring --ignore-not-found
fi
