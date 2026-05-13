# Supply Chain Cooling Shim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python 3.12+ local-shell shim that enforces a 7-day cooling period for `pip`, `npm`, `pnpm`, and `npx`, using native controls where available and custom cooled-version selection for `npx`.

**Architecture:** One executable (`bin/cooling-shim`) dispatches by symlink name, classifies guarded commands, injects native settings for `pip`, `npm`, and `pnpm`, and performs custom npm registry lookups for `npx` and `npm exec --package`. The implementation uses only the Python 3.12 standard library and keeps each policy concern in a small focused module with `unittest` coverage.

**Tech Stack:** Python 3.12+, stdlib (`dataclasses`, `datetime`, `json`, `os`, `pathlib`, `shutil`, `sys`, `tempfile`, `tomllib`, `urllib`, `unittest`)

---

## File Map

- `bin/cooling-shim`: executable Python entrypoint used by all symlinked commands
- `src/cooling_shim/__init__.py`: package marker
- `src/cooling_shim/models.py`: shared dataclasses for config, command context, invocations, and package requests
- `src/cooling_shim/config.py`: config loading from `~/.config/cooling/config.toml`
- `src/cooling_shim/cli.py`: top-level `main()` function, dependency injection points, and user-facing error reporting
- `src/cooling_shim/real_bin.py`: lookup of the real package-manager binary without recursing into the shim directory
- `src/cooling_shim/dispatch.py`: guarded-command detection and tool-specific routing
- `src/cooling_shim/native.py`: native policy injection for `pip`, `npm`, and `pnpm`
- `src/cooling_shim/errors.py`: typed policy failures for fail-closed behavior
- `src/cooling_shim/cache.py`: JSON cache for npm package metadata with TTL checks
- `src/cooling_shim/npm_registry.py`: npm packument fetching through `urllib.request`
- `src/cooling_shim/npx.py`: `npx` and `npm exec --package` parsing, cooled-version selection, and argv rewriting
- `src/cooling_shim/installer.py`: safe symlink installer for local-shell rollout
- `scripts/install_shims.py`: convenience script to install symlinks into `~/.local/bin`
- `docs/superpowers/runbooks/cooling-shim-local-setup.md`: local installation and rollback instructions
- `tests/test_cli.py`: config loading and `argv[0]` parsing tests
- `tests/test_dispatch.py`: guarded-command classification and real-binary lookup tests
- `tests/test_native.py`: native policy injection tests
- `tests/test_npx.py`: npm metadata, caching, cooled-version selection, and argv rewrite tests
- `tests/test_main.py`: end-to-end `main()` behavior with injected fakes
- `tests/test_installer.py`: symlink installation safety tests

### Task 1: Bootstrap The Python Shim Package

**Files:**
- Create: `bin/cooling-shim`
- Create: `src/cooling_shim/__init__.py`
- Create: `src/cooling_shim/models.py`
- Create: `src/cooling_shim/config.py`
- Create: `src/cooling_shim/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cooling_shim.cli import build_context
from cooling_shim.config import load_config


class LoadConfigTests(unittest.TestCase):
    def test_load_config_returns_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertEqual(config.min_age_days, 7)
        self.assertTrue(config.enable_pip)
        self.assertTrue(config.enable_npm)
        self.assertTrue(config.enable_pnpm)
        self.assertTrue(config.enable_npx)
        self.assertTrue(config.fail_closed_on_missing_metadata)
        self.assertEqual(config.cache_ttl_seconds, 3600)


class BuildContextTests(unittest.TestCase):
    def test_build_context_uses_symlink_name(self) -> None:
        context = build_context([
            "/home/user/.local/bin/pip",
            "install",
            "requests",
        ])

        self.assertEqual(context.tool_name, "pip")
        self.assertEqual(context.subcommand, "install")
        self.assertEqual(context.args, ("install", "requests"))

    def test_build_context_rejects_empty_argv(self) -> None:
        with self.assertRaises(ValueError):
            build_context([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_cli -v`

Expected: `FAIL` with `ModuleNotFoundError: No module named 'cooling_shim'`

- [ ] **Step 3: Write minimal implementation**

```python
# bin/cooling-shim
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cooling_shim.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# src/cooling_shim/__init__.py
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
```

```python
# src/cooling_shim/models.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600


@dataclass(slots=True, frozen=True)
class CommandContext:
    tool_name: str
    args: tuple[str, ...]
    subcommand: str | None
```

```python
# src/cooling_shim/config.py
from __future__ import annotations

from pathlib import Path
import tomllib

from cooling_shim.models import AppConfig


def default_config_path() -> Path:
    return Path.home() / ".config" / "cooling" / "config.toml"


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or default_config_path()
    if not path.exists():
        return AppConfig()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
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
```

```python
# src/cooling_shim/cli.py
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from cooling_shim.config import load_config
from cooling_shim.models import CommandContext


SUPPORTED_TOOLS = frozenset({"pip", "npm", "pnpm", "npx"})


def build_context(argv: Sequence[str]) -> CommandContext:
    if not argv:
        raise ValueError("argv must not be empty")

    tool_name = Path(argv[0]).name
    args = tuple(argv[1:])
    subcommand = args[0] if args else None
    return CommandContext(tool_name=tool_name, args=args, subcommand=subcommand)


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    actual_argv = tuple(sys.argv if argv is None else argv)
    context = build_context(actual_argv)
    _ = load_config()
    return 0 if context.tool_name in SUPPORTED_TOOLS else 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_cli -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add bin/cooling-shim src/cooling_shim/__init__.py src/cooling_shim/models.py src/cooling_shim/config.py src/cooling_shim/cli.py tests/test_cli.py
git commit -m "feat: bootstrap python cooling shim"
```

### Task 2: Add Real-Binary Resolution And Command Classification

**Files:**
- Modify: `src/cooling_shim/models.py`
- Create: `src/cooling_shim/real_bin.py`
- Create: `src/cooling_shim/dispatch.py`
- Modify: `src/cooling_shim/cli.py`
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispatch.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cooling_shim.dispatch import build_passthrough_invocation, should_guard_command
from cooling_shim.models import CommandContext
from cooling_shim.real_bin import resolve_real_binary


class ResolveRealBinaryTests(unittest.TestCase):
    def test_resolve_real_binary_skips_shim_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shim_dir = root / "shim"
            real_dir = root / "real"
            shim_dir.mkdir()
            real_dir.mkdir()

            real_binary = real_dir / "npm"
            real_binary.write_text("#!/bin/sh\n", encoding="utf-8")
            real_binary.chmod(0o755)

            resolved = resolve_real_binary("npm", shim_dir, f"{shim_dir}:{real_dir}")

        self.assertEqual(resolved, real_binary)


class GuardedCommandTests(unittest.TestCase):
    def test_pip_install_is_guarded(self) -> None:
        context = CommandContext("pip", ("install", "requests"), "install")
        self.assertTrue(should_guard_command(context))

    def test_pip_list_is_passthrough(self) -> None:
        context = CommandContext("pip", ("list",), "list")
        self.assertFalse(should_guard_command(context))

    def test_npm_run_is_passthrough(self) -> None:
        context = CommandContext("npm", ("run", "test"), "run")
        self.assertFalse(should_guard_command(context))

    def test_npm_install_is_guarded(self) -> None:
        context = CommandContext("npm", ("install",), "install")
        self.assertTrue(should_guard_command(context))


class PassthroughInvocationTests(unittest.TestCase):
    def test_build_passthrough_invocation_keeps_arguments_unchanged(self) -> None:
        invocation = build_passthrough_invocation(
            real_binary=Path("/usr/bin/pip"),
            context=CommandContext("pip", ("list",), "list"),
        )

        self.assertEqual(invocation.program, Path("/usr/bin/pip"))
        self.assertEqual(invocation.argv, ("/usr/bin/pip", "list"))
        self.assertEqual(invocation.env_overrides, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_dispatch -v`

Expected: `FAIL` with import errors for `cooling_shim.dispatch` and `cooling_shim.real_bin`

- [ ] **Step 3: Write minimal implementation**

```python
# Replace src/cooling_shim/models.py with this version.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600


@dataclass(slots=True, frozen=True)
class CommandContext:
    tool_name: str
    args: tuple[str, ...]
    subcommand: str | None


@dataclass(slots=True, frozen=True)
class Invocation:
    program: Path
    argv: tuple[str, ...]
    env_overrides: dict[str, str]
```

```python
# src/cooling_shim/real_bin.py
from __future__ import annotations

from pathlib import Path


def resolve_real_binary(tool_name: str, shim_dir: Path, path_value: str | None) -> Path:
    if not path_value:
        raise FileNotFoundError(f"PATH is empty; cannot resolve {tool_name}")

    for entry in path_value.split(":"):
        if not entry:
            continue
        candidate_dir = Path(entry)
        if candidate_dir.resolve() == shim_dir.resolve():
            continue

        candidate = candidate_dir / tool_name
        if candidate.exists() and candidate.is_file():
            return candidate

    raise FileNotFoundError(f"Could not resolve real binary for {tool_name}")
```

```python
# src/cooling_shim/dispatch.py
from __future__ import annotations

from pathlib import Path

from cooling_shim.models import CommandContext, Invocation


GUARDED_SUBCOMMANDS: dict[str, set[str]] = {
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
    argv = (str(real_binary), *context.args)
    return Invocation(program=real_binary, argv=argv, env_overrides={})
```

```python
# Replace src/cooling_shim/cli.py with this version.
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping, Sequence

from cooling_shim.config import load_config
from cooling_shim.dispatch import build_passthrough_invocation, should_guard_command
from cooling_shim.models import CommandContext, Invocation
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
    env: Mapping[str, str] | None = None,
    runner: Callable[[Invocation], int] | None = None,
) -> int:
    import sys

    actual_argv = tuple(sys.argv if argv is None else argv)
    actual_env = dict(os.environ if env is None else env)
    context = build_context(actual_argv)
    _ = load_config()

    if context.tool_name not in SUPPORTED_TOOLS:
        return 2

    shim_path = Path(actual_argv[0]).resolve()
    shim_dir = shim_path.parent
    real_binary = resolve_real_binary(context.tool_name, shim_dir, actual_env.get("PATH"))

    invocation = build_passthrough_invocation(real_binary, context)
    if should_guard_command(context):
        invocation = build_passthrough_invocation(real_binary, context)

    if runner is None:
        return 0
    return runner(invocation)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_dispatch -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/cooling_shim/models.py src/cooling_shim/real_bin.py src/cooling_shim/dispatch.py src/cooling_shim/cli.py tests/test_dispatch.py
git commit -m "feat: add binary resolution and command classification"
```

### Task 3: Inject Native Cooling Controls For pip, npm, And pnpm

**Files:**
- Create: `src/cooling_shim/native.py`
- Modify: `src/cooling_shim/dispatch.py`
- Test: `tests/test_native.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_native.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import unittest

from cooling_shim.dispatch import build_invocation
from cooling_shim.models import AppConfig, CommandContext


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


class NativePolicyTests(unittest.TestCase):
    def test_pip_install_sets_uploaded_prior_to_env(self) -> None:
        invocation = build_invocation(
            context=CommandContext("pip", ("install", "requests"), "install"),
            config=AppConfig(),
            real_binary=Path("/usr/bin/pip"),
            now_utc=FIXED_NOW,
        )

        self.assertEqual(invocation.env_overrides["PIP_UPLOADED_PRIOR_TO"], "P7D")
        self.assertEqual(invocation.argv, ("/usr/bin/pip", "install", "requests"))

    def test_npm_install_injects_before_cutoff(self) -> None:
        invocation = build_invocation(
            context=CommandContext("npm", ("install", "left-pad"), "install"),
            config=AppConfig(),
            real_binary=Path("/usr/bin/npm"),
            now_utc=FIXED_NOW,
        )

        self.assertEqual(
            invocation.argv,
            (
                "/usr/bin/npm",
                "--before=2026-05-06T12:00:00Z",
                "install",
                "left-pad",
            ),
        )

    def test_pnpm_install_sets_release_age_env(self) -> None:
        invocation = build_invocation(
            context=CommandContext("pnpm", ("install",), "install"),
            config=AppConfig(),
            real_binary=Path("/usr/bin/pnpm"),
            now_utc=FIXED_NOW,
        )

        self.assertEqual(invocation.env_overrides["pnpm_config_minimum_release_age"], "10080")
        self.assertEqual(invocation.env_overrides["pnpm_config_minimum_release_age_strict"], "true")
        self.assertEqual(
            invocation.env_overrides["pnpm_config_minimum_release_age_ignore_missing_time"],
            "false",
        )

    def test_npm_run_is_left_unchanged(self) -> None:
        invocation = build_invocation(
            context=CommandContext("npm", ("run", "test"), "run"),
            config=AppConfig(),
            real_binary=Path("/usr/bin/npm"),
            now_utc=FIXED_NOW,
        )

        self.assertEqual(invocation.argv, ("/usr/bin/npm", "run", "test"))
        self.assertEqual(invocation.env_overrides, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_native -v`

Expected: `FAIL` with `ImportError` for `build_invocation`

- [ ] **Step 3: Write minimal implementation**

```python
# src/cooling_shim/native.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cooling_shim.models import AppConfig, Invocation


def iso_cutoff(now_utc: datetime, min_age_days: int) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=min_age_days)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def inject_pip_policy(invocation: Invocation, config: AppConfig) -> Invocation:
    env = dict(invocation.env_overrides)
    env["PIP_UPLOADED_PRIOR_TO"] = f"P{config.min_age_days}D"
    return Invocation(program=invocation.program, argv=invocation.argv, env_overrides=env)


def inject_npm_policy(invocation: Invocation, config: AppConfig, now_utc: datetime) -> Invocation:
    cutoff = iso_cutoff(now_utc, config.min_age_days)
    argv = (invocation.argv[0], f"--before={cutoff}", *invocation.argv[1:])
    return Invocation(program=invocation.program, argv=argv, env_overrides=dict(invocation.env_overrides))


def inject_pnpm_policy(invocation: Invocation, config: AppConfig) -> Invocation:
    env = dict(invocation.env_overrides)
    env["pnpm_config_minimum_release_age"] = str(config.min_age_days * 24 * 60)
    env["pnpm_config_minimum_release_age_strict"] = "true"
    env["pnpm_config_minimum_release_age_ignore_missing_time"] = "false"
    return Invocation(program=invocation.program, argv=invocation.argv, env_overrides=env)
```

```python
# Replace src/cooling_shim/dispatch.py with this version.
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.native import inject_npm_policy, inject_pip_policy, inject_pnpm_policy


GUARDED_SUBCOMMANDS: dict[str, set[str]] = {
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
    argv = (str(real_binary), *context.args)
    return Invocation(program=real_binary, argv=argv, env_overrides={})


def build_invocation(
    context: CommandContext,
    config: AppConfig,
    real_binary: Path,
    now_utc: datetime,
) -> Invocation:
    invocation = build_passthrough_invocation(real_binary, context)
    if not should_guard_command(context):
        return invocation

    if context.tool_name == "pip" and config.enable_pip:
        return inject_pip_policy(invocation, config)

    if context.tool_name == "npm" and config.enable_npm:
        return inject_npm_policy(invocation, config, now_utc)

    if context.tool_name == "pnpm" and config.enable_pnpm:
        return inject_pnpm_policy(invocation, config)

    return invocation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_native -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/cooling_shim/native.py src/cooling_shim/dispatch.py tests/test_native.py
git commit -m "feat: inject native cooling policy for pip npm and pnpm"
```

### Task 4: Add npx Cooling Logic, npm Packument Fetching, And Cache TTLs

**Files:**
- Modify: `src/cooling_shim/models.py`
- Create: `src/cooling_shim/errors.py`
- Create: `src/cooling_shim/cache.py`
- Create: `src/cooling_shim/npm_registry.py`
- Create: `src/cooling_shim/npx.py`
- Modify: `src/cooling_shim/dispatch.py`
- Test: `tests/test_npx.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_npx.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from cooling_shim.cache import JsonCache
from cooling_shim.errors import PolicyError
from cooling_shim.models import AppConfig, CommandContext
from cooling_shim.npx import parse_package_spec, rewrite_package_spec, select_cooled_version
from cooling_shim.dispatch import build_invocation


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


PACKUMENT = {
    "name": "create-vite",
    "time": {
        "created": "2024-01-01T00:00:00.000Z",
        "modified": "2026-05-13T11:00:00.000Z",
        "6.0.0": "2026-05-12T10:00:00.000Z",
        "5.4.1": "2026-05-06T11:59:00.000Z",
        "5.4.0": "2026-05-01T12:00:00.000Z",
    },
}


class SpecParsingTests(unittest.TestCase):
    def test_parse_unpinned_package(self) -> None:
        request = parse_package_spec("create-vite")
        self.assertEqual(request.package_name, "create-vite")
        self.assertIsNone(request.requested_version)

    def test_parse_scoped_unpinned_package(self) -> None:
        request = parse_package_spec("@scope/tool")
        self.assertEqual(request.package_name, "@scope/tool")
        self.assertIsNone(request.requested_version)

    def test_parse_scoped_pinned_package(self) -> None:
        request = parse_package_spec("@scope/tool@1.2.3")
        self.assertEqual(request.package_name, "@scope/tool")
        self.assertEqual(request.requested_version, "1.2.3")


class CooledVersionSelectionTests(unittest.TestCase):
    def test_selects_latest_version_older_than_minimum_age(self) -> None:
        version = select_cooled_version(PACKUMENT, FIXED_NOW, min_age_days=7)
        self.assertEqual(version, "5.4.0")

    def test_rejects_when_no_version_is_old_enough(self) -> None:
        too_new = {
            "name": "fresh-package",
            "time": {
                "created": "2026-05-11T00:00:00.000Z",
                "modified": "2026-05-13T11:00:00.000Z",
                "1.0.0": "2026-05-12T10:00:00.000Z",
            },
        }

        with self.assertRaises(PolicyError):
            select_cooled_version(too_new, FIXED_NOW, min_age_days=7)


class CacheTests(unittest.TestCase):
    def test_cache_expires_entries_after_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = JsonCache(Path(temp_dir) / "npm-packuments.json")
            cache.put("create-vite", PACKUMENT, fetched_at=FIXED_NOW)

            hit = cache.get(
                "create-vite",
                now_utc=FIXED_NOW + timedelta(minutes=30),
                ttl_seconds=3600,
            )
            expired = cache.get(
                "create-vite",
                now_utc=FIXED_NOW + timedelta(hours=2),
                ttl_seconds=3600,
            )

        self.assertIsNotNone(hit)
        self.assertIsNone(expired)


class NpxInvocationTests(unittest.TestCase):
    def test_rewrite_package_spec_pins_selected_version(self) -> None:
        self.assertEqual(rewrite_package_spec("create-vite", "5.4.0"), "create-vite@5.4.0")

    def test_build_invocation_rewrites_npx_to_cooled_version(self) -> None:
        invocation = build_invocation(
            context=CommandContext("npx", ("create-vite", "demo"), "create-vite"),
            config=AppConfig(),
            real_binary=Path("/usr/bin/npx"),
            now_utc=FIXED_NOW,
            load_packument=lambda package_name: PACKUMENT,
        )

        self.assertEqual(
            invocation.argv,
            (
                "/usr/bin/npx",
                "create-vite@5.4.0",
                "demo",
            ),
        )

    def test_build_invocation_rejects_pinned_npx_version_that_is_too_new(self) -> None:
        with self.assertRaises(PolicyError):
            build_invocation(
                context=CommandContext("npx", ("create-vite@6.0.0", "demo"), "create-vite@6.0.0"),
                config=AppConfig(),
                real_binary=Path("/usr/bin/npx"),
                now_utc=FIXED_NOW,
                load_packument=lambda package_name: PACKUMENT,
            )

    def test_build_invocation_rewrites_npm_exec_package_flag(self) -> None:
        invocation = build_invocation(
            context=CommandContext(
                "npm",
                ("exec", "--package", "create-vite", "--", "create-vite", "demo"),
                "exec",
            ),
            config=AppConfig(),
            real_binary=Path("/usr/bin/npm"),
            now_utc=FIXED_NOW,
            load_packument=lambda package_name: PACKUMENT,
        )

        self.assertEqual(
            invocation.argv,
            (
                "/usr/bin/npm",
                "exec",
                "--package",
                "create-vite@5.4.0",
                "--",
                "create-vite",
                "demo",
            ),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_npx -v`

Expected: `FAIL` with import errors for `cooling_shim.cache`, `cooling_shim.errors`, and `cooling_shim.npx`

- [ ] **Step 3: Write minimal implementation**

```python
# Replace src/cooling_shim/models.py with this version.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600


@dataclass(slots=True, frozen=True)
class CommandContext:
    tool_name: str
    args: tuple[str, ...]
    subcommand: str | None


@dataclass(slots=True, frozen=True)
class Invocation:
    program: Path
    argv: tuple[str, ...]
    env_overrides: dict[str, str]


@dataclass(slots=True, frozen=True)
class PackageRequest:
    package_name: str
    requested_version: str | None
```

```python
# src/cooling_shim/errors.py
from __future__ import annotations


class PolicyError(RuntimeError):
    pass
```

```python
# src/cooling_shim/cache.py
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


class JsonCache:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.cache_path.exists():
            return {}
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, dict[str, object]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, key: str, now_utc: datetime, ttl_seconds: int) -> dict[str, object] | None:
        payload = self._load()
        entry = payload.get(key)
        if entry is None:
            return None

        fetched_at = datetime.fromisoformat(str(entry["fetched_at"]))
        age_seconds = (now_utc.astimezone(timezone.utc) - fetched_at).total_seconds()
        if age_seconds > ttl_seconds:
            return None
        return dict(entry["value"])

    def put(self, key: str, value: dict[str, object], fetched_at: datetime) -> None:
        payload = self._load()
        payload[key] = {
            "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
            "value": value,
        }
        self._save(payload)
```

```python
# src/cooling_shim/npm_registry.py
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import urlopen

from cooling_shim.cache import JsonCache


def default_cache() -> JsonCache:
    return JsonCache(Path.home() / ".cache" / "cooling" / "npm-packuments.json")


def load_packument(
    package_name: str,
    now_utc: datetime,
    ttl_seconds: int,
    cache: JsonCache | None = None,
    fetcher: Callable[[str], bytes] | None = None,
) -> dict[str, object]:
    active_cache = cache or default_cache()
    cached = active_cache.get(package_name, now_utc=now_utc, ttl_seconds=ttl_seconds)
    if cached is not None:
        return cached

    active_fetcher = fetcher or _fetch_url
    url = f"https://registry.npmjs.org/{quote(package_name, safe='')}"
    payload = json.loads(active_fetcher(url).decode("utf-8"))
    active_cache.put(package_name, payload, fetched_at=now_utc)
    return payload


def _fetch_url(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()
```

```python
# src/cooling_shim/npx.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cooling_shim.errors import PolicyError
from cooling_shim.models import PackageRequest


def parse_package_spec(spec: str) -> PackageRequest:
    if spec.startswith("@"):
        name, separator, version = spec[1:].rpartition("@")
        if separator:
            return PackageRequest(package_name=f"@{name}", requested_version=version or None)
        return PackageRequest(package_name=spec, requested_version=None)

    name, separator, version = spec.partition("@")
    if separator:
        return PackageRequest(package_name=name, requested_version=version or None)
    return PackageRequest(package_name=spec, requested_version=None)


def rewrite_package_spec(spec: str, selected_version: str) -> str:
    request = parse_package_spec(spec)
    return f"{request.package_name}@{selected_version}"


def validate_requested_version(
    package_name: str,
    requested_version: str,
    packument: dict[str, object],
    now_utc: datetime,
    min_age_days: int,
) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=min_age_days)
    time_data = dict(packument.get("time", {}))
    published_at = time_data.get(requested_version)
    if published_at is None:
        raise PolicyError(f"Missing publish time for {package_name}@{requested_version}")

    published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
    if published > cutoff:
        raise PolicyError(f"Requested version is too new: {package_name}@{requested_version}")
    return requested_version


def rewrite_npm_exec_args(args: tuple[str, ...], selected_version: str) -> tuple[str, ...]:
    rewritten = list(args)
    for index, value in enumerate(rewritten[:-1]):
        if value == "--package":
            rewritten[index + 1] = rewrite_package_spec(rewritten[index + 1], selected_version)
            return tuple(rewritten)
    raise PolicyError("npm exec is missing a --package value")


def select_cooled_version(packument: dict[str, object], now_utc: datetime, min_age_days: int) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=min_age_days)
    time_data = dict(packument.get("time", {}))
    candidates: list[tuple[datetime, str]] = []

    for version, published_at in time_data.items():
        if version in {"created", "modified"}:
            continue
        published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if published <= cutoff:
            candidates.append((published, version))

    if not candidates:
        raise PolicyError(f"No cooled version is available for {packument.get('name', 'package')}")

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]
```

```python
# Replace src/cooling_shim/dispatch.py with this version.
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.native import inject_npm_policy, inject_pip_policy, inject_pnpm_policy
from cooling_shim.npx import (
    parse_package_spec,
    rewrite_npm_exec_args,
    rewrite_package_spec,
    select_cooled_version,
    validate_requested_version,
)


GUARDED_SUBCOMMANDS: dict[str, set[str]] = {
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
    argv = (str(real_binary), *context.args)
    return Invocation(program=real_binary, argv=argv, env_overrides={})


def build_invocation(
    context: CommandContext,
    config: AppConfig,
    real_binary: Path,
    now_utc: datetime,
    load_packument: Callable[[str], dict[str, object]] | None = None,
) -> Invocation:
    invocation = build_passthrough_invocation(real_binary, context)
    if context.tool_name == "npm" and context.subcommand == "exec" and config.enable_npx:
        if load_packument is None:
            raise ValueError("load_packument is required for npm exec package resolution")
        package_index = context.args.index("--package") + 1
        original_spec = context.args[package_index]
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
            argv=(str(real_binary), *rewrite_npm_exec_args(context.args, selected_version)),
            env_overrides={},
        )

    if context.tool_name == "npx" and config.enable_npx:
        if load_packument is None:
            raise ValueError("load_packument is required for npx")
        original_spec = context.args[0]
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
            else select_cooled_version(
                packument,
                now_utc,
                min_age_days=config.min_age_days,
            )
        )
        argv = (
            str(real_binary),
            rewrite_package_spec(original_spec, selected_version),
            *context.args[1:],
        )
        return Invocation(program=real_binary, argv=argv, env_overrides={})

    if not should_guard_command(context):
        return invocation

    if context.tool_name == "pip" and config.enable_pip:
        return inject_pip_policy(invocation, config)

    if context.tool_name == "npm" and config.enable_npm:
        return inject_npm_policy(invocation, config, now_utc)

    if context.tool_name == "pnpm" and config.enable_pnpm:
        return inject_pnpm_policy(invocation, config)

    return invocation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_npx -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/cooling_shim/models.py src/cooling_shim/errors.py src/cooling_shim/cache.py src/cooling_shim/npm_registry.py src/cooling_shim/npx.py src/cooling_shim/dispatch.py tests/test_npx.py
git commit -m "feat: add cooled version selection for npx"
```

### Task 5: Wire main() End To End And Report Policy Errors Clearly

**Files:**
- Modify: `src/cooling_shim/cli.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path
import unittest

from cooling_shim.cli import main
from cooling_shim.models import AppConfig, Invocation


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


class MainFlowTests(unittest.TestCase):
    def test_main_runs_pip_with_native_age_filter(self) -> None:
        captured: dict[str, Invocation] = {}

        def runner(invocation: Invocation) -> int:
            captured["invocation"] = invocation
            return 0

        exit_code = main(
            argv=["/shim/pip", "install", "requests"],
            env={"PATH": "/shim:/usr/bin"},
            config=AppConfig(),
            now_utc=lambda: FIXED_NOW,
            resolve_binary=lambda tool_name, shim_dir, path_value: Path("/usr/bin/pip"),
            load_packument=lambda package_name: {},
            runner=runner,
            stderr=io.StringIO(),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["invocation"].env_overrides["PIP_UPLOADED_PRIOR_TO"], "P7D")

    def test_main_prints_policy_error_and_returns_one(self) -> None:
        stderr = io.StringIO()

        exit_code = main(
            argv=["/shim/npx", "fresh-package"],
            env={"PATH": "/shim:/usr/bin"},
            config=AppConfig(),
            now_utc=lambda: FIXED_NOW,
            resolve_binary=lambda tool_name, shim_dir, path_value: Path("/usr/bin/npx"),
            load_packument=lambda package_name: {
                "name": "fresh-package",
                "time": {
                    "created": "2026-05-11T00:00:00.000Z",
                    "modified": "2026-05-13T11:00:00.000Z",
                    "1.0.0": "2026-05-12T10:00:00.000Z",
                },
            },
            runner=lambda invocation: 0,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("No cooled version is available for fresh-package", stderr.getvalue())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_main -v`

Expected: `FAIL` because `main()` does not accept injected dependencies yet

- [ ] **Step 3: Write minimal implementation**

```python
# Replace src/cooling_shim/cli.py with this version.
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Callable, Mapping, Sequence, TextIO

from cooling_shim.config import load_config
from cooling_shim.dispatch import build_invocation
from cooling_shim.errors import PolicyError
from cooling_shim.models import AppConfig, CommandContext, Invocation
from cooling_shim.npm_registry import load_packument as default_load_packument
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
    merged_env = dict(os.environ)
    merged_env.update(invocation.env_overrides)
    os.execvpe(str(invocation.program), invocation.argv, merged_env)
    return 0


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    config: AppConfig | None = None,
    now_utc: Callable[[], datetime] | None = None,
    resolve_binary: Callable[[str, Path, str | None], Path] = resolve_real_binary,
    load_packument: Callable[[str], dict[str, object]] | None = None,
    runner: Callable[[Invocation], int] = exec_runner,
    stderr: TextIO | None = None,
) -> int:
    actual_argv = tuple(sys.argv if argv is None else argv)
    actual_env = dict(os.environ if env is None else env)
    active_stderr = stderr or sys.stderr
    active_now = now_utc or (lambda: datetime.now(timezone.utc))
    active_config = config or load_config()

    try:
        context = build_context(actual_argv)
        if context.tool_name not in SUPPORTED_TOOLS:
            return 2

        shim_path = Path(actual_argv[0]).resolve()
        real_binary = resolve_binary(context.tool_name, shim_path.parent, actual_env.get("PATH"))

        if load_packument is None:
            packument_loader = lambda package_name: default_load_packument(
                package_name,
                now_utc=active_now(),
                ttl_seconds=active_config.cache_ttl_seconds,
            )
        else:
            packument_loader = load_packument

        invocation = build_invocation(
            context=context,
            config=active_config,
            real_binary=real_binary,
            now_utc=active_now(),
            load_packument=packument_loader,
        )
        return runner(invocation)
    except PolicyError as exc:
        active_stderr.write(f"cooling-shim: {exc}\n")
        return 1
    except FileNotFoundError as exc:
        active_stderr.write(f"cooling-shim: {exc}\n")
        return 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_main -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/cooling_shim/cli.py tests/test_main.py
git commit -m "feat: wire end-to-end command execution"
```

### Task 6: Install Local Symlinks And Document Local-Shell Usage

**Files:**
- Create: `src/cooling_shim/installer.py`
- Create: `scripts/install_shims.py`
- Create: `docs/superpowers/runbooks/cooling-shim-local-setup.md`
- Test: `tests/test_installer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_installer.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cooling_shim.installer import install_shims


class InstallerTests(unittest.TestCase):
    def test_install_shims_creates_master_and_tool_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            target_dir = root / ".local" / "bin"
            repo_root.mkdir()
            (repo_root / "bin").mkdir()
            (repo_root / "bin" / "cooling-shim").write_text("#!/usr/bin/env python3\n", encoding="utf-8")

            install_shims(repo_root=repo_root, target_dir=target_dir, tool_names=("pip", "npm", "pnpm", "npx"))

            self.assertTrue((target_dir / "cooling-shim").is_symlink())
            self.assertEqual((target_dir / "pip").resolve(), (target_dir / "cooling-shim").resolve())
            self.assertEqual((target_dir / "npm").resolve(), (target_dir / "cooling-shim").resolve())

    def test_install_shims_refuses_to_overwrite_non_symlink_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            target_dir = root / ".local" / "bin"
            repo_root.mkdir()
            (repo_root / "bin").mkdir()
            (repo_root / "bin" / "cooling-shim").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            target_dir.mkdir(parents=True)
            (target_dir / "pip").write_text("existing file\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install_shims(repo_root=repo_root, target_dir=target_dir, tool_names=("pip",))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m unittest tests.test_installer -v`

Expected: `FAIL` with `ImportError` for `cooling_shim.installer`

- [ ] **Step 3: Write minimal implementation**

```python
# src/cooling_shim/installer.py
from __future__ import annotations

from pathlib import Path


def _ensure_replacable(path: Path) -> None:
    if path.exists() and not path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite non-symlink target: {path}")


def install_shims(repo_root: Path, target_dir: Path, tool_names: tuple[str, ...]) -> None:
    source = repo_root / "bin" / "cooling-shim"
    target_dir.mkdir(parents=True, exist_ok=True)

    master_link = target_dir / "cooling-shim"
    _ensure_replacable(master_link)
    if master_link.exists() or master_link.is_symlink():
        master_link.unlink()
    master_link.symlink_to(source)

    for tool_name in tool_names:
        tool_link = target_dir / tool_name
        _ensure_replacable(tool_link)
        if tool_link.exists() or tool_link.is_symlink():
            tool_link.unlink()
        tool_link.symlink_to(master_link)
```

```python
# scripts/install_shims.py
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cooling_shim.installer import install_shims


def main() -> int:
    install_shims(
        repo_root=REPO_ROOT,
        target_dir=Path.home() / ".local" / "bin",
        tool_names=("pip", "npm", "pnpm", "npx"),
    )
    print("Installed cooling-shim symlinks into ~/.local/bin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```markdown
<!-- docs/superpowers/runbooks/cooling-shim-local-setup.md -->
# Cooling Shim Local Setup

## Install

Run:

```bash
python scripts/install_shims.py
```

Ensure `~/.local/bin` appears before system package-manager paths in `PATH`.

Example shell snippet:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Config

Create `~/.config/cooling/config.toml`:

```toml
min_age_days = 7
enable_pip = true
enable_npm = true
enable_pnpm = true
enable_npx = true
fail_closed_on_missing_metadata = true
cache_ttl_seconds = 3600
```

## Rollback

Remove the symlinks if you need to disable the shim quickly:

```bash
rm -f ~/.local/bin/cooling-shim ~/.local/bin/pip ~/.local/bin/npm ~/.local/bin/pnpm ~/.local/bin/npx
```
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m unittest tests.test_installer -v`

Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `PYTHONPATH=src python -m unittest discover -s tests -v`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/cooling_shim/installer.py scripts/install_shims.py docs/superpowers/runbooks/cooling-shim-local-setup.md tests/test_installer.py
git commit -m "feat: add local-shell shim installer"
```

## Self-Review Checklist

- `pip` native `PIP_UPLOADED_PRIOR_TO=P7D` is covered in Task 3 and exercised end to end in Task 5.
- `npm` native `--before=<computed cutoff>` is covered in Task 3.
- `pnpm` native release-age env injection is covered in Task 3.
- `npx` newest cooled-version selection is covered in Task 4.
- pinned `npx` version validation is covered in Task 4.
- `npm exec --package` cooled-version rewriting is covered in Task 4.
- Fail-closed policy errors are covered in Task 4 and surfaced in Task 5.
- Single master executable plus symlink rollout is covered in Task 6.
- Local-shell setup instructions are covered in Task 6.
