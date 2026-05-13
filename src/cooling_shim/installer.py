from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _ensure_replaceable(path: Path) -> None:
    if path.exists() and not path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite non-symlink target: {path}")


def _replace_symlink(path: Path, target: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()
    path.symlink_to(target)


def install_shims(repo_root: Path, target_dir: Path, tool_names: Iterable[str]) -> None:
    source = repo_root / "bin" / "cooling-shim"
    if not source.exists():
        raise FileNotFoundError(f"Missing shim source: {source}")

    tool_names = tuple(tool_names)
    planned_paths = (target_dir / "cooling-shim", *(target_dir / tool_name for tool_name in tool_names))
    for path in planned_paths:
        _ensure_replaceable(path)

    target_dir.mkdir(parents=True, exist_ok=True)

    master_link = target_dir / "cooling-shim"
    _replace_symlink(master_link, source)

    for tool_name in tool_names:
        _replace_symlink(target_dir / tool_name, master_link)
