"""Tests for the Jaeger span-dropping proxy."""

from __future__ import annotations

import json
import random
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen

from cloudperfeval.agents.jaeger_proxy import (
    JaegerFaultProxy,
    JaegerProxySpec,
    drop_spans_in_response,
    jaeger_proxy_timeout_from_config,
    _should_mutate,
)
from cloudperfeval.config import config
from cloudperfeval.fault.pumba import FaultSpec
from cloudperfeval.problems.base import PerformanceProblem
from cloudperfeval.tasks.resource_diagnosis import ResourceDiagnosis
from cloudperfeval.workload.generator import WorkloadSpec


def _trace(spans: list[dict], processes: dict | None = None) -> dict:
    return {
        "data": [
            {
                "traceID": "abc",
                "spans": spans,
                "processes": processes
                or {
                    "p1": {"serviceName": "frontend"},
                    "p2": {"serviceName": "home-timeline-service"},
                },
            }
        ],
        "total": 0,
        "limit": 0,
        "offset": 0,
        "errors": None,
    }


class DropSpansTests(unittest.TestCase):
    def test_no_filters_keeps_all(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "RedisGet"},
            ]
        )
        out = drop_spans_in_response(body, 1.0, random.Random(0))
        self.assertEqual(out, body)

    def test_operations_always_dropped_even_at_zero_prob(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "RedisGet"},
                {"spanID": "3", "processID": "p2", "operationName": "ReadHomeTimeline"},
            ]
        )
        out = drop_spans_in_response(
            body, 0.0, random.Random(0), operations=["RedisGet"]
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1", "3"])

    def test_services_dropped_with_probability(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
                {"spanID": "3", "processID": "p2", "operationName": "RedisGet"},
            ]
        )
        out = drop_spans_in_response(
            body, 1.0, random.Random(0), services=["home-timeline-service"]
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_service_drop_prob_zero_keeps_service_spans(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
            ]
        )
        out = drop_spans_in_response(
            body, 0.0, random.Random(0), services=["home-timeline-service"]
        )
        self.assertEqual(out, body)

    def test_seeded_service_drop_is_deterministic(self) -> None:
        spans = [
            {
                "spanID": str(i),
                "processID": "p2",
                "operationName": f"op{i}",
            }
            for i in range(20)
        ]
        a = drop_spans_in_response(
            _trace(spans),
            0.5,
            random.Random(42),
            services=["home-timeline-service"],
        )
        b = drop_spans_in_response(
            _trace(spans),
            0.5,
            random.Random(42),
            services=["home-timeline-service"],
        )
        self.assertEqual(a, b)
        self.assertLess(len(a["data"][0]["spans"]), 20)
        self.assertGreater(len(a["data"][0]["spans"]), 0)

    def test_operations_always_and_services_probabilistic(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "RedisGet"},
                {"spanID": "3", "processID": "p2", "operationName": "ReadHomeTimeline"},
                {"spanID": "4", "processID": "p1", "operationName": "RedisGet"},
            ]
        )
        # RedisGet always dropped; remaining home-timeline spans dropped with p=1.
        out = drop_spans_in_response(
            body,
            1.0,
            random.Random(0),
            services=["home-timeline-service"],
            operations=["RedisGet"],
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_per_service_rates_applied_independently(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
            ]
        )
        # frontend never dropped, home-timeline always dropped.
        out = drop_spans_in_response(
            body,
            0.0,
            random.Random(0),
            services={"frontend": 0.0, "home-timeline-service": 1.0},
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_per_service_rates_ignore_shared_drop_prob(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
            ]
        )
        # Mapping wins: frontend keeps rate 0 even though drop_prob is 1.
        out = drop_spans_in_response(
            body,
            1.0,
            random.Random(0),
            services={"frontend": 0.0, "home-timeline-service": 1.0},
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_list_services_fall_back_to_drop_prob(self) -> None:
        body = _trace(
            [
                {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
                {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
            ]
        )
        out = drop_spans_in_response(
            body, 1.0, random.Random(0), services=["home-timeline-service"]
        )
        kept_ids = [s["spanID"] for s in out["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_invalid_service_rate_raises(self) -> None:
        with self.assertRaises(ValueError):
            drop_spans_in_response(
                _trace([]), 0.0, random.Random(0), services={"frontend": 1.5}
            )

    def test_should_mutate_only_trace_gets(self) -> None:
        self.assertTrue(_should_mutate("GET", "/api/traces"))
        self.assertTrue(_should_mutate("GET", "/api/traces?service=x"))
        self.assertTrue(_should_mutate("GET", "/api/traces/deadbeef"))
        self.assertFalse(_should_mutate("GET", "/api/services"))
        self.assertFalse(_should_mutate("HEAD", "/api/traces"))
        self.assertFalse(_should_mutate("POST", "/api/traces"))


class _FakeJaeger(BaseHTTPRequestHandler):
    payload: bytes = b"{}"

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class JaegerFaultProxyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        spans = [
            {
                "spanID": str(i),
                "processID": "p2",
                "operationName": f"op{i}",
            }
            for i in range(10)
        ]
        _FakeJaeger.payload = json.dumps(_trace(spans)).encode("utf-8")
        self.upstream = HTTPServer(("127.0.0.1", 0), _FakeJaeger)
        self.upstream_thread = threading.Thread(
            target=self.upstream.serve_forever, daemon=True
        )
        self.upstream_thread.start()
        self.backend_url = f"http://127.0.0.1:{self.upstream.server_address[1]}"

    def tearDown(self) -> None:
        self.upstream.shutdown()
        self.upstream.server_close()
        self.upstream_thread.join(timeout=5)

    def test_proxy_drops_service_spans_on_traces_endpoint(self) -> None:
        with JaegerFaultProxy(
            self.backend_url,
            drop_prob=1.0,
            services=["home-timeline-service"],
            seed=1,
            host="127.0.0.1",
        ) as proxy:
            with urlopen(f"{proxy.public_url}/api/traces?service=frontend", timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["data"][0]["spans"], [])

    def test_proxy_honors_per_service_rates(self) -> None:
        spans = [
            {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
            {"spanID": "2", "processID": "p2", "operationName": "ReadHomeTimeline"},
        ]
        _FakeJaeger.payload = json.dumps(_trace(spans)).encode("utf-8")
        with JaegerFaultProxy(
            self.backend_url,
            services={"frontend": 0.0, "home-timeline-service": 1.0},
            seed=1,
            host="127.0.0.1",
        ) as proxy:
            self.assertEqual(
                proxy.service_rates,
                {"frontend": 0.0, "home-timeline-service": 1.0},
            )
            with urlopen(f"{proxy.public_url}/api/traces?service=frontend", timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        kept_ids = [s["spanID"] for s in body["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_proxy_always_drops_operations(self) -> None:
        spans = [
            {"spanID": "1", "processID": "p1", "operationName": "GetHome"},
            {"spanID": "2", "processID": "p2", "operationName": "RedisGet"},
        ]
        _FakeJaeger.payload = json.dumps(_trace(spans)).encode("utf-8")
        with JaegerFaultProxy(
            self.backend_url,
            drop_prob=0.0,
            operations=["RedisGet"],
            seed=1,
            host="127.0.0.1",
        ) as proxy:
            with urlopen(f"{proxy.public_url}/api/traces?service=frontend", timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        kept_ids = [s["spanID"] for s in body["data"][0]["spans"]]
        self.assertEqual(kept_ids, ["1"])

    def test_proxy_passthrough_non_trace_paths(self) -> None:
        _FakeJaeger.payload = json.dumps({"data": ["frontend", "jaeger-query"]}).encode(
            "utf-8"
        )
        with JaegerFaultProxy(
            self.backend_url, drop_prob=1.0, seed=1, host="127.0.0.1"
        ) as proxy:
            with urlopen(f"{proxy.public_url}/api/services", timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(body["data"], ["frontend", "jaeger-query"])

    def test_drop_prob_validation(self) -> None:
        with self.assertRaises(ValueError):
            JaegerFaultProxy("http://127.0.0.1:16686", drop_prob=1.5)

    def test_container_url_uses_host_docker_internal(self) -> None:
        with JaegerFaultProxy(
            self.backend_url, drop_prob=0.0, host="127.0.0.1"
        ) as proxy:
            self.assertTrue(
                proxy.container_url().startswith("http://host.docker.internal:")
            )
            self.assertIn(str(proxy.listen_port), proxy.container_url())


class JaegerProxySpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = config.get("agent_sandbox")

    def tearDown(self) -> None:
        config.set("agent_sandbox", self.previous)

    def test_from_value_none_means_no_proxy(self) -> None:
        self.assertIsNone(JaegerProxySpec.from_value(None))

    def test_from_value_parses_dict(self) -> None:
        spec = JaegerProxySpec.from_value(
            {
                "drop_prob": 0.25,
                "services": ["home-timeline-service", "frontend"],
                "operations": "RedisGet, MemcachedGet",
                "seed": 7,
            }
        )
        assert spec is not None
        self.assertEqual(spec.drop_prob, 0.25)
        self.assertEqual(spec.services, ("home-timeline-service", "frontend"))
        # List form inherits the shared drop_prob for every service.
        self.assertEqual(
            spec.service_rates,
            {"home-timeline-service": 0.25, "frontend": 0.25},
        )
        self.assertEqual(spec.operations, ("RedisGet", "MemcachedGet"))
        self.assertEqual(spec.seed, 7)

    def test_spec_accepts_per_service_rates(self) -> None:
        spec = JaegerProxySpec(
            services={"home-timeline-service": 0.5, "post-storage-service": 0.1},
        )
        self.assertEqual(
            spec.service_rates,
            {"home-timeline-service": 0.5, "post-storage-service": 0.1},
        )
        self.assertEqual(
            sorted(spec.services), ["home-timeline-service", "post-storage-service"]
        )

    def test_spec_rejects_out_of_range_service_rate(self) -> None:
        with self.assertRaises(ValueError):
            JaegerProxySpec(services={"frontend": 2.0})

    def test_invalid_drop_prob_raises(self) -> None:
        with self.assertRaises(ValueError):
            JaegerProxySpec(drop_prob=1.5)

    def test_timeout_from_config(self) -> None:
        config.set("agent_sandbox", {"jaeger_proxy": {"timeout": 12}})
        self.assertEqual(jaeger_proxy_timeout_from_config(), 12.0)
        config.set("agent_sandbox", {})
        self.assertEqual(jaeger_proxy_timeout_from_config(), 60.0)

    def test_problem_defaults_to_no_jaeger_proxy(self) -> None:
        problem = PerformanceProblem(
            problem_id="test.no_proxy",
            fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=1),
            workload=WorkloadSpec(mode="sustained", endpoint="/x"),
            task=ResourceDiagnosis(endpoint="/x"),
            bottleneck_service="home-timeline-service",
        )
        self.assertIsNone(problem.jaeger_proxy)

    def test_problem_accepts_jaeger_proxy_spec(self) -> None:
        problem = PerformanceProblem(
            problem_id="test.with_proxy",
            fault=FaultSpec("cpu", "home-timeline-service", cpu_workers=1),
            workload=WorkloadSpec(mode="sustained", endpoint="/x"),
            task=ResourceDiagnosis(endpoint="/x"),
            bottleneck_service="home-timeline-service",
            jaeger_proxy={
                "drop_prob": 0.4,
                "services": ["home-timeline-service"],
                "operations": ["RedisGet"],
                "seed": 3,
            },
        )
        assert problem.jaeger_proxy is not None
        self.assertEqual(problem.jaeger_proxy.drop_prob, 0.4)
        self.assertEqual(problem.jaeger_proxy.services, ("home-timeline-service",))
        self.assertEqual(problem.jaeger_proxy.operations, ("RedisGet",))
        self.assertEqual(problem.jaeger_proxy.seed, 3)


if __name__ == "__main__":
    unittest.main()
