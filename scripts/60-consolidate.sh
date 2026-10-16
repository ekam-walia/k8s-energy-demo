#!/usr/bin/env bash
# Stand-in for node consolidation (cluster autoscaler / Karpenter) on a demo cluster:
# cordon and drain the worker that currently runs the fewest demo pods.
# On a real cluster, let your autoscaler do this and skip the script.
#   scripts/60-consolidate.sh           drain one worker
#   scripts/60-consolidate.sh restore   uncordon all workers
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl

workers() { kubectl get nodes -l '!node-role.kubernetes.io/control-plane' -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'; }

if [[ "${1:-}" == "restore" ]]; then
  for n in $(workers); do kubectl uncordon "$n"; done
  exit 0
fi

pods_on() { kubectl -n demo get pods -l app=demo-app -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' | grep -cx "$1" || true; }

best=""; best_count=999999
for n in $(workers); do
  [[ "$(kubectl get node "$n" -o jsonpath='{.spec.unschedulable}')" == "true" ]] && continue
  c="$(pods_on "$n")"
  if (( c < best_count )); then best="$n"; best_count="$c"; fi
done

if [[ -z "$best" ]]; then echo "No schedulable worker found." >&2; exit 1; fi
log "Draining $best (${best_count} demo pods; they move to the other workers)"
kubectl drain "$best" --ignore-daemonsets --delete-emptydir-data --force --timeout=180s
kubectl -n demo rollout status deploy/demo-app --timeout=180s
kubectl get nodes
echo
echo "NOTE: on kind this only cordons a container. Nothing powers off. On real hardware, a removed node is where the idle-power saving comes from."
