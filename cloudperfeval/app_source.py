"""Read-only access to application source under apps/<suite>/source."""

from __future__ import annotations

from pathlib import Path

from cloudperfeval.config import config

MAX_LIST_ENTRIES = 1000
MAX_READ_LINES = 500


class AppSourceReader:
    def _root(self) -> tuple[Path | None, str | None]:
        root = config.app_source_dir()
        if root is None:
            return None, "Error: No active suite; source tree unavailable."
        if not root.is_dir():
            return None, f"Error: Application source directory not found: {root}"
        return root, None

    def _resolve(self, rel_path: str) -> tuple[Path | None, str | None]:
        root, err = self._root()
        if err:
            return None, err

        rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
        if rel in (".", ""):
            return root, None

        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None, f"Error: Path {rel_path!r} is outside the application source tree."
        return candidate, None

    def list_dir(self, path: str = "") -> str:
        target, err = self._resolve(path)
        if err:
            return err
        assert target is not None

        if not target.is_dir():
            return f"Error: {path!r} is not a directory."

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        if len(entries) > MAX_LIST_ENTRIES:
            entries = entries[:MAX_LIST_ENTRIES]
            truncated = True
        else:
            truncated = False

        rel_root = config.app_source_dir()
        assert rel_root is not None
        lines = [f"SOURCE_DIR\t{rel_root}"]
        if path:
            lines.append(f"PATH\t{path}")
        lines.append("TYPE\tNAME")
        for entry in entries:
            kind = "dir" if entry.is_dir() else "file"
            lines.append(f"{kind}\t{entry.name}")
        if truncated:
            lines.append(f"(truncated to {MAX_LIST_ENTRIES} entries)")
        return "\n".join(lines)

    def read_file(
        self,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        target, err = self._resolve(path)
        if err:
            return err
        assert target is not None

        if not target.is_file():
            return f"Error: {path!r} is not a file."

        if start_line < 1:
            return "Error: start_line must be >= 1."

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: {path!r} is not a UTF-8 text file."

        lines = text.splitlines()
        total = len(lines)

        if end_line is None:
            end_line = start_line + MAX_READ_LINES - 1
        if end_line < start_line:
            return "Error: end_line must be >= start_line."

        end_line = min(end_line, start_line + MAX_READ_LINES - 1)
        slice_start = start_line
        slice_end = min(end_line, total)
        if slice_start > total:
            return f"Error: start_line {start_line} is past end of file ({total} lines)."

        selected = lines[slice_start - 1:slice_end]
        header = f"FILE\t{path}\tlines {slice_start}-{slice_end} of {total}"
        body = "\n".join(f"{i:6d}|{line}" for i, line in enumerate(selected, start=slice_start))
        parts = [header, body]
        if slice_end < total:
            parts.append(
                f"(more lines available; use read_source({path!r}, start_line={slice_end + 1}))"
            )
        return "\n".join(parts)
