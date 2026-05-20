from __future__ import annotations

import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import siberia.cli as siberia
from siberia import __version__
from siberia.cli import AppConfig, cmd_config, cmd_shellenv, load_config, main, parse_age


class PackageImportTests(unittest.TestCase):
    def test_package_cli_module_can_be_imported(self) -> None:
        module = importlib.import_module("siberia.cli")
        self.assertEqual(module.__version__, "0.2.0")
        self.assertEqual(__version__, "0.2.0")

    def test_main_supports_top_level_version_flag(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = main(["--version"], out=out, err=err, env={})

        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "0.2.0")
        self.assertEqual(err.getvalue(), "")

    def test_module_main_remains_callable(self) -> None:
        module = importlib.import_module("siberia.cli")
        out = io.StringIO()
        rc = module.main(["shellenv", "--age", "7d"], out=out, err=io.StringIO(), env={})
        self.assertEqual(rc, 0)
        self.assertIn("PIP_UPLOADED_PRIOR_TO=P7D", out.getvalue())


class PackagingMetadataTests(unittest.TestCase):
    def test_pyproject_exists(self) -> None:
        self.assertTrue((ROOT / "pyproject.toml").exists())


class WorkflowPresenceTests(unittest.TestCase):
    def test_ci_workflow_exists(self) -> None:
        self.assertTrue((ROOT / ".github/workflows/ci.yml").exists())

    def test_release_workflow_exists(self) -> None:
        self.assertTrue((ROOT / ".github/workflows/release.yml").exists())


class ReleaseDocsTests(unittest.TestCase):
    def test_runner_and_release_runbook_exists(self) -> None:
        self.assertTrue((ROOT / "docs/superpowers/runbooks/github-runners-and-releases.md").exists())

    def test_homebrew_formula_template_exists(self) -> None:
        self.assertTrue((ROOT / "docs/homebrew/siberia.rb").exists())


class LoadConfigTests(unittest.TestCase):
    def test_default_config_path_uses_siberia_namespace(self) -> None:
        self.assertEqual(
            siberia.DEFAULT_CONFIG_PATH,
            Path("~/.config/siberia/config.toml").expanduser(),
        )

    def test_load_config_returns_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertEqual(config.min_age_days, 7)
        self.assertTrue(config.enable_pip)
        self.assertTrue(config.enable_npm)
        self.assertTrue(config.enable_pnpm)
        self.assertTrue(config.fail_closed_on_missing_metadata)
        self.assertEqual(config.cache_ttl_seconds, 3600)

    def test_load_config_defaults_new_hardening_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertTrue(config.pnpm_block_exotic_subdeps)
        self.assertFalse(config.pnpm_strict_dep_builds)
        self.assertFalse(config.npm_ignore_scripts)

    def test_load_config_reads_values_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                "\n".join([
                    "min_age_days = 14",
                    "enable_pip = false",
                    "enable_npm = true",
                    "enable_pnpm = false",
                    "enable_npx = true",
                    "fail_closed_on_missing_metadata = false",
                    "cache_ttl_seconds = 90",
                ]),
                encoding="utf-8",
            )
            config = load_config(config_path)

        self.assertEqual(config.min_age_days, 14)
        self.assertFalse(config.enable_pip)
        self.assertTrue(config.enable_npm)
        self.assertFalse(config.enable_pnpm)
        self.assertTrue(config.enable_npx)
        self.assertFalse(config.fail_closed_on_missing_metadata)
        self.assertEqual(config.cache_ttl_seconds, 90)

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

    def test_load_config_rejects_invalid_boolean_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text('enable_pip = "false"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config_path)

    def test_load_config_rejects_invalid_integer_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text('cache_ttl_seconds = "3600"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(config_path)

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

    def test_env_var_overrides_all_tools(self) -> None:
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

    def test_legacy_cooling_env_var_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"COOLING_ENABLE_PIP": "0"},
            )

        self.assertTrue(config.enable_pip)

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


class ShellenvSubcommandTests(unittest.TestCase):
    def test_shellenv_emits_pip_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export PIP_UPLOADED_PRIOR_TO=P7D", out.getvalue())

    def test_shellenv_omits_pip_exports_when_pip_is_disabled(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7, enable_pip=False), out)
        self.assertNotIn("PIP_UPLOADED_PRIOR_TO", out.getvalue())

    def test_shellenv_emits_uv_export(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7), out)
        self.assertIn("export UV_EXCLUDE_NEWER=P7D", out.getvalue())

    def test_shellenv_omits_uv_exports_when_uv_is_disabled(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7, enable_uv=False), out)
        self.assertNotIn("UV_EXCLUDE_NEWER", out.getvalue())

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

    def test_shellenv_skips_disabled_tools(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=7, enable_npm=False, enable_npx=False), out)
        self.assertNotIn("npm_config_min_release_age", out.getvalue())

    def test_shellenv_respects_custom_days(self) -> None:
        out = io.StringIO()
        cmd_shellenv(AppConfig(min_age_days=14), out)
        self.assertIn("export npm_config_min_release_age=14", out.getvalue())


class ConfigSubcommandTests(unittest.TestCase):
    def test_config_verbose_lists_all_managed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            out = io.StringIO()
            cmd_config(AppConfig(), home, out, verbose=True)
            content = out.getvalue()
            self.assertIn("~/.config/pip/pip.conf", content)
            self.assertIn("[write] global.uploaded-prior-to = P7D", content)
            self.assertIn("~/.config/uv/uv.toml", content)
            self.assertIn("[write] exclude-newer = P7D", content)
            self.assertIn("~/.npmrc", content)
            self.assertIn("[write] min-release-age = 7", content)
            self.assertIn("[skip] ignore-scripts (option disabled)", content)
            self.assertIn("~/.config/pnpm/rc", content)
            self.assertIn("[write] minimum-release-age = 10080", content)
            self.assertIn("[write] minimum-release-age-strict = true", content)
            self.assertIn("[write] minimum-release-age-ignore-missing-time = false", content)
            self.assertIn("[write] block-exotic-subdeps = true", content)
            self.assertIn("[skip] strict-dep-builds (option disabled)", content)

    def test_config_verbose_lists_skipped_fields_for_disabled_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            out = io.StringIO()
            cmd_config(
                AppConfig(enable_pip=False, enable_npm=False, enable_npx=False, enable_uv=False, enable_pnpm=False),
                home,
                out,
                verbose=True,
            )
            content = out.getvalue()
            self.assertIn("~/.config/pip/pip.conf", content)
            self.assertIn("[skip] global.uploaded-prior-to (tool disabled)", content)
            self.assertIn("~/.config/uv/uv.toml", content)
            self.assertIn("[skip] exclude-newer (tool disabled)", content)
            self.assertIn("~/.npmrc", content)
            self.assertIn("[skip] min-release-age (tool disabled)", content)
            self.assertIn("[skip] ignore-scripts (tool disabled)", content)
            self.assertIn("~/.config/pnpm/rc", content)
            self.assertIn("[skip] minimum-release-age (tool disabled)", content)
            self.assertIn("[skip] minimum-release-age-strict (tool disabled)", content)
            self.assertIn("[skip] minimum-release-age-ignore-missing-time (tool disabled)", content)
            self.assertIn("[skip] block-exotic-subdeps (tool disabled)", content)
            self.assertIn("[skip] strict-dep-builds (tool disabled)", content)

    def test_config_writes_pip_conf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            pip_conf = home / ".config" / "pip" / "pip.conf"
            self.assertTrue(pip_conf.exists())
            content = pip_conf.read_text()
            self.assertIn("uploaded-prior-to", content)
            self.assertIn("P7D", content)

    def test_config_writes_uv_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            uv_toml = home / ".config" / "uv" / "uv.toml"
            self.assertTrue(uv_toml.exists())
            content = uv_toml.read_text()
            self.assertIn("exclude-newer", content)
            self.assertIn("P7D", content)

    def test_config_skips_pip_conf_when_pip_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_pip=False), home, io.StringIO())
            pip_conf = home / ".config" / "pip" / "pip.conf"
            self.assertFalse(pip_conf.exists())

    def test_config_skips_uv_toml_when_uv_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_uv=False), home, io.StringIO())
            uv_toml = home / ".config" / "uv" / "uv.toml"
            self.assertFalse(uv_toml.exists())

    def test_config_writes_npmrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            content = (home / ".npmrc").read_text()
            self.assertIn("min-release-age=7", content)

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

    def test_config_writes_pnpm_rc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("minimum-release-age=10080", content)

    def test_config_writes_pnpm_minimum_release_age_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("minimum-release-age-strict=true", content)

    def test_config_writes_pnpm_fail_closed_ignore_missing_time_false_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("minimum-release-age-ignore-missing-time=false", content)

    def test_config_writes_pnpm_fail_open_ignore_missing_time_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(fail_closed_on_missing_metadata=False), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertIn("minimum-release-age-ignore-missing-time=true", content)

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

    def test_config_is_idempotent_for_pnpm_rc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "rc").read_text()
            self.assertEqual(content.count("minimum-release-age-strict"), 1)
            self.assertEqual(content.count("minimum-release-age-ignore-missing-time"), 1)

    def test_config_is_idempotent_for_npmrc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            content = (home / ".npmrc").read_text()
            self.assertEqual(content.count("min-release-age"), 1)

    def test_config_updates_existing_npmrc_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            cmd_config(AppConfig(min_age_days=14), home, io.StringIO())
            content = (home / ".npmrc").read_text()
            self.assertIn("min-release-age=14", content)
            self.assertNotIn("min-release-age=7", content)

    def test_config_skips_disabled_npm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_npm=False, enable_npx=False), home, io.StringIO())
            self.assertFalse((home / ".npmrc").exists())


class MainSubcommandTests(unittest.TestCase):
    def test_main_shellenv_returns_zero(self) -> None:
        out = io.StringIO()
        with patch("siberia.cli.load_config", return_value=AppConfig()):
            rc = main(["shellenv"], out=out)
        self.assertEqual(rc, 0)

    def test_main_shellenv_days_flag_overrides_config(self) -> None:
        out = io.StringIO()
        with patch("siberia.cli.load_config", return_value=AppConfig(min_age_days=7)):
            rc = main(["shellenv", "--age", "21d"], out=out)
        self.assertEqual(rc, 0)
        self.assertIn("npm_config_min_release_age=21", out.getvalue())

    def test_main_init_is_rejected_by_argparse(self) -> None:
        err = io.StringIO()
        with patch("sys.stderr", err):
            with self.assertRaises(SystemExit) as exc:
                main(["init"])
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("invalid choice", err.getvalue())
        self.assertIn("init", err.getvalue())

    def test_main_config_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with patch("siberia.cli.load_config", return_value=AppConfig()):
                rc = main(["config"], env={"HOME": tmp}, out=out)
            self.assertEqual(rc, 0)

    def test_main_config_verbose_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with patch("siberia.cli.load_config", return_value=AppConfig()):
                rc = main(["config", "--verbose"], env={"HOME": tmp}, out=out)
            self.assertEqual(rc, 0)
            self.assertIn("[write] global.uploaded-prior-to = P7D", out.getvalue())

    def test_main_config_reports_warning_for_explicit_npm_ignore_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".npmrc").write_text("ignore-scripts=true\n", encoding="utf-8")
            out = io.StringIO()
            with patch("siberia.cli.load_config", return_value=AppConfig(npm_ignore_scripts=False)):
                rc = main(["config"], env={"HOME": tmp}, out=out)
            self.assertEqual(rc, 0)
            self.assertIn("warning:", out.getvalue())

    def test_main_exits_one_on_bad_config(self) -> None:
        err = io.StringIO()
        with patch("siberia.cli.load_config", side_effect=ValueError("bad")):
            rc = main(["shellenv"], err=err)
        self.assertEqual(rc, 1)
        self.assertIn("siberia:", err.getvalue())


class CheckCommandTests(unittest.TestCase):
    def test_cmd_check_supports_uv_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "uv.lock"
            lockfile.write_text(
                "\n".join([
                    "version = 1",
                    "",
                    "[[package]]",
                    'name = "urllib3"',
                    'version = "2.2.1"',
                    'source = { registry = "https://pypi.org/simple" }',
                    "",
                    "[[package]]",
                    'name = "local-package"',
                    'version = "0.1.0"',
                    'source = { editable = "." }',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._pypi_published_at", return_value=now):
                violations = siberia._check_uv_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("urllib3", "2.2.1")])

    def test_cmd_check_supports_npm_shrinkwrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "npm-shrinkwrap.json"
            lockfile.write_text(
                """
                {
                  "packages": {
                    "": {},
                    "node_modules/react": {
                      "version": "19.0.0"
                    }
                  }
                }
                """,
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now):
                violations = siberia._check_npm_shrinkwrap(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("react", "19.0.0")])

    def test_cmd_check_supports_bun_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "bun.lock"
            lockfile.write_text(
                """
                {
                  "lockfileVersion": 1,
                  "packages": {
                    "react": ["react@19.0.0", "", {}, "sha512-test"],
                    "workspace-pkg": ["workspace:packages/app", "", {}, ""]
                  }
                }
                """,
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now):
                violations = siberia._check_bun_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("react", "19.0.0")])

    def test_cmd_check_supports_deno_lock_npm_entries_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "deno.lock"
            lockfile.write_text(
                """
                {
                  "version": "5",
                  "npm": {
                    "chalk@5.3.0": {"integrity": "sha512-test"}
                  },
                  "jsr": {
                    "@std/assert@1.0.0": {"integrity": "abc123"}
                  }
                }
                """,
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_deno_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("chalk", "5.3.0")])
        mocked_lookup.assert_called_once_with("chalk", "5.3.0")

    def test_cmd_check_supports_poetry_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "poetry.lock"
            lockfile.write_text(
                "\n".join([
                    "[[package]]",
                    'name = "requests"',
                    'version = "2.32.3"',
                    "",
                    "[[package]]",
                    'name = "requests"',
                    'version = "2.32.3"',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._pypi_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_poetry_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("requests", "2.32.3")])
        mocked_lookup.assert_called_once_with("requests", "2.32.3")

    def test_cmd_check_supports_pipfile_lock_default_and_develop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "Pipfile.lock"
            lockfile.write_text(
                """
                {
                  "default": {
                    "requests": {"version": "==2.32.3"}
                  },
                  "develop": {
                    "pytest": {"version": "==8.3.3"}
                  }
                }
                """,
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._pypi_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_pipfile_lock(lockfile, 7, now)

        self.assertEqual(
            [(item.package, item.version) for item in violations],
            [("requests", "2.32.3"), ("pytest", "8.3.3")],
        )
        self.assertEqual(mocked_lookup.call_count, 2)

    def test_cmd_check_scan_finds_new_supported_lockfiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "nested" / "uv.lock").write_text(
                "\n".join([
                    "version = 1",
                    "",
                    "[[package]]",
                    'name = "urllib3"',
                    'version = "2.2.1"',
                    'source = { registry = "https://pypi.org/simple" }',
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        rc = siberia.cmd_check(AppConfig(), [], True, out, err)
                    finally:
                        os.chdir(cwd)

        self.assertEqual(rc, 1)
        self.assertIn("VIOLATION:", out.getvalue())

    def test_cmd_check_reports_unsupported_file_type(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = siberia.cmd_check(AppConfig(), ["bun.lockb"], False, out, err)

        self.assertEqual(rc, 0)
        self.assertIn("unsupported file type", err.getvalue())

    def test_main_check_supports_explicit_new_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "Pipfile.lock"
            lockfile.write_text(
                """
                {
                  "default": {
                    "requests": {"version": "==2.32.3"}
                  },
                  "develop": {}
                }
                """,
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    rc = main(["check", str(lockfile)], out=out, err=err, env={})

        self.assertEqual(rc, 1)
        self.assertIn("requests@2.32.3", out.getvalue())


class NativeEnvOverrideTests(unittest.TestCase):
    def test_pip_env_overrides_uses_iso_duration(self) -> None:
        self.assertEqual(siberia.pip_env_overrides(AppConfig())["PIP_UPLOADED_PRIOR_TO"], "P7D")

    def test_pip_env_overrides_respects_custom_days(self) -> None:
        self.assertEqual(siberia.pip_env_overrides(AppConfig(min_age_days=14))["PIP_UPLOADED_PRIOR_TO"], "P14D")

    def test_uv_env_overrides_uses_iso_duration(self) -> None:
        self.assertEqual(siberia.uv_env_overrides(AppConfig())["UV_EXCLUDE_NEWER"], "P7D")

    def test_npm_env_overrides_uses_days(self) -> None:
        self.assertEqual(siberia.npm_env_overrides(AppConfig())["npm_config_min_release_age"], "7")

    def test_npm_env_overrides_omit_ignore_scripts_by_default(self) -> None:
        env = siberia.npm_env_overrides(AppConfig())
        self.assertNotIn("npm_config_ignore_scripts", env)

    def test_npm_env_overrides_add_ignore_scripts_when_enabled(self) -> None:
        env = siberia.npm_env_overrides(AppConfig(npm_ignore_scripts=True))
        self.assertEqual(env["npm_config_ignore_scripts"], "true")

    def test_npm_env_overrides_respects_custom_days(self) -> None:
        self.assertEqual(siberia.npm_env_overrides(AppConfig(min_age_days=14))["npm_config_min_release_age"], "14")

    def test_pnpm_env_overrides_converts_to_minutes(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig())
        self.assertEqual(env["pnpm_config_minimum_release_age"], "10080")
        self.assertEqual(env["pnpm_config_minimum_release_age_strict"], "true")

    def test_pnpm_env_overrides_enable_block_exotic_subdeps_by_default(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig())
        self.assertEqual(env["pnpm_config_block_exotic_subdeps"], "true")

    def test_pnpm_env_overrides_omit_strict_dep_builds_by_default(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig())
        self.assertNotIn("pnpm_config_strict_dep_builds", env)

    def test_pnpm_env_overrides_add_strict_dep_builds_when_enabled(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig(pnpm_strict_dep_builds=True))
        self.assertEqual(env["pnpm_config_strict_dep_builds"], "true")

    def test_pnpm_env_overrides_fail_closed_sets_ignore_false(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig(fail_closed_on_missing_metadata=True))
        self.assertEqual(env["pnpm_config_minimum_release_age_ignore_missing_time"], "false")

    def test_pnpm_env_overrides_fail_open_sets_ignore_true(self) -> None:
        env = siberia.pnpm_env_overrides(AppConfig(fail_closed_on_missing_metadata=False))
        self.assertEqual(env["pnpm_config_minimum_release_age_ignore_missing_time"], "true")


class ParseAgeTests(unittest.TestCase):
    def test_bare_integer_is_days(self) -> None:
        self.assertEqual(parse_age("7"), 7)

    def test_d_suffix(self) -> None:
        self.assertEqual(parse_age("7d"), 7)

    def test_day_suffix(self) -> None:
        self.assertEqual(parse_age("7day"), 7)

    def test_days_suffix(self) -> None:
        self.assertEqual(parse_age("14days"), 14)

    def test_w_suffix_converts_to_days(self) -> None:
        self.assertEqual(parse_age("2w"), 14)

    def test_week_suffix(self) -> None:
        self.assertEqual(parse_age("1week"), 7)

    def test_weeks_suffix(self) -> None:
        self.assertEqual(parse_age("3weeks"), 21)

    def test_case_insensitive(self) -> None:
        self.assertEqual(parse_age("2W"), 14)
        self.assertEqual(parse_age("7D"), 7)

    def test_invalid_value_raises(self) -> None:
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_age("two weeks")

    def test_main_age_weeks_overrides_config(self) -> None:
        out = io.StringIO()
        with patch("siberia.cli.load_config", return_value=AppConfig(min_age_days=7)):
            rc = main(["shellenv", "--age", "2w"], out=out)
        self.assertEqual(rc, 0)
        self.assertIn("npm_config_min_release_age=14", out.getvalue())
