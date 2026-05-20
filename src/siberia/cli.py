#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import sys
import time
import tomllib
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from . import __version__


# ---------------------------------------------------------------------------
# Age parsing
# ---------------------------------------------------------------------------

_AGE_PATTERN = re.compile(r"^(\d+)\s*(d|day|days|w|week|weeks)?$", re.IGNORECASE)
_REAL_DATETIME = datetime
_PUBLISHED_AT_CACHE: dict[tuple[str, str, str], datetime | None] = {}
_KNOWN_OLD_VERSION_FLOORS: dict[tuple[str, str, int], tuple[str, datetime]] = {}
_CHECK_CACHE_LOADED = False
_CURRENT_CTIME_THRESHOLD_DAYS = 0
_CURRENT_CACHE_TTL_SECONDS = 3600
_CURRENT_AGE_THRESHOLD_DAYS = 7


def _default_check_cache_path() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if cache_home:
        return Path(cache_home).expanduser() / "siberia" / "check-cache.json"
    return Path("~/.cache/siberia/check-cache.json").expanduser()


def _read_cache_document() -> dict[str, dict[str, dict[str, str | None]]]:
    if not _CHECK_CACHE_PATH.exists():
        return {"entries": {}, "known_old_floors": {}}
    try:
        loaded = json.loads(_CHECK_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": {}, "known_old_floors": {}}
    if not isinstance(loaded, dict):
        return {"entries": {}, "known_old_floors": {}}
    if "entries" in loaded or "known_old_floors" in loaded:
        entries = loaded.get("entries") if isinstance(loaded.get("entries"), dict) else {}
        known_old_floors = loaded.get("known_old_floors") if isinstance(loaded.get("known_old_floors"), dict) else {}
        return {"entries": entries, "known_old_floors": known_old_floors}
    # Backward compatibility for cache files written before sections were added.
    return {"entries": loaded, "known_old_floors": {}}


def _write_cache_document(document: dict[str, dict[str, dict[str, str | None]]]) -> None:
    _CHECK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CHECK_CACHE_PATH.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_version(version: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(?:\.\d+)*", version):
        return None
    parts = tuple(int(part) for part in version.split("."))
    trimmed = list(parts)
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed.pop()
    return tuple(trimmed)


def _known_old_floor_hit(registry: str, package: str, version: str, threshold_days: int) -> datetime | None:
    requested = _normalize_version(version)
    if requested is None:
        return None
    floor = _KNOWN_OLD_VERSION_FLOORS.get((registry, package, threshold_days))
    if floor is None:
        return None
    floor_version, published_at = floor
    known = _normalize_version(floor_version)
    if known is None or requested > known:
        return None
    return published_at


def _record_known_old_floor(
    registry: str,
    package: str,
    version: str,
    published_at: datetime,
    now: datetime,
    threshold_days: int,
) -> None:
    if threshold_days <= 0:
        return
    normalized = _normalize_version(version)
    if normalized is None:
        return
    age_days = (now - published_at).total_seconds() / 86400
    if age_days < threshold_days:
        return
    floor_key = (registry, package, threshold_days)
    current = _KNOWN_OLD_VERSION_FLOORS.get(floor_key)
    if current is not None:
        current_version, _current_published_at = current
        known = _normalize_version(current_version)
        if known is not None and normalized <= known:
            return
    _KNOWN_OLD_VERSION_FLOORS[floor_key] = (version, published_at)
    _persist_known_old_floor(floor_key, version, published_at, now)


def _load_persistent_cache(now: datetime, ttl_seconds: int) -> None:
    global _CHECK_CACHE_LOADED, _CURRENT_CACHE_TTL_SECONDS
    _CURRENT_CACHE_TTL_SECONDS = ttl_seconds
    if _CHECK_CACHE_LOADED or ttl_seconds <= 0 or not _CHECK_CACHE_PATH.exists():
        _CHECK_CACHE_LOADED = True
        return
    document = _read_cache_document()
    for raw_key, entry in document["entries"].items():
        if not isinstance(raw_key, str) or not isinstance(entry, dict):
            continue
        parts = raw_key.split("|", 2)
        if len(parts) != 3:
            continue
        cached_at = entry.get("cached_at")
        if not isinstance(cached_at, str):
            continue
        try:
            cached_at_dt = _REAL_DATETIME.fromisoformat(cached_at)
        except ValueError:
            continue
        if (now - cached_at_dt).total_seconds() > ttl_seconds:
            continue
        published_at = entry.get("published_at")
        if isinstance(published_at, str):
            try:
                _PUBLISHED_AT_CACHE[tuple(parts)] = _REAL_DATETIME.fromisoformat(published_at)
            except ValueError:
                continue
        else:
            _PUBLISHED_AT_CACHE[tuple(parts)] = None
    for raw_key, entry in document["known_old_floors"].items():
        if not isinstance(raw_key, str) or not isinstance(entry, dict):
            continue
        parts = raw_key.split("|", 2)
        if len(parts) != 3:
            continue
        cached_at = entry.get("cached_at")
        published_at = entry.get("published_at")
        version = entry.get("version")
        if not isinstance(cached_at, str) or not isinstance(published_at, str) or not isinstance(version, str):
            continue
        try:
            cached_at_dt = _REAL_DATETIME.fromisoformat(cached_at)
            published_at_dt = _REAL_DATETIME.fromisoformat(published_at)
            threshold_days = int(parts[2])
        except (TypeError, ValueError):
            continue
        if (now - cached_at_dt).total_seconds() > ttl_seconds:
            continue
        _KNOWN_OLD_VERSION_FLOORS[(parts[0], parts[1], threshold_days)] = (version, published_at_dt)
    _CHECK_CACHE_LOADED = True


def _persist_cache_entry(cache_key: tuple[str, str, str], published_at: datetime | None, now: datetime) -> None:
    document = _read_cache_document()
    document["entries"]["|".join(cache_key)] = {
        "published_at": published_at.isoformat() if published_at is not None else None,
        "cached_at": now.isoformat(),
    }
    _write_cache_document(document)


def _persist_known_old_floor(
    floor_key: tuple[str, str, int],
    version: str,
    published_at: datetime,
    now: datetime,
) -> None:
    document = _read_cache_document()
    document["known_old_floors"][f"{floor_key[0]}|{floor_key[1]}|{floor_key[2]}"] = {
        "version": version,
        "published_at": published_at.isoformat(),
        "cached_at": now.isoformat(),
    }
    _write_cache_document(document)


def _find_ctime_artifact(package: str, version: str) -> Path | None:
    search_root = Path(".siberia-ctime")
    if not search_root.exists():
        return None
    normalized_package = package.replace("/", "-")
    token = f"{normalized_package}-{version}"
    for candidate in search_root.rglob("*"):
        if candidate.is_file() and token in candidate.name:
            return candidate
    return None


def _ctime_allows_skip(package: str, version: str, now: datetime) -> bool:
    artifact = _find_ctime_artifact(package, version)
    if artifact is None:
        return False
    age_days = (now.timestamp() - artifact.stat().st_ctime) / 86400
    return age_days >= _CURRENT_CTIME_THRESHOLD_DAYS


def parse_age(value: str) -> int:
    """Parse a human-friendly age string into days.

    Accepted formats:
        7        -> 7 days (bare integer defaults to days)
        7d       -> 7 days
        7days    -> 7 days
        2w       -> 14 days
        2weeks   -> 14 days
    """
    match = _AGE_PATTERN.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid age {value!r}: use an integer (days) or a suffix: 7d, 2w"
        )
    n = int(match.group(1))
    unit = (match.group(2) or "d").lower()
    if unit.startswith("w"):
        return n * 7
    return n


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    enable_uv: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600
    pnpm_block_exotic_subdeps: bool = True
    pnpm_strict_dep_builds: bool = False
    npm_ignore_scripts: bool = False


DEFAULT_CONFIG_PATH = Path("~/.config/siberia/config.toml").expanduser()
_CHECK_CACHE_PATH = _default_check_cache_path()

_BOOL_ENV_VARS: dict[str, str] = {
    "enable_pip": "SIBERIA_ENABLE_PIP",
    "enable_npm": "SIBERIA_ENABLE_NPM",
    "enable_pnpm": "SIBERIA_ENABLE_PNPM",
    "enable_npx": "SIBERIA_ENABLE_NPX",
    "enable_uv": "SIBERIA_ENABLE_UV",
    "fail_closed_on_missing_metadata": "SIBERIA_FAIL_CLOSED_ON_MISSING_METADATA",
    "pnpm_block_exotic_subdeps": "SIBERIA_PNPM_BLOCK_EXOTIC_SUBDEPS",
    "pnpm_strict_dep_builds": "SIBERIA_PNPM_STRICT_DEP_BUILDS",
    "npm_ignore_scripts": "SIBERIA_NPM_IGNORE_SCRIPTS",
}

_INT_ENV_VARS: dict[str, str] = {
    "min_age_days": "SIBERIA_MIN_AGE_DAYS",
    "cache_ttl_seconds": "SIBERIA_CACHE_TTL_SECONDS",
}


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


def _apply_env_overrides(kwargs: dict[str, object], env: Mapping[str, str]) -> None:
    for field, var in _BOOL_ENV_VARS.items():
        raw = env.get(var)
        if raw is None:
            continue
        if raw in ("1", "true", "yes"):
            kwargs[field] = True
        elif raw in ("0", "false", "no"):
            kwargs[field] = False
        else:
            raise ValueError(f"{var} must be '1'/'true'/'yes' or '0'/'false'/'no', got {raw!r}")
    for field, var in _INT_ENV_VARS.items():
        raw = env.get(var)
        if raw is None:
            continue
        try:
            kwargs[field] = int(raw)
        except ValueError as exc:
            raise ValueError(f"{var} must be an integer, got {raw!r}") from exc


def load_config(
    config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        kwargs: dict[str, object] = {}
        if env is not None:
            _apply_env_overrides(kwargs, env)
        return AppConfig(**kwargs)  # type: ignore[arg-type]
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    kwargs = {
        "min_age_days": _get_int(data, "min_age_days", 7),
        "enable_pip": _get_bool(data, "enable_pip", True),
        "enable_npm": _get_bool(data, "enable_npm", True),
        "enable_pnpm": _get_bool(data, "enable_pnpm", True),
        "enable_npx": _get_bool(data, "enable_npx", True),
        "enable_uv": _get_bool(data, "enable_uv", True),
        "fail_closed_on_missing_metadata": _get_bool(data, "fail_closed_on_missing_metadata", True),
        "cache_ttl_seconds": _get_int(data, "cache_ttl_seconds", 3600),
        "pnpm_block_exotic_subdeps": _get_bool(data, "pnpm_block_exotic_subdeps", True),
        "pnpm_strict_dep_builds": _get_bool(data, "pnpm_strict_dep_builds", False),
        "npm_ignore_scripts": _get_bool(data, "npm_ignore_scripts", False),
    }
    if env is not None:
        _apply_env_overrides(kwargs, env)
    return AppConfig(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Native env overrides
# ---------------------------------------------------------------------------


def pip_env_overrides(config: AppConfig) -> dict[str, str]:
    return {"PIP_UPLOADED_PRIOR_TO": f"P{config.min_age_days}D"}


def uv_env_overrides(config: AppConfig) -> dict[str, str]:
    return {"UV_EXCLUDE_NEWER": f"P{config.min_age_days}D"}


def npm_env_overrides(config: AppConfig) -> dict[str, str]:
    env = {"npm_config_min_release_age": str(config.min_age_days)}
    if config.npm_ignore_scripts:
        env["npm_config_ignore_scripts"] = "true"
    return env


def pnpm_env_overrides(config: AppConfig) -> dict[str, str]:
    minutes = config.min_age_days * 24 * 60
    env = {
        "pnpm_config_minimum_release_age": str(minutes),
        "pnpm_config_minimum_release_age_strict": "true",
        "pnpm_config_minimum_release_age_ignore_missing_time": (
            "false" if config.fail_closed_on_missing_metadata else "true"
        ),
    }
    if config.pnpm_block_exotic_subdeps:
        env["pnpm_config_block_exotic_subdeps"] = "true"
    if config.pnpm_strict_dep_builds:
        env["pnpm_config_strict_dep_builds"] = "true"
    return env


# ---------------------------------------------------------------------------
# siberia shellenv
# ---------------------------------------------------------------------------


def cmd_shellenv(config: AppConfig, out: TextIO) -> int:
    lines: list[str] = []
    if config.enable_pip:
        for key, value in pip_env_overrides(config).items():
            lines.append(f"export {key}={value}")
    if config.enable_uv:
        for key, value in uv_env_overrides(config).items():
            lines.append(f"export {key}={value}")
    if config.enable_npm or config.enable_npx:
        for key, value in npm_env_overrides(config).items():
            lines.append(f"export {key}={value}")
    if config.enable_pnpm:
        for key, value in pnpm_env_overrides(config).items():
            lines.append(f"export {key}={value}")
    print("\n".join(lines), file=out)
    return 0


# ---------------------------------------------------------------------------
# siberia config
# ---------------------------------------------------------------------------


def _write_ini_section(path: Path, section: str, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.RawConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, key, value)
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


def _write_toml_key(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(key) and "=" in line:
                lines.append(f'{key} = "{value}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{key} = "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_kv_file(path: Path, key: str, value: str) -> None:
    """Idempotently set key=value in a .npmrc-style key=value file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_kv_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            return line.split("=", 1)[1].strip()
    return None


def _verbose_config_line(
    lines_by_path: dict[str, list[str]],
    home: Path,
    path: Path,
    status: str,
    field: str,
    detail: str,
) -> None:
    display_path = str(path).replace(str(home), "~", 1) if str(path).startswith(str(home)) else str(path)
    lines_by_path.setdefault(display_path, []).append(f"[{status}] {field}{detail}")


def _print_verbose_config_report(lines_by_path: dict[str, list[str]], out: TextIO) -> None:
    for display_path, lines in lines_by_path.items():
        print(display_path, file=out)
        for line in lines:
            print(f"  {line}", file=out)


def cmd_config(config: AppConfig, home: Path, out: TextIO, verbosity: int = 0) -> int:
    verbose = verbosity > 0
    written: list[str] = []
    verbose_lines: dict[str, list[str]] = {}
    pip_path = home / ".config" / "pip" / "pip.conf"
    uv_path = home / ".config" / "uv" / "uv.toml"
    npm_path = home / ".npmrc"
    pnpm_path = home / ".config" / "pnpm" / "rc"

    if config.enable_pip:
        _write_ini_section(pip_path, "global", "uploaded-prior-to", f"P{config.min_age_days}D")
        written.append(str(pip_path))
        if verbose:
            _verbose_config_line(
                verbose_lines,
                home,
                pip_path,
                "write",
                "global.uploaded-prior-to",
                f" = P{config.min_age_days}D",
            )
    elif verbose:
        _verbose_config_line(verbose_lines, home, pip_path, "skip", "global.uploaded-prior-to", " (tool disabled)")

    if config.enable_uv:
        _write_toml_key(uv_path, "exclude-newer", f"P{config.min_age_days}D")
        written.append(str(uv_path))
        if verbose:
            _verbose_config_line(
                verbose_lines,
                home,
                uv_path,
                "write",
                "exclude-newer",
                f" = P{config.min_age_days}D",
            )
    elif verbose:
        _verbose_config_line(verbose_lines, home, uv_path, "skip", "exclude-newer", " (tool disabled)")

    if config.enable_npm or config.enable_npx:
        _write_kv_file(npm_path, "min-release-age", str(config.min_age_days))
        if verbose:
            _verbose_config_line(
                verbose_lines,
                home,
                npm_path,
                "write",
                "min-release-age",
                f" = {config.min_age_days}",
            )
        if config.npm_ignore_scripts:
            _write_kv_file(npm_path, "ignore-scripts", "true")
            if verbose:
                _verbose_config_line(verbose_lines, home, npm_path, "write", "ignore-scripts", " = true")
        elif _read_kv_value(npm_path, "ignore-scripts") is not None:
            print("warning: leaving explicit ignore-scripts setting unchanged in ~/.npmrc", file=out)
            if verbose:
                _verbose_config_line(
                    verbose_lines,
                    home,
                    npm_path,
                    "skip",
                    "ignore-scripts",
                    " (explicit user setting left unchanged)",
                )
        elif verbose:
            _verbose_config_line(verbose_lines, home, npm_path, "skip", "ignore-scripts", " (option disabled)")
        written.append(str(npm_path))
    elif verbose:
        _verbose_config_line(verbose_lines, home, npm_path, "skip", "min-release-age", " (tool disabled)")
        _verbose_config_line(verbose_lines, home, npm_path, "skip", "ignore-scripts", " (tool disabled)")

    if config.enable_pnpm:
        _write_kv_file(pnpm_path, "minimum-release-age", str(config.min_age_days * 24 * 60))
        _write_kv_file(pnpm_path, "minimum-release-age-strict", "true")
        _write_kv_file(
            pnpm_path,
            "minimum-release-age-ignore-missing-time",
            "false" if config.fail_closed_on_missing_metadata else "true",
        )
        if verbose:
            _verbose_config_line(
                verbose_lines,
                home,
                pnpm_path,
                "write",
                "minimum-release-age",
                f" = {config.min_age_days * 24 * 60}",
            )
            _verbose_config_line(
                verbose_lines,
                home,
                pnpm_path,
                "write",
                "minimum-release-age-strict",
                " = true",
            )
            _verbose_config_line(
                verbose_lines,
                home,
                pnpm_path,
                "write",
                "minimum-release-age-ignore-missing-time",
                " = false" if config.fail_closed_on_missing_metadata else " = true",
            )
        if config.pnpm_block_exotic_subdeps:
            _write_kv_file(pnpm_path, "block-exotic-subdeps", "true")
            if verbose:
                _verbose_config_line(verbose_lines, home, pnpm_path, "write", "block-exotic-subdeps", " = true")
        elif verbose:
            _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "block-exotic-subdeps", " (option disabled)")
        if config.pnpm_strict_dep_builds:
            _write_kv_file(pnpm_path, "strict-dep-builds", "true")
            if verbose:
                _verbose_config_line(verbose_lines, home, pnpm_path, "write", "strict-dep-builds", " = true")
        elif verbose:
            _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "strict-dep-builds", " (option disabled)")
        written.append(str(pnpm_path))
    elif verbose:
        _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "minimum-release-age", " (tool disabled)")
        _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "minimum-release-age-strict", " (tool disabled)")
        _verbose_config_line(
            verbose_lines,
            home,
            pnpm_path,
            "skip",
            "minimum-release-age-ignore-missing-time",
            " (tool disabled)",
        )
        _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "block-exotic-subdeps", " (tool disabled)")
        _verbose_config_line(verbose_lines, home, pnpm_path, "skip", "strict-dep-builds", " (tool disabled)")

    if verbose:
        _print_verbose_config_report(verbose_lines, out)

    for path in written:
        print(f"wrote {path}", file=out)
    return 0


# ---------------------------------------------------------------------------
# siberia check
# ---------------------------------------------------------------------------


class Violation:
    __slots__ = ("file", "package", "version", "published_at", "age_days", "threshold_days")

    def __init__(
        self,
        file: Path,
        package: str,
        version: str,
        published_at: datetime,
        age_days: float,
        threshold_days: int,
    ) -> None:
        self.file = file
        self.package = package
        self.version = version
        self.published_at = published_at
        self.age_days = age_days
        self.threshold_days = threshold_days

    def __str__(self) -> str:
        return (
            f"{self.file}: {self.package}@{self.version} published "
            f"{self.published_at.strftime('%Y-%m-%d')} "
            f"({self.age_days:.1f} days ago, threshold {self.threshold_days}d)"
        )


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode())


def _npm_published_at(package: str, version: str) -> datetime | None:
    _load_persistent_cache(_REAL_DATETIME.now(timezone.utc), _CURRENT_CACHE_TTL_SECONDS)
    cache_key = ("npm", package, version)
    if cache_key in _PUBLISHED_AT_CACHE:
        return _PUBLISHED_AT_CACHE[cache_key]
    known_old = _known_old_floor_hit("npm", package, version, _CURRENT_AGE_THRESHOLD_DAYS)
    if known_old is not None:
        _PUBLISHED_AT_CACHE[cache_key] = known_old
        return known_old
    try:
        data = _http_get_json(f"https://registry.npmjs.org/{package}")
        timestamp = data.get("time", {}).get(version)
        if timestamp:
            published_at = _REAL_DATETIME.fromisoformat(timestamp.replace("Z", "+00:00"))
            _PUBLISHED_AT_CACHE[cache_key] = published_at
            _persist_cache_entry(cache_key, published_at, _REAL_DATETIME.now(timezone.utc))
            _record_known_old_floor("npm", package, version, published_at, datetime.now(timezone.utc), _CURRENT_AGE_THRESHOLD_DAYS)
            return published_at
    except Exception:
        pass
    _PUBLISHED_AT_CACHE[cache_key] = None
    _persist_cache_entry(cache_key, None, _REAL_DATETIME.now(timezone.utc))
    return None


def _pypi_published_at(package: str, version: str) -> datetime | None:
    _load_persistent_cache(_REAL_DATETIME.now(timezone.utc), _CURRENT_CACHE_TTL_SECONDS)
    cache_key = ("pypi", package, version)
    if cache_key in _PUBLISHED_AT_CACHE:
        return _PUBLISHED_AT_CACHE[cache_key]
    known_old = _known_old_floor_hit("pypi", package, version, _CURRENT_AGE_THRESHOLD_DAYS)
    if known_old is not None:
        _PUBLISHED_AT_CACHE[cache_key] = known_old
        return known_old
    try:
        data = _http_get_json(f"https://pypi.org/pypi/{package}/{version}/json")
        for url in data.get("urls", []):
            timestamp = url.get("upload_time_iso_8601") or url.get("upload_time")
            if timestamp:
                published_at = _REAL_DATETIME.fromisoformat(timestamp.replace("Z", "+00:00"))
                _PUBLISHED_AT_CACHE[cache_key] = published_at
                _persist_cache_entry(cache_key, published_at, _REAL_DATETIME.now(timezone.utc))
                _record_known_old_floor("pypi", package, version, published_at, datetime.now(timezone.utc), _CURRENT_AGE_THRESHOLD_DAYS)
                return published_at
    except Exception:
        pass
    _PUBLISHED_AT_CACHE[cache_key] = None
    _persist_cache_entry(cache_key, None, _REAL_DATETIME.now(timezone.utc))
    return None


def _crates_published_at(package: str, version: str) -> datetime | None:
    _load_persistent_cache(_REAL_DATETIME.now(timezone.utc), _CURRENT_CACHE_TTL_SECONDS)
    cache_key = ("crates", package, version)
    if cache_key in _PUBLISHED_AT_CACHE:
        return _PUBLISHED_AT_CACHE[cache_key]
    known_old = _known_old_floor_hit("crates", package, version, _CURRENT_AGE_THRESHOLD_DAYS)
    if known_old is not None:
        _PUBLISHED_AT_CACHE[cache_key] = known_old
        return known_old
    try:
        data = _http_get_json(f"https://crates.io/api/v1/crates/{package}/{version}")
        timestamp = data.get("version", {}).get("created_at")
        if timestamp:
            published_at = _REAL_DATETIME.fromisoformat(timestamp.replace("Z", "+00:00"))
            _PUBLISHED_AT_CACHE[cache_key] = published_at
            _persist_cache_entry(cache_key, published_at, _REAL_DATETIME.now(timezone.utc))
            _record_known_old_floor("crates", package, version, published_at, datetime.now(timezone.utc), _CURRENT_AGE_THRESHOLD_DAYS)
            return published_at
    except Exception:
        pass
    _PUBLISHED_AT_CACHE[cache_key] = None
    _persist_cache_entry(cache_key, None, _REAL_DATETIME.now(timezone.utc))
    return None


def _prefetch_crates_versions(packages: list[tuple[str, str]], now: datetime) -> None:
    requested: dict[str, set[str]] = {}
    for package, version in packages:
        if not package or not version:
            continue
        cache_key = ("crates", package, version)
        if cache_key in _PUBLISHED_AT_CACHE:
            continue
        if _known_old_floor_hit("crates", package, version, _CURRENT_AGE_THRESHOLD_DAYS) is not None:
            continue
        requested.setdefault(package, set()).add(version)
    for package, versions in requested.items():
        try:
            data = _http_get_json(f"https://crates.io/api/v1/crates/{package}")
        except Exception:
            continue
        matched_versions: set[str] = set()
        for entry in data.get("versions", []):
            if not isinstance(entry, dict):
                continue
            version = entry.get("num")
            timestamp = entry.get("created_at")
            if not isinstance(version, str) or version not in versions or not isinstance(timestamp, str):
                continue
            published_at = _REAL_DATETIME.fromisoformat(timestamp.replace("Z", "+00:00"))
            cache_key = ("crates", package, version)
            _PUBLISHED_AT_CACHE[cache_key] = published_at
            _persist_cache_entry(cache_key, published_at, _REAL_DATETIME.now(timezone.utc))
            _record_known_old_floor("crates", package, version, published_at, now, _CURRENT_AGE_THRESHOLD_DAYS)
            matched_versions.add(version)
        for version in versions - matched_versions:
            cache_key = ("crates", package, version)
            if cache_key not in _PUBLISHED_AT_CACHE:
                _PUBLISHED_AT_CACHE[cache_key] = None
                _persist_cache_entry(cache_key, None, _REAL_DATETIME.now(timezone.utc))


def _collect_violations(
    path: Path,
    packages: list[tuple[str, str]],
    threshold_days: int,
    now: datetime,
    published_lookup,
) -> list[Violation]:
    violations: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for name, version in packages:
        if not name or not version or (name, version) in seen:
            continue
        seen.add((name, version))
        if _CURRENT_CTIME_THRESHOLD_DAYS and _ctime_allows_skip(name, version, now):
            continue
        published_at = published_lookup(name, version)
        if published_at is None:
            continue
        age = (now - published_at).total_seconds() / 86400
        if age < threshold_days:
            violations.append(Violation(path, name, version, published_at, age, threshold_days))
    return violations


def _npm_packages_from_lock_data(data: dict) -> list[tuple[str, str]]:
    packages: list[tuple[str, str]] = []
    for node_path, info in data.get("packages", {}).items():
        if not node_path or not isinstance(info, dict):
            continue
        name = info.get("name") or node_path.split("node_modules/")[-1]
        version = info.get("version", "")
        if isinstance(name, str) and isinstance(version, str) and version:
            packages.append((name, version))
    return packages


def _check_package_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _collect_violations(path, _npm_packages_from_lock_data(data), threshold_days, now, _npm_published_at)


def _check_npm_shrinkwrap(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    return _check_package_lock(path, threshold_days, now)


def _check_pnpm_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    for match in re.finditer(r"^\s+/?([^@\s/][^@\s]*?)@([^\s:]+):", text, re.MULTILINE):
        name, version = match.group(1), match.group(2)
        packages.append((name, version))
    return _collect_violations(path, packages, threshold_days, now, _npm_published_at)


def _check_bun_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    for value in data.get("packages", {}).values():
        if not isinstance(value, list) or not value:
            continue
        resolved = value[0]
        if not isinstance(resolved, str) or "@" not in resolved:
            continue
        if resolved.startswith(("workspace:", "link:", "file:")):
            continue
        name, version = resolved.rsplit("@", 1)
        if name and version:
            packages.append((name, version))
    return _collect_violations(path, packages, threshold_days, now, _npm_published_at)


def _check_deno_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    for key in data.get("npm", {}):
        if not isinstance(key, str) or "@" not in key:
            continue
        name, version = key.rsplit("@", 1)
        if name and version:
            packages.append((name, version))
    return _collect_violations(path, packages, threshold_days, now, _npm_published_at)


def _check_uv_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    for package in data.get("package", []):
        if not isinstance(package, dict):
            continue
        name = package.get("name")
        version = package.get("version")
        source = package.get("source")
        if not isinstance(name, str) or not isinstance(version, str):
            continue
        if isinstance(source, dict) and "registry" not in source:
            continue
        packages.append((name, version))
    return _collect_violations(path, packages, threshold_days, now, _pypi_published_at)


def _check_poetry_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[[package]]":
            if "name" in current and "version" in current:
                packages.append((current["name"], current["version"]))
            current = {}
            continue
        if stripped.startswith("name = "):
            current["name"] = stripped.split("=", 1)[1].strip().strip('"')
        elif stripped.startswith("version = "):
            current["version"] = stripped.split("=", 1)[1].strip().strip('"')
    if "name" in current and "version" in current:
        packages.append((current["name"], current["version"]))
    return _collect_violations(path, packages, threshold_days, now, _pypi_published_at)


def _check_pipfile_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    packages: list[tuple[str, str]] = []
    for section in ("default", "develop"):
        entries = data.get(section, {})
        if not isinstance(entries, dict):
            continue
        for name, info in entries.items():
            if not isinstance(name, str) or not isinstance(info, dict):
                continue
            version = info.get("version")
            if not isinstance(version, str):
                continue
            packages.append((name, version.lstrip("=")))
    return _collect_violations(path, packages, threshold_days, now, _pypi_published_at)


def _scan_lockfile_targets(root: Path) -> list[Path]:
    candidates: list[Path] = []
    supported_names = set(_LOCKFILE_CHECKERS)
    for current_root, _dirs, files in os.walk(root):
        base = Path(current_root)
        for name in files:
            if not (name.endswith(".lock") or name == "requirements.txt" or name.endswith(".lock.json") or name.endswith(".lock.yaml")):
                continue
            if name in supported_names:
                candidates.append(base / name)
    return sorted(candidates)


def _status_line(stream: TextIO, path: Path, ok: bool) -> str:
    rendered_path = str(path)
    if hasattr(stream, "isatty") and stream.isatty():
        if ok:
            return f"\x1b[32m✓ {rendered_path}\x1b[0m"
        return f"\x1b[31m✗ {rendered_path}\x1b[0m"
    if ok:
        return f"OK {rendered_path}"
    return f"X {rendered_path}"


def _verbose_check(err: TextIO, verbosity: int, level: int, message: str) -> None:
    if verbosity >= level:
        print(message, file=err)


def _check_requirements_txt(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    violations: list[Violation] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return violations
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if not match:
            continue
        name, version = match.group(1), match.group(2)
        published_at = _pypi_published_at(name, version)
        if published_at is None:
            continue
        age = (now - published_at).total_seconds() / 86400
        if age < threshold_days:
            violations.append(Violation(path, name, version, published_at, age, threshold_days))
    return violations


def _check_cargo_lock(path: Path, threshold_days: int, now: datetime) -> list[Violation]:
    violations: list[Violation] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return violations
    current: dict[str, str] = {}
    packages: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line == "[[package]]":
            current = {}
        elif line.startswith("name = "):
            current["name"] = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("version = "):
            current["version"] = line.split("=", 1)[1].strip().strip('"')
        elif line == "" and "name" in current and "version" in current:
            packages.append((current["name"], current["version"]))
            current = {}
    if "name" in current and "version" in current:
        packages.append((current["name"], current["version"]))
    _prefetch_crates_versions(packages, now)
    return _collect_violations(path, packages, threshold_days, now, _crates_published_at)


_LOCKFILE_CHECKERS = {
    "package-lock.json": _check_package_lock,
    "npm-shrinkwrap.json": _check_npm_shrinkwrap,
    "pnpm-lock.yaml": _check_pnpm_lock,
    "bun.lock": _check_bun_lock,
    "deno.lock": _check_deno_lock,
    "requirements.txt": _check_requirements_txt,
    "uv.lock": _check_uv_lock,
    "poetry.lock": _check_poetry_lock,
    "Pipfile.lock": _check_pipfile_lock,
    "Cargo.lock": _check_cargo_lock,
}


def cmd_check(
    config: AppConfig,
    files: list[str],
    scan: bool,
    out: TextIO,
    err: TextIO,
    verbosity: int = 0,
    use_ctime: bool = False,
) -> int:
    global _CURRENT_CTIME_THRESHOLD_DAYS, _CURRENT_AGE_THRESHOLD_DAYS
    now = datetime.now(timezone.utc)
    threshold = config.min_age_days
    _load_persistent_cache(now, config.cache_ttl_seconds)
    _CURRENT_CTIME_THRESHOLD_DAYS = threshold if use_ctime else 0
    _CURRENT_AGE_THRESHOLD_DAYS = threshold

    if scan:
        targets = _scan_lockfile_targets(Path("."))
        _verbose_check(err, verbosity, 1, f"scan: discovered {len(targets)} supported lockfiles")
    elif files:
        targets = [Path(path) for path in files]
    else:
        targets = [Path(name) for name in _LOCKFILE_CHECKERS if Path(name).exists()]

    if not targets:
        print("siberia check: no lockfiles found", file=err)
        return 0

    all_violations: list[Violation] = []
    for target in targets:
        checker = _LOCKFILE_CHECKERS.get(target.name)
        if checker is None:
            print(f"siberia check: unsupported file type: {target}", file=err)
            continue
        if not target.exists():
            print(f"siberia check: file not found: {target}", file=err)
            continue
        _verbose_check(err, verbosity, 1, f"check: starting {target}")
        started = time.perf_counter()
        violations = checker(target, threshold, now)
        elapsed = time.perf_counter() - started
        print(_status_line(out, target, ok=not violations), file=out)
        for violation in violations:
            print(f"VIOLATION: {violation}", file=out)
        _verbose_check(err, verbosity, 2, f"check: finished {target} in {elapsed:.2f}s")
        if verbosity >= 3:
            for violation in violations:
                registry = "pypi"
                if target.name in {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "bun.lock", "deno.lock"}:
                    registry = "npm"
                elif target.name == "Cargo.lock":
                    registry = "crates"
                _verbose_check(err, verbosity, 3, f"lookup: {registry} {violation.package}@{violation.version}")
        if violations:
            all_violations.extend(violations)

    if all_violations:
        print(
            f"\nsiberia check: {len(all_violations)} violation(s) found "
            f"(threshold: {threshold} days)",
            file=err,
        )
        return 1

    print(f"siberia check: all packages meet the {threshold}-day age requirement", file=out)
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    active_argv = argv if argv is not None else sys.argv[1:]
    active_env = env if env is not None else dict(os.environ)
    active_out = out if out is not None else sys.stdout
    active_err = err if err is not None else sys.stderr

    parser = argparse.ArgumentParser(
        prog="siberia",
        description="Supply-chain age policy enforcer",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shellenv_parser = subparsers.add_parser("shellenv", help="Print shell exports for eval")
    shellenv_parser.add_argument(
        "--age",
        type=parse_age,
        default=None,
        metavar="DURATION",
        help="Minimum package age, e.g. 7d or 2w (default: 7d)",
    )

    config_parser = subparsers.add_parser("config", help="Write native config files")
    config_parser.add_argument(
        "--age",
        type=parse_age,
        default=None,
        metavar="DURATION",
        help="Minimum package age, e.g. 7d or 2w (default: 7d)",
    )
    config_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity; repeat for more detail",
    )

    check_parser = subparsers.add_parser("check", help="Audit lockfiles for too-new packages")
    check_parser.add_argument("files", nargs="*", help="Lockfiles to check")
    check_parser.add_argument("--scan", action="store_true", help="Recursively scan for lockfiles")
    check_parser.add_argument(
        "--use-ctime",
        action="store_true",
        help="Aggressively trust local file ctime heuristics before cache or network lookups",
    )
    check_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity; repeat for more detail",
    )
    check_parser.add_argument(
        "--age",
        type=parse_age,
        default=None,
        metavar="DURATION",
        help="Minimum package age, e.g. 7d or 2w (default: 7d)",
    )

    if active_argv == ["--version"]:
        print(__version__, file=active_out)
        return 0

    args = parser.parse_args(active_argv)

    try:
        config = load_config(env=active_env)
    except ValueError as exc:
        print(f"siberia: {exc}", file=active_err)
        return 1

    if args.age is not None:
        config = replace(config, min_age_days=args.age)

    if args.command == "shellenv":
        return cmd_shellenv(config, active_out)

    if args.command == "config":
        home = Path(active_env.get("HOME", str(Path.home())))
        return cmd_config(config, home, active_out, verbosity=args.verbose)

    if args.command == "check":
        return cmd_check(
            config,
            args.files,
            args.scan,
            active_out,
            active_err,
            verbosity=args.verbose,
            use_ctime=args.use_ctime,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
