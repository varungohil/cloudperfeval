"""Pumba-based fault injection for Docker Swarm.

A `FaultSpec` describes *what* to inject (delay or cpu stress) and *which*
service to target. `PumbaInjector` runs the `pumba` CLI on the node hosting the
target task (resolved from Swarm placement), tracks the background process so it
can be stopped on recover, and cleans up leftovers.

Network delay supports optional scoping:
  - `peer_service`: delay only egress from `target_service` toward that peer
    (pumba netem `--target <peer-vip>`; repeatable for multi-network services).
  - `egress_port` / `ingress_port`: limit delay to matching source/dest ports.

Prerequisite: `pumba` must be installed on every Swarm node (with `tc`/iproute2
for netem faults). The harness does not run Pumba inside Docker.

Pumba reference:
  net delay : pumba netem [--target IP] [--egress-port P] [--ingress-port P]
              --duration D delay --time MS <source-containers>
  stress cpu: pumba stress --duration D --stressors "..." <target>
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from cloudperfeval.config import config
from cloudperfeval.shell import Shell
from cloudperfeval.swarm import SwarmCtl


@dataclass
class FaultSpec:
    fault_type: Literal["delay", "cpu"]
    target_service: str          # source service (delay egress from its containers)

    # network delay params
    delay_ms: int = 300
    jitter_ms: int = 50
    correlation: int = 20
    peer_service: str | None = None       # delay only X -> Y (pumba --target)
    egress_port: int | str | None = None  # pumba --egress-port (source port(s))
    ingress_port: int | str | None = None # pumba --ingress-port (dest port(s))

    # cpu stress params
    cpu_workers: int = 2

    # common
    duration: str = "10m"
    pumba_bin: str = ""

    def __post_init__(self) -> None:
        if self.fault_type != "delay" and (
            self.peer_service or self.egress_port is not None or self.ingress_port is not None
        ):
            raise ValueError(
                "peer_service and port filters are only valid for delay faults"
            )

    def summary(self) -> str:
        if self.fault_type == "delay":
            scope = (
                f"{self.target_service} -> {self.peer_service}"
                if self.peer_service
                else self.target_service
            )
            ports = []
            if self.egress_port is not None:
                ports.append(f"egress-port={self.egress_port}")
            if self.ingress_port is not None:
                ports.append(f"ingress-port={self.ingress_port}")
            port_note = f" ({', '.join(ports)})" if ports else ""
            return (
                f"network delay {self.delay_ms}ms (jitter {self.jitter_ms}ms) "
                f"on {scope}{port_note}"
            )
        return f"cpu stress {self.cpu_workers} worker(s) on {self.target_service}"


def faults_summary(specs: list["FaultSpec"]) -> str:
    """Human-readable summary of one or more fault specs."""
    if not specs:
        return "(no faults)"
    if len(specs) == 1:
        return specs[0].summary()
    return f"{len(specs)} faults: " + "; ".join(s.summary() for s in specs)


class PumbaInjector:
    """Inject and recover Pumba faults via the host-installed pumba binary."""

    def __init__(self):
        self.swarm = SwarmCtl()
        self.stack_name = config.get("stack_name", "")
        self.node_host_map: dict = config.get("node_host_map", {}) or {}
        self.node_domain_suffix = config.get("node_domain_suffix", "")
        self._active: dict[str, str] = {}  # chaos_id -> node_host it runs on

    def _pumba_bin(self, spec: FaultSpec) -> str:
        return os.path.expanduser(
            spec.pumba_bin or config.get("pumba_bin", "pumba")
        )

    def _resolve_node_host(self, service: str) -> str:
        """SSH-reachable host running the target service's task."""
        nodes = self.swarm.running_nodes_for(service)
        if not nodes:
            return config.get("manager_host", "localhost")
        node = nodes[0].split(".", 1)[0]
        if node in self.node_host_map:
            return self.node_host_map[node]
        if self.node_domain_suffix:
            return f"{node}.{self.node_domain_suffix}"
        return nodes[0]

    def _target_regex(self, service: str) -> str:
        qualified = self.swarm.qualified_name(service)
        return f're2:^/?{qualified}\\.'

    def _resolve_peer_targets(self, peer_service: str) -> list[str]:
        cidrs = self.swarm.service_endpoint_cidrs(peer_service)
        if not cidrs:
            raise RuntimeError(
                f"Could not resolve network endpoint for peer service "
                f"{peer_service!r} (need Swarm VIP or running task IP)"
            )
        return cidrs

    def _netem_scope_flags(self, spec: FaultSpec) -> str:
        """Optional pumba netem filters: --target, --egress-port, --ingress-port."""
        flags = ""
        if spec.peer_service:
            for cidr in self._resolve_peer_targets(spec.peer_service):
                flags += f" --target {cidr}"
        if spec.egress_port is not None:
            flags += f" --egress-port {spec.egress_port}"
        if spec.ingress_port is not None:
            flags += f" --ingress-port {spec.ingress_port}"
        return flags

    def _pumba_args(self, spec: FaultSpec) -> str:
        """Pumba subcommand + flags (without nohup/background wrapper)."""
        target = self._target_regex(spec.target_service)
        bin_ = self._pumba_bin(spec)
        if spec.fault_type == "delay":
            return (
                f"{bin_} --log-level info netem --duration {spec.duration}"
                f"{self._netem_scope_flags(spec)} "
                f"delay --time {spec.delay_ms} --jitter {spec.jitter_ms} "
                f"--correlation {spec.correlation} \"{target}\""
            )
        if spec.fault_type == "cpu":
            return (
                f"{bin_} --log-level info stress --duration {spec.duration} "
                f"--stressors \"--cpu {spec.cpu_workers} "
                f"--timeout {self._duration_seconds(spec.duration)}s\" "
                f"\"{target}\""
            )
        raise ValueError(f"Unknown fault_type: {spec.fault_type}")

    @staticmethod
    def _chaos_paths(chaos_id: str) -> tuple[str, str]:
        return f"/tmp/{chaos_id}.pid", f"/tmp/{chaos_id}.log"

    def _start_command(self, spec: FaultSpec, chaos_id: str) -> str:
        pidfile, logfile = self._chaos_paths(chaos_id)
        return (
            f"nohup {self._pumba_args(spec)} >{logfile} 2>&1 & "
            f"pid=$!; echo $pid > {pidfile}; "
            f"sleep 0.5; "
            f"if ! kill -0 $pid 2>/dev/null; then "
            f"echo '[ERROR] Pumba failed to start:'; cat {logfile}; exit 1; "
            f"fi"
        )

    def _stop_command(self, chaos_id: str) -> str:
        pidfile, logfile = self._chaos_paths(chaos_id)
        return (
            f"if [ -f {pidfile} ]; then "
            f"kill $(cat {pidfile}) 2>/dev/null || true; "
            f"rm -f {pidfile} {logfile}; fi"
        )

    @staticmethod
    def _duration_seconds(duration: str) -> int:
        d = duration.strip().lower()
        try:
            if d.endswith("ms"):
                return max(1, int(float(d[:-2]) / 1000))
            if d.endswith("s"):
                return int(float(d[:-1]))
            if d.endswith("m"):
                return int(float(d[:-1]) * 60)
            if d.endswith("h"):
                return int(float(d[:-1]) * 3600)
            return int(float(d))
        except ValueError:
            return 600

    def _inject_one(self, spec: FaultSpec) -> str:
        node_host = self._resolve_node_host(spec.target_service)
        chaos_id = f"cpe-chaos-{spec.fault_type}-{uuid.uuid4().hex[:8]}"
        pumba_cmd = self._pumba_args(spec)
        command = self._start_command(spec, chaos_id)

        print(f"[FAULT] Injecting {spec.summary()}")
        print(f"[FAULT] node: {node_host}")
        print(f"[FAULT] pumba cmd: {pumba_cmd}")
        print(f"[FAULT] remote shell: {command}")

        out = Shell.exec_on_node(node_host, command)
        if out.startswith("[ERROR]"):
            raise RuntimeError(
                f"Failed to start Pumba ({spec.summary()}) on {node_host}: {out}"
            )
        self._active[chaos_id] = node_host
        print(f"[FAULT] Started on node {node_host} (chaos={chaos_id})")
        return chaos_id

    def inject(self, spec: FaultSpec) -> str:
        chaos_id = self._inject_one(spec)
        time.sleep(config.get("fault_settle_seconds", 5))
        return chaos_id

    def inject_all(self, specs: list[FaultSpec]) -> list[str]:
        if not specs:
            return []
        chaos_ids: list[str] = []
        for spec in specs:
            chaos_ids.append(self._inject_one(spec))
        time.sleep(config.get("fault_settle_seconds", 5))
        return chaos_ids

    def recover(self, chaos_id: str | None = None) -> None:
        targets = ([chaos_id] if chaos_id else list(self._active.keys()))
        for name in targets:
            node_host = self._active.get(name, config.get("manager_host", "localhost"))
            Shell.exec_on_node(node_host, self._stop_command(name))
            self._active.pop(name, None)
            print(f"[FAULT] Recovered pumba process {name} on {node_host}")

    def recover_many(self, chaos_ids: list[str]) -> None:
        for cid in chaos_ids:
            self.recover(cid)

    def recover_all(self) -> None:
        self.recover()
        Shell.exec(
            "for f in /tmp/cpe-chaos-*.pid; do "
            "[ -f \"$f\" ] && kill $(cat \"$f\") 2>/dev/null; rm -f \"$f\"; "
            "done; rm -f /tmp/cpe-chaos-*.log"
        )
