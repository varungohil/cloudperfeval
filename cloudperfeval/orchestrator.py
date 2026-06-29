"""Orchestrator: inject -> load -> agent loop -> grade -> recover.

This is the execution engine described in the design. `init_problem(problem_id)`
sets up the environment (fault + workload) and returns the agent-facing prompt;
`run(max_steps)` drives the turn-based agent loop and, on a valid submission,
grades it with `problem.eval(...)`. The fault is always recovered in `finally`.
"""

from __future__ import annotations

from cloudperfeval.actions import SwarmActions, get_actions_doc
from cloudperfeval.parser import ResponseParser
from cloudperfeval.problems.registry import ProblemRegistry
from cloudperfeval.session import Session
from cloudperfeval.status import (
    InvalidActionError,
    ResponseParsingError,
    SessionPrint,
    SubmissionStatus,
)


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
