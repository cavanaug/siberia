from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Callable
import sys

from cooling_shim.config import load_config
from cooling_shim.dispatch import build_invocation
from cooling_shim.errors import PolicyError
from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim import npm_registry
from cooling_shim.real_bin import resolve_real_binary


SUPPORTED_TOOLS = frozenset({"pip", "npm", "pnpm", "npx"})


def build_context(argv: Sequence[str]) -> CommandContext:
    if not argv:
        raise ValueError("argv must not be empty")

    tool_name = Path(argv[0]).name
    args = tuple(argv[1:])
    subcommand = args[0] if args else None
    return CommandContext(tool_name=tool_name, args=args, subcommand=subcommand)


def exec_runner(invocation: Invocation) -> int:
    exec_env = dict(os.environ)
    exec_env.update(invocation.env_overrides)
    os.execvpe(str(invocation.program), invocation.argv, exec_env)
    return 0


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    config: AppConfig | None = None,
    clock: Callable[[], datetime] | None = None,
    binary_resolver: Callable[[str, Path, str | None], Path] | None = None,
    packument_loader: Callable[[str], dict[str, object]] | None = None,
    runner: Callable[[Invocation], int] | None = None,
    stderr: object | None = None,
) -> int:
    active_argv = tuple(sys.argv if argv is None else argv)
    active_env = dict(os.environ if env is None else env)
    active_clock = clock or (lambda: datetime.now(timezone.utc))
    active_binary_resolver = binary_resolver or resolve_real_binary
    active_runner = runner or exec_runner
    active_stderr = sys.stderr if stderr is None else stderr

    try:
        context = build_context(active_argv)

        if context.tool_name not in SUPPORTED_TOOLS:
            return 2

        active_config = config if config is not None else load_config()
        now_utc = active_clock()

        shim_dir = Path(active_argv[0]).resolve().parent
        real_binary = active_binary_resolver(context.tool_name, shim_dir, active_env.get("PATH"))

        active_packument_loader = packument_loader
        if active_packument_loader is None:
            def active_packument_loader(package_name: str) -> dict[str, object]:
                return npm_registry.load_packument(
                    package_name,
                    now_utc=now_utc,
                    ttl_seconds=active_config.cache_ttl_seconds,
                )

        invocation = build_invocation(
            context=context,
            config=active_config,
            real_binary=real_binary,
            now_utc=now_utc,
            load_packument=active_packument_loader,
        )
        return active_runner(invocation)
    except (PolicyError, FileNotFoundError) as error:
        print(f"cooling-shim: {error}", file=active_stderr)
        return 1
