from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudperfeval.agents.sandbox import (
    build_docker_command,
    prepare_sandbox_paths,
)
from cloudperfeval.agents.docker_proxy import (
    DockerReadOnlyProxy,
    docker_read_allowed,
)
from cloudperfeval.agents.coding import AutonomousCodingAgent, build_instruction
from cloudperfeval.config import config
from cloudperfeval.tools.call import available_actions
from cloudperfeval.tools.dispatch import SUBMISSION_ENV
from cloudperfeval.tools.gateway import ToolGateway, dispatch_remote


class ToolGatewayTests(unittest.TestCase):
    def test_submit_crosses_gateway_and_writes_host_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submission = root / "submission.json"
            with ToolGateway(root / "gateway", {SUBMISSION_ENV: str(submission)}) as gateway:
                result = dispatch_remote(
                    str(gateway.socket_path),
                    gateway.token,
                    "submit",
                    (),
                    {"solution": {"root_cause_service": "frontend"}},
                )

            self.assertIn("Submission accepted", result)
            self.assertEqual(
                json.loads(submission.read_text(encoding="utf-8")),
                {"root_cause_service": "frontend"},
            )

    def test_gateway_rejects_manager_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ToolGateway(Path(tmp) / "gateway", {}) as gateway:
                result = dispatch_remote(
                    str(gateway.socket_path),
                    gateway.token,
                    "exec_shell",
                    (),
                    {"command": "touch /tmp/escape"},
                )
            self.assertIn("disabled in sandboxed runs", result)

    def test_gateway_rejects_bad_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with ToolGateway(Path(tmp) / "gateway", {}) as gateway:
                result = dispatch_remote(
                    str(gateway.socket_path),
                    "wrong-token",
                    "list_services",
                    (),
                    {},
                )
            self.assertEqual(result, "Error: unauthorized")


class DockerCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = config.get("agent_sandbox")
        config.set(
            "agent_sandbox",
            {
                "enabled": True,
                "runtime": "docker",
                "image": "test-sandbox:latest",
                "cpus": 1,
                "memory_limit": "512m",
                "pids_limit": 64,
                "network": "none",
            },
        )

    def tearDown(self) -> None:
        config.set("agent_sandbox", self.previous)

    def test_docker_jail_has_only_expected_host_writable_mount(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = prepare_sandbox_paths(Path(tmp))
            command, env = build_docker_command(
                ["python", "-c", "print('ok')"],
                agent_kind="claude",
                paths=paths,
                env={
                    "ANTHROPIC_API_KEY": "secret",
                    "CPE_TOOL_TOKEN": "token",
                    "UNRELATED_SECRET": "must-not-pass",
                },
            )
            rendered = " ".join(command)

            self.assertIn("--read-only", command)
            self.assertIn("--cap-drop=ALL", command)
            self.assertIn("--security-opt=no-new-privileges", command)
            self.assertIn(f"src={paths.scratch},dst=/scratch", rendered)
            self.assertIn(f"src={paths.gateway_dir},dst=/run/cpe,readonly", rendered)
            self.assertNotIn("/var/run/docker.sock", rendered)
            self.assertNotIn(str(Path(__file__).parents[1]), rendered)
            self.assertNotIn("agent_workdirs", rendered)
            self.assertNotIn("secret", rendered)
            self.assertNotIn("UNRELATED_SECRET", env)
            self.assertIn(
                "DOCKER_HOST=unix:///run/cpe/docker.sock",
                command,
            )
            self.assertNotEqual(env.get("DOCKER_HOST"), "unix:///run/cpe/docker.sock")

    def test_disabled_action_is_hidden_from_cli_listing(self) -> None:
        with patch.dict(os.environ, {"CPE_DISABLED_ACTIONS": "exec_shell"}, clear=False):
            self.assertNotIn("exec_shell", available_actions())
            self.assertIn("list_services", available_actions())
            from cloudperfeval.tools.call import parse_args

            with self.assertRaises(SystemExit):
                parse_args(["exec_shell", "--arg", "command=true"])

    def test_docker_proxy_policy_is_get_only_and_path_limited(self) -> None:
        self.assertTrue(docker_read_allowed("GET", "/v1.51/services"))
        self.assertTrue(docker_read_allowed("GET", "/services/id/logs?stdout=1"))
        self.assertFalse(docker_read_allowed("POST", "/services/id/update"))
        self.assertFalse(docker_read_allowed("DELETE", "/containers/id"))
        self.assertFalse(docker_read_allowed("GET", "/secrets"))

    def test_sandbox_prompt_has_no_cpe_tool_descriptions(self) -> None:
        prompt = build_instruction(
            task_desc=(
                "diagnose\nWhen confident, submit:\n\n"
                "```\nsubmit({'root_cause_service':'x'})\n```\n"
            ),
            instructions="SENTINEL ORIGINAL TOOL INSTRUCTIONS",
            apis={"sentinel_tool": "SENTINEL TOOL DESCRIPTION"},
        )
        self.assertIn("DIRECT INVESTIGATION", prompt)
        self.assertIn("$CPE_PROMETHEUS_URL", prompt)
        self.assertIn("/scratch/submission.json", prompt)
        self.assertNotIn("sentinel_tool", prompt)
        self.assertNotIn("SENTINEL TOOL DESCRIPTION", prompt)
        self.assertNotIn("SENTINEL ORIGINAL TOOL INSTRUCTIONS", prompt)
        self.assertNotIn("cloudperfeval.tools.call", prompt)
        self.assertNotIn("submit({'root_cause_service'", prompt)

    def test_solution_loads_from_scratch_without_submit_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            scratch = workdir / "scratch"
            scratch.mkdir()
            (scratch / "submission.json").write_text(
                '{"root_cause_service":"frontend"}',
                encoding="utf-8",
            )
            solution = AutonomousCodingAgent()._load_solution(workdir)
            self.assertEqual(solution, {"root_cause_service": "frontend"})


@unittest.skipUnless(
    os.environ.get("CPE_RUN_DOCKER_SANDBOX_TESTS") == "1",
    "set CPE_RUN_DOCKER_SANDBOX_TESTS=1 to run Docker integration tests",
)
class DockerRuntimeIntegrationTests(unittest.TestCase):
    def test_container_isolation_and_direct_read_only_access(self) -> None:
        previous = config.get("agent_sandbox")
        config.set(
            "agent_sandbox",
            {
                "enabled": True,
                "runtime": "docker",
                "image": "cpe-agent-sandbox:latest",
                "network": "none",
                "cpus": 1,
                "memory_limit": "512m",
                "pids_limit": 64,
            },
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                paths = prepare_sandbox_paths(workdir)
                submission = paths.scratch / "submission.json"
                app_source = workdir / "app-source"
                app_source.mkdir()
                (app_source / "visible.txt").write_text("read-only", encoding="utf-8")
                with DockerReadOnlyProxy(paths.gateway_dir):
                    direct_env = {
                        "CPE_PROMETHEUS_URL": "http://prometheus.invalid",
                        "CPE_JAEGER_URL": "http://jaeger.invalid",
                        "CPE_STACK_NAME": "sn",
                    }
                    inner = (
                        "touch /scratch/allowed && "
                        "! touch /opt/cpe/forbidden 2>/dev/null && "
                        "test ! -S /var/run/docker.sock && "
                        "test -S /run/cpe/docker.sock && "
                        "python -c \"import importlib.util; "
                        "assert importlib.util.find_spec('cloudperfeval') is None\" && "
                        "docker version --format '{{.Server.Version}}' >/dev/null && "
                        "docker service ls >/dev/null && "
                        "docker node ls >/dev/null && "
                        "test \"$(curl -sS --unix-socket /run/cpe/docker.sock "
                        "-X POST -o /dev/null -w '%{http_code}' "
                        "http://localhost/containers/create)\" = 403 && "
                        "test -r /opt/app-source/visible.txt && "
                        "! touch /opt/app-source/forbidden 2>/dev/null && "
                        "ln -s /opt/app-source /scratch/outside && "
                        "! touch /scratch/outside/forbidden 2>/dev/null && "
                        "printf '%s' '{\"root_cause_service\":\"frontend\"}' "
                        "> /scratch/submission.json"
                    )
                    command, env = build_docker_command(
                        ["bash", "-lc", inner],
                        agent_kind="claude",
                        paths=paths,
                        env=direct_env,
                        readonly_mounts=[(app_source, "/opt/app-source")],
                    )
                    completed = subprocess.run(
                        command,
                        env=env,
                        text=True,
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue((paths.scratch / "allowed").exists())
                self.assertFalse((Path(__file__).parents[1] / "forbidden").exists())
                self.assertEqual(
                    json.loads(submission.read_text(encoding="utf-8")),
                    {"root_cause_service": "frontend"},
                )
        finally:
            config.set("agent_sandbox", previous)


if __name__ == "__main__":
    unittest.main()
