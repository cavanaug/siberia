from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Mapping
import os
from pathlib import Path
from typing import Callable
import sys

from cooling_shim.config import load_config
from cooling_shim.dispatch import build_passthrough_invocation, should_guard_command
from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.real_bin import resolve_real_binary


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
    env: Mapping[str, str] | None = None,
    runner: Callable[[Invocation], int] | None = None,
) -> int:
    active_argv = tuple(sys.argv if argv is None else argv)
    active_env = dict(os.environ if env is None else env)
    context = build_context(active_argv)
    config_loader()

    if context.tool_name not in SUPPORTED_TOOLS:
        return 2

    shim_dir = Path(active_argv[0]).resolve().parent
    real_binary = resolve_real_binary(context.tool_name, shim_dir, active_env.get("PATH"))
    invocation = build_passthrough_invocation(real_binary, context)

    if should_guard_command(context):
        invocation = build_passthrough_invocation(real_binary, context)

    if runner is None:
        return 0

    return runner(invocation)
