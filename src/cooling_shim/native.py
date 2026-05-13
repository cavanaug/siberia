from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cooling_shim.models import AppConfig


def pip_env_overrides(config: AppConfig) -> dict[str, str]:
    return {"PIP_UPLOADED_PRIOR_TO": f"P{config.min_age_days}D"}


def npm_before_flag(now_utc: datetime, config: AppConfig) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=config.min_age_days)
    return f"--before={cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}"


def inject_npm_before(argv: tuple[str, ...], now_utc: datetime, config: AppConfig) -> tuple[str, ...]:
    if len(argv) < 2:
        return argv

    return (argv[0], npm_before_flag(now_utc, config), *argv[1:])


def pnpm_env_overrides(config: AppConfig) -> dict[str, str]:
    minimum_release_age_minutes = config.min_age_days * 24 * 60
    return {
        "pnpm_config_minimum_release_age": str(minimum_release_age_minutes),
        "pnpm_config_minimum_release_age_strict": "true",
        "pnpm_config_minimum_release_age_ignore_missing_time": (
            "false" if config.fail_closed_on_missing_metadata else "true"
        ),
    }
