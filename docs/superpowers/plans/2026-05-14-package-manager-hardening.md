# Package Manager Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Siberia's native package-manager hardening with default-on pnpm exotic-subdependency blocking, opt-in pnpm strict dependency build blocking, and opt-in npm script blocking, while documenting package-manager capability differences clearly.

**Architecture:** Keep the change inside the existing single-file CLI by extending `AppConfig`, env/config emission helpers, and the `config` writer flow. Reuse the existing key-value file writer for `.npmrc`-style files, add one small helper for sticky explicit-user-setting detection, and update the README plus unit tests in place.

**Tech Stack:** Python 3 standard library, `unittest`, TOML config parsing via `tomllib`

---

## File Map

- Modify: `siberia.py`
  Responsibility: config model, env overrides, init/config behavior, warning behavior for explicit npm config, CLI plumbing
- Modify: `tests/test_siberia.py`
  Responsibility: unit coverage for new config fields, env exports, config writes, warning behavior, and npm/`npx` shared enablement
- Modify: `README.md`
  Responsibility: user-facing documentation for new protections and package-manager capability differences

### Task 1: Extend Config Model For New Hardening Flags

**Files:**
- Modify: `siberia.py`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

```python
class LoadConfigTests(unittest.TestCase):
    def test_load_config_defaults_new_hardening_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertTrue(config.pnpm_block_exotic_subdeps)
        self.assertFalse(config.pnpm_strict_dep_builds)
        self.assertFalse(config.npm_ignore_scripts)

    def test_load_config_reads_new_hardening_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                "\n".join([
                    "pnpm_block_exotic_subdeps = false",
                    "pnpm_strict_dep_builds = true",
                    "npm_ignore_scripts = true",
                ]),
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertFalse(config.pnpm_block_exotic_subdeps)
        self.assertTrue(config.pnpm_strict_dep_builds)
        self.assertTrue(config.npm_ignore_scripts)

    def test_env_var_overrides_new_hardening_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={
                    "COOLING_PNPM_BLOCK_EXOTIC_SUBDEPS": "0",
                    "COOLING_PNPM_STRICT_DEP_BUILDS": "1",
                    "COOLING_NPM_IGNORE_SCRIPTS": "1",
                },
            )

        self.assertFalse(config.pnpm_block_exotic_subdeps)
        self.assertTrue(config.pnpm_strict_dep_builds)
        self.assertTrue(config.npm_ignore_scripts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.LoadConfigTests -v`
Expected: `FAIL` because `AppConfig` and `load_config()` do not yet expose the new fields

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True, frozen=True)
class AppConfig:
    min_age_days: int = 7
    enable_pip: bool = True
    enable_pipx: bool = True
    enable_npm: bool = True
    enable_pnpm: bool = True
    enable_npx: bool = True
    enable_uv: bool = True
    fail_closed_on_missing_metadata: bool = True
    cache_ttl_seconds: int = 3600
    pnpm_block_exotic_subdeps: bool = True
    pnpm_strict_dep_builds: bool = False
    npm_ignore_scripts: bool = False


_BOOL_ENV_VARS: dict[str, str] = {
    "enable_pip": "COOLING_ENABLE_PIP",
    "enable_pipx": "COOLING_ENABLE_PIPX",
    "enable_npm": "COOLING_ENABLE_NPM",
    "enable_pnpm": "COOLING_ENABLE_PNPM",
    "enable_npx": "COOLING_ENABLE_NPX",
    "enable_uv": "COOLING_ENABLE_UV",
    "fail_closed_on_missing_metadata": "COOLING_FAIL_CLOSED_ON_MISSING_METADATA",
    "pnpm_block_exotic_subdeps": "COOLING_PNPM_BLOCK_EXOTIC_SUBDEPS",
    "pnpm_strict_dep_builds": "COOLING_PNPM_STRICT_DEP_BUILDS",
    "npm_ignore_scripts": "COOLING_NPM_IGNORE_SCRIPTS",
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
        "enable_pipx": _get_bool(data, "enable_pipx", True),
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_siberia.LoadConfigTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add siberia.py tests/test_siberia.py
git commit -m "feat: add hardening config flags"
```

### Task 2: Add Env Export Support For pnpm And npm Hardening

**Files:**
- Modify: `siberia.py`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

```python
class NativeEnvOverrideTests(unittest.TestCase):
    def test_npm_env_overrides_omit_ignore_scripts_by_default(self) -> None:
        env = siberia.npm_env_overrides(AppConfig())
        self.assertNotIn("npm_config_ignore_scripts", env)

    def test_npm_env_overrides_add_ignore_scripts_when_enabled(self) -> None:
        env = siberia.npm_env_overrides(AppConfig(npm_ignore_scripts=True))
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_pnpm_env_overrides_enable_block_exotic_subdeps_by_default(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig())
        self.assertEqual(env["pnpm_config_block_exotic_subdeps"], "true")

    def test_pnpm_env_overrides_omit_strict_dep_builds_by_default(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig())
        self.assertNotIn("pnpm_config_strict_dep_builds", env)

    def test_pnpm_env_overrides_add_strict_dep_builds_when_enabled(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig(pnpm_strict_dep_builds=True))
        self.assertEqual(env["pnpm_config_strict_dep_builds"], "true")


class InitSubcommandTests(unittest.TestCase):
    def test_init_emits_pnpm_block_exotic_export(self) -> None:
        out = io.StringIO()
        cmd_init(AppConfig(), out)
        self.assertIn("export pnpm_config_block_exotic_subdeps=true", out.getvalue())

    def test_init_omits_pnpm_strict_dep_builds_by_default(self) -> None:
        out = io.StringIO()
        cmd_init(AppConfig(), out)
        self.assertNotIn("pnpm_config_strict_dep_builds", out.getvalue())

    def test_init_emits_pnpm_strict_dep_builds_when_enabled(self) -> None:
        out = io.StringIO()
        cmd_init(AppConfig(pnpm_strict_dep_builds=True), out)
        self.assertIn("export pnpm_config_strict_dep_builds=true", out.getvalue())

    def test_init_emits_npm_ignore_scripts_when_npm_enabled(self) -> None:
        out = io.StringIO()
        cmd_init(AppConfig(npm_ignore_scripts=True), out)
        self.assertIn("export npm_config_ignore_scripts=true", out.getvalue())

    def test_init_emits_npm_ignore_scripts_for_npx_only_mode(self) -> None:
        out = io.StringIO()
        cmd_init(
            AppConfig(enable_npm=False, enable_npx=True, npm_ignore_scripts=True),
            out,
        )
        self.assertIn("export npm_config_ignore_scripts=true", out.getvalue())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.NativeEnvOverrideTests tests.test_siberia.InitSubcommandTests -v`
Expected: `FAIL` because the new env keys are not emitted yet

- [ ] **Step 3: Write minimal implementation**

```python
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


def cmd_init(config: AppConfig, out: TextIO) -> int:
    lines: list[str] = []
    if config.enable_pip or config.enable_pipx:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_siberia.NativeEnvOverrideTests tests.test_siberia.InitSubcommandTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add siberia.py tests/test_siberia.py
git commit -m "feat: export package manager hardening settings"
```

### Task 3: Persist pnpm Hardening And Handle Sticky npm Script Settings

**Files:**
- Modify: `siberia.py`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

```python
class ConfigSubcommandTests(unittest.TestCase):
    def test_config_writes_pnpm_block_exotic_subdeps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("block-exotic-subdeps=true", content)

    def test_config_omits_pnpm_strict_dep_builds_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertNotIn("strict-dep-builds=true", content)

    def test_config_writes_pnpm_strict_dep_builds_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(pnpm_strict_dep_builds=True), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("strict-dep-builds=true", content)

    def test_config_writes_npm_ignore_scripts_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(npm_ignore_scripts=True), home, io.StringIO())
            content = (home / ".npmrc").read_text()
            self.assertIn("ignore-scripts=true", content)

    def test_config_leaves_explicit_npm_ignore_scripts_when_disabled_and_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            npmrc = home / ".npmrc"
            npmrc.write_text("ignore-scripts=true\n", encoding="utf-8")
            out = io.StringIO()
            cmd_config(AppConfig(npm_ignore_scripts=False), home, out)
            self.assertEqual(npmrc.read_text(encoding="utf-8"), "ignore-scripts=true\nmin-release-age=7\n")
            self.assertIn("warning:", out.getvalue())

    def test_config_writes_npm_settings_for_npx_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(
                AppConfig(enable_npm=False, enable_npx=True, npm_ignore_scripts=True),
                home,
                io.StringIO(),
            )
            content = (home / ".npmrc").read_text()
            self.assertIn("min-release-age=7", content)
            self.assertIn("ignore-scripts=true", content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.ConfigSubcommandTests -v`
Expected: `FAIL` because pnpm hardening keys, warnings, and npx-only npm writes are not implemented yet

- [ ] **Step 3: Write minimal implementation**

```python
def _read_kv_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
        if line.startswith(f"{key} ="):
            return line.split("=", 1)[1].strip()
    return None


def cmd_config(config: AppConfig, home: Path, out: TextIO) -> int:
    written: list[str] = []
    if config.enable_pip or config.enable_pipx:
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
        else:
            ignore_scripts = _read_kv_value(p, "ignore-scripts")
            if ignore_scripts is not None:
                print(
                    "warning: leaving explicit ignore-scripts setting unchanged in ~/.npmrc",
                    file=out,
                )
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

Run: `python -m unittest tests.test_siberia.ConfigSubcommandTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add siberia.py tests/test_siberia.py
git commit -m "feat: persist native hardening settings"
```

### Task 4: Update README For Capability Differences And New Protections

**Files:**
- Modify: `README.md`
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Write the failing test**

```python
class MainSubcommandTests(unittest.TestCase):
    def test_main_config_reports_warning_for_explicit_npm_ignore_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".npmrc").write_text("ignore-scripts=true\n", encoding="utf-8")
            out = io.StringIO()
            with patch("siberia.load_config", return_value=AppConfig(npm_ignore_scripts=False)):
                rc = main(["config"], env={"HOME": tmp}, out=out)
            self.assertEqual(rc, 0)
            self.assertIn("warning:", out.getvalue())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_siberia.MainSubcommandTests -v`
Expected: `FAIL` if the warning path is not exercised through `main()` yet

- [ ] **Step 3: Write minimal implementation and docs**

```markdown
## What siberia does

Siberia provides three tools:

### `siberia init`

This sets:
- `PIP_UPLOADED_PRIOR_TO=P7D` — blocks pip and pipx from installing packages younger than 7 days
- `UV_EXCLUDE_NEWER=P7D` — same for uv
- `npm_config_min_release_age=7` — same for npm and npx
- `pnpm_config_minimum_release_age=10080` — same for pnpm (in minutes)
- `pnpm_config_block_exotic_subdeps=true` — blocks transitive pnpm dependencies from using exotic sources like git or tarball URLs
- `pnpm_config_strict_dep_builds=true` — optional pnpm hardening that fails installs on unreviewed dependency build scripts
- `npm_config_ignore_scripts=true` — optional npm/npx hardening that blocks dependency lifecycle scripts broadly

### Native capability differences

- `pnpm` has the strongest native hardening surface in this set: release-age gating, exotic-source blocking, and opt-in strict dependency build blocking.
- `npm` supports release-age gating and a blunt `ignore-scripts` mode, but not pnpm-style exotic-subdependency blocking or per-dependency build approvals.
- `pip` and `uv` currently provide age-based controls, but not the same class of native script-approval or exotic-source restrictions.
- `npm` and `npx` share the same native npm config surface, so Siberia's npm-native settings affect both tools.
```

Use that content to update the existing README sections rather than appending duplicates.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_siberia.MainSubcommandTests -v`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add README.md siberia.py tests/test_siberia.py
git commit -m "docs: explain native hardening support"
```

### Task 5: Run Full Verification

**Files:**
- Modify: none
- Test: `tests/test_siberia.py`

- [ ] **Step 1: Run the full test suite**

Run: `python -m unittest tests.test_siberia -v`
Expected: `OK`

- [ ] **Step 2: Review CLI output manually**

Run: `python siberia.py init`
Expected: output includes `pnpm_config_block_exotic_subdeps=true` and does not include `pnpm_config_strict_dep_builds=true` or `npm_config_ignore_scripts=true` by default

- [ ] **Step 3: Review opt-in CLI output manually**

Run: `COOLING_PNPM_STRICT_DEP_BUILDS=1 COOLING_NPM_IGNORE_SCRIPTS=1 python siberia.py init`
Expected: output includes `pnpm_config_strict_dep_builds=true` and `npm_config_ignore_scripts=true`

- [ ] **Step 4: Commit**

```bash
git add README.md siberia.py tests/test_siberia.py
git commit -m "test: verify package manager hardening flow"
```

## Self-Review

- Spec coverage check: the plan covers config defaults and overrides, pnpm default-on exotic blocking, opt-in pnpm strict builds, sticky npm `ignore-scripts` warnings, npm/`npx` shared behavior, tests, and README updates.
- Placeholder scan: each task includes concrete file paths, test code, commands, and expected outcomes.
- Type consistency check: `pnpm_block_exotic_subdeps`, `pnpm_strict_dep_builds`, and `npm_ignore_scripts` are used consistently across config, env, tests, and docs.
