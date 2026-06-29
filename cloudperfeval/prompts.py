"""Prompt assembly: combine a problem's symptom prompt with the API catalog."""

DOCS = """\
{task_desc}

You are provided with the following read-only observability APIs:

{telemetry_apis}

You also have a (non-interactive) read-only terminal on the Swarm manager:

{shell_api}

You submit your final diagnosis with:

{submit_api}

Instructions:
- Respond with exactly ONE API call per turn, inside a single ``` code block.
- Do not put any other text inside the code block.
- Investigation is READ-ONLY: do not scale, deploy, update, remove, or otherwise
  modify Swarm services, nodes, or the stack. Diagnose, then submit.

Example:

```
list_trace_services()
```
"""


def build_system_message(task_desc: str, apis: dict[str, str]) -> str:
    shell_api = {k: v for k, v in apis.items() if k == "exec_shell"}
    submit_api = {k: v for k, v in apis.items() if k == "submit"}
    telemetry_apis = {
        k: v for k, v in apis.items() if k not in ("exec_shell", "submit")
    }

    def stringify(d: dict[str, str]) -> str:
        return "\n\n".join(f"{k}\n{v}" for k, v in d.items())

    return DOCS.format(
        task_desc=task_desc,
        telemetry_apis=stringify(telemetry_apis),
        shell_api=stringify(shell_api),
        submit_api=stringify(submit_api),
    )


RESP_INSTR = """\
Respond with:
Thought: <your reasoning about the previous observation>
Action:
```
<a single API call>
```
"""
