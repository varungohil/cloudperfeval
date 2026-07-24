"""Fault injection for Docker Swarm (Pumba + connection-pool limits).

A `FaultSpec` describes *what* to inject and *which* service to target.
Supported fault types:
  - ``delay`` / ``cpu`` / ``icache``: Pumba on the node hosting the target task
  - ``icache_burst``: host ``stress-ng --icache`` burst+sleep loop pinned to the
    core running the target task (lower average CPU than continuous Pumba stress)
  - ``connections``: shrink a Thrift/client pool in ``service-config.json`` for
    ``target_service`` toward ``peer_service`` (Seer Case B–style backpressure).
    Optional ``also_restart`` force-updates parent/caller services after the
    target config swap so they drop stale VIP/Thrift connections.

Network delay supports optional scoping:
  - `peer_service`: delay only egress from `target_service` toward that peer
    (pumba netem `--target <peer-ip>`; CIDR suffixes from Swarm are stripped).
  - `egress_port` / `ingress_port`: limit delay to matching source/dest ports.

``cpu`` and ``icache`` run a stress-ng sidecar under the target container's
cgroup via ``pumba stress`` (``--cpu`` / ``--icache`` stressors). This competes
for the target's CPU quota; microarchitectural interference (including L1i
thrashing) is incidental to shared scheduling, not explicit core pinning.

For netem faults the egress interface is auto-detected by running
`ip route get <peer-ip>` inside the target task's network namespace (Swarm
overlay traffic often uses eth2, not Pumba's default eth0).

Prerequisite: `pumba` must be installed on every Swarm node (with `tc`/iproute2
for netem faults). ``icache_burst`` requires ``stress-ng`` on worker nodes.
The harness does not run Pumba inside Docker.

Pumba reference:
  net delay : pumba netem [--target IP] [--egress-port P] [--ingress-port P]
              --duration D delay --time MS <source-containers>
  stress    : pumba stress --duration D --stressors "..." <target>
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cloudperfeval.config import config
from cloudperfeval.shell import Shell
from cloudperfeval.swarm import SwarmCtl

_SERVICE_CONFIG_MOUNT = (
    "/social-network-microservices/config/service-config.json"
)


class FaultInjectionError(RuntimeError):
    """Pumba failed to start or its /tmp log shows the fault did not apply."""


_PUMBA_LOG_FAIL = (
    re.compile(r'level=warning msg="no containers found"'),
    re.compile(r"level=error\b"),
    re.compile(r"level=fatal\b"),
)
_STRESS_LOG_OK = re.compile(r'level=info msg="stress testing container"')
_PUMBA_LOG_OK = {
    "delay": re.compile(r'level=info msg="running netem on container"'),
    "cpu": _STRESS_LOG_OK,
    "icache": _STRESS_LOG_OK,
}
_ICACHE_BURST_LOG_OK = re.compile(r"\[FAULT\] icache burst loop started")
_STRESS_FAULT_TYPES = frozenset({"cpu", "icache"})
_PUMBA_CONTAINER_NAME = re.compile(r"name=(/\S+)")
_ROUTE_DEV_RE = re.compile(r"(?:\d+\.\d+\.\d+\.\d+|default)\s+dev\s+(\S+)")


def parse_route_interface(route_get_output: str) -> str | None:
    """Parse `dev <iface>` from `ip route get` output."""
    match = _ROUTE_DEV_RE.search(route_get_output)
    return match.group(1) if match else None


def container_names_from_log(log: str) -> list[str]:
    """Container names Pumba touched, parsed from its log file."""
    seen: set[str] = set()
    names: list[str] = []
    for name in _PUMBA_CONTAINER_NAME.findall(log):
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def verify_pumba_log(log: str, spec: FaultSpec) -> None:
    """Raise FaultInjectionError when Pumba's log shows the fault did not apply."""
    text = log.strip()
    if not text:
        raise FaultInjectionError(
            f"Pumba log is empty for {spec.summary()} "
            f"(no matching container or netem/stress did not run)"
        )

    for pattern in _PUMBA_LOG_FAIL:
        if pattern.search(text):
            raise FaultInjectionError(
                f"Pumba reported failure for {spec.summary()}: {text}"
            )

    ok_pattern = _PUMBA_LOG_OK.get(spec.fault_type)
    if ok_pattern and not ok_pattern.search(text):
        raise FaultInjectionError(
            f"Pumba log for {spec.summary()} missing expected success line: {text}"
        )


def verify_icache_burst_log(log: str, spec: FaultSpec) -> None:
    """Raise FaultInjectionError when the burst loop did not start or run."""
    text = log.strip()
    if not text or not _ICACHE_BURST_LOG_OK.search(text):
        raise FaultInjectionError(
            f"icache burst log for {spec.summary()} missing start marker: {text!r}"
        )
    if re.search(r"command not found|No such file|cannot execute", text, re.I):
        raise FaultInjectionError(
            f"icache burst stress-ng failed for {spec.summary()}: {text}"
        )


@dataclass
class FaultSpec:
    fault_type: Literal["delay", "cpu", "icache", "icache_burst", "connections"]
    target_service: str          # source service (delay egress / pool owner)

    # network delay params
    delay_ms: int = 300
    jitter_ms: int = 50
    correlation: int = 20
    peer_service: str | None = None       # delay only X -> Y (pumba --target)
    egress_port: int | str | None = None  # pumba --egress-port (source port(s))
    ingress_port: int | str | None = None # pumba --ingress-port (dest port(s))

    # stress-ng params (cpu / icache / icache_burst)
    cpu_workers: int = 2
    icache_workers: int = 2
    icache_burst_ms: int = 50
    icache_sleep_ms: int = 200

    # connection-pool limit params (service-config.json ClientPool max size)
    connections: int = 1
    # After the target service is restarted for a connections fault, also
    # force-update these caller/parent services so they drop stale VIP/Thrift
    # connections (otherwise e.g. frontend keeps hitting a dead home-timeline).
    also_restart: list[str] = field(default_factory=list)

    # common
    duration: str = "10m"
    pumba_bin: str = ""
    # Injected for red-herring telemetry, but excluded from ground truth /
    # grading. Use for off-path stress that should not affect endpoint latency.
    decoy: bool = False

    def __post_init__(self) -> None:
        if self.fault_type in _STRESS_FAULT_TYPES and (
            self.peer_service
            or self.egress_port is not None
            or self.ingress_port is not None
        ):
            raise ValueError(
                "peer_service and port filters are only valid for delay faults"
            )
        if self.fault_type == "cpu" and self.cpu_workers < 1:
            raise ValueError("cpu_workers must be >= 1")
        if self.fault_type == "icache" and self.icache_workers < 1:
            raise ValueError("icache_workers must be >= 1")
        if self.fault_type == "icache_burst":
            if self.icache_workers < 1:
                raise ValueError("icache_workers must be >= 1")
            if self.icache_burst_ms < 1:
                raise ValueError("icache_burst_ms must be >= 1")
            if self.icache_sleep_ms < 0:
                raise ValueError("icache_sleep_ms must be >= 0")
            if (
                self.peer_service
                or self.egress_port is not None
                or self.ingress_port is not None
            ):
                raise ValueError(
                    "peer_service and port filters are only valid for delay faults"
                )
        if self.fault_type == "connections":
            if not self.peer_service:
                raise ValueError(
                    "peer_service is required for connections faults "
                    "(config key whose client-pool size is reduced)"
                )
            if self.connections < 1:
                raise ValueError("connections must be >= 1")
            if self.egress_port is not None or self.ingress_port is not None:
                raise ValueError(
                    "port filters are only valid for delay faults"
                )

    def summary(self) -> str:
        decoy_note = " [decoy]" if self.decoy else ""
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
                f"on {scope}{port_note}{decoy_note}"
            )
        if self.fault_type == "connections":
            return (
                f"client-pool connections={self.connections} on "
                f"{self.target_service} -> {self.peer_service}{decoy_note}"
            )
        if self.fault_type == "icache":
            return (
                f"icache stress {self.icache_workers} worker(s) on "
                f"{self.target_service}{decoy_note}"
            )
        if self.fault_type == "icache_burst":
            return (
                f"icache burst {self.icache_workers} worker(s), "
                f"{self.icache_burst_ms}ms burst / {self.icache_sleep_ms}ms sleep, "
                f"pinned to {self.target_service} core{decoy_note}"
            )
        return (
            f"cpu stress {self.cpu_workers} worker(s) on "
            f"{self.target_service}{decoy_note}"
        )


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
        self._active: dict[str, str] = {}  # chaos_id -> node_host (pumba) or manager
        # connections faults: chaos_id -> restore metadata
        self._conn_meta: dict[str, dict] = {}

    def _pumba_bin(self, spec: FaultSpec) -> str:
        return os.path.expanduser(
            spec.pumba_bin or config.get("pumba_bin", "pumba")
        )

    def _stress_ng_bin(self) -> str:
        return os.path.expanduser(
            config.get("stress_ng_bin", "/users/varuncg/bin/stress-ng")
        )

    def _stress_ng_image(self) -> str:
        return config.get(
            "stress_ng_image", "ghcr.io/alexei-led/stress-ng:latest"
        )

    def _resolve_node_host(self, service: str) -> str:
        """SSH-reachable host running the target service's task."""
        nodes = self.swarm.running_nodes_for(service)
        if not nodes:
            return config.get("manager_host", "localhost")
        return self._node_to_host(nodes[0])

    @staticmethod
    def _short_node_name(node: str) -> str:
        return node.split(".", 1)[0]

    def _node_to_host(self, node: str) -> str:
        short = self._short_node_name(node)
        if short in self.node_host_map:
            return self.node_host_map[short]
        if self.node_domain_suffix and "." not in node:
            return f"{short}.{self.node_domain_suffix}"
        return node

    def _target_regex(self, service: str) -> str:
        qualified = self.swarm.qualified_name(service)
        return f're2:^/?{qualified}\\.'

    @staticmethod
    def _peer_target_ip(endpoint: str) -> str:
        """Bare IP for pumba --target (strip Swarm CIDR suffixes like /16, /32)."""
        return endpoint.split("/", 1)[0]

    def _resolve_peer_targets(self, peer_service: str) -> list[str]:
        endpoints = self.swarm.service_endpoint_cidrs(peer_service)
        if not endpoints:
            raise FaultInjectionError(
                f"Could not resolve network endpoint for peer service "
                f"{peer_service!r} (need Swarm VIP or running task IP)"
            )
        return [self._peer_target_ip(addr) for addr in endpoints]

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

    def _running_container_id(self, node_host: str, service: str) -> str:
        """Container ID for a running task of *service* on *node_host*."""
        name = self.swarm.qualified_name(service)
        cid = Shell.exec_on_node(
            node_host,
            f"docker ps --filter name={name!r} --format '{{{{.ID}}}}' | head -1",
        ).strip()
        if not cid or cid.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"No running container for {service!r} on {node_host} "
                f"(needed to detect netem interface)"
            )
        return cid

    def _detect_egress_interface(
        self, node_host: str, container_id: str, dest_ip: str,
    ) -> str:
        """Interface used for egress to *dest_ip* inside a task netns."""
        cmd = (
            f"pid=$(docker inspect {container_id!r} --format '{{{{.State.Pid}}}}'); "
            f"if [ -z \"$pid\" ] || [ \"$pid\" = 0 ]; then exit 1; fi; "
            f"sudo nsenter -t \"$pid\" -n ip route get {dest_ip}"
        )
        out = Shell.exec_on_node(node_host, cmd).strip()
        if out.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"Could not resolve route to {dest_ip} in container "
                f"{container_id}: {out}"
            )
        iface = parse_route_interface(out)
        if not iface:
            raise FaultInjectionError(
                f"Could not parse egress interface for {dest_ip} from: {out!r}"
            )
        return iface

    def _resolve_netem_interface(self, spec: FaultSpec, node_host: str) -> str:
        """Pick the container interface Pumba should attach netem to."""
        if spec.fault_type != "delay":
            return config.get("pumba_default_interface", "eth0")

        if not spec.peer_service:
            return config.get("pumba_default_interface", "eth0")

        peer_ips = self._resolve_peer_targets(spec.peer_service)
        container_id = self._running_container_id(node_host, spec.target_service)
        iface = self._detect_egress_interface(node_host, container_id, peer_ips[0])
        for peer_ip in peer_ips[1:]:
            other = self._detect_egress_interface(
                node_host, container_id, peer_ip,
            )
            if other != iface:
                print(
                    f"[FAULT] Warning: peer {peer_ip} routes via {other}, "
                    f"using {iface} from {peer_ips[0]}"
                )
        return iface

    def _pumba_args(self, spec: FaultSpec, netem_interface: str = "eth0") -> str:
        """Pumba subcommand + flags (without nohup/background wrapper)."""
        target = self._target_regex(spec.target_service)
        bin_ = self._pumba_bin(spec)
        if spec.fault_type == "delay":
            return (
                f"{bin_} --log-level info netem --duration {spec.duration}"
                f" --interface {netem_interface}"
                f"{self._netem_scope_flags(spec)} "
                f"delay --time {spec.delay_ms} --jitter {spec.jitter_ms} "
                f"--correlation {spec.correlation} \"{target}\""
            )
        if spec.fault_type in _STRESS_FAULT_TYPES:
            stressor = (
                f"--cpu {spec.cpu_workers}"
                if spec.fault_type == "cpu"
                else f"--icache {spec.icache_workers}"
            )
            return (
                f"{bin_} --log-level info stress --duration {spec.duration} "
                f"--stressors \"{stressor} "
                f"--timeout {self._duration_seconds(spec.duration)}s\" "
                f"\"{target}\""
            )
        raise ValueError(f"Unknown fault_type: {spec.fault_type}")

    @staticmethod
    def _chaos_paths(chaos_id: str) -> tuple[str, str]:
        return f"/tmp/{chaos_id}.pid", f"/tmp/{chaos_id}.log"

    def _start_command(
        self, spec: FaultSpec, chaos_id: str, netem_interface: str = "eth0",
    ) -> str:
        pidfile, logfile = self._chaos_paths(chaos_id)
        return (
            f"nohup {self._pumba_args(spec, netem_interface)} >{logfile} 2>&1 & "
            f"pid=$!; echo $pid > {pidfile}; "
            f"sleep 0.5; "
            f"if ! kill -0 $pid 2>/dev/null; then "
            f"echo '[ERROR] Pumba failed to start:'; cat {logfile}; exit 1; "
            f"fi"
        )

    def _ensure_stress_ng_command(self) -> str:
        """Shell snippet: install host stress-ng from the Pumba stress image if missing."""
        stress = self._stress_ng_bin()
        image = self._stress_ng_image()
        return (
            f"stress_ng={stress!r}; "
            f"if [ ! -x \"$stress_ng\" ]; then "
            f"  mkdir -p \"$(dirname \"$stress_ng\")\"; "
            f"  tmp=$(docker create {image!r}) || exit 1; "
            f"  docker cp \"$tmp\":/stress-ng \"$stress_ng\" || "
            f"{{ docker rm -f \"$tmp\" >/dev/null; exit 1; }}; "
            f"  docker rm -f \"$tmp\" >/dev/null; "
            f"  chmod +x \"$stress_ng\"; "
            f"fi; "
            f"\"$stress_ng\" --help >/dev/null 2>&1 || "
            f"{{ echo \"[ERROR] stress-ng not runnable at $stress_ng\"; exit 1; }}; "
        )

    def _icache_burst_start_command(
        self, spec: FaultSpec, chaos_id: str, container_id: str,
    ) -> str:
        """Host loop: taskset to service core, burst icache stress, then sleep."""
        _, logfile = self._chaos_paths(chaos_id)
        pidfile, _ = self._chaos_paths(chaos_id)
        stress = self._stress_ng_bin()
        sleep_sec = spec.icache_sleep_ms / 1000.0
        loop_body = (
            f"while true; do "
            f"{stress} --icache {spec.icache_workers} "
            f"--timeout {spec.icache_burst_ms}ms --quiet; "
            f"sleep {sleep_sec}; done"
        )
        return (
            f"{self._ensure_stress_ng_command()}"
            f"cid={container_id!r}; "
            f'pid=$(docker inspect "$cid" --format \'{{{{.State.Pid}}}}\'); '
            f'if [ -z "$pid" ] || [ "$pid" = 0 ]; then '
            f'echo "[ERROR] no container pid for icache_burst"; exit 1; fi; '
            f'cpu=$(ps -o psr= -p "$pid" 2>/dev/null | tr -d " "); '
            f'if [ -z "$cpu" ]; then cpu=0; fi; '
            f'echo "[FAULT] icache burst loop started cpu=$cpu target_pid=$pid '
            f'stress_ng={stress}" '
            f"> {logfile}; "
            f"nohup setsid bash -c {loop_body!r} >>{logfile} 2>&1 < /dev/null & "
            f"loop_pid=$!; echo $loop_pid > {pidfile}; "
            # Pin the whole process group to the service's core.
            f"taskset -pc \"$cpu\" $loop_pid >/dev/null 2>&1 || "
            f"taskset -c \"$cpu\" -p $loop_pid >/dev/null 2>&1 || true; "
            f"sleep 0.5; "
            f"if ! kill -0 $loop_pid 2>/dev/null; then "
            f"echo '[ERROR] icache burst failed to start:'; cat {logfile}; exit 1; "
            f"fi; "
            # Fail fast if the first burst could not exec stress-ng.
            f"sleep {max(0.2, sleep_sec)}; "
            f"if grep -qiE 'command not found|No such file|cannot execute' "
            f"{logfile}; then "
            f"kill -TERM -$loop_pid 2>/dev/null || kill $loop_pid 2>/dev/null || true; "
            f"echo '[ERROR] icache burst stress-ng failed:'; cat {logfile}; exit 1; "
            f"fi"
        )

    def _stop_command(self, chaos_id: str) -> str:
        pidfile, _ = self._chaos_paths(chaos_id)
        return (
            f"if [ -f {pidfile} ]; then "
            f"pid=$(cat {pidfile}); "
            # Kill process group (icache_burst setsid) then the pid itself.
            f"kill -TERM -$pid 2>/dev/null || true; "
            f"kill -TERM $pid 2>/dev/null || true; "
            f"sleep 0.2; "
            f"kill -KILL -$pid 2>/dev/null || true; "
            f"kill -KILL $pid 2>/dev/null || true; "
            f"rm -f {pidfile}; fi"
        )

    def _remove_chaos_files(self, chaos_id: str, node_host: str) -> None:
        pidfile, logfile = self._chaos_paths(chaos_id)
        Shell.exec_on_node(node_host, f"rm -f {pidfile} {logfile}")

    def _read_chaos_log_raw(self, chaos_id: str, node_host: str) -> str:
        _, logfile = self._chaos_paths(chaos_id)
        return Shell.exec_on_node(
            node_host, f"cat {logfile} 2>/dev/null || true",
        ).strip()

    def _reset_container_tc(self, node_host: str, container_name: str) -> None:
        """Remove leftover prio/netem qdiscs Pumba may have left in a task netns."""
        cname = container_name.lstrip("/")
        cmd = (
            f"cid=$(docker ps --filter name={cname!r} --format '{{{{.ID}}}}' | head -1); "
            f"if [ -z \"$cid\" ]; then exit 0; fi; "
            f"pid=$(docker inspect \"$cid\" --format '{{{{.State.Pid}}}}'); "
            f"if [ -z \"$pid\" ] || [ \"$pid\" = 0 ]; then exit 0; fi; "
            f"for dev in $(sudo nsenter -t \"$pid\" -n ip -o link show 2>/dev/null "
            f"| awk -F': ' '{{print $2}}' | cut -d@ -f1 | grep -v '^lo$'); do "
            f"  if sudo nsenter -t \"$pid\" -n tc qdisc show dev \"$dev\" 2>/dev/null "
            f"| grep -qE 'qdisc (prio|netem)'; then "
            f"    sudo nsenter -t \"$pid\" -n tc qdisc del dev \"$dev\" root "
            f"2>/dev/null || true; "
            f"    echo \"[FAULT] Cleared tc rules on {cname} dev $dev\"; "
            f"  fi; "
            f"done"
        )
        out = Shell.exec_on_node(node_host, cmd).strip()
        if out:
            print(out)

    def _swarm_node_hosts(self) -> list[str]:
        raw = Shell.exec("docker node ls --format '{{.Hostname}}'")
        if raw.startswith("[ERROR]"):
            return []
        hosts: list[str] = []
        seen: set[str] = set()
        for line in raw.splitlines():
            node = line.strip()
            if not node:
                continue
            host = self._node_to_host(node)
            if host not in seen:
                seen.add(host)
                hosts.append(host)
        return hosts

    def _recover_one(self, chaos_id: str, node_host: str) -> None:
        if chaos_id in self._conn_meta or chaos_id.startswith("cpe-chaos-connections-"):
            self._recover_connections(chaos_id)
            return
        log = self._read_chaos_log_raw(chaos_id, node_host)
        Shell.exec_on_node(node_host, self._stop_command(chaos_id))
        for container in container_names_from_log(log):
            self._reset_container_tc(node_host, container)
        self._remove_chaos_files(chaos_id, node_host)
        self._active.pop(chaos_id, None)
        label = "icache burst" if chaos_id.startswith("cpe-chaos-icache_burst-") else "pumba"
        print(f"[FAULT] Recovered {label} process {chaos_id} on {node_host}")

    def _recover_leftover_chaos_files(self, node_host: str) -> None:
        try:
            raw = Shell.exec_on_node(
                node_host, "ls /tmp/cpe-chaos-*.pid 2>/dev/null || true",
            )
        except RuntimeError as e:
            print(f"[FAULT] Skipping leftover cleanup on {node_host}: {e}")
            return
        chaos_ids: list[str] = []
        for line in raw.splitlines():
            path = line.strip()
            if path.endswith(".pid"):
                chaos_ids.append(os.path.basename(path)[:-4])
        for chaos_id in chaos_ids:
            if chaos_id in self._active:
                continue
            self._recover_one(chaos_id, node_host)

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

    def _service_config_path(self) -> Path:
        override = config.get("service_config_path")
        if override:
            return Path(override).expanduser().resolve()
        app_src = config.app_source_dir()
        if app_src is None:
            raise FaultInjectionError(
                "Cannot locate service-config.json: no active suite "
                "(apply_suite_profile) and service_config_path unset"
            )
        path = app_src / "config" / "service-config.json"
        if not path.is_file():
            raise FaultInjectionError(f"service-config.json not found at {path}")
        return path

    def _service_config_binding(self, service: str) -> tuple[str, str]:
        """Return (ConfigName, mount target) for service-config.json on *service*."""
        name = self.swarm.qualified_name(service)
        raw = Shell.exec(
            f"docker service inspect {name} "
            f"--format '{{{{json .Spec.TaskTemplate.ContainerSpec.Configs}}}}'",
            timeout=60,
        ).strip()
        if raw.startswith("[ERROR]") or not raw or raw == "null":
            raise FaultInjectionError(
                f"Could not inspect configs for {service!r}: {raw}"
            )
        try:
            configs = json.loads(raw)
        except json.JSONDecodeError as e:
            raise FaultInjectionError(
                f"Bad configs JSON for {service!r}: {e}: {raw[:200]!r}"
            ) from e
        for entry in configs or []:
            file_meta = entry.get("File") or {}
            target = file_meta.get("Name") or ""
            cfg_name = entry.get("ConfigName") or ""
            if cfg_name and target.endswith("service-config.json"):
                return cfg_name, target
        raise FaultInjectionError(
            f"No service-config.json config binding found on {service!r}"
        )

    def _wait_service_ready(self, service: str, timeout_sec: int = 180) -> None:
        name = self.swarm.qualified_name(service)
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            replicas = Shell.exec(
                f"docker service ls --filter name={name} "
                f"--format '{{{{.Name}}}} {{{{.Replicas}}}}'",
                timeout=30,
            ).strip()
            for line in replicas.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == name and parts[1] == "1/1":
                    return
            time.sleep(2)
        raise FaultInjectionError(
            f"Service {service!r} did not reach 1/1 within {timeout_sec}s"
        )

    def _force_restart_service(self, service: str) -> None:
        """Force-update a Swarm service and wait until it is 1/1 again."""
        name = self.swarm.qualified_name(service)
        print(f"[FAULT] Force-restarting {service} ({name})")
        out = Shell.exec(
            f"docker service update --detach=false --force {name}",
            timeout=300,
        )
        if out.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"Failed to force-restart {service!r}: {out}"
            )
        self._wait_service_ready(service)

    def _force_restart_services(self, services: list[str]) -> None:
        seen: set[str] = set()
        for svc in services:
            if not svc or svc in seen:
                continue
            seen.add(svc)
            self._force_restart_service(svc)

    def _verify_connections_in_task(self, spec: FaultSpec) -> None:
        node_host = self._resolve_node_host(spec.target_service)
        cid = self._running_container_id(node_host, spec.target_service)
        raw = Shell.exec_on_node(
            node_host,
            f"docker exec {cid} cat {_SERVICE_CONFIG_MOUNT}",
            timeout=60,
        )
        if raw.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"Could not read service-config inside {spec.target_service}: {raw}"
            )
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError as e:
            raise FaultInjectionError(
                f"Invalid service-config in task: {e}"
            ) from e
        peer = spec.peer_service or ""
        got = (cfg.get(peer) or {}).get("connections")
        if got != spec.connections:
            raise FaultInjectionError(
                f"Expected {peer}.connections={spec.connections} in task, got {got!r}"
            )
        print(
            f"[FAULT] Verified {peer}.connections={got} in "
            f"{spec.target_service} task on {node_host}"
        )

    def _inject_connections(self, spec: FaultSpec) -> str:
        """Shrink ClientPool max size via a temporary Swarm config + service update."""
        assert spec.peer_service is not None
        chaos_id = f"cpe-chaos-connections-{uuid.uuid4().hex[:8]}"
        config_name = f"cpe-conn-{uuid.uuid4().hex[:8]}"
        manager = config.get("manager_host", "localhost")

        print(f"[FAULT] Injecting {spec.summary()}")
        src_path = self._service_config_path()
        with open(src_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if spec.peer_service not in cfg or not isinstance(cfg[spec.peer_service], dict):
            raise FaultInjectionError(
                f"Config key {spec.peer_service!r} missing in {src_path}"
            )
        original = cfg[spec.peer_service].get("connections")
        cfg[spec.peer_service]["connections"] = spec.connections
        print(
            f"[FAULT] {spec.peer_service}.connections: "
            f"{original} -> {spec.connections} (source {src_path})"
        )

        orig_cfg_name, mount_target = self._service_config_binding(spec.target_service)
        print(
            f"[FAULT] Replacing Swarm config {orig_cfg_name!r} on "
            f"{spec.target_service} (mount {mount_target})"
        )

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp:
                json.dump(cfg, tmp, indent=2)
                tmp.write("\n")
                tmp_path = tmp.name
            create_out = Shell.exec(
                f"docker config create {config_name} {tmp_path}",
                timeout=60,
            )
            if create_out.startswith("[ERROR]"):
                raise FaultInjectionError(
                    f"docker config create failed: {create_out}"
                )

            svc = self.swarm.qualified_name(spec.target_service)
            update_out = Shell.exec(
                f"docker service update --detach=false "
                f"--config-rm {orig_cfg_name} "
                f"--config-add source={config_name},target={mount_target} "
                f"{svc}",
                timeout=300,
            )
            if update_out.startswith("[ERROR]"):
                Shell.exec(f"docker config rm {config_name}", timeout=60)
                raise FaultInjectionError(
                    f"docker service update failed: {update_out}"
                )
            self._wait_service_ready(spec.target_service)
            self._verify_connections_in_task(spec)
            if spec.also_restart:
                print(
                    f"[FAULT] Restarting parent/caller services after "
                    f"{spec.target_service} config change: {spec.also_restart}"
                )
                self._force_restart_services(spec.also_restart)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        self._active[chaos_id] = manager
        self._conn_meta[chaos_id] = {
            "service": spec.target_service,
            "config_name": config_name,
            "original_config_name": orig_cfg_name,
            "mount_target": mount_target,
            "peer_service": spec.peer_service,
            "connections": spec.connections,
            "also_restart": list(spec.also_restart),
        }
        print(f"[FAULT] Started connections fault (chaos={chaos_id})")
        return chaos_id

    def _recover_connections(self, chaos_id: str) -> None:
        meta = self._conn_meta.pop(chaos_id, None)
        self._active.pop(chaos_id, None)
        if not meta:
            print(f"[FAULT] No connections metadata for {chaos_id}; skip")
            return
        svc = self.swarm.qualified_name(meta["service"])
        cfg_name = meta["config_name"]
        orig = meta["original_config_name"]
        mount = meta["mount_target"]
        also_restart = list(meta.get("also_restart") or [])
        print(
            f"[FAULT] Restoring {meta['service']} config "
            f"{cfg_name!r} -> {orig!r}"
        )
        # Current binding may already be the temporary config.
        try:
            current_name, _ = self._service_config_binding(meta["service"])
        except FaultInjectionError:
            current_name = cfg_name
        update_out = Shell.exec(
            f"docker service update --detach=false "
            f"--config-rm {current_name} "
            f"--config-add source={orig},target={mount} "
            f"{svc}",
            timeout=300,
        )
        if update_out.startswith("[ERROR]"):
            print(f"[FAULT] Warning: failed to restore config: {update_out}")
        else:
            try:
                self._wait_service_ready(meta["service"])
            except FaultInjectionError as e:
                print(f"[FAULT] Warning: {e}")
        if also_restart:
            try:
                print(
                    f"[FAULT] Restarting parent/caller services after "
                    f"{meta['service']} config restore: {also_restart}"
                )
                self._force_restart_services(also_restart)
            except FaultInjectionError as e:
                print(f"[FAULT] Warning: parent restart failed: {e}")
        rm_out = Shell.exec(f"docker config rm {cfg_name}", timeout=60)
        if rm_out.startswith("[ERROR]"):
            print(f"[FAULT] Warning: docker config rm {cfg_name}: {rm_out}")
        print(f"[FAULT] Recovered connections fault {chaos_id}")

    def _inject_icache_burst(self, spec: FaultSpec) -> str:
        node_host = self._resolve_node_host(spec.target_service)
        container_id = self._running_container_id(node_host, spec.target_service)
        chaos_id = f"cpe-chaos-icache_burst-{uuid.uuid4().hex[:8]}"
        command = self._icache_burst_start_command(spec, chaos_id, container_id)

        print(f"[FAULT] Injecting {spec.summary()}")
        print(f"[FAULT] node: {node_host}")
        print(f"[FAULT] container: {container_id}")
        print(f"[FAULT] remote shell: {command}")

        out = Shell.exec_on_node(node_host, command)
        if out.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"Failed to start icache burst ({spec.summary()}) on "
                f"{node_host}: {out}"
            )
        self._active[chaos_id] = node_host
        print(f"[FAULT] Started on node {node_host} (chaos={chaos_id})")
        return chaos_id

    def _inject_one(self, spec: FaultSpec) -> str:
        if spec.fault_type == "connections":
            return self._inject_connections(spec)
        if spec.fault_type == "icache_burst":
            return self._inject_icache_burst(spec)

        node_host = self._resolve_node_host(spec.target_service)
        chaos_id = f"cpe-chaos-{spec.fault_type}-{uuid.uuid4().hex[:8]}"
        netem_interface = (
            self._resolve_netem_interface(spec, node_host)
            if spec.fault_type == "delay"
            else "eth0"
        )
        pumba_cmd = self._pumba_args(spec, netem_interface)
        command = self._start_command(spec, chaos_id, netem_interface)

        print(f"[FAULT] Injecting {spec.summary()}")
        print(f"[FAULT] node: {node_host}")
        if spec.fault_type == "delay":
            print(f"[FAULT] netem interface: {netem_interface} (auto-detected)")
        print(f"[FAULT] pumba cmd: {pumba_cmd}")
        print(f"[FAULT] remote shell: {command}")

        out = Shell.exec_on_node(node_host, command)
        if out.startswith("[ERROR]"):
            raise FaultInjectionError(
                f"Failed to start Pumba ({spec.summary()}) on {node_host}: {out}"
            )
        self._active[chaos_id] = node_host
        print(f"[FAULT] Started on node {node_host} (chaos={chaos_id})")
        return chaos_id

    def _read_chaos_log(self, chaos_id: str, node_host: str) -> str:
        _, logfile = self._chaos_paths(chaos_id)
        pidfile, _ = self._chaos_paths(chaos_id)
        out = Shell.exec_on_node(
            node_host,
            f"if [ -f {pidfile} ] && ! kill -0 $(cat {pidfile}) 2>/dev/null; then "
            f"echo '[ERROR] Pumba process exited'; fi; "
            f"cat {logfile} 2>/dev/null || true",
        )
        if out.startswith("[ERROR] Pumba process exited"):
            prefix, _, log = out.partition("\n")
            if prefix:
                print(f"[FAULT] {prefix} ({chaos_id})")
            return log.strip()
        return out.strip()

    def _verify_chaos_log(self, chaos_id: str, node_host: str, spec: FaultSpec) -> None:
        log = self._read_chaos_log(chaos_id, node_host)
        if log:
            print(f"[FAULT] fault log ({chaos_id}):\n{log}")
        if spec.fault_type == "icache_burst":
            verify_icache_burst_log(log, spec)
        else:
            verify_pumba_log(log, spec)

    def inject(self, spec: FaultSpec) -> str:
        chaos_id = self._inject_one(spec)
        time.sleep(config.get("fault_settle_seconds", 5))
        if spec.fault_type != "connections":
            node_host = self._active[chaos_id]
            self._verify_chaos_log(chaos_id, node_host, spec)
        return chaos_id

    def inject_all(self, specs: list[FaultSpec]) -> list[str]:
        if not specs:
            return []
        pairs: list[tuple[FaultSpec, str]] = []
        for spec in specs:
            pairs.append((spec, self._inject_one(spec)))
        time.sleep(config.get("fault_settle_seconds", 5))
        for spec, chaos_id in pairs:
            if spec.fault_type == "connections":
                continue
            self._verify_chaos_log(chaos_id, self._active[chaos_id], spec)
        return [chaos_id for _, chaos_id in pairs]

    def recover(self, chaos_id: str | None = None) -> None:
        targets = ([chaos_id] if chaos_id else list(self._active.keys()))
        for name in list(targets):
            node_host = self._active.get(name, config.get("manager_host", "localhost"))
            self._recover_one(name, node_host)

    def recover_many(self, chaos_ids: list[str]) -> None:
        for cid in chaos_ids:
            self.recover(cid)

    def recover_all(self) -> None:
        self.recover()
        manager_host = config.get("manager_host", "localhost")
        nodes = [manager_host]
        nodes.extend(h for h in self._swarm_node_hosts() if h != manager_host)
        for node_host in nodes:
            self._recover_leftover_chaos_files(node_host)
