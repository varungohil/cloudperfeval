"""Agent factory."""

from __future__ import annotations

from cloudperfeval.agents.llm import LLMAgent
from cloudperfeval.agents.manual import ManualAgent

AGENT_CHOICES = ("llm", "manual")


def create_agent(agent_type: str, model: str | None = None):
    agent_type = agent_type.lower()
    if agent_type == "llm":
        return LLMAgent(model=model)
    if agent_type == "manual":
        return ManualAgent(model=model)
    raise ValueError(
        f"Unknown agent type {agent_type!r}. Choose from: {', '.join(AGENT_CHOICES)}"
    )
