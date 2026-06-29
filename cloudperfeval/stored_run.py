"""Persist store-phase snapshots between CLI phases (store / run)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from cloudperfeval.config import config

_STORED_RUNS_DIR = "stored_runs"


@dataclass
class StoredRun:
    """Load sent under fault during store phase; Jaeger capture happens in run phase."""

    snapshot_id: str
    problem_id: str
    trace_id: str | None
    spec_summary: str
    raw_loadgen_output: str
    recorded_at: float
    workload_mode: str = "single"
    trace_service: str = "frontend-service"
    load_start_ts: float | None = None
    load_end_ts: float | None = None

    @classmethod
    def store_dir(cls) -> Path:
        return Path(config.get("results_dir", "./results")) / _STORED_RUNS_DIR

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex[:12]

    def path(self) -> Path:
        return self.store_dir() / f"{self.snapshot_id}.json"

    def save(self) -> Path:
        self.store_dir().mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return self.path()

    @classmethod
    def _parse_snapshot_data(cls, data: dict) -> dict:
        data.pop("chaos_ids", None)  # legacy field from older snapshots
        if "store_id" in data and "snapshot_id" not in data:
            data["snapshot_id"] = data.pop("store_id")
        return data

    @classmethod
    def load(cls, snapshot_id: str) -> StoredRun:
        path = cls.store_dir() / f"{snapshot_id}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"No snapshot {snapshot_id!r} at {path}. "
                "Run with --phase snapshot first, or pass --list-snapshots to see ids."
            )
        data = cls._parse_snapshot_data(json.loads(path.read_text(encoding="utf-8")))
        return cls(**data)

    @classmethod
    def require(cls, snapshot_id: str, problem_id: str | None = None) -> StoredRun:
        stored = cls.load(snapshot_id)
        if problem_id and stored.problem_id != problem_id:
            raise ValueError(
                f"Snapshot {snapshot_id!r} is for {stored.problem_id!r}, "
                f"not {problem_id!r}"
            )
        return stored

    @classmethod
    def list_runs(cls, problem_id: str | None = None) -> list[StoredRun]:
        directory = cls.store_dir()
        if not directory.is_dir():
            return []
        runs: list[StoredRun] = []
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                stored = cls.load(path.stem)
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
            if problem_id and stored.problem_id != problem_id:
                continue
            runs.append(stored)
        return runs

    @classmethod
    def format_list(cls, problem_id: str | None = None) -> str:
        runs = cls.list_runs(problem_id=problem_id)
        if not runs:
            suffix = f" for {problem_id!r}" if problem_id else ""
            return f"(no snapshots{suffix})"
        lines = ["SNAPSHOT_ID\tRECORDED_AT\tPROBLEM_ID\tTRACE_ID"]
        for run in runs:
            recorded = datetime.fromtimestamp(
                run.recorded_at, tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S UTC")
            trace = run.trace_id or "-"
            lines.append(f"{run.snapshot_id}\t{recorded}\t{run.problem_id}\t{trace}")
        return "\n".join(lines)
