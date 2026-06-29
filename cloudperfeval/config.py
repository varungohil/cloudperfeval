"""YAML-backed config loader.

Per-suite deployment overrides live under `suites.<suite_id>` in the YAML file.
Call `apply_suite_profile(suite_id)` before setting up a problem.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yml"

SUITE_OVERRIDE_KEYS = (
    "stack_name",
    "frontend_url",
    "jaeger_url",
    "prometheus_url",
    "manager_host",
    "loadgen_host",
    "wrk_bin",
    "wrk_cwd",
    "wrk_ulimit_n",
    "wrk_distribution",
    "node_host_map",
    "node_domain_suffix",
    "fault_settle_seconds",
)


class Config:
    def __init__(self, config_file: Path | str = CONFIG_PATH):
        self.config_file = Path(config_file)
        self._defaults: dict = {}
        self._data: dict = {}
        self._active_suite: str | None = None
        self.reload(self.config_file)

    def reload(self, config_file: Path | str | None = None) -> None:
        path = Path(config_file) if config_file is not None else self.config_file
        self.config_file = path
        if path.exists():
            with open(path, "r") as f:
                self._defaults = yaml.safe_load(f) or {}
        else:
            self._defaults = {}
        self._data = copy.deepcopy(self._defaults)
        self._active_suite = None

    def _suite_profiles(self) -> dict:
        return (
            self._defaults.get("suites")
            or self._defaults.get("benchmarks")
            or self._defaults.get("apps")
            or {}
        )

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def apply_suite_profile(self, suite_id: str) -> None:
        """Reset overridable keys to defaults, then apply the suite profile."""
        if self._active_suite == suite_id:
            return

        self._data = copy.deepcopy(self._defaults)
        profile = self._suite_profiles().get(suite_id) or {}
        for key in SUITE_OVERRIDE_KEYS:
            if key in profile:
                self._data[key] = profile[key]
        self._active_suite = suite_id

    def apply_benchmark_profile(self, benchmark_id: str) -> None:
        """Deprecated alias for apply_suite_profile."""
        self.apply_suite_profile(benchmark_id)

    def apply_app_profile(self, app_id: str) -> None:
        """Deprecated alias for apply_suite_profile."""
        self.apply_suite_profile(app_id)

    @property
    def active_suite(self) -> str | None:
        return self._active_suite

    def app_source_dir(self) -> Path | None:
        """Return apps/<suite>/source for the active suite, if any."""
        if not self._active_suite:
            return None
        return BASE_DIR / "apps" / self._active_suite / "source"


config = Config()


def resolve_node_host(host: str) -> str:
    """Map short cluster node names (e.g. node-4) to SSH/HTTP-reachable hostnames."""
    if host in ("localhost", "", None):
        return config.get("manager_host", "localhost")
    node_host_map = config.get("node_host_map", {}) or {}
    if host in node_host_map:
        return node_host_map[host]
    suffix = config.get("node_domain_suffix", "")
    if suffix and "." not in host:
        return f"{host}.{suffix}"
    return host
