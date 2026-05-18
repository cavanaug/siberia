# Siberia Config And Shellenv Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename Siberia's config and shell-export surface from `cooling`/`init` to `siberia`/`shellenv`, while treating `pipx` as part of the pip family and `uvx` as part of the uv family.

**Architecture:** Keep the change inside the existing single-file CLI by updating the config model, env-override names, and subcommand parser in `siberia`. Use `tests/test_siberia.py` to lock the clean-break rename in place, then update the README so the documented config path, env vars, and command names match the implementation.

**Tech Stack:** Python 3 standard library, `unittest`, TOML config parsing via `tomllib`

---

## File Map

- Modify: `siberia`
  Responsibility: default config path, `AppConfig`, env override maps, pip/uv family behavior, `shellenv` subcommand, argparse dispatch, top-level usage docstring
- Modify: `tests/test_siberia.py`
  Responsibility: config-loading coverage, env-override coverage, pip/uv family coverage, `shellenv` subcommand coverage, main-parser coverage
- Modify: `README.md`
  Responsibility: user-facing command examples, config path and env-var docs, explicit `pipx`/`uvx` family mapping, clean-break migration note

### Task 1: Rename The Config Namespace And Collapse Pipx Into The Pip Family

**Files:**
- Modify: `siberia`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

Replace the env-override block in `tests/test_siberia.py` and add the default-path plus config-writer coverage below.

```python
from siberia import (
    AppConfig,
    DEFAULT_CONFIG_PATH,
    load_config,
    cmd_init,
    cmd_config,
    main,
    parse_age,
)


class LoadConfigTests(unittest.TestCase):
    def test_default_config_path_uses_siberia_namespace(self) -> None:
        self.assertEqual(
            DEFAULT_CONFIG_PATH,
            Path("~/.config/siberia/config.toml").expanduser(),
        )

    def test_env_var_overrides_bool_field_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"SIBERIA_ENABLE_PIP": "0"},
            )
        self.assertFalse(config.enable_pip)
        self.assertTrue(config.enable_npm)

    def test_env_var_overrides_bool_field_over_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("enable_pip = true\n", encoding="utf-8")
            config = load_config(config_path, env={"SIBERIA_ENABLE_PIP": "0"})
        self.assertFalse(config.enable_pip)

    def test_env_var_overrides_int_field_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"SIBERIA_MIN_AGE_DAYS": "14"},
            )
        self.assertEqual(config.min_age_days, 14)

    def test_env_var_overrides_all_tool_families(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={
                    "SIBERIA_ENABLE_PIP": "0",
                    "SIBERIA_ENABLE_NPM": "0",
                    "SIBERIA_ENABLE_PNPM": "0",
                    "SIBERIA_ENABLE_NPX": "0",
                    "SIBERIA_ENABLE_UV": "0",
                },
            )
        self.assertFalse(config.enable_pip)
        self.assertFalse(config.enable_npm)
        self.assertFalse(config.enable_pnpm)
        self.assertFalse(config.enable_npx)
        self.assertFalse(config.enable_uv)

    def test_env_var_overrides_new_hardening_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={
                    "SIBERIA_PNPM_BLOCK_EXOTIC_SUBDEPS": "0",
                    "SIBERIA_PNPM_STRICT_DEP_BUILDS": "1",
                    "SIBERIA_NPM_IGNORE_SCRIPTS": "1",
                },
            )

        self.assertFalse(config.pnpm_block_exotic_subdeps)
        self.assertTrue(config.pnpm_strict_dep_builds)
        self.assertTrue(config.npm_ignore_scripts)

    def test_env_var_accepts_true_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("enable_pip = false\n", encoding="utf-8")
            for truthy in ("1", "true", "yes"):
                config = load_config(config_path, env={"SIBERIA_ENABLE_PIP": truthy})
                self.assertTrue(config.enable_pip, f"expected True for {truthy!r}")

    def test_env_var_rejects_invalid_bool_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                load_config(
                    Path(temp_dir) / "missing.toml",
                    env={"SIBERIA_ENABLE_PIP": "maybe"},
                )

    def test_env_var_rejects_invalid_int_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                load_config(
                    Path(temp_dir) / "missing.toml",
                    env={"SIBERIA_MIN_AGE_DAYS": "two"},
                )

    def test_legacy_cooling_env_vars_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"COOLING_ENABLE_PIP": "0"},
            )
        self.assertTrue(config.enable_pip)


class ConfigSubcommandTests(unittest.TestCase):
    def test_config_skips_disabled_pip_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_pip=False), home, io.StringIO())
            self.assertFalse((home / ".config" / "pip" / "pip.conf").exists())

    def test_config_skips_disabled_uv_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_uv=False), home, io.StringIO())
            self.assertFalse((home / ".config" / "uv" / "uv.toml").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.LoadConfigTests tests.test_siberia.ConfigSubcommandTests -v`
Expected: `FAIL` because `DEFAULT_CONFIG_PATH` still points at `~/.config/cooling/config.toml`, env overrides still use `COOLING_*`, and `enable_pip=False` still does not suppress pip-family config writes.

- [ ] **Step 3: Write minimal implementation**

Update `siberia` with the renamed config path, renamed env-var maps, reduced `AppConfig`, and pip-family gating that no longer references `enable_pipx`.

```python
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


def cmd_init(config: AppConfig, out: TextIO) -> int:
    lines: list[str] = []
    if config.enable_pip:
        for k, v in pip_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_uv:
        for k, v in uv_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_npm or config.enable_npx:
        for k, v in npm_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_pnpm:
        for k, v in pnpm_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    print("\n".join(lines), file=out)
    return 0


def cmd_config(config: AppConfig, home: Path, out: TextIO) -> int:
    written: list[str] = []
    if config.enable_pip:
        p = home / ".config" / "pip" / "pip.conf"
        _write_ini_section(p, "global", "uploaded-prior-to", f"P{config.min_age_days}D")
        written.append(str(p))
    if config.enable_uv:
        p = home / ".config" / "uv" / "uv.toml"
        _write_toml_key(p, "exclude-newer", f"P{config.min_age_days}D")
        written.append(str(p))
    if config.enable_npm or config.enable_npx:
        p = home / ".npmrc"
        _write_kv_file(p, "min-release-age", str(config.min_age_days))
        if config.npm_ignore_scripts:
            _write_kv_file(p, "ignore-scripts", "true")
        elif _read_kv_value(p, "ignore-scripts") is not None:
            print("warning: leaving explicit ignore-scripts setting unchanged in ~/.npmrc", file=out)
        written.append(str(p))
    if config.enable_pnpm:
        p = home / ".config" / "pnpm" / "rc"
        _write_kv_file(p, "minimum-release-age", str(config.min_age_days * 24 * 60))
        if config.pnpm_block_exotic_subdeps:
            _write_kv_file(p, "block-exotic-subdeps", "true")
        if config.pnpm_strict_dep_builds:
            _write_kv_file(p, "strict-dep-builds", "true")
        written.append(str(p))
    for path in written:
        print(f"wrote {path}", file=out)
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_siberia.LoadConfigTests tests.test_siberia.ConfigSubcommandTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add siberia tests/test_siberia.py
git commit -m "refactor: rename config namespace to siberia"
```

### Task 2: Replace `init` With `shellenv`

**Files:**
- Modify: `siberia`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

Rename the imported function in `tests/test_siberia.py`, replace `InitSubcommandTests` with `ShellenvSubcommandTests`, and update the main-parser tests to exercise `shellenv` instead of `init`.

```python
from siberia import (
    AppConfig,
    DEFAULT_CONFIG_PATH,
    load_config,
    cmd_shellenv,
    cmd_config,
    main,
    parse_age,
)


class ShellenvSubcommandTests(unittest.TestCase):
    def test_shellenv_emits_pip_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export PIP_UPLOADED_PRIOR_TO=P7D", out.getvalue())

    def test_shellenv_emits_uv_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export UV_EXCLUDE_NEWER=P7D", out.getvalue())

    def test_shellenv_emits_npm_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export npm_config_min_release_age=7", out.getvalue())

    def test_shellenv_emits_npm_ignore_scripts_when_npm_enabled(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(npm_ignore_scripts=True), out)
        self.assertIn("export npm_config_ignore_scripts=true", out.getvalue())

    def test_shellenv_emits_npm_ignore_scripts_for_npx_only_mode(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(enable_npm=False, enable_npx=True, npm_ignore_scripts=True), out)
        self.assertIn("export npm_config_ignore_scripts=true", out.getvalue())

    def test_shellenv_emits_pnpm_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export pnpm_config_minimum_release_age=10080", out.getvalue())

    def test_shellenv_emits_pnpm_block_exotic_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(), out)
        self.assertIn("export pnpm_config_block_exotic_subdeps=true", out.getvalue())

    def test_shellenv_omits_pnpm_strict_dep_builds_by_default(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(), out)
        self.assertNotIn("pnpm_config_strict_dep_builds", out.getvalue())

    def test_shellenv_emits_pnpm_strict_dep_builds_when_enabled(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(pnpm_strict_dep_builds=True), out)
        self.assertIn("export pnpm_config_strict_dep_builds=true", out.getvalue())

    def test_shellenv_skips_disabled_npm(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7, enable_npm=False, enable_npx=False), out)
        self.assertNotIn("npm_config_min_release_age", out.getvalue())

    def test_shellenv_skips_disabled_pip_family(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(enable_pip=False), out)
        self.assertNotIn("PIP_UPLOADED_PRIOR_TO", out.getvalue())

    def test_shellenv_skips_disabled_uv_family(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(enable_uv=False), out)
        self.assertNotIn("UV_EXCLUDE_NEWER", out.getvalue())

    def test_shellenv_respects_custom_days(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=14), out)
        self.assertIn("export npm_config_min_release_age=14", out.getvalue())


class MainSubcommandTests(unittest.TestCase):
    def test_main_shellenv_returns_zero(self) -> None:
        out = io.StringIO()
        with patch("siberia.load_config", return_value=AppConfig()):
            rc = main(["shellenv"], out=out)
        self.assertEqual(rc, 0)

    def test_main_shellenv_days_flag_overrides_config(self) -> None:
        out = io.StringIO()
        with patch("siberia.load_config", return_value=AppConfig(min_age_days=7)):
            rc = main(["shellenv", "--age", "21d"], out=out)
        self.assertEqual(rc, 0)
        self.assertIn("npm_config_min_release_age=21", out.getvalue())

    def test_main_init_is_rejected(self) -> None:
        err = io.StringIO()
        with patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as exc:
                main(["init"])
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("invalid choice", err.getvalue())


class ParseAgeTests(unittest.TestCase):
    def test_main_age_weeks_overrides_config(self) -> None:
        out = io.StringIO()
        with patch("siberia.load_config", return_value=AppConfig(min_age_days=7)):
            rc = main(["shellenv", "--age", "2w"], out=out)
        self.assertEqual(rc, 0)
        self.assertIn("npm_config_min_release_age=14", out.getvalue())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.ShellenvSubcommandTests tests.test_siberia.MainSubcommandTests tests.test_siberia.ParseAgeTests -v`
Expected: `FAIL` because `cmd_shellenv()` does not exist yet and argparse still only knows the `init` subcommand.

- [ ] **Step 3: Write minimal implementation**

Rename the subcommand handler, update the top-level usage string, remove the `init` parser, and dispatch only through `shellenv`.

```python
#!/usr/bin/env python3
"""siberia — supply-chain age policy enforcer.

Usage:
    eval "$(siberia shellenv)"
    eval "$(siberia shellenv --age 2w)"
    siberia config --age 14d
    siberia check [files...] [--scan]
"""


def cmd_shellenv(config: AppConfig, out: TextIO) -> int:
    lines: list[str] = []
    if config.enable_pip:
        for k, v in pip_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_uv:
        for k, v in uv_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_npm or config.enable_npx:
        for k, v in npm_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    if config.enable_pnpm:
        for k, v in pnpm_env_overrides(config).items():
            lines.append(f"export {k}={v}")
    print("\n".join(lines), file=out)
    return 0


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

    check_parser = subparsers.add_parser("check", help="Audit lockfiles for too-new packages")
    check_parser.add_argument("files", nargs="*", help="Lockfiles to check")
    check_parser.add_argument("--scan", action="store_true", help="Recursively scan for lockfiles")
    check_parser.add_argument(
        "--age",
        type=parse_age,
        default=None,
        metavar="DURATION",
        help="Minimum package age, e.g. 7d or 2w (default: 7d)",
    )

    args = parser.parse_args(active_argv)

    try:
        config = load_config(env=active_env)
    except ValueError as e:
        print(f"siberia: {e}", file=active_err)
        return 1

    if args.age is not None:
        config = replace(config, min_age_days=args.age)

    if args.command == "shellenv":
        return cmd_shellenv(config, active_out)

    if args.command == "config":
        home = Path(active_env.get("HOME", str(Path.home())))
        return cmd_config(config, home, active_out)

    if args.command == "check":
        return cmd_check(config, args.files, args.scan, active_out, active_err)

    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_siberia.ShellenvSubcommandTests tests.test_siberia.MainSubcommandTests tests.test_siberia.ParseAgeTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add siberia tests/test_siberia.py
git commit -m "refactor: replace init with shellenv"
```

### Task 3: Update The README And Run Final Verification

**Files:**
- Modify: `README.md`
- Verify: `siberia`
- Verify: `tests/test_siberia.py`

- [ ] **Step 1: Verify the README still shows the old names**

Run: `rg -n "siberia init|~/.config/cooling/config.toml|enable_pipx|COOLING_" README.md`
Expected: matches for the old command name, old config path, `enable_pipx`, and `COOLING_*` examples.

- [ ] **Step 2: Rewrite the README sections that describe commands and configuration**

Replace the command/config snippets in `README.md` with the text below.

```md
## What siberia does

Siberia provides three tools:

### `siberia shellenv`

Prints shell export statements that configure each tool's native hardening settings via environment variables. Add this to your shell
profile:

```sh
eval "$(siberia shellenv)"
# or with a custom age:
eval "$(siberia shellenv --age 14d)"
eval "$(siberia shellenv --age 2w)"
```

This sets:

- `PIP_UPLOADED_PRIOR_TO=P7D` — blocks `pip` and `pipx` from installing packages younger than 7 days
- `UV_EXCLUDE_NEWER=P7D` — same for `uv` and `uvx`
- `npm_config_min_release_age=7` — same for `npm` and `npx`
- `npm_config_ignore_scripts=true` — optional `npm` and `npx` hardening that blocks dependency lifecycle scripts broadly
- `pnpm_config_minimum_release_age=10080` — same for `pnpm` (in minutes)
- `pnpm_config_block_exotic_subdeps=true` — blocks transitive pnpm dependencies from using exotic sources like git or tarball URLs
- `pnpm_config_strict_dep_builds=true` — optional pnpm hardening that fails installs on unreviewed dependency build scripts

### `siberia config`

Writes the same policy persistently to each tool's native config file, so it applies even in environments where your shell profile is not
sourced (CI, Docker, subprocess invocations):

```sh
siberia config
siberia config --age 14d
```

Writes to: `~/.config/pip/pip.conf`, `~/.config/uv/uv.toml`, `~/.npmrc`, `~/.config/pnpm/rc`. All writes are idempotent.

Additional hardening written by `siberia config`:

- pnpm enables `block-exotic-subdeps=true` by default
- pnpm can opt into `strict-dep-builds=true`
- npm and npx can opt into `ignore-scripts=true`

If `.npmrc` already contains an explicit `ignore-scripts` setting and Siberia is not configured to manage it, Siberia leaves that user
choice in place and prints a warning instead of overriding it.

### `siberia check`

Audits lockfiles for packages that are younger than the age threshold, fetching publish timestamps from registry APIs:

```sh
siberia check                          # checks known lockfiles in current directory
siberia check package-lock.json        # explicit file
siberia check --scan                   # recursively scan the project tree
siberia check --scan --age 30d         # stricter threshold for audit
```

Supported lockfiles:

| File | Registry |
|------|----------|
| `package-lock.json` | registry.npmjs.org |
| `pnpm-lock.yaml` | registry.npmjs.org |
| `requirements.txt` | pypi.org |
| `Cargo.lock` | crates.io |

Exits 1 if any violations are found. Suitable as a CI gate.

---

## Installation

Siberia is a single Python file with no dependencies beyond the standard library (Python 3.11+):

```sh
curl -o siberia https://raw.githubusercontent.com/your-org/siberia/main/siberia
chmod +x siberia
```

Or clone the repo and run directly:

```sh
python3 siberia shellenv
```

---

## Configuration

Siberia reads `~/.config/siberia/config.toml` if present:

```toml
min_age_days = 7
enable_pip = true
enable_npm = true
enable_pnpm = true
enable_npx = true
enable_uv = true
fail_closed_on_missing_metadata = true
pnpm_block_exotic_subdeps = true
pnpm_strict_dep_builds = false
npm_ignore_scripts = false
```

All fields can be overridden via environment variables:

```sh
SIBERIA_MIN_AGE_DAYS=14
SIBERIA_ENABLE_NPM=0
SIBERIA_FAIL_CLOSED_ON_MISSING_METADATA=false
```

This is a clean-break rename: Siberia no longer reads `~/.config/cooling/config.toml` or any `COOLING_*` environment variables.

The `--age` flag on any subcommand overrides both the config file and environment variables for that invocation.

## Native Capability Differences

- `pnpm` has the strongest native hardening surface in this set: release-age gating, exotic-source blocking, and opt-in strict dependency
  build blocking.
- `npm` supports release-age gating and an opt-in but blunt `ignore-scripts` mode, but not pnpm-style exotic-transitive blocking or
  per-dependency build approvals.
- `pip` and `pipx` share the same pip-native age gate, but not pnpm-style exotic-source blocking or npm-style lifecycle-script toggles.
- `uv` and `uvx` share the same uv-native age gate, but not the same class of script-approval or exotic-source restrictions available in
  pnpm.
- `npm` and `npx` share the same native npm config surface, so Siberia's npm-native settings affect both tools.
```

- [ ] **Step 3: Verify the README shows only the new surface**

Run: `rg -n "siberia init|~/.config/cooling/config.toml|enable_pipx|COOLING_" README.md`
Expected: no matches

Run: `rg -n "shellenv|~/.config/siberia/config.toml|SIBERIA_|pipx|uvx" README.md`
Expected: matches in the command section, config section, and native capability section.

- [ ] **Step 4: Run the full verification pass**

Run: `python -m unittest tests.test_siberia -v`
Expected: `OK`

Run: `python3 siberia shellenv --age 2w`
Expected: output includes `PIP_UPLOADED_PRIOR_TO=P14D`, `UV_EXCLUDE_NEWER=P14D`, `npm_config_min_release_age=14`, and `pnpm_config_minimum_release_age=20160`

Run: `tmp_home="$(mktemp -d)" && HOME="$tmp_home" python3 siberia config --age 2w`
Expected: output lists `wrote` lines for `$tmp_home/.config/pip/pip.conf`, `$tmp_home/.config/uv/uv.toml`, `$tmp_home/.npmrc`, and `$tmp_home/.config/pnpm/rc`

- [ ] **Step 5: Commit**

```bash
git add README.md siberia tests/test_siberia.py
git commit -m "docs: rename shellenv and siberia config surface"
```
