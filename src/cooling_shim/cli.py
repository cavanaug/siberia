from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Callable
import sys

from cooling_shim.config import load_config
from cooling_shim.models import AppConfig
from cooling_shim.models import CommandContext


SUPPORTED_TOOLS = frozenset({"pip", "npm", "pnpm", "npx"})


def build_context(argv: Sequence[str]) -> CommandContext:
    if not argv:
        raise ValueError("argv must not be empty")

    tool_name = Path(argv[0]).name
    args = tuple(argv[1:])
    subcommand = args[0] if args else None
    return CommandContext(tool_name=tool_name, args=args, subcommand=subcommand)


def main(
    argv: Sequence[str] | None = None,
    config_loader: Callable[[], AppConfig] = load_config,
) -> int:
    active_argv = list(sys.argv if argv is None else argv)
    context = build_context(active_argv)
    config_loader()
    return 0 if context.tool_name in SUPPORTED_TOOLS else 2
