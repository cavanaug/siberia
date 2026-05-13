from __future__ import annotations

from pathlib import Path
import tomllib

from cooling_shim.models import AppConfig


DEFAULT_CONFIG_PATH = Path("~/.config/cooling/config.toml").expanduser()


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return AppConfig()

    data = tomllib.loads(path.read_text())
    return AppConfig(
        min_age_days=int(data.get("min_age_days", 7)),
        enable_pip=bool(data.get("enable_pip", True)),
        enable_npm=bool(data.get("enable_npm", True)),
        enable_pnpm=bool(data.get("enable_pnpm", True)),
        enable_npx=bool(data.get("enable_npx", True)),
        fail_closed_on_missing_metadata=bool(
            data.get("fail_closed_on_missing_metadata", True)
        ),
        cache_ttl_seconds=int(data.get("cache_ttl_seconds", 3600)),
    )
