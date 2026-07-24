"""Docker-backed filesystem jail for autonomous coding agents."""

from __future__ import annotations

import os
import shlex
import shutil
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cloudperfeval.config import config

DEFAULT_IMAGE = "cpe-agent-sandbox:latest"
SAFE_ENV_KEYS = {
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_MODEL",
    "FORCE_AUTO_BACKGROUND_TASKS",
    "ENABLE_BACKGROUND_TASKS",
    "CPE_STACK_NAME",
    "CPE_PROMETHEUS_URL",
    "CPE_JAEGER_URL",
    "DOCKER_HOST",
}


@dataclass(frozen=True)
class SandboxSettings:
    enabled: bool = False
    runtime: str = "docker"
    image: str = DEFAULT_IMAGE
    cpus: float = 2
    memory: str = "4g"
    pids_limit: int = 512
    network: str = "bridge"
    claude_bin: str = "claude"
    codex_bin: str = "codex"

    @classmethod
    def from_config(cls) -> "SandboxSettings":
        raw = config.get("agent_sandbox", {}) or {}
        if not isinstance(raw, dict):
            raise ValueError("agent_sandbox config must be a mapping")
        return cls(
            enabled=bool(raw.get("enabled", False)),
            runtime=str(raw.get("runtime", "docker")),
            image=str(raw.get("image", DEFAULT_IMAGE)),
            cpus=float(raw.get("cpus", 2)),
            memory=str(raw.get("memory_limit", raw.get("memory", "4g"))),
            pids_limit=int(raw.get("pids_limit", 512)),
            network=str(raw.get("network", "bridge")),
            claude_bin=str(raw.get("claude_bin", "claude")),
            codex_bin=str(raw.get("codex_bin", "codex")),
        )


@dataclass(frozen=True)
class SandboxPaths:
    workdir: Path
    scratch: Path
    gateway_dir: Path
    home: Path


def prepare_sandbox_paths(workdir: Path) -> SandboxPaths:
    workdir = Path(workdir).resolve()
    scratch = workdir / "scratch"
    # Linux Unix-domain socket paths are limited to roughly 108 bytes. CPE run
    # names are intentionally descriptive and often exceed that once nested
    # under results/agent_workdirs, so use a deterministic short host path.
    digest = hashlib.sha256(str(workdir).encode("utf-8")).hexdigest()[:20]
    gateway_dir = Path(tempfile.gettempdir()) / "cpe-agent-gateways" / digest
    home = scratch / "home"
    for path in (scratch, gateway_dir, home):
        path.mkdir(parents=True, exist_ok=True)
    gateway_dir.chmod(0o700)
    return SandboxPaths(
        workdir=workdir,
        scratch=scratch,
        gateway_dir=gateway_dir,
        home=home,
    )


def sandbox_enabled() -> bool:
    return SandboxSettings.from_config().enabled


def _mount(source: Path, target: str, *, readonly: bool = False) -> str:
    options = f"type=bind,src={source},dst={target}"
    if readonly:
        options += ",readonly"
    return options


def build_docker_command(
    agent_command: list[str],
    *,
    agent_kind: str,
    paths: SandboxPaths,
    env: dict[str, str],
    readonly_mounts: list[tuple[Path, str]] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Wrap an agent command in a hardened, short-lived Docker container."""
    settings = SandboxSettings.from_config()
    if settings.runtime != "docker":
        raise ValueError(f"Unsupported agent sandbox runtime: {settings.runtime!r}")
    docker = shutil.which("docker")
    if docker is None:
        raise FileNotFoundError("agent sandbox is enabled but docker is not on PATH")

    guest_env = {key: value for key, value in env.items() if key in SAFE_ENV_KEYS}
    guest_env.update(
        {
            "HOME": "/scratch/home",
            "DOCKER_HOST": "unix:///run/cpe/docker.sock",
        }
    )
    if agent_kind == "claude":
        guest_env["CLAUDE_CONFIG_DIR"] = "/scratch/home/.claude"
    elif agent_kind == "codex":
        guest_env["CODEX_HOME"] = "/scratch/home/.codex"

    # Docker's `-e NAME` reads values from the subprocess environment, keeping
    # credentials out of argv and process listings.
    docker_env = os.environ.copy()
    docker_env.update(guest_env)
    # DOCKER_HOST is for the Docker CLI *inside* the container. Do not expose
    # that guest socket path to the host Docker CLI that launches the container.
    if "DOCKER_HOST" in os.environ:
        docker_env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]
    else:
        docker_env.pop("DOCKER_HOST", None)

    cmd = [
        docker,
        "run",
        "--rm",
        "--interactive",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--pids-limit={settings.pids_limit}",
        f"--cpus={settings.cpus:g}",
        f"--memory={settings.memory}",
        f"--network={settings.network}",
        f"--user={os.getuid()}:{os.getgid()}",
        "--workdir=/scratch",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=256m",
        "--mount",
        _mount(paths.scratch, "/scratch"),
        "--mount",
        _mount(paths.gateway_dir, "/run/cpe", readonly=True),
    ]
    source_dir = config.app_source_dir()
    if source_dir is not None and source_dir.is_dir():
        cmd.extend(["--mount", _mount(source_dir.resolve(), "/opt/app-source", readonly=True)])
    for source, target in readonly_mounts or []:
        cmd.extend(["--mount", _mount(Path(source).resolve(), target, readonly=True)])
    for key in sorted(guest_env):
        if key == "DOCKER_HOST":
            cmd.extend(["--env", f"{key}={guest_env[key]}"])
        else:
            cmd.extend(["--env", key])
    cmd.append(settings.image)
    cmd.extend(agent_command)
    return cmd, docker_env


def sandbox_description(command: list[str]) -> str:
    """Redacted command string suitable for run metadata."""
    return " ".join(shlex.quote(part) for part in command[:12]) + " ..."
