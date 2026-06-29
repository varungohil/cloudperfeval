"""Capture stdout/stderr during a problem run for session artifacts."""

from __future__ import annotations

import sys
from io import StringIO


class _Tee:
    """Write to multiple streams (console + in-memory buffer)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            if hasattr(stream, "flush"):
                stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            if hasattr(stream, "flush"):
                stream.flush()

    def isatty(self) -> bool:
        return any(getattr(s, "isatty", lambda: False)() for s in self.streams)


class RunLogCapture:
    """Duplicate process stdout/stderr to a buffer until ``stop()``."""

    def __init__(self):
        self._buffer = StringIO()
        self._stdout = None
        self._stderr = None

    def start(self) -> None:
        if self._stdout is not None:
            return
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = _Tee(self._stdout, self._buffer)
        sys.stderr = _Tee(self._stderr, self._buffer)

    def stop(self) -> str:
        if self._stdout is None:
            return self._buffer.getvalue()
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        self._stdout = None
        self._stderr = None
        return self._buffer.getvalue()

    def __enter__(self) -> "RunLogCapture":
        self.start()
        return self

    def __exit__(self, *_args) -> None:
        self.stop()
