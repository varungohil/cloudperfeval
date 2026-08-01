"""Tests for coalescing same-service peer-scoped Pumba delays."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from cloudperfeval.fault.pumba import (
    FaultInjectionError,
    FaultSpec,
    PumbaInjector,
    delay_coalesce_key,
    group_specs_for_inject,
)


def _delay(peer: str, *, decoy: bool = False, delay_ms: int = 50) -> FaultSpec:
    return FaultSpec(
        "delay",
        "frontend",
        peer_service=peer,
        delay_ms=delay_ms,
        jitter_ms=1,
        ingress_port=9090,
        decoy=decoy,
    )


class TestGroupSpecsForInject(unittest.TestCase):
    def test_coalesces_same_service_peer_delays(self):
        home = _delay("home-timeline-service")
        user = _delay("user-timeline-service", decoy=True)
        groups = group_specs_for_inject([home, user])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], [home, user])

    def test_merges_across_intervening_cpu(self):
        home = _delay("home-timeline-service")
        cpu = FaultSpec("cpu", "home-timeline-service", cpu_workers=30)
        user = _delay("user-timeline-service")
        groups = group_specs_for_inject([home, cpu, user])
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], [home, user])
        self.assertEqual(groups[1], [cpu])

    def test_different_delay_ms_not_coalesced(self):
        a = _delay("home-timeline-service", delay_ms=50)
        b = _delay("user-timeline-service", delay_ms=100)
        groups = group_specs_for_inject([a, b])
        self.assertEqual(len(groups), 2)

    def test_unscoped_delay_not_coalesced(self):
        scoped = _delay("home-timeline-service")
        unscoped = FaultSpec("delay", "frontend", delay_ms=50, jitter_ms=1)
        self.assertIsNone(delay_coalesce_key(unscoped))
        groups = group_specs_for_inject([scoped, unscoped])
        self.assertEqual(len(groups), 2)

    def test_different_services_not_coalesced(self):
        a = FaultSpec(
            "delay",
            "frontend",
            peer_service="home-timeline-service",
            delay_ms=50,
            jitter_ms=1,
            ingress_port=9090,
        )
        b = FaultSpec(
            "delay",
            "home-timeline-service",
            peer_service="post-storage-service",
            delay_ms=50,
            jitter_ms=1,
            ingress_port=9090,
        )
        groups = group_specs_for_inject([a, b])
        self.assertEqual(len(groups), 2)


class TestCompatibleDelayGroups(unittest.TestCase):
    def test_incompatible_same_service_raises(self):
        groups = group_specs_for_inject(
            [
                _delay("home-timeline-service", delay_ms=50),
                _delay("user-timeline-service", delay_ms=100),
            ]
        )
        with self.assertRaises(FaultInjectionError) as ctx:
            PumbaInjector._check_compatible_delay_groups(groups)
        self.assertIn("incompatible delay", str(ctx.exception))

    def test_coalesced_group_ok(self):
        groups = group_specs_for_inject(
            [
                _delay("home-timeline-service"),
                _delay("user-timeline-service"),
            ]
        )
        PumbaInjector._check_compatible_delay_groups(groups)


class TestMultiTargetPumbaArgs(unittest.TestCase):
    def test_pumba_args_repeats_target_for_peers(self):
        inj = PumbaInjector()
        inj.swarm = MagicMock()
        inj._resolve_peer_targets = MagicMock(
            side_effect=lambda peer: {
                "home-timeline-service": ["10.0.0.1"],
                "user-timeline-service": ["10.0.0.2"],
            }[peer]
        )
        inj._target_regex = MagicMock(return_value="re2:^/?sn_frontend\\.")
        inj._pumba_bin = MagicMock(return_value="pumba")

        spec = _delay("home-timeline-service")
        cmd = inj._pumba_args(
            spec,
            netem_interface="eth2",
            peer_services=["home-timeline-service", "user-timeline-service"],
        )
        self.assertIn("--target 10.0.0.1", cmd)
        self.assertIn("--target 10.0.0.2", cmd)
        self.assertIn("--ingress-port 9090", cmd)
        self.assertIn("--interface eth2", cmd)
        self.assertIn("delay --time 50 --jitter 1", cmd)
        self.assertEqual(cmd.count("--target "), 2)


if __name__ == "__main__":
    unittest.main()
