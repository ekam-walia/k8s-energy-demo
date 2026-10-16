"""Tests for tools/collect.py and tools/compare.py using a mock Prometheus. Run: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import collect  # noqa: E402
import compare  # noqa: E402


def make_handler(answers, seen):
    """answers: list of (substring, value-or-None). First substring found in the query wins."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)["query"][0]
            seen.append(q)
            result = []
            for sub, val in answers:
                if sub in q:
                    if val is not None:
                        if isinstance(val, dict):  # per-zone vector
                            result = [{"metric": {"zone": z}, "value": [0, str(v)]} for z, v in val.items()]
                        else:
                            result = [{"metric": {}, "value": [0, str(val)]}]
                    break
            body = json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    return H


@contextlib.contextmanager
def mock_prom(answers):
    seen = []
    srv = HTTPServer(("127.0.0.1", 0), make_handler(answers, seen))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}", seen
    finally:
        srv.shutdown()


# Order matters: most specific substring first.
BEFORE = [
    ("avg by (zone)", {"package": 12.0, "core": 5.0}),
    ("kube_deployment_status_replicas_available", 6),
    ("kube_pod_container_resource_requests{namespace=\"demo\",resource=\"memory\"}", 6.0),
    ("container_memory_working_set_bytes", 0.5),
    ("kube_node_status_allocatable", 1.5),
    ("kube_pod_container_resource_requests", 6.0),
    ("container_cpu_usage_seconds_total", 0.5),
    ("kube_pod_info", 3),
    ("kube_pod_container_status_restarts_total", 0),
    ("kube_pod_container_status_last_terminated_reason", 0),
    ("kepler_pod_cpu_watts", 1.2),
    ("kepler_node_cpu_active_watts", 4.0),
    ("kepler_node_cpu_idle_watts", 8.0),
    ("kepler_node_cpu_watts", 12.0),
    ("kepler_pod_cpu_joules_total", 0.4),
    ("kepler_node_cpu_joules_total", 4.3),
]


class CollectTests(unittest.TestCase):
    def run_collect(self, answers, label="before", extra=()):
        with mock_prom(answers) as (url, seen), tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, f"{label}.json")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                collect.main(["--prom", url, "--label", label, "--out", out, *extra])
            with open(out) as f:
                return json.load(f), seen

    def test_collects_values_and_waste_ratio(self):
        res, seen = self.run_collect(BEFORE)
        v = res["values"]
        self.assertEqual(res["zone"], "package")
        self.assertEqual(v["replicas"], 6)
        self.assertAlmostEqual(v["waste_ratio"], 1 - 0.5 / 6.0)
        self.assertEqual(v["pod_watts"], 1.2)
        self.assertEqual(v["nodes_with_demo_pods"], 3)
        self.assertTrue(any('zone="package"' in q for q in seen))

    def test_zone_fallback_to_highest_power_when_no_package(self):
        answers = [("avg by (zone)", {"core": 5.0, "dram": 2.0})] + BEFORE[1:]
        res, seen = self.run_collect(answers)
        self.assertEqual(res["zone"], "core")
        self.assertTrue(any('zone="core"' in q for q in seen))

    def test_explicit_zone_skips_detection(self):
        res, seen = self.run_collect(BEFORE, extra=["--zone", "dram"])
        self.assertEqual(res["zone"], "dram")
        self.assertFalse(any(q.startswith("avg by (zone)") for q in seen))

    def test_no_kepler_gives_empty_power_values(self):
        answers = [("avg by (zone)", None)] + [a for a in BEFORE[1:] if "kepler" not in a[0]]
        res, _ = self.run_collect(answers)
        self.assertIsNone(res["zone"])
        self.assertNotIn("pod_watts", res["values"])
        self.assertIsNotNone(res["values"]["requested_cpu_cores"])

    def test_empty_result_is_none_and_waste_none(self):
        answers = [("avg by (zone)", None), ("kube_pod_container_resource_requests", None)] + BEFORE[1:]
        res, _ = self.run_collect(answers)
        self.assertIsNone(res["values"]["requested_cpu_cores"])
        self.assertIsNone(res["values"]["waste_ratio"])


class CompareTests(unittest.TestCase):
    def table(self, b, a):
        with tempfile.TemporaryDirectory() as d:
            pb, pa = os.path.join(d, "b.json"), os.path.join(d, "a.json")
            for path, data in ((pb, b), (pa, a)):
                with open(path, "w") as f:
                    json.dump(data, f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                compare.main([pb, pa])
            return buf.getvalue()

    def test_table_and_changes(self):
        b = {"label": "before", "window": "6m", "zone": "package",
             "values": {"requested_cpu_cores": 6.0, "used_cpu_cores": 0.5, "waste_ratio": 0.9167, "nodes_with_demo_pods": 3,
                        "restarts": 0, "pod_watts": 1.0}}
        a = {"label": "after", "window": "6m", "zone": "package",
             "values": {"requested_cpu_cores": 0.3, "used_cpu_cores": 0.5, "waste_ratio": 0.0, "nodes_with_demo_pods": 2,
                        "restarts": 0, "pod_watts": 1.0}}
        out = self.table(b, a)
        self.assertIn("| Requested CPU (cores) | 6.00 | 0.30 | -95% |", out)
        self.assertIn("| Waste ratio (CPU) | 92% | 0% | -92 pts |", out)
        self.assertIn("| Nodes running demo pods | 3 | 2 | -33% |", out)
        self.assertIn("| Pod restarts (total) | 0 | 0 | 0 |", out)
        self.assertNotIn("WARNING", out)

    def test_zone_mismatch_warns_and_missing_rows_hidden(self):
        b = {"label": "b", "window": "6m", "zone": "package", "values": {"pod_watts": 1.0, "node_idle_watts": None}}
        a = {"label": "a", "window": "6m", "zone": "core", "values": {"pod_watts": 2.0, "node_idle_watts": None}}
        out = self.table(b, a)
        self.assertIn("WARNING", out)
        self.assertNotIn("idle power", out)


if __name__ == "__main__":
    unittest.main()
