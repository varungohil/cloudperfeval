"""A single-LLM ReAct-style agent over an OpenAI-compatible Chat API.

Env:
  OPENAI_API_KEY     (required for OpenAI)
  CPE_MODEL          (default model, e.g. gpt-4o)
  OPENAI_BASE_URL    (optional, for compatible gateways / vLLM)
"""

from __future__ import annotations

import os

from cloudperfeval.prompts import RESP_INSTR, build_system_message


def _uses_max_completion_tokens(model: str) -> bool:
    name = model.lower()
    return name.startswith(("gpt-5", "o1", "o3", "o4"))


def _completion_kwargs(model: str, messages: list[dict]) -> dict:
    kwargs: dict = {"model": model, "messages": messages}
    if _uses_max_completion_tokens(model):
        kwargs["max_completion_tokens"] = 1024
    else:
        kwargs["max_tokens"] = 1024
        kwargs["temperature"] = 0.5
        kwargs["top_p"] = 0.95
    return kwargs


class LLMAgent:
    def __init__(self, model: str | None = None):
        from openai import OpenAI  # lazy import

        self.model = model or os.getenv("CPE_MODEL", "gpt-4o")
        base_url = os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        self.history: list[dict] = []
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def init_context(self, problem_desc: str, instructions: str, apis: dict[str, str]):
        self.history = []
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        self.history.append({"role": "system", "content": build_system_message(problem_desc, apis)})
        self.history.append({"role": "user", "content": instructions})

    def _record_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)
        self.usage["prompt_tokens"] += prompt
        self.usage["completion_tokens"] += completion
        self.usage["input_tokens"] += prompt
        self.usage["output_tokens"] += completion
        self.usage["total_tokens"] += total

    async def get_action(self, input_text: str) -> str:
        self.history.append({"role": "user", "content": input_text + "\n\n" + RESP_INSTR})
        response = self.client.chat.completions.create(
            **_completion_kwargs(self.model, self.history)
        )
        self._record_usage(response)
        content = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": content})
        return content
