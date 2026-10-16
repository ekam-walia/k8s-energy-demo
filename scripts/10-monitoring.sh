#!/usr/bin/env bash
# Install Prometheus + Grafana (kube-prometheus-stack), metrics-server (for the HPA) and the demo dashboard.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl helm

log "Installing kube-prometheus-stack"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install "$MONITORING_RELEASE" prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f "$ROOT/helm/kube-prometheus-stack-values.yaml" --wait --timeout 10m

if ! kubectl -n kube-system get deploy metrics-server >/dev/null 2>&1; then
  log "Installing metrics-server (needed by the HPA)"
  kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
  # kind kubelets use self-signed certs.
  if [[ "${INSECURE_KUBELET_TLS:-1}" == "1" ]]; then
    kubectl -n kube-system patch deploy metrics-server --type=json \
      -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
  fi
  kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
fi

log "Loading the Grafana dashboard"
kubectl -n monitoring create configmap energy-waste-dashboard \
  --from-file=energy-waste.json="$ROOT/dashboards/energy-waste.json" \
  --dry-run=client -o yaml \
  | kubectl label --local -f - grafana_dashboard=1 -o yaml \
  | kubectl apply -f -

echo "Done. Open Grafana with: scripts/port-forward.sh   (user: admin / password: admin)"
