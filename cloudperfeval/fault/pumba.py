"""Pumba-based fault injection for Docker Swarm.

A `FaultSpec` describes *what* to inject (delay or cpu stress) and *which*
service to target. `PumbaInjector` runs the `pumba` CLI on the node hosting the
target task (resolved from Swarm placement), tracks the background process so it
can be stopped on recover, and cleans up leftovers.

Network delay supports optional scoping:
  - `peer_service`: delay only egress from `target_service` toward that peer
    (pumba netem `--target <peer-ip>`; CIDR suffixes from Swarm are stripped).
  - `egress_port` / `ingress_port`: limit delay to matching source/dest ports.

For netem faults the egress interface is auto-detected by running
`ip route get <peer-ip>` inside the target task's network namespace (Swarm
overlay traffic often uses eth2, not Pumba's default eth0).

Prerequisite: `pumba` must be installed on every Swarm node (with `tc`/iproute2
for netem faults). The harness does not run Pumba inside Docker.

Pumba reference:
  net delay : pumba netem [--target IP] [--egress-port P] [--ingress-port P]
              --duration D delay --time MS <source-containers>
  stress cpu: pumba stress --duration D --stressors "..." <target>
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from cloudperfeval.config import config
from cloudperfeval.shell import Shell
from cloudperfeval.swarm import SwarmCtl


class FaultInjectionError(RuntimeError):
    """Pumba failed to start or its /tmp log shows the fault did not apply."""


_PUMBA_LOG_FAIL = (
    re.compile(r'level=warning msg="no containers found"'),
    re.compile(r"level=error\b"),
    re.compile(r"level=fatal\b"),
)
_PUMBA_LOG_OK = {
    "delay": re.compile(r'level=info msg="running netem on container"'),
    "cpu": re.compile(r'level=info msg="stress testing container"'),
}
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

    def _stop_command(self, chaos_id: str) -> str:
        pidfile, _ = self._chaos_paths(chaos_id)
        return (
            f"if [ -f {pidfile} ]; then "
            f"kill $(cat {pidfile}) 2>/dev/null || true; "
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
        log = self._read_chaos_log_raw(chaos_id, node_host)
        Shell.exec_on_node(node_host, self._stop_command(chaos_id))
        for container in container_names_from_log(log):
            self._reset_container_tc(node_host, container)
        self._remove_chaos_files(chaos_id, node_host)
        self._active.pop(chaos_id, None)
        print(f"[FAULT] Recovered pumba process {chaos_id} on {node_host}")

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

    def _inject_one(self, spec: FaultSpec) -> str:
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
            print(f"[FAULT] pumba log ({chaos_id}):\n{log}")
        verify_pumba_log(log, spec)

    def inject(self, spec: FaultSpec) -> str:
        chaos_id = self._inject_one(spec)
        time.sleep(config.get("fault_settle_seconds", 5))
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
