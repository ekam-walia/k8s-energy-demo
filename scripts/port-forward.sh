#!/usr/bin/env bash
# Open Grafana (http://localhost:3000, admin/admin) and Prometheus (http://localhost:9090). Ctrl+C to stop.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl
trap 'kill 0' EXIT
kubectl -n monitoring port-forward "svc/$GRAFANA_SVC" 3000:80 &
kubectl -n monitoring port-forward "svc/$PROM_SVC" 9090:9090 &
echo "Grafana:    http://localhost:3000   (dashboard: 'Energy & Waste Demo')"
echo "Prometheus: http://localhost:9090"
wait
