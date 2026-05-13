from __future__ import annotations

from pathlib import Path
import tomllib

from cooling_shim.models import AppConfig


DEFAULT_CONFIG_PATH = Path("~/.config/cooling/config.toml").expanduser()


def _get_bool(data: dict[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be a boolean")


def _get_int(data: dict[str, object], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be an integer")


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return AppConfig()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return AppConfig(
        min_age_days=_get_int(data, "min_age_days", 7),
        enable_pip=_get_bool(data, "enable_pip", True),
        enable_npm=_get_bool(data, "enable_npm", True),
        enable_pnpm=_get_bool(data, "enable_pnpm", True),
        enable_npx=_get_bool(data, "enable_npx", True),
        fail_closed_on_missing_metadata=_get_bool(
            data, "fail_closed_on_missing_metadata", True
        ),
        cache_ttl_seconds=_get_int(data, "cache_ttl_seconds", 3600),
    )
