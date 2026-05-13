from __future__ import annotations

from pathlib import Path


def resolve_real_binary(tool_name: str, shim_dir: Path, path_value: str | None) -> Path:
    if not path_value:
        raise FileNotFoundError(f"PATH is empty; cannot resolve {tool_name}")

    resolved_shim_dir = shim_dir.resolve()
    for entry in path_value.split(":"):
        if not entry:
            continue

        candidate_dir = Path(entry)
        if candidate_dir.resolve() == resolved_shim_dir:
            continue

        candidate = candidate_dir / tool_name
        if candidate.exists() and candidate.is_file():
            return candidate

    raise FileNotFoundError(f"Could not resolve real binary for {tool_name}")
