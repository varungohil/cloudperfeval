"""Claude Code agent — SREGym / Harbor-style `claude -p` workflow.

Claude investigates via Bash + `python -m cloudperfeval.tools.call` (no MCP
config). Auth prefers CLAUDE_CODE_OAUTH_TOKEN over ANTHROPIC_API_KEY.
"""

from __future__ import annotations

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
    claude_auth_env,
    default_timeout_sec,
    parse_agent_stream_usage,
    run_streaming_cli,
    setup_claude_sessions,
    strip_model_name,
    which_or_raise,
    write_instruction_file,
)


class ClaudeCodeAgent(AutonomousCodingAgent):
    """Run Claude Code non-interactively (SREGym-compatible flags + auth)."""

    _OUTPUT_FILENAME = "claude-code.txt"

    # Same allow-list as SREGym / Harbor Claude Code agent.
    ALLOWED_TOOLS = [
        "Bash",
        "Edit",
        "Write",
        "Read",
        "Glob",
        "Grep",
        "LS",
        "WebFetch",
        "NotebookEdit",
        "NotebookRead",
        "TodoRead",
        "TodoWrite",
        "Agent",
        "Skill",
        "SlashCommand",
        "Task",
        "WebSearch",
    ]

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

        model = strip_model_name(self.model, default="sonnet") or "sonnet"
        invalid_patterns = (
            "bedrock",
            "litellm",
            "azure",
            "openai",
            "watsonx",
            "gemini",
        )
        if any(p in model.lower() for p in invalid_patterns):
            model = "sonnet"

        sandboxed = sandbox_enabled()
        sandbox_paths = prepare_sandbox_paths(workdir) if sandboxed else None
        sessions_dir = (
            sandbox_paths.home / ".claude" if sandbox_paths else workdir / "sessions"
        )
        setup_claude_sessions(sessions_dir)

        base_env = child_env(
            tool_env,
            {
                "CLAUDE_CONFIG_DIR": str(sessions_dir),
                "FORCE_AUTO_BACKGROUND_TASKS": "1",
                "ENABLE_BACKGROUND_TASKS": "1",
                "ANTHROPIC_MODEL": model,
            },
        )
        env = claude_auth_env(base_env)
        if env is None:
            msg = (
                "No Anthropic auth found. Set ANTHROPIC_API_KEY or "
                "CLAUDE_CODE_OAUTH_TOKEN before running --agent claude-code."
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
            claude = SandboxSettings.from_config().claude_bin
        else:
            claude = which_or_raise(
                "claude",
                "Install Claude Code (https://docs.anthropic.com/en/docs/claude-code) "
                "and ensure `claude` is on PATH.",
            )

        cmd = [
            claude,
            "--verbose",
            "--output-format",
            "stream-json",
            "-p",
            instruction,
            "--allowedTools",
            *self.ALLOWED_TOOLS,
        ]
        run_cwd = workdir
        if sandbox_paths is not None:
            cmd, env = build_docker_command(
                cmd,
                agent_kind="claude",
                paths=sandbox_paths,
                env=env,
            )

        history = [
            {"role": "system", "content": instruction},
            {
                "role": "meta",
                "content": (
                    f"cmd={sandbox_description(cmd) if sandboxed else 'claude --verbose --output-format stream-json -p ...'} "
                    f"--allowedTools ... model={model} timeout_sec={timeout}"
                ),
            },
        ]

        output_path = workdir / self._OUTPUT_FILENAME
        stdout, returncode, timed_out = await run_streaming_cli(
            cmd,
            cwd=run_cwd,
            env=env,
            output_path=output_path,
            timeout=timeout,
        )

        history.append({"role": "assistant", "content": stdout[-50000:] if stdout else ""})
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
