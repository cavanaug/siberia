from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.native import inject_npm_before, pip_env_overrides, pnpm_env_overrides
from cooling_shim.npx import (
    npm_exec_package_specs,
    package_spec_argument_index,
    parse_package_spec,
    rewrite_npm_exec_args,
    rewrite_package_spec,
    select_cooled_version,
    validate_requested_version,
)


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
    load_packument: Callable[[str], dict[str, object]] | None = None,
) -> Invocation:
    invocation = build_passthrough_invocation(real_binary, context)

    if (
        context.tool_name == "npm"
        and context.subcommand == "exec"
        and config.enable_npx
        and any(arg == "--package" or arg.startswith("--package=") for arg in context.args)
    ):
        if load_packument is None:
            raise ValueError("load_packument is required for npm exec package resolution")

        selected_versions: dict[str, str] = {}
        for original_spec in npm_exec_package_specs(context.args):
            request = parse_package_spec(original_spec)
            packument = load_packument(request.package_name)
            selected_versions[original_spec] = (
                validate_requested_version(
                    request.package_name,
                    request.requested_version,
                    packument,
                    now_utc,
                    min_age_days=config.min_age_days,
                )
                if request.requested_version
                else select_cooled_version(packument, now_utc, min_age_days=config.min_age_days)
            )

        return Invocation(
            program=real_binary,
            argv=inject_npm_before(
                (str(real_binary), *rewrite_npm_exec_args(context.args, selected_versions)),
                now_utc,
                config,
            ),
            env_overrides={},
        )

    if context.tool_name == "npx" and config.enable_npx:
        if load_packument is None:
            raise ValueError("load_packument is required for npx")

        spec_index = package_spec_argument_index(context.args)
        original_spec = context.args[spec_index]
        request = parse_package_spec(original_spec)
        packument = load_packument(request.package_name)
        selected_version = (
            validate_requested_version(
                request.package_name,
                request.requested_version,
                packument,
                now_utc,
                min_age_days=config.min_age_days,
            )
            if request.requested_version
            else select_cooled_version(packument, now_utc, min_age_days=config.min_age_days)
        )
        return Invocation(
            program=real_binary,
            argv=(
                str(real_binary),
                *context.args[:spec_index],
                rewrite_package_spec(original_spec, selected_version),
                *context.args[spec_index + 1 :],
            ),
            env_overrides={},
        )

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
