"""Status enums, errors, and session printing."""

from enum import Enum

try:
    from colorama import Fore, Style
except Exception:  # colorama is optional
    class _Noop:
        def __getattr__(self, _):
            return ""

    Fore = Style = _Noop()

from cloudperfeval.config import config


class SubmissionStatus(Enum):
    VALID_SUBMISSION = 1
    INVALID_SUBMISSION = 2


class InvalidActionError(Exception):
    def __init__(self, action_name):
        super().__init__(f"Invalid action: {action_name}")
        self.action_name = action_name


class ResponseParsingError(Exception):
    def __init__(self, message):
        super().__init__(f"Error parsing response: {message}")
        self.message = message


class SessionPrint:
    def __init__(self):
        self.enable_printing = config.get("print_session", True)

    def agent(self, action):
        if self.enable_printing:
            print(f"{Fore.GREEN}Agent:\n{Style.RESET_ALL}{action}")

    def service(self, response):
        if self.enable_printing:
            print(f"{Fore.BLUE}Service:\n{Style.RESET_ALL}{response}\n\n")

    def result(self, results):
        print(f"{Fore.MAGENTA}Results:\n{Style.RESET_ALL}{results}")
