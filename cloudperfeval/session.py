"""Session bookkeeping for an agent run (history, solution, results)."""

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from cloudperfeval.config import config

if TYPE_CHECKING:
    from cloudperfeval.run_log import RunLogCapture


def problem_short_name(problem_id: str) -> str:
    """Short problem name (without suite prefix) for result artifact filenames."""
    return problem_id.split(":", 1)[-1]


class Session:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.problem_id = None
        self.problem_desc = None
        self.agent_name = None
        self.solution = None
        self.results = {}
        self.history: list[dict] = []
        self.run_log = ""
        self.run_log_path: str | None = None
        self.start_time = None
        self.end_time = None
        self._run_log_capture: RunLogCapture | None = None

    def set_problem(self, problem_id: str, problem_desc: str):
        self.problem_id = problem_id
        self.problem_desc = problem_desc

    def set_agent(self, agent_name: str):
        self.agent_name = agent_name

    def set_solution(self, solution):
        self.solution = solution

    def set_results(self, results):
        self.results = results

    def add(self, item: dict):
        if item:
            self.history.append(item)

    def begin_run_log(self) -> None:
        from cloudperfeval.run_log import RunLogCapture

        if self._run_log_capture is None:
            self._run_log_capture = RunLogCapture()
            self._run_log_capture.start()

    def end_run_log(self) -> str:
        if self._run_log_capture is not None:
            self.run_log = self._run_log_capture.stop()
            self._run_log_capture = None
        return self.run_log

    def start(self):
        self.start_time = time.time()

    def end(self):
        self.end_time = time.time()

    def get_duration(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            return time.time() - self.start_time
        return 0.0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "problem_id": self.problem_id,
            "agent": self.agent_name,
            "problem_desc": self.problem_desc,
            "history": self.history,
            "solution": self.solution,
            "results": self.results,
            "duration": self.get_duration(),
            "run_log_path": self.run_log_path,
        }

    def _artifact_stem(self) -> str:
        if self.problem_id:
            return f"{problem_short_name(self.problem_id)}_{self.session_id}"
        return self.session_id

    def to_json(self) -> str:
        results_dir = Path(config.get("results_dir", "./results"))
        results_dir.mkdir(parents=True, exist_ok=True)
        stem = self._artifact_stem()
        path = results_dir / f"{stem}.json"
        if self.run_log:
            log_path = results_dir / f"{stem}.log"
            log_path.write_text(self.run_log, encoding="utf-8")
            self.run_log_path = str(log_path)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return str(path)
