from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.native import inject_npm_before, pip_env_overrides, pnpm_env_overrides


GUARDED_SUBCOMMANDS: dict[str, set[str | None]] = {
    "pip": {"install"},
    "npm": {"install", "ci", "update", "exec"},
    "pnpm": {"install", "add", "update"},
    "npx": {None},
}


def should_guard_command(context: CommandContext) -> bool:
    if context.tool_name == "npx":
        return True

    guarded = GUARDED_SUBCOMMANDS.get(context.tool_name, set())
    return context.subcommand in guarded


def build_passthrough_invocation(real_binary: Path, context: CommandContext) -> Invocation:
    return Invocation(
        program=real_binary,
        argv=(str(real_binary), *context.args),
        env_overrides={},
    )


def build_invocation(
    context: CommandContext,
    config: AppConfig,
    real_binary: Path,
    now_utc: datetime,
) -> Invocation:
    invocation = build_passthrough_invocation(real_binary, context)

    if not should_guard_command(context):
        return invocation

    if context.tool_name == "pip":
        if not config.enable_pip:
            return invocation

        return Invocation(
            program=real_binary,
            argv=invocation.argv,
            env_overrides=pip_env_overrides(config),
        )

    if context.tool_name == "npm":
        if not config.enable_npm:
            return invocation

        return Invocation(
            program=real_binary,
            argv=inject_npm_before(invocation.argv, now_utc, config),
            env_overrides={},
        )

    if context.tool_name == "pnpm":
        if not config.enable_pnpm:
            return invocation

        return Invocation(
            program=real_binary,
            argv=invocation.argv,
            env_overrides=pnpm_env_overrides(config),
        )

    return invocation
