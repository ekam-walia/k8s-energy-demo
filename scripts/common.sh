#!/usr/bin/env bash
# Shared helpers. Sourced by the other scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-energy-demo}"
MONITORING_RELEASE="monitoring"
PROM_SVC="${MONITORING_RELEASE}-kube-prometheus-prometheus"
GRAFANA_SVC="${MONITORING_RELEASE}-grafana"

need() {
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || { echo "ERROR: '$c' is required but not installed." >&2; exit 1; }
  done
}

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
