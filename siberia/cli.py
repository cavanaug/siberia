from __future__ import annotations

from pathlib import Path


_SOURCE_CLI = Path(__file__).resolve().parents[1] / "src" / "siberia" / "cli.py"

with _SOURCE_CLI.open("rb") as handle:
    exec(compile(handle.read(), str(_SOURCE_CLI), "exec"), globals(), globals())
