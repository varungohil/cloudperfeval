"""Orchestrator: inject -> load -> agent loop -> grade -> recover.

This is the execution engine described in the design. `init_problem(problem_id)`
sets up the environment (fault + workload) and returns the agent-facing prompt;
`run(max_steps)` drives the turn-based agent loop and, on a valid submission,
grades it with `problem.eval(...)`. The fault is always recovered in `finally`.

Coding agents (`codex`, `claude-code`) use an autonomous SREGym-style path:
they receive one instruction, investigate via Bash + `python -m
cloudperfeval.tools.call`, write submission.json, and the orchestrator grades it.
"""

from __future__ import annotations

from pathlib import Path

from cloudperfeval.actions import SwarmActions, get_actions_doc
from cloudperfeval.agents.docker_proxy import DockerReadOnlyProxy
from cloudperfeval.agents.sandbox import prepare_sandbox_paths, sandbox_enabled
from cloudperfeval.config import config
from cloudperfeval.parser import ResponseParser
from cloudperfeval.problems.registry import ProblemRegistry
from cloudperfeval.session import Session, problem_short_name
from cloudperfeval.status import (
    InvalidActionError,
    ResponseParsingError,
    SessionPrint,
    SubmissionStatus,
)
from cloudperfeval.tools.dispatch import tool_env_for_session


def _apply_agent_usage(results: dict, agent) -> None:
    """Copy accumulated LLM token usage onto results (same pattern as duration_sec)."""
    usage = getattr(agent, "usage", None)
    if not isinstance(usage, dict):
        return
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    ):
        if key in usage:
            results.setdefault(key, usage[key])


class Orchestrator:
    def __init__(self):
        self.agent = None
        self.agent_name = None
        self.session: Session | None = None
        self.parser = ResponseParser()
        self.actions = SwarmActions()
        self.sprint = SessionPrint()
        self.registry = ProblemRegistry()
        self.problem = None
        self._log_capture = None

    # ---- setup -----------------------------------------------------------
    def register_agent(self, agent, name="agent"):
        self.agent = agent
        self.agent_name = name
        from cloudperfeval.run_log import RunLogCapture

        self._log_capture = RunLogCapture()
        self._log_capture.start()

    def init_problem(self, problem_id: str, phase: str = "full", snapshot_id: str | None = None):
        """Instantiate the problem, inject fault, run workload, build prompt.

        phase:
          full  — inject, load, Jaeger wait/capture, agent prompt (default)
          snapshot — inject, load, save snapshot, recover fault, exit
          run   — load snapshot by id, Jaeger wait/capture, agent prompt

        Returns:
            (task_desc, instructions, apis) for the agent's context.
        """
        from cloudperfeval.stored_run import StoredRun

        self.session = Session()
        self.session.set_agent(self.agent_name)
        if self._log_capture is not None:
            self.session._run_log_capture = self._log_capture
            self._log_capture = None
        else:
            self.session.begin_run_log()
        self.problem = self.registry.get_problem_instance(problem_id)

        if phase == "snapshot":
            print(f"[ENV] Saving snapshot for '{problem_id}': {self.problem.faults_summary()}")
            self.problem.setup_store()
            return None, None, None

        if phase == "run":
            if not snapshot_id:
                raise ValueError(
                    "--phase run requires --snapshot-id. "
                    "Use --list-snapshots to see available snapshots."
                )
            stored = StoredRun.require(snapshot_id, problem_id)
            print(
                f"[ENV] Resuming '{problem_id}' from snapshot {snapshot_id!r} "
                f"({stored.path()})"
            )
            self.problem.setup_from_stored(stored)
        else:
            print(f"[ENV] Setting up problem '{problem_id}': {self.problem.faults_summary()}")
            self.problem.setup()

        task_desc = self.problem.get_task_description()
        instructions = self.problem.get_instructions()
        apis = get_actions_doc()

        self.session.set_problem(problem_id, task_desc)
        return task_desc, instructions, apis

    # ---- interaction -----------------------------------------------------
    async def ask_agent(self, input_text: str) -> str:
        assert self.session is not None and self.agent is not None
        response = await self.agent.get_action(input_text)
        self.session.add({"role": "assistant", "content": response})
        return response

    async def ask_env(self, action: str):
        assert self.session is not None
        try:
            parsed = self.parser.parse(action)
        except ResponseParsingError as e:
            self.session.add({"role": "env", "content": str(e)})
            return str(e)

        api, args, kwargs = parsed["api_name"], parsed["args"], parsed["kwargs"]
        if api == "submit":
            self.session.set_solution(args[0] if len(args) == 1 else (args or kwargs))

        try:
            method = getattr(self.actions, api, None)
            if method is None or not callable(method):
                raise InvalidActionError(api)
            env_response = method(*args, **kwargs)
        except InvalidActionError as e:
            env_response = str(e)
        except TypeError as e:
            env_response = f"Error calling {api}: {e}"
        except Exception as e:
            env_response = f"Unhandled error during {api}: {e}"

        self.session.add({"role": "env", "content": str(env_response)})
        return env_response

    # ---- main loop -------------------------------------------------------
    async def run(self, max_steps: int) -> dict:
        assert self.session is not None and self.problem is not None
        if getattr(self.agent, "autonomous", False):
            return await self._run_autonomous(max_steps)
        return await self._run_turn_based(max_steps)

    async def _run_turn_based(self, max_steps: int) -> dict:
        assert self.session is not None and self.problem is not None
        action_instr = "Please take the next action"
        env_response, results = "", {}
        step = 0
        self.session.start()

        try:
            for step in range(max_steps):
                action = await self.ask_agent(action_instr)
                self.sprint.agent(action)

                env_response = await self.ask_env(action)
                self.sprint.service(env_response)

                if env_response == SubmissionStatus.VALID_SUBMISSION:
                    results = self.problem.eval(
                        self.session.solution,
                        self.session.history,
                        self.session.get_duration(),
                    )
                    results["submission"] = "valid"
                    break
                elif env_response == SubmissionStatus.INVALID_SUBMISSION:
                    results = {"submission": "invalid", "success": False}
                    break

                action_instr = str(env_response) + "\n" + "Please take the next action"

            if not results:
                # max_steps reached without a submission
                results = {"submission": "none", "success": False}
                results["steps"] = step + 1
        finally:
            self.session.end()
            results.setdefault("steps", step + 1)
            results.setdefault("duration_sec", round(self.session.get_duration(), 2))
            _apply_agent_usage(results, self.agent)
            self.session.set_results(results)
            self.sprint.result(results)
            print(f"[ENV] Recovering fault for '{self.problem.problem_id}'")
            self.problem.teardown()

        return {
            "history": self.session.history,
            "final_state": env_response,
            "results": results,
        }

    async def _run_autonomous(self, max_steps: int) -> dict:
        """Hand control to a coding agent (Claude Code / Codex) until submit/exit."""
        assert self.session is not None and self.problem is not None and self.agent is not None

        results_dir = Path(config.get("results_dir", "./results")).resolve()
        workdir = (
            results_dir
            / "agent_workdirs"
            / f"{problem_short_name(self.problem.problem_id)}_{self.session.session_id}"
        ).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        submission_file = (workdir / "submission.json").resolve()
        tool_env = tool_env_for_session(submission_file=submission_file)
        docker_proxy: DockerReadOnlyProxy | None = None
        if sandbox_enabled():
            sandbox_paths = prepare_sandbox_paths(workdir)
            manager_host = config.get("manager_host", "localhost")
            if manager_host != "localhost":
                raise RuntimeError(
                    "tool-less sandbox mode requires manager_host=localhost "
                    "for the read-only Docker API proxy"
                )
            docker_proxy = DockerReadOnlyProxy(sandbox_paths.gateway_dir).start()
            tool_env = {
                "CPE_PROMETHEUS_URL": str(config.get("prometheus_url", "")),
                "CPE_JAEGER_URL": str(config.get("jaeger_url", "")),
                "CPE_STACK_NAME": str(config.get("stack_name", "")),
            }

        print(f"[ENV] Autonomous agent workdir: {workdir}")
        if docker_proxy is not None:
            print("[ENV] Agent filesystem sandbox: tool-less direct investigation")

        env_response: str = ""
        results: dict = {}
        self.session.start()
        try:
            outcome = await self.agent.run_autonomous(
                workdir=workdir,
                tool_env=tool_env,
                max_steps=max_steps,
            )
            for item in getattr(outcome, "history", None) or []:
                self.session.add(item)
            if outcome.stdout:
                self.sprint.agent(outcome.stdout)
            if outcome.stderr:
                self.session.add({"role": "env", "content": f"[stderr]\n{outcome.stderr}"})

            solution = outcome.solution
            if solution is not None:
                self.session.set_solution(solution)
                results = self.problem.eval(
                    self.session.solution,
                    self.session.history,
                    self.session.get_duration(),
                )
                results["submission"] = "valid"
                env_response = SubmissionStatus.VALID_SUBMISSION.name
            else:
                results = {"submission": "none", "success": False}
                env_response = "no submission"
                if outcome.timed_out:
                    results["error"] = "agent timed out before submit"
                    env_response = "timeout"
                elif outcome.returncode not in (0, None):
                    results["error"] = (
                        f"agent exited with code {outcome.returncode}"
                    )

            results["agent_workdir"] = str(workdir)
            results["agent_returncode"] = outcome.returncode
            if outcome.timed_out:
                results["timed_out"] = True
        finally:
            if docker_proxy is not None:
                docker_proxy.stop()
            self.session.end()
            results.setdefault("steps", max_steps)
            results.setdefault("duration_sec", round(self.session.get_duration(), 2))
            _apply_agent_usage(results, self.agent)
            self.session.set_results(results)
            self.sprint.result(results)
            print(f"[ENV] Recovering fault for '{self.problem.problem_id}'")
            self.problem.teardown()

        return {
            "history": self.session.history,
            "final_state": env_response,
            "results": results,
        }

    def save_session(self) -> dict:
        """Flush captured stdout/stderr and write session JSON + log artifacts."""
        if self.session is not None:
            self.session.end_run_log()
            path = self.session.to_json()
            if self.session.run_log_path:
                print(f"Session saved to {path}")
                print(f"Run log saved to {self.session.run_log_path}")
            else:
                print(f"Session saved to {path}")
            return {
                "session_path": path,
                "run_log_path": self.session.run_log_path,
            }

        if self._log_capture is not None:
            self._log_capture.stop()
            self._log_capture = None
        return {}
