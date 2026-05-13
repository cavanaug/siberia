from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600


@dataclass(frozen=True)
class CommandContext:
    tool_name: str
    args: tuple[str, ...]
    subcommand: str | None = None
