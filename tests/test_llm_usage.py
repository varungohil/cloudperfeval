"""Unit tests for LLM / coding-agent token usage tracking."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cloudperfeval.agents.coding import parse_agent_stream_usage
from cloudperfeval.agents.llm import LLMAgent
from cloudperfeval.orchestrator import _apply_agent_usage


def _usage(prompt: int, completion: int, total: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total if total is not None else prompt + completion,
    )


def _completion_response(content: str, usage: SimpleNamespace | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


class ApplyAgentUsageTests(unittest.TestCase):
    def test_copies_usage_onto_results(self):
        agent = SimpleNamespace(
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
            }
        )
        results: dict = {"duration_sec": 1.5}
        _apply_agent_usage(results, agent)
        self.assertEqual(results["prompt_tokens"], 10)
        self.assertEqual(results["completion_tokens"], 4)
        self.assertEqual(results["input_tokens"], 10)
        self.assertEqual(results["output_tokens"], 4)
        self.assertEqual(results["total_tokens"], 14)
        self.assertEqual(results["duration_sec"], 1.5)

    def test_does_not_overwrite_existing_keys(self):
        agent = SimpleNamespace(
            usage={"prompt_tokens": 99, "completion_tokens": 1, "total_tokens": 100}
        )
        results = {"prompt_tokens": 5}
        _apply_agent_usage(results, agent)
        self.assertEqual(results["prompt_tokens"], 5)
        self.assertEqual(results["completion_tokens"], 1)

    def test_skips_agents_without_usage(self):
        results: dict = {}
        _apply_agent_usage(results, SimpleNamespace())
        self.assertEqual(results, {})


class LLMAgentUsageTests(unittest.TestCase):
    def _make_agent(self) -> LLMAgent:
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            return LLMAgent(model="gpt-4o")

    def test_record_usage_accumulates(self):
        agent = self._make_agent()
        agent._record_usage(_completion_response("a", _usage(100, 20)))
        agent._record_usage(_completion_response("b", _usage(50, 10)))
        self.assertEqual(
            agent.usage,
            {
                "prompt_tokens": 150,
                "completion_tokens": 30,
                "input_tokens": 150,
                "output_tokens": 30,
                "total_tokens": 180,
            },
        )

    def test_record_usage_ignores_missing_usage(self):
        agent = self._make_agent()
        agent._record_usage(_completion_response("ok", None))
        self.assertEqual(
            agent.usage,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )

    def test_init_context_resets_usage(self):
        agent = self._make_agent()
        agent.usage = {
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
        }
        agent.init_context("problem", "do the thing", {"get_traces": "doc"})
        self.assertEqual(
            agent.usage,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )
        self.assertEqual(len(agent.history), 2)

    def test_get_action_records_usage(self):
        agent = self._make_agent()
        agent.history = [{"role": "system", "content": "sys"}]
        agent.client.chat.completions.create.return_value = _completion_response(
            "```\nsubmit({})\n```",
            _usage(120, 30, 150),
        )

        content = asyncio.run(agent.get_action("next"))
        self.assertIn("submit", content)
        self.assertEqual(
            agent.usage,
            {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "input_tokens": 120,
                "output_tokens": 30,
                "total_tokens": 150,
            },
        )
        agent.client.chat.completions.create.assert_called_once()


class ParseAgentStreamUsageTests(unittest.TestCase):
    def test_codex_turn_completed(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "thread.started"}),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 800,
                            "output_tokens": 50,
                            "reasoning_output_tokens": 10,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 200,
                            "output_tokens": 25,
                        },
                    }
                ),
            ]
        )
        self.assertEqual(
            parse_agent_stream_usage(stdout),
            {"input_tokens": 1200, "output_tokens": 75, "total_tokens": 1275},
        )

    def test_claude_result_sums_cache_fields(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "usage": {
                                "input_tokens": 9,
                                "cache_creation_input_tokens": 100,
                                "cache_read_input_tokens": 200,
                                "output_tokens": 3,
                            }
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "usage": {
                            "input_tokens": 12,
                            "cache_creation_input_tokens": 500,
                            "cache_read_input_tokens": 9000,
                            "output_tokens": 400,
                        },
                    }
                ),
            ]
        )
        self.assertEqual(
            parse_agent_stream_usage(stdout),
            {
                "input_tokens": 12 + 500 + 9000,
                "output_tokens": 400,
                "total_tokens": 12 + 500 + 9000 + 400,
            },
        )

    def test_empty_or_garbage_stdout(self):
        self.assertEqual(
            parse_agent_stream_usage(""),
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )
        self.assertEqual(
            parse_agent_stream_usage("not json\n{bad}\n"),
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )


if __name__ == "__main__":
    unittest.main()
