#!/usr/bin/env python3
"""Collect the numbers for one demo phase (before/after) from Prometheus.

Averages every gauge over the last --window, and uses increase() for energy, so the
two phases are compared on the same footing. Output is a small JSON file that
compare.py turns into the result table for your slide.

Standard library only.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

STEP = "30s"


def query(prom, expr):
    url = f"{prom.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, timeout=30) as r:
        body = json.load(r)
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus error for {expr!r}: {body}")
    return body["data"]["result"]


def scalar(prom, expr):
    """First value of an instant query as float, or None if the result is empty/NaN."""
    res = query(prom, expr)
    if not res:
        return None
    v = float(res[0]["value"][1])
    return None if v != v else v


def avg(expr, window):
    return f"avg_over_time(({expr})[{window}:{STEP}])"


def detect_zone(prom, window):
    """Pick the Kepler RAPL-style zone to use. Prefer 'package'; else the zone with the highest power."""
    res = query(prom, f"avg by (zone)(avg_over_time(kepler_node_cpu_watts[{window}]))")
    zones = {r["metric"].get("zone", ""): float(r["value"][1]) for r in res}
    if not zones:
        return None
    if "package" in zones:
        return "package"
    return max(zones, key=zones.get)


def build_queries(ns, zone, window):
    req_cpu = f'sum(kube_pod_container_resource_requests{{namespace="{ns}",resource="cpu"}})'
    used_cpu = f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",container!="",container!="POD"}}[2m]))'
    req_mem = f'sum(kube_pod_container_resource_requests{{namespace="{ns}",resource="memory"}})'
    used_mem = f'sum(container_memory_working_set_bytes{{namespace="{ns}",container!="",container!="POD"}})'
    alloc = 'avg(kube_node_status_allocatable{resource="cpu"})'
    q = {
        "replicas": avg(f'sum(kube_deployment_status_replicas_available{{namespace="{ns}",deployment="demo-app"}})', window),
        "requested_cpu_cores": avg(req_cpu, window),
        "used_cpu_cores": avg(used_cpu, window),
        "requested_mem_gib": avg(f"({req_mem}) / 1024^3", window),
        "used_mem_gib": avg(f"({used_mem}) / 1024^3", window),
        "requested_node_equiv": avg(f"({req_cpu}) / {alloc}", window),
        "used_node_equiv": avg(f"({used_cpu}) / {alloc}", window),
        "nodes_with_demo_pods": f'count(count by (node)(kube_pod_info{{namespace="{ns}",pod=~"demo-app-.*"}}))',
        "restarts": f'sum(kube_pod_container_status_restarts_total{{namespace="{ns}"}})',
        "oomkilled": f'sum(kube_pod_container_status_last_terminated_reason{{namespace="{ns}",reason="OOMKilled"}}) or vector(0)',
    }
    if zone:
        q.update({
            "pod_watts": avg(f'sum(kepler_pod_cpu_watts{{pod_namespace="{ns}",zone="{zone}"}})', window),
            "node_active_watts": avg(f'sum(kepler_node_cpu_active_watts{{zone="{zone}"}})', window),
            "node_idle_watts": avg(f'sum(kepler_node_cpu_idle_watts{{zone="{zone}"}})', window),
            "node_total_watts": avg(f'sum(kepler_node_cpu_watts{{zone="{zone}"}})', window),
            "pod_energy_wh": f'sum(increase(kepler_pod_cpu_joules_total{{pod_namespace="{ns}",zone="{zone}"}}[{window}])) / 3600',
            "node_energy_wh": f'sum(increase(kepler_node_cpu_joules_total{{zone="{zone}"}}[{window}])) / 3600',
        })
    return q


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prom", default="http://localhost:9090", help="Prometheus base URL")
    ap.add_argument("--label", required=True, help="phase name, e.g. before or after")
    ap.add_argument("--window", default="6m", help="averaging window ending now (default 6m)")
    ap.add_argument("--namespace", default="demo")
    ap.add_argument("--zone", default="auto", help="Kepler zone label, or 'auto' (default)")
    ap.add_argument("--out", required=True, help="output JSON path")
    a = ap.parse_args(argv)

    zone = detect_zone(a.prom, a.window) if a.zone == "auto" else a.zone
    if not zone:
        print("WARNING: no kepler_node_cpu_watts series found; Kepler metrics will be empty.", file=sys.stderr)

    values = {}
    for name, expr in build_queries(a.namespace, zone, a.window).items():
        try:
            values[name] = scalar(a.prom, expr)
        except Exception as e:  # keep going so one bad query doesn't lose the whole run
            print(f"WARNING: query {name} failed: {e}", file=sys.stderr)
            values[name] = None

    req, used = values.get("requested_cpu_cores"), values.get("used_cpu_cores")
    values["waste_ratio"] = (1 - used / req) if req and used is not None else None

    out = {"label": a.label, "window": a.window, "zone": zone, "namespace": a.namespace, "values": values}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"saved {a.out} (zone={zone}, window={a.window})")


if __name__ == "__main__":
    main()
