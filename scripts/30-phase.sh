#!/usr/bin/env bash
# Run one measured phase of the demo.
#   scripts/30-phase.sh before     deploys the over-provisioned app, runs the load, saves results/before.json
#   scripts/30-phase.sh after      applies the right-sized app + HPA, runs the SAME load, saves results/after.json
#
# Knobs (environment variables):
#   QPS=40         requests per second (keep identical for before and after)
#   DURATION=8m    load duration       (keep identical for before and after)
#   WINDOW=6m      averaging window at the end of the run (skips the warm-up)
#   CONSOLIDATE=1  after the fix, drain one worker first (stand-in for cluster autoscaler / Karpenter)
#   ZONE=auto      Kepler zone label, or a name such as package
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need kubectl python3 curl

PHASE="${1:-}"
case "$PHASE" in before|after) ;; *) echo "usage: $0 before|after" >&2; exit 1 ;; esac

QPS="${QPS:-40}"
DURATION="${DURATION:-8m}"
WINDOW="${WINDOW:-6m}"
ZONE="${ZONE:-auto}"
mkdir -p "$ROOT/results"

kubectl apply -f "$ROOT/manifests/00-namespace.yaml"

if [[ "$PHASE" == "before" ]]; then
  log "Deploying the over-provisioned app"
  kubectl delete hpa demo-app -n demo --ignore-not-found
  kubectl apply -f "$ROOT/manifests/10-app-before.yaml"
else
  log "Applying the right-sized app + HPA"
  kubectl apply -f "$ROOT/manifests/20-app-after.yaml"
fi
kubectl -n demo rollout status deploy/demo-app --timeout=300s

if [[ "$PHASE" == "after" && "${CONSOLIDATE:-0}" == "1" ]]; then
  "$ROOT/scripts/60-consolidate.sh"
fi

log "Starting load: ${QPS} qps for ${DURATION}"
kubectl -n demo delete job "loadgen-$PHASE" --ignore-not-found
sed -e "s/__RUN__/$PHASE/g" -e "s/__QPS__/$QPS/g" -e "s/__DURATION__/$DURATION/g" \
  "$ROOT/manifests/30-loadgen.yaml" | kubectl apply -f -

# Wait for the job to finish (duration + 3 minutes of slack for image pull and startup).
secs=$(python3 - "$DURATION" <<'PY'
import re, sys
m = re.fullmatch(r"(\d+)([smh])", sys.argv[1])
n, u = int(m.group(1)), m.group(2)
print(n * {"s": 1, "m": 60, "h": 3600}[u] + 180)
PY
)
kubectl -n demo wait --for=condition=complete "job/loadgen-$PHASE" --timeout="${secs}s"
kubectl -n demo logs "job/loadgen-$PHASE" > "$ROOT/results/loadgen-$PHASE.txt"

log "Collecting numbers from Prometheus (window: $WINDOW)"
kubectl -n monitoring port-forward "svc/$PROM_SVC" 9090:9090 >/dev/null 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -sf localhost:9090/-/ready >/dev/null && break; sleep 1; done

python3 "$ROOT/tools/collect.py" --prom http://localhost:9090 --label "$PHASE" \
  --window "$WINDOW" --zone "$ZONE" --out "$ROOT/results/$PHASE.json"

echo
echo "Latency lines from the load generator:"
grep -E "target (50|90|95|99)%|^Code " "$ROOT/results/loadgen-$PHASE.txt" || true
