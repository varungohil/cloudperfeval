"""A human-in-the-loop agent: you type API calls at the prompt.

Useful for testing problems end-to-end without an LLM. The system message and
API catalog are printed once; thereafter you paste a single API call per turn.
"""

from __future__ import annotations

from cloudperfeval.prompts import build_system_message


class ManualAgent:
    def __init__(self, model: str | None = None):
        self.model = model or "human"
        self.printed = False

    def init_context(self, problem_desc: str, instructions: str, apis: dict[str, str]):
        print("\n" + "=" * 70)
        print(build_system_message(problem_desc, apis))
        print(instructions)
        print("=" * 70 + "\n")

    async def get_action(self, input_text: str) -> str:
        print(f"\n[ENV] {input_text}\n")
        print("Enter a single API call wrapped in a ``` code block.")
        print("Finish input with a line containing only 'END'.\n")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "END":
                break
            lines.append(line)
        text = "\n".join(lines).strip()
        # Allow bare calls without fences for convenience.
        if "```" not in text:
            text = f"```\n{text}\n```"
        return text
