"""Shared helpers for autonomous coding-agent backends (Claude Code, Codex).

Mirrors SREGym / Harbor's coding-agent pattern:
- one inline instruction string (no turn-based LLM loop)
- agents use Bash + `python -m cloudperfeval.tools.call` (like kubectl)
- submit writes submission.json; orchestrator grades after the CLI exits
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cloudperfeval.config import config
from cloudperfeval.tools.dispatch import ACTION_NAMES, read_submission

REPO_ROOT = Path(__file__).resolve().parents[2]


def empty_token_usage() -> dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def parse_agent_stream_usage(stdout: str) -> dict[str, int]:
    """Extract input/output token totals from Codex or Claude Code JSONL stdout.

    Codex emits ``turn.completed`` events with ``usage.input_tokens`` /
    ``usage.output_tokens`` (summed across turns).

    Claude Code emits a final ``type=result`` event whose ``usage`` has
    ``input_tokens``, cache fields, and ``output_tokens``. Input is the sum of
    non-cached + cache-creation + cache-read tokens.
    """
    usage = empty_token_usage()
    if not stdout:
        return usage

    codex_input = 0
    codex_output = 0
    saw_codex = False
    claude_usage: dict | None = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue

        event_type = obj.get("type")
        if event_type == "turn.completed" and isinstance(obj.get("usage"), dict):
            u = obj["usage"]
            saw_codex = True
            codex_input += int(u.get("input_tokens") or 0)
            codex_output += int(u.get("output_tokens") or 0)
        elif event_type == "result" and isinstance(obj.get("usage"), dict):
            claude_usage = obj["usage"]

    if saw_codex:
        usage["input_tokens"] = codex_input
        usage["output_tokens"] = codex_output
        usage["total_tokens"] = codex_input + codex_output
        return usage

    if claude_usage is not None:
        inp = (
            int(claude_usage.get("input_tokens") or 0)
            + int(claude_usage.get("cache_creation_input_tokens") or 0)
            + int(claude_usage.get("cache_read_input_tokens") or 0)
        )
        out = int(claude_usage.get("output_tokens") or 0)
        usage["input_tokens"] = inp
        usage["output_tokens"] = out
        usage["total_tokens"] = inp + out
        return usage

    return usage


@dataclass
class CodingAgentResult:
    solution: Any | None = None
    history: list[dict] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    workdir: str | None = None
    timed_out: bool = False
    usage: dict[str, int] = field(default_factory=empty_token_usage)


def python_executable() -> str:
    return sys.executable or "python3"


def which_or_raise(binary: str, install_hint: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise FileNotFoundError(
            f"{binary!r} not found on PATH. {install_hint}"
        )
    return path


def strip_model_name(model: str | None, default: str | None = None) -> str | None:
    """Drop provider prefixes like openai/gpt-4.1 -> gpt-4.1."""
    if not model:
        return default
    return model.split("/")[-1]


def default_timeout_sec(max_steps: int) -> int:
    """Map turn budget onto a wall-clock timeout for autonomous agents."""
    env = os.environ.get("CPE_AGENT_TIMEOUT_SEC")
    if env:
        return max(60, int(env))
    return max(300, int(max_steps) * 90)


def tool_cli_prefix() -> str:
    return f"{python_executable()} -m cloudperfeval.tools.call"


def build_instruction(
    *,
    task_desc: str,
    instructions: str,
    apis: dict[str, str],
) -> str:
    """Build a single SREGym-style instruction for Claude Code / Codex."""
    sandbox_config = config.get("agent_sandbox", {}) or {}
    sandboxed = bool(sandbox_config.get("enabled", False))
    if sandboxed:
        direct_task = re.sub(
            r"\n\s*When confident, submit(?: using one of the schemas below)?:"
            r"\s*```.*?```\s*",
            "\n",
            task_desc,
            flags=re.DOTALL,
        )
        direct_task = direct_task.replace(
            "Use get_traces(service, start_ts, end_ts) or"
            " query_metric_range(promql, start_ts, end_ts) over this interval.",
            "Query Jaeger and Prometheus directly over this interval.",
        ).replace(
            "Use query_metric_range(promql, start_ts, end_ts) or"
            " get_traces(service, start_ts, end_ts) to inspect metrics and"
            " traces over exactly this interval.",
            "Query Prometheus and Jaeger directly over exactly this interval.",
        )
        return textwrap.dedent(
            f"""\
            You are an SRE agent diagnosing a cloud performance anomaly.

            CRITICAL: You are running in an AUTOMATED environment. Work autonomously
            and make all decisions yourself. DO NOT ask for user confirmation or
            approval. Investigation is READ-ONLY: do not scale, deploy, update,
            remove, or otherwise modify Swarm services, nodes, or the stack.

            -------------------------------------------------------------------------
            TASK
            -------------------------------------------------------------------------

            {direct_task.strip()}

            -------------------------------------------------------------------------
            DIRECT INVESTIGATION
            -------------------------------------------------------------------------

            Investigate with Bash and scripts that you create under /scratch.

            Available read-only inputs:
            - Docker Swarm state through the Docker CLI. DOCKER_HOST points to a
              GET-only API proxy. Useful commands include:
                docker stack services "$CPE_STACK_NAME"
                docker service ps <service> --no-trunc
                docker service inspect <service>
                docker service logs --tail 200 <service>
                docker node ls
            - Prometheus HTTP API at $CPE_PROMETHEUS_URL. Key endpoints:
                GET /api/v1/query?query=<promql>&time=<epoch>
                GET /api/v1/query_range?query=<promql>&start=<epoch>&end=<epoch>&step=<sec>
                GET /api/v1/label/__name__/values   (list metric names)
            - Jaeger HTTP API at $CPE_JAEGER_URL. Key endpoints:
                GET /api/services
                GET /api/services/<service>/operations
                GET /api/traces?service=<service>&start=<microsec>&end=<microsec>&limit=<n>
                GET /api/traces/<trace_id>
              Note: Jaeger trace start/end are in MICROSECONDS (epoch*1e6).
            - Application source at /opt/app-source (read-only).

            You may use curl, jq, Python, Bash, and create/run helper scripts. Your
            only persistent writable directory is /scratch.

            -------------------------------------------------------------------------
            HOW TO SUBMIT
            -------------------------------------------------------------------------

            Write the final diagnosis as JSON to /scratch/submission.json, then exit.
            Do this exactly once when confident.

            Service-diagnosis example:
              {{"root_cause_service":"compose-post-service","reason":"..."}}

            Resource-diagnosis examples:
              {{"resource":"cpu","service":"home-timeline-service","reason":"..."}}
              {{"resource":"network","from_service":"frontend-service","to_service":"home-timeline-service","reason":"..."}}

            Multi-fault example (report every injected fault):
              {{"faults":[{{"resource":"cpu","service":"home-timeline-service","reason":"..."}},{{"resource":"network","from_service":"frontend-service","to_service":"home-timeline-service","reason":"..."}}]}}
            """
        ).strip() + "\n"

    py_cli = "python -m cloudperfeval.tools.call" if sandboxed else tool_cli_prefix()
    action_names = tuple(name for name in ACTION_NAMES if not (sandboxed and name == "exec_shell"))
    api_docs = "\n\n".join(
        f"### {name}\n{doc}"
        for name, doc in apis.items()
        if name in action_names
    )
    tools_list = ", ".join(action_names)
    workspace_section = (
        """
        WRITABLE WORKSPACE
        -------------------------------------------------------------------------

        Your only writable directory is /scratch. Create helper scripts, notes,
        and intermediate files there, and run them with Bash, for example:
          python /scratch/analyze.py

        The application source is read-only at /opt/app-source and through
        list_source/read_source. Manager-side exec_shell is disabled; use the
        first-class CPE observability tools for cluster inspection.

        -------------------------------------------------------------------------
        """
        if sandboxed
        else ""
    )

    return textwrap.dedent(
        f"""\
        You are an SRE agent diagnosing a cloud performance anomaly.

        CRITICAL: You are running in an AUTOMATED environment. Work autonomously
        and make all decisions yourself. DO NOT ask for user confirmation or
        approval. Proceed with the best diagnosis based on your analysis.
        Investigation is READ-ONLY: do not scale, deploy, update, remove, or
        otherwise modify Swarm services, nodes, or the stack.

        -------------------------------------------------------------------------
        TASK
        -------------------------------------------------------------------------

        {task_desc.strip()}

        {instructions.strip()}

        {workspace_section}
        -------------------------------------------------------------------------
        HOW TO INVESTIGATE (Bash tools)
        -------------------------------------------------------------------------

        Call CloudPerfEval tools from the shell (same idea as using kubectl in
        SREGym). Available actions: {tools_list}

          {py_cli} --list
          {py_cli} list_services
          {py_cli} get_traces --arg service=frontend-service
          {py_cli} get_trace_by_id --arg trace_id=<id>
          {py_cli} get_metrics_range --arg query='...' --arg start=<epoch> --arg end=<epoch>
          {py_cli} get_logs --arg service=frontend-service
          {py_cli} submit --json '{{"root_cause_service":"...","reason":"..."}}'

        Keyword args: `--arg KEY=VALUE` (repeatable) or `--json '{{...}}'`.
        Values are JSON-decoded when possible.

        API reference:
        {api_docs}

        -------------------------------------------------------------------------
        HOW TO SUBMIT
        -------------------------------------------------------------------------

        When confident, submit EXACTLY ONCE, then exit. Do not keep probing.

        Service-diagnosis example:
          {py_cli} submit --json '{{"root_cause_service":"compose-post-service","reason":"..."}}'

        Resource-diagnosis examples:
          {py_cli} submit --json '{{"resource":"cpu","service":"home-timeline-service","reason":"..."}}'
          {py_cli} submit --json '{{"resource":"network","from_service":"frontend-service","to_service":"home-timeline-service","reason":"..."}}'

        Multi-fault (report every injected fault):
          {py_cli} submit --json '{{"faults":[{{"resource":"cpu","service":"home-timeline-service","reason":"..."}},{{"resource":"network","from_service":"frontend-service","to_service":"home-timeline-service","reason":"..."}}]}}'

        After a successful submit, stop. The harness grades your submission.
        """
    ).strip() + "\n"


def write_instruction_file(workdir: Path, instruction: str) -> Path:
    """Persist the instruction for debugging (agents get it inline like SREGym)."""
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / "INSTRUCTION.md"
    path.write_text(instruction, encoding="utf-8")
    return path


def child_env(tool_env: dict[str, str], extra: dict[str, str] | None = None) -> dict[str, str]:
    """Host env + CPE tool session vars + PYTHONPATH for tools.call."""
    env = os.environ.copy()
    env.update(tool_env)
    pythonpath = os.pathsep.join(
        p for p in [str(REPO_ROOT), env.get("PYTHONPATH", "")] if p
    )
    env["PYTHONPATH"] = pythonpath
    if extra:
        env.update(extra)
    return env


def resolve_codex_home(workdir: Path) -> tuple[Path, bool]:
    """Pick CODEX_HOME and optionally materialize API-key auth (SREGym parity).

    Prefer existing ~/.codex/auth.json (subscription/OAuth) without copying into
    results/. Otherwise use the run workdir and write auth.json from
    OPENAI_API_KEY.

    Returns (codex_home, created_api_key_auth).
    """
    home_codex = Path.home() / ".codex"
    if (home_codex / "auth.json").exists():
        return home_codex, False

    codex_home = Path(workdir)
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_file = codex_home / "auth.json"
    if auth_file.exists():
        return codex_home, False

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return codex_home, False

    auth_file.write_text(
        json.dumps({"OPENAI_API_KEY": api_key}),
        encoding="utf-8",
    )
    try:
        auth_file.chmod(0o600)
    except OSError:
        pass
    return codex_home, True


def cleanup_codex_auth(codex_home: Path, created: bool) -> None:
    if not created:
        return
    auth_file = Path(codex_home) / "auth.json"
    if auth_file.exists():
        try:
            auth_file.unlink()
        except OSError:
            pass


def setup_claude_sessions(sessions_dir: Path) -> None:
    """Create Claude Code session layout (SREGym / Harbor parity)."""
    sessions_dir = Path(sessions_dir)
    for sub in (
        "debug",
        "projects/-app",
        "shell-snapshots",
        "statsig",
        "todos",
    ):
        (sessions_dir / sub).mkdir(parents=True, exist_ok=True)


def claude_auth_env(base: dict[str, str]) -> dict[str, str] | None:
    """Prefer CLAUDE_CODE_OAUTH_TOKEN over ANTHROPIC_API_KEY (SREGym parity).

    Returns None if neither credential is available.
    """
    env = dict(base)
    api_key = env.get("ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    oauth = env.get("CLAUDE_CODE_OAUTH_TOKEN", "") or os.environ.get(
        "CLAUDE_CODE_OAUTH_TOKEN", ""
    )
    if not api_key and not oauth:
        return None
    if oauth:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth
        env.pop("ANTHROPIC_API_KEY", None)
    elif api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    return env


# Codex/Claude --json events embed full tool stdout in one line; the default
# asyncio StreamReader limit (64 KiB) raises ValueError on those lines.
_STREAM_READER_LIMIT = 16 * 1024 * 1024


async def run_streaming_cli(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    output_path: Path,
    timeout: int,
) -> tuple[str, int | None, bool]:
    """Run a CLI, stream stdout+stderr into output_path (SREGym-style)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            limit=_STREAM_READER_LIMIT,
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Failed to launch {cmd[0]}: {e}") from e

    chunks: list[str] = []
    timed_out = False

    async def _pump() -> None:
        assert proc.stdout is not None
        with open(output_path, "w", encoding="utf-8") as out_file:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                out_file.write(text)
                out_file.flush()
                chunks.append(text)
                # Mirror SREGym: also print live agent output.
                print(text, end="", flush=True)

    try:
        await asyncio.wait_for(_pump(), timeout=timeout)
        await proc.wait()
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass

    return "".join(chunks), proc.returncode, timed_out


class AutonomousCodingAgent:
    """Base class for agents that own their own tool loop (Claude Code / Codex)."""

    autonomous = True

    def __init__(self, model: str | None = None):
        self.model = model
        self.task_desc = ""
        self.instructions = ""
        self.apis: dict[str, str] = {}
        self.submission_file: Path | None = None
        self.usage = empty_token_usage()

    def init_context(self, problem_desc: str, instructions: str, apis: dict[str, str]):
        self.task_desc = problem_desc
        self.instructions = instructions
        self.apis = apis
        self.usage = empty_token_usage()

    async def get_action(self, input_text: str) -> str:
        raise RuntimeError(
            f"{type(self).__name__} is autonomous and does not use get_action(); "
            "use run_autonomous() via the orchestrator"
        )

    async def run_autonomous(
        self,
        *,
        workdir: Path,
        tool_env: dict[str, str],
        max_steps: int,
    ) -> CodingAgentResult:
        raise NotImplementedError

    def _build_instruction(self) -> str:
        return build_instruction(
            task_desc=self.task_desc,
            instructions=self.instructions,
            apis=self.apis,
        )

    def _load_solution(self, workdir: Path) -> Any | None:
        sub = workdir / "submission.json"
        if not sub.exists():
            sub = workdir / "scratch" / "submission.json"
        self.submission_file = sub
        return read_submission(sub)
