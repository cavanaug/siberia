from __future__ import annotations

from pathlib import Path


_SHIM_DIR = Path(__file__).resolve().parent
_SOURCE_DIR = _SHIM_DIR.parent / "src" / "siberia"
_SOURCE_INIT = _SOURCE_DIR / "__init__.py"

__path__ = [str(_SHIM_DIR), str(_SOURCE_DIR)]

with _SOURCE_INIT.open("rb") as handle:
    exec(compile(handle.read(), str(_SOURCE_INIT), "exec"), globals(), globals())
