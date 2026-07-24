"""Agent factory."""

from __future__ import annotations

from cloudperfeval.agents.claude_code import ClaudeCodeAgent
from cloudperfeval.agents.codex_agent import CodexAgent
from cloudperfeval.agents.llm import LLMAgent
from cloudperfeval.agents.manual import ManualAgent

AGENT_CHOICES = ("manual", "llm", "codex", "claude-code")


def create_agent(agent_type: str, model: str | None = None):
    agent_type = agent_type.lower()
    if agent_type == "llm":
        return LLMAgent(model=model)
    if agent_type == "manual":
        return ManualAgent(model=model)
    if agent_type == "codex":
        return CodexAgent(model=model)
    if agent_type in ("claude-code", "claude_code", "claudecode"):
        return ClaudeCodeAgent(model=model)
    raise ValueError(
        f"Unknown agent type {agent_type!r}. Choose from: {', '.join(AGENT_CHOICES)}"
    )
