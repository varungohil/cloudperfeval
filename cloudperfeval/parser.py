"""Parse an agent's response into a single API call."""

import ast
import re

from cloudperfeval.status import ResponseParsingError


class ResponseParser:
    def validate(self, response: str):
        actions = re.findall(r"```\s*\n(.*?)\n```", response, re.DOTALL)
        if len(actions) != 1:
            raise ResponseParsingError(
                "Format validation failure. Provide exactly one ``` code block "
                'containing a single API call, e.g.\n```\nget_traces("frontend")\n```'
            )

    def parse(self, response: str) -> dict:
        self.validate(response)
        code_block = self.extract_codeblock(response)
        api_name = self.parse_api_name(code_block)
        args, kwargs = self.parse_args(code_block, is_shell_command=api_name == "exec_shell")
        return {"api_name": api_name, "args": args, "kwargs": kwargs}

    def extract_codeblock(self, response: str) -> str:
        outputlines = response.split("\n")
        indexlines = [i for i, line in enumerate(outputlines) if "```" in line]
        if len(indexlines) < 2:
            return ""
        return "\n".join(outputlines[indexlines[0] + 1: indexlines[1]])

    def parse_api_name(self, response: str) -> str:
        first_parenthesis = response.find("(")
        if first_parenthesis != -1:
            return response[:first_parenthesis].strip()
        return ""

    def parse_args(self, response: str, is_shell_command=False):
        first_parenthesis = response.find("(")
        last_parenthesis = response.rfind(")")
        if first_parenthesis == -1 or last_parenthesis == -1:
            raise ResponseParsingError("No API call found!")

        args_str = response[first_parenthesis + 1: last_parenthesis].strip()
        if not args_str:
            return [], {}

        if is_shell_command:
            if args_str.startswith("command="):
                args_str = args_str[len("command="):].strip()
            if args_str.startswith('"') and args_str.endswith('"'):
                arg = args_str.strip('"')
            elif args_str.startswith("'") and args_str.endswith("'"):
                arg = args_str.strip("'")
            else:
                raise ResponseParsingError("commands must be quoted strings")
            arg = arg.replace('\\"', '"').replace("\\'", "'")
            return [arg], {}

        try:
            parsed = ast.parse(f"func({args_str})")
            call = parsed.body[0].value
            args, kwargs = [], {}
            for arg in call.args:
                args.append(self.eval_ast_node(arg))
            for kwarg in call.keywords:
                kwargs[kwarg.arg] = self.eval_ast_node(kwarg.value)
            return args, kwargs
        except ResponseParsingError:
            raise
        except Exception as e:
            raise ResponseParsingError(f"Error parsing response: {str(e)}")

    def eval_ast_node(self, node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return [self.eval_ast_node(elt) for elt in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(self.eval_ast_node(elt) for elt in node.elts)
        elif isinstance(node, ast.Dict):
            return {
                self.eval_ast_node(k): self.eval_ast_node(v)
                for k, v in zip(node.keys, node.values)
            }
        elif isinstance(node, ast.Name):
            return {"True": True, "False": False, "None": None}.get(node.id, node.id)
        raise ResponseParsingError(f"Unsupported AST node type: {type(node)}")
