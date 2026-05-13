from __future__ import annotations

from pathlib import Path

from cooling_shim.models import CommandContext, Invocation


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
