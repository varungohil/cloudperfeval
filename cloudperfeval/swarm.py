"""Thin wrapper around the `docker` Swarm CLI (read + placement helpers).

Service names are resolved against the configured stack so callers can use
short names ("frontend") instead of fully-qualified ones ("sn_frontend").
"""

from cloudperfeval.config import config
from cloudperfeval.shell import Shell


class SwarmCtl:
    def __init__(self):
        self.stack_name = config.get("stack_name")

    # ---- name resolution -------------------------------------------------
    def qualified_name(self, service: str) -> str:
        if not self.stack_name:
            return service
        prefix = f"{self.stack_name}_"
        return service if service.startswith(prefix) else f"{prefix}{service}"

    # ---- read operations -------------------------------------------------
    def list_services(self) -> str:
        if self.stack_name:
            return Shell.exec(f"docker stack services {self.stack_name}")
        return Shell.exec("docker service ls")

    def service_ps(self, service: str) -> str:
        name = self.qualified_name(service)
        return Shell.exec(
            f"docker service ps {name} --no-trunc "
            f"--format 'table {{{{.Name}}}}\\t{{{{.Node}}}}\\t{{{{.CurrentState}}}}\\t{{{{.Error}}}}'"
        )

    def service_logs(self, service: str, tail: int = 200) -> str:
        name = self.qualified_name(service)
        return Shell.exec(f"docker service logs --tail {int(tail)} --timestamps {name}")

    def service_inspect(self, service: str) -> str:
        name = self.qualified_name(service)
        return Shell.exec(f"docker service inspect {name} --pretty")

    def nodes(self) -> str:
        return Shell.exec("docker node ls")

    # ---- placement -------------------------------------------------------
    def _short_node(self, fqdn: str) -> str:
        host = fqdn.split(".", 1)[0]
        return host if host.startswith("node-") else fqdn

    def _short_service(self, task_name: str) -> str:
        name = task_name.rsplit(".", 1)[0]
        prefix = f"{self.stack_name}_" if self.stack_name else ""
        return name[len(prefix):] if prefix and name.startswith(prefix) else name

    def running_nodes_for(self, service: str) -> list[str]:
        """Return the node hostname(s) currently running a service's tasks."""
        name = self.qualified_name(service)
        raw = Shell.exec(
            f"docker service ps {name} --filter desired-state=running --no-trunc "
            f"--format '{{{{.Node}}}}'"
        )
        if raw.startswith("[ERROR]"):
            return []
        nodes = []
        for line in raw.splitlines():
            line = line.strip()
            if line and line not in nodes:
                nodes.append(line)
        return nodes

    def service_virtual_ips(self, service: str) -> list[str]:
        """Return Swarm overlay VIP CIDRs for a service (for pumba netem --target)."""
        name = self.qualified_name(service)
        raw = Shell.exec(
            f"docker service inspect {name} "
            f"--format '{{{{range .Endpoint.VirtualIPs}}}}{{{{.Addr}}}} {{{{end}}}}'"
        )
        if raw.startswith("[ERROR]"):
            return []
        return [part.strip() for part in raw.split() if part.strip()]

    def service_task_ips(self, service: str) -> list[str]:
        """Return /32 CIDRs for running task container IPs (fallback if no VIP)."""
        name = self.qualified_name(service)
        task_ids = Shell.exec(
            f"docker service ps {name} --filter desired-state=running -q --no-trunc"
        )
        if task_ids.startswith("[ERROR]") or not task_ids.strip():
            return []
        ips: list[str] = []
        for task_id in task_ids.split():
            task_id = task_id.strip()
            if not task_id:
                continue
            ip = Shell.exec(
                f"docker inspect {task_id} "
                f"--format '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}"
                f"{{{{end}}}}'"
            ).strip()
            if ip and not ip.startswith("[ERROR]") and ip not in ips:
                ips.append(f"{ip}/32")
        return ips

    def service_endpoint_cidrs(self, service: str) -> list[str]:
        """VIP CIDRs for a service, falling back to task container IPs."""
        cidrs = self.service_virtual_ips(service)
        if cidrs:
            return cidrs
        return self.service_task_ips(service)

    def service_node_mapping(self) -> str:
        if self.stack_name:
            raw_ids = Shell.exec(f"docker stack services {self.stack_name} -q").strip()
        else:
            raw_ids = Shell.exec("docker service ls -q").strip()
        if raw_ids.startswith("[ERROR]"):
            return raw_ids
        svc_ids = raw_ids.split()
        if not svc_ids:
            return "(no services found)"

        raw = Shell.exec(
            f"docker service ps {' '.join(svc_ids)} --filter desired-state=running --no-trunc "
            f"--format '{{{{.Name}}}}\\t{{{{.Node}}}}'"
        )
        if raw.startswith("[ERROR]"):
            return raw

        placement: dict[str, set[str]] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or "\t" not in line:
                continue
            task_name, node = line.split("\t", 1)
            placement.setdefault(self._short_service(task_name), set()).add(self._short_node(node))

        if not placement:
            return "(no running tasks found)"
        lines = ["SERVICE\tNODE(S)\tREPLICAS"]
        for service in sorted(placement):
            nodes = sorted(placement[service])
            node_col = nodes[0] if len(nodes) == 1 else f"global ({len(nodes)} nodes)"
            lines.append(f"{service}\t{node_col}\t{len(nodes)}")
        return "\n".join(lines)
