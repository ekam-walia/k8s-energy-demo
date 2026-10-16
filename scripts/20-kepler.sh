#!/usr/bin/env bash
# Install Kepler from its official OCI Helm chart.
#   MODE=kind  (default) -> fake CPU meter, synthetic numbers, workflow demo only
#   MODE=real            -> real power meters (RAPL/hwmon) on bare metal
# Optional: KEPLER_CHART_VERSION=<chart version>  KEPLER_IMAGE_TAG=<image tag, e.g. v0.11.4>
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl helm

MODE="${MODE:-kind}"
case "$MODE" in kind|real) ;; *) echo "MODE must be 'kind' or 'real'" >&2; exit 1 ;; esac

extra=()
[[ -n "${KEPLER_CHART_VERSION:-}" ]] && extra+=(--version "$KEPLER_CHART_VERSION")
[[ -n "${KEPLER_IMAGE_TAG:-}" ]] && extra+=(--set "image.tag=$KEPLER_IMAGE_TAG")

log "Installing Kepler (mode: $MODE)"
helm upgrade --install kepler oci://quay.io/sustainable_computing_io/charts/kepler \
  --namespace kepler --create-namespace \
  -f "$ROOT/helm/kepler-values-$MODE.yaml" ${extra[@]+"${extra[@]}"} --wait --timeout 5m

kubectl -n kepler get pods -o wide
echo
echo "Check the metric names and zones on YOUR version before the talk:"
echo "  kubectl -n kepler port-forward svc/kepler 28282:28282 &"
echo "  curl -s localhost:28282/metrics | grep -E '^kepler_(node|pod)_cpu_(watts|active_watts|idle_watts)' | head -20"
