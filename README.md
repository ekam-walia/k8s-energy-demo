# From Kubernetes Resources to Energy: demo kit

One over-provisioned app, one fix, one fair before/after comparison, measured with
Prometheus, Grafana and Kepler.

**Demo ki kahani (Hinglish):** eemork app jo zyada CPU/my maangti hai (before) -> hum real usage dekhkar
requests sahi karte hain aur HPA lagate hain (fix) -> same load dobara chalate hain (after) -> dashboard par
waste, nodes aur Kepler ki energy ka comparison. Sabse badi seekh: pod ki energy zyada nahi badalti,
saving tab hoti hai jab poori machine (node) hat jaati hai.

> **Status:** the files were syntax-checked (shell, YAML, JSON, all 33 PromQL expressions) and the Python
> tools have unit tests against a mock Prometheus. They were **not run on a live cluster** (the build
> sandbox could not reach one). Do one full dry run before the talk, using the checklist below.

## Two modes, and what each one can honestly show

| | Mode `kind` (laptop) | Mode `real` (bare metal) |
| --- | --- | --- |
| Use it for | Showing the workflow live | The numbers on your results slide |
| Kepler power meter | `fake` (synthetic numbers) | `rapl` / `hwmon` (real hardware readings) |
| Waste ratio, requests vs usage | Real | Real |
| Pod and node spreading, HPA | Real | Real |
| Watts and energy | **Synthetic. Do not quote them.** | Real, but CPU-only (see limits) |
| "Removing a node saves idle power" | Cannot show it (a kind node is just a container) | Yes, when a node is actually removed or powered off |

So: run the live demo on kind, and put numbers from a real-hardware run on the result slide. Say which is which.

## What you need

`docker`, `kind`, `kubectl`, `helm`, `python3` (3.8+). Network access to `quay.io`, `registry.k8s.io`,
`docker.io` and GitHub. For `real` mode, a Linux cluster on bare metal where `/sys/class/powercap` (RAPL) is readable.

## Quick start (kind)

```bash
scripts/00-kind-up.sh        # 1 control plane + 3 workers
scripts/10-monitoring.sh     # Prometheus, Grafana, metrics-server, the dashboard
MODE=kind scripts/20-kepler.sh
scripts/port-forward.sh      # Grafana http://localhost:3000 (admin/admin), dashboard "Energy & Waste Demo"
```

Run the measured phases in a second terminal (the first one keeps the port-forwards open):

```bash
scripts/30-phase.sh before                   # over-provisioned app + load -> results/before.json
scripts/40-show-diff.sh                      # the fix, as a diff (show this on screen)
CONSOLIDATE=1 scripts/30-phase.sh after     # right-sized app + HPA, drain one worker, SAME load -> results/after.json
scripts/50-compare.sh                        # Markdown table for your result slide
scripts/90-teardown.sh                       # clean up
```

Defaults: 40 requests/s for 8 minutes, averaged over the last 6 minutes (skips warm-up). Change with
`QPS=`, `DURATION=`, `WINDOW=`. **Use identical values for before and after.**

### Real hardware

Same steps, but use your cluster instead of kind (skip `00-kind-up.sh`), set `INSECURE_KUBELET_TLS=0` when
running `10-monitoring.sh` (unless your kubelets need it), and run `MODE=real scripts/20-kepler.sh`.
Skip `CONSOLIDATE=1`: let your cluster autoscaler or Karpenter remove the emptied node, then run
`scripts/30-phase.sh after` once the node count has settled.

## Live run sheet (8 minutes of stage time)

Do the full 8-minute runs the day before. On stage use a short live window and fall back to the saved
results and a recording if anything is slow. Short live run: `DURATION=3m WINDOW=2m`.

| Time | Do | Say (one idea) |
| --- | --- | --- |
| 0:00 | Grafana, "Energy & Waste Demo", app already running as BEFORE | "We asked for 6 CPUs. Look at the gap on the first panel." |
| 1:00 | Point at waste ratio, memory panel, nodes running demo pods | "The scheduler sees the reservation, not the usage." |
| 2:00 | Run `scripts/40-show-diff.sh` | "Same image and code. Only resources and scaling changed." |
| 3:00 | `CONSOLIDATE=1 DURATION=3m WINDOW=2m scripts/30-phase.sh after` | "Same load again. Watch requests drop and pods move." |
| 5:00 | Safety panel: restarts and OOMKills flat | "Not cheaper because it broke. Latency and restarts are unchanged." |
| 6:00 | Kepler panels: pod watts vs node active/idle | "Pod energy barely moves. The idle part belongs to the machine." |
| 7:00 | `scripts/50-compare.sh` output, then your real-hardware slide | "Savings show up when whole nodes go away." |

## Before you present: checklist

- [ ] **Check Kepler's metric names and zones on your version.** `kubectl -n kepler port-forward svc/kepler 28282:28282`, then
  `curl -s localhost:28282/metrics | grep -E '^kepler_(node|pod)_cpu_'`. The dashboard's **Kepler zone** dropdown
  defaults to `package`. If your zones are named differently, pick one in the dropdown (use one zone, never add
  zones together, because some zones contain others).
- [ ] Pin the version you demo and write it on a slide: `KEPLER_IMAGE_TAG=<tag> scripts/20-kepler.sh`. This kit was written against the current Kepler (0.10+ line), which reads `/proc` and `/sys` and no longer uses eBPF. Older blog posts and dashboards use different metric names.
- [ ] **Open the dashboard and make sure every panel shows data.** If panels say "datasource not found", edit
  `dashboards/energy-waste.json` and replace `"uid": "prometheus"` with your Prometheus data source uid.
- [ ] **Tune the load.** `registry.k8s.io/hpa-example` burns CPU per request, so usage depends on your machine. Run the BEFORE phase once and look at "CPU used". Raise or lower `QPS` until usage is roughly 0.3 to 0.6 cores in total, then keep that QPS for both phases.
- [ ] **Re-derive the right-sized values from your own data** (below) and update `manifests/20-app-after.yaml` if they differ.
- [ ] Do the full run twice. Use the better-documented one, and keep both to show it repeats.
- [ ] Record a screen capture of a complete run as the fallback.
- [ ] Put the results (`results/*.json`, `results/loadgen-*.txt`) and screenshots of each key panel in your slides.

### Choosing right-sized values

After the BEFORE run, ask Prometheus for the 95th percentile of real per-pod usage:

```promql
# CPU (cores) per pod, p95 over the last hour
quantile_over_time(0.95,
  sum by (pod)(rate(container_cpu_usage_seconds_total{namespace="demo",container!="",container!="POD"}[5m]))[1h:1m])

# Memory (bytes) per pod, max over the last hour
max_over_time(sum by (pod)(container_memory_working_set_bytes{namespace="demo",container!="",container!="POD"})[1h:1m])
```

Set the CPU request near that p95 plus headroom, and the memory request near the max plus headroom. For a
longer-running service use days of data, not one hour. Alternatives that do this for you: Vertical Pod
Autoscaler in recommendation mode, Goldilocks, or KRR.

## Queries behind the dashboard

| Panel | PromQL |
| --- | --- |
| Requested CPU | `sum(kube_pod_container_resource_requests{namespace="demo",resource="cpu"})` |
| Used CPU | `sum(rate(container_cpu_usage_seconds_total{namespace="demo",container!="",container!="POD"}[2m]))` |
| Waste ratio | `1 - used / requested` |
| Pod power | `sum(kepler_pod_cpu_watts{pod_namespace="demo",zone="$zone"})` |
| Node active / idle power | `sum(kepler_node_cpu_active_watts{zone="$zone"})`, `sum(kepler_node_cpu_idle_watts{zone="$zone"})` |
| Energy over the range | `sum(increase(kepler_pod_cpu_joules_total{pod_namespace="demo",zone="$zone"}[$__range])) / 3600` (Wh) |

Joules per second is watts, and 3600 joules is 1 watt-hour.

## Limits to say out loud

- Kepler estimates **CPU** power (for example the RAPL package domain). Its authors note CPU-only values are
  expected to be roughly 40 to 70 percent of whole-server power (IPMI), because DRAM, fans, network cards and
  power-supply losses are not included.
- Kepler attributes **active** CPU usage to workloads. **Idle** power is not assigned to pods, which is why
  the node-level idle panel matters for the "remove the node" story.
- On VMs without readable power meters, Kepler cannot read hardware power. VM power modelling is still being
  developed. Check your platform before you promise numbers.
- In a public cloud you do not control the physical server. Your usage and bill drop for certain. The
  fleet-level energy saving depends on the provider.
- Energy is not carbon. Carbon needs the grid's carbon intensity at that place and time.
- Short runs are noisy. Repeat the experiment and show the range.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| No `kepler_*` series in Prometheus | Is the Kepler pod `Running`? Is there a ServiceMonitor (`kubectl -n kepler get servicemonitor`)? Did you install the monitoring stack first (it provides the CRD)? |
| Kepler pod crashes in kind | Check `kubectl -n kepler logs ds/kepler`. Make sure you used `MODE=kind` (fake meter). |
| Kepler crashes on real nodes | No readable power meter. Check `/sys/class/powercap`, or see the Kepler docs for `hwmon`. |
| No pod-level watts | Pods must be running when Kepler samples. Check `kepler_pod_cpu_watts` for your namespace label `pod_namespace`. |
| HPA shows `<unknown>` | metrics-server is not ready. `kubectl top pods -n demo` should work. |
| Pods `Pending` in BEFORE | Your nodes have fewer than 1 free CPU each. Lower the request in `10-app-before.yaml` (keep it far above real usage). |
| `waste_ratio` is `-` in the results | No request or usage series yet. Wait a few minutes after the rollout and rerun `collect.py`. |

## Files

```
kind/kind-config.yaml                 3 workers
helm/                                 values for kube-prometheus-stack and Kepler (kind, real)
manifests/10-app-before.yaml          6 x (1 CPU, 512Mi): the guess
manifests/20-app-after.yaml           right-sized requests + HPA
manifests/30-loadgen.yaml             constant-rate fortio Job (templated by scripts/30-phase.sh)
dashboards/energy-waste.json          Grafana dashboard (loaded as a ConfigMap)
scripts/                              00 kind, 10 monitoring, 20 kepler, 30 phase, 40 diff, 50 compare, 60 consolidate, 90 teardown
tools/collect.py, tools/compare.py    numbers from Prometheus -> before/after table
tests/test_tools.py                   python3 -m unittest discover -s tests
```
