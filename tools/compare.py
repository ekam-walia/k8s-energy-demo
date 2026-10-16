#!/usr/bin/env python3
"""Print the before/after result table (Markdown) from two collect.py JSON files."""
import argparse
import json

# key, label, format, "lower is better" hint used only for the arrow
ROWS = [
    ("replicas", "Replicas (avg)", "{:.1f}"),
    ("requested_cpu_cores", "Requested CPU (cores)", "{:.2f}"),
    ("used_cpu_cores", "Used CPU (cores)", "{:.2f}"),
    ("waste_ratio", "Waste ratio (CPU)", "{:.0%}"),
    ("requested_mem_gib", "Requested memory (GiB)", "{:.2f}"),
    ("used_mem_gib", "Used memory (GiB)", "{:.2f}"),
    ("requested_node_equiv", "Requested CPU, node-equivalents", "{:.2f}"),
    ("nodes_with_demo_pods", "Nodes running demo pods", "{:.0f}"),
    ("pod_watts", "Demo pods power (W, avg)", "{:.2f}"),
    ("node_active_watts", "Nodes active power (W, avg)", "{:.2f}"),
    ("node_idle_watts", "Nodes idle power (W, avg)", "{:.2f}"),
    ("pod_energy_wh", "Demo pods energy (Wh over window)", "{:.3f}"),
    ("node_energy_wh", "All nodes energy (Wh over window)", "{:.3f}"),
    ("restarts", "Pod restarts (total)", "{:.0f}"),
    ("oomkilled", "OOMKilled containers", "{:.0f}"),
]


def fmt(fmtstr, v):
    return "-" if v is None else fmtstr.format(v)


def change(b, a, key):
    if b is None or a is None:
        return "-"
    if key == "waste_ratio":
        return f"{(a - b) * 100:+.0f} pts"
    if b == 0:
        return "0" if a == 0 else f"+{a:g}"
    return f"{(a - b) / b * 100:+.0f}%"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("before")
    ap.add_argument("after")
    a = ap.parse_args(argv)
    with open(a.before) as fb, open(a.after) as fa:
        b, af = json.load(fb), json.load(fa)

    lines = ["| Metric | Before | After | Change |", "| --- | --- | --- | --- |"]
    for key, label, f in ROWS:
        bv, av = b["values"].get(key), af["values"].get(key)
        if bv is None and av is None:
            continue
        lines.append(f"| {label} | {fmt(f, bv)} | {fmt(f, av)} | {change(bv, av, key)} |")
    print("\n".join(lines))
    print(f"\nWindow: before={b['window']}, after={af['window']}. Kepler zone: before={b['zone']}, after={af['zone']}.")
    if b["zone"] != af["zone"]:
        print("WARNING: the Kepler zone differs between runs; power and energy rows are not comparable.")


if __name__ == "__main__":
    main()
