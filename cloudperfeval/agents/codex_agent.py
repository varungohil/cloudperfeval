"""OpenAI Codex agent — SREGym / Harbor-style `codex exec` workflow.

Codex investigates via Bash + `python -m cloudperfeval.tools.call` (no project
MCP config). Auth prefers existing ~/.codex credentials, else writes auth.json
from OPENAI_API_KEY under CODEX_HOME (the run workdir).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from cloudperfeval.agents.sandbox import (
    SandboxSettings,
    build_docker_command,
    prepare_sandbox_paths,
    sandbox_description,
    sandbox_enabled,
)
from cloudperfeval.agents.coding import (
    AutonomousCodingAgent,
    CodingAgentResult,
    child_env,
    cleanup_codex_auth,
    default_timeout_sec,
    parse_agent_stream_usage,
    resolve_codex_home,
    run_streaming_cli,
    strip_model_name,
    which_or_raise,
    write_instruction_file,
)


class CodexAgent(AutonomousCodingAgent):
    """Run Codex non-interactively (SREGym-compatible flags + auth)."""

    _OUTPUT_FILENAME = "codex.txt"

    async def run_autonomous(
        self,
        *,
        workdir: Path,
        tool_env: dict[str, str],
        max_steps: int,
    ) -> CodingAgentResult:
        workdir = workdir.resolve()
        workdir.mkdir(parents=True, exist_ok=True)

        instruction = self._build_instruction()
        write_instruction_file(workdir, instruction)
        timeout = default_timeout_sec(max_steps)
        model = strip_model_name(self.model)
        sandboxed = sandbox_enabled()
        sandbox_paths = prepare_sandbox_paths(workdir) if sandboxed else None

        # SREGym: prefer subscription ~/.codex; else workdir + OPENAI_API_KEY.
        if sandboxed:
            codex_home = Path.home() / ".codex"
            created_auth = False
        else:
            codex_home, created_auth = resolve_codex_home(workdir)
        if not (codex_home / "auth.json").exists() and not os.environ.get(
            "OPENAI_API_KEY"
        ):
            msg = (
                "No OpenAI auth found for Codex. Set OPENAI_API_KEY or run "
                "`codex login` (expects ~/.codex/auth.json)."
            )
            return CodingAgentResult(
                solution=None,
                history=[
                    {"role": "system", "content": instruction},
                    {"role": "env", "content": msg},
                ],
                stdout="",
                stderr=msg,
                returncode=1,
                workdir=str(workdir),
                timed_out=False,
            )

        if sandboxed:
            codex = SandboxSettings.from_config().codex_bin
        else:
            codex = which_or_raise(
                "codex",
                "Install the OpenAI Codex CLI (https://github.com/openai/codex) "
                "and ensure `codex` is on PATH.",
            )

        # Our Docker jail is the isolation boundary. Codex's own bubblewrap
        # sandbox (`--sandbox workspace-write`) needs unprivileged user
        # namespaces, which the container does not grant, so every command
        # would fail with `bwrap: No permissions to create a new namespace`.
        # Bypass Codex's nested sandbox and rely on Docker instead.
        execution_flags = ["--dangerously-bypass-approvals-and-sandbox"]
        cmd = [
            codex,
            "exec",
            *execution_flags,
            "--skip-git-repo-check",
            "--json",
            "--enable",
            "unified_exec",
            "-c",
            "model_reasoning_effort=high",
        ]
        if model:
            cmd.extend(["--model", model])
        cmd.extend(["--", instruction])

        env = child_env(tool_env, {"CODEX_HOME": str(codex_home)})
        # Subscription path: don't let a stale OPENAI_API_KEY override OAuth.
        if (
            not created_auth
            and codex_home == Path.home() / ".codex"
            and (codex_home / "auth.json").exists()
        ):
            env.pop("OPENAI_API_KEY", None)
        if sandbox_paths is not None:
            # CODEX_HOME lives under the writable scratch mount and must exist
            # before `codex exec` starts. Seed it with usable auth: prefer an
            # existing host auth.json, else materialize one from OPENAI_API_KEY.
            host_codex_home = sandbox_paths.home / ".codex"
            host_codex_home.mkdir(parents=True, exist_ok=True)
            dest_auth = host_codex_home / "auth.json"
            host_auth = codex_home / "auth.json"
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if host_auth.exists():
                shutil.copy2(host_auth, dest_auth)
            elif api_key:
                dest_auth.write_text(
                    json.dumps({"OPENAI_API_KEY": api_key}), encoding="utf-8"
                )
            try:
                dest_auth.chmod(0o600)
            except OSError:
                pass
            cmd, env = build_docker_command(
                cmd,
                agent_kind="codex",
                paths=sandbox_paths,
                env=env,
            )

        history = [
            {"role": "system", "content": instruction},
            {
                "role": "meta",
                "content": (
                    f"cmd={sandbox_description(cmd) if sandboxed else ' '.join(cmd[:8]) + '...'} "
                    f"timeout_sec={timeout} "
                    f"CODEX_HOME={codex_home} auth_created={created_auth}"
                ),
            },
        ]

        output_path = workdir / self._OUTPUT_FILENAME
        try:
            stdout, returncode, timed_out = await run_streaming_cli(
                cmd,
                cwd=workdir,
                env=env,
                output_path=output_path,
                timeout=timeout,
            )
        finally:
            cleanup_codex_auth(codex_home, created_auth)

        history.append(
            {"role": "assistant", "content": stdout[-50000:] if stdout else ""}
        )
        solution = self._load_solution(workdir)
        usage = parse_agent_stream_usage(stdout)
        self.usage = usage
        return CodingAgentResult(
            solution=solution,
            history=history,
            stdout=stdout,
            stderr="",
            returncode=returncode,
            workdir=str(workdir),
            timed_out=timed_out,
            usage=usage,
        )
