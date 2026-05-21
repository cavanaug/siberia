from __future__ import annotations

import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import siberia.cli as siberia
from siberia import __version__
from siberia.cli import AppConfig, cmd_config, cmd_shellenv, load_config, main, parse_age


class TtyStringIO(io.StringIO):
    def __init__(self, *, is_tty: bool) -> None:
        super().__init__()
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


class PackageImportTests(unittest.TestCase):
    def test_package_cli_module_can_be_imported(self) -> None:
        module = importlib.import_module("siberia.cli")
        self.assertEqual(module.__version__, "0.4.0")
        self.assertEqual(__version__, "0.4.0")

    def test_module_cli_is_runnable_from_repo_root(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        import_result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import pathlib, siberia, siberia.cli; "
                    "print(pathlib.Path(siberia.__file__).resolve()); "
                    "print(pathlib.Path(siberia.cli.__file__).resolve())"
                ),
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
            check=True,
        )
        result = subprocess.run(
            [sys.executable, "-m", "siberia.cli", "shellenv", "--age", "7d"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
        )

        self.assertEqual(
            import_result.stdout.splitlines(),
            [
                str((ROOT / "siberia" / "__init__.py").resolve()),
                str((ROOT / "siberia" / "cli.py").resolve()),
            ],
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("export PIP_UPLOADED_PRIOR_TO=P7D", result.stdout)

    def test_importing_package_does_not_preload_cli_module(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, siberia; print(siberia.__version__); print('siberia.cli' in sys.modules)",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(SRC)},
            check=True,
        )

        self.assertEqual(result.stdout.splitlines(), ["0.4.0", "False"])

    def test_main_supports_top_level_version_flag(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = main(["--version"], out=out, err=err, env={})

        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), "0.4.0")
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


class DocumentationCoverageTests(unittest.TestCase):
    def test_readme_mentions_repo_root_module_entrypoint(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python -m siberia.cli shellenv", content)

    def test_readme_mentions_audit_lock_command(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("siberia audit-lock", content)
        self.assertIn("uvx siberia audit-lock --scan", content)
        self.assertIn("Persistent `audit-lock` cache", content)
        self.assertNotIn("Persistent `check` cache", content)

    def test_readme_mentions_enable_yarn_config_flag(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("enable_yarn = true", content)
        self.assertIn("SIBERIA_ENABLE_YARN=0", content)

    def test_readme_mentions_yarn_native_capability(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("yarn.lock", content)
        self.assertIn("npmMinimalAgeGate", content)
        self.assertIn("modern Yarn lockfiles", content)

    def test_readme_mentions_yarn_project_config_boundary(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("config --project PATH", content)
        self.assertIn("PATH/.yarnrc.yml", content)

    def test_readme_mentions_bun_native_minimum_release_age(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("~/.bunfig.toml", content)
        self.assertIn("minimumReleaseAge", content)

    def test_readme_mentions_dependabot_cooldown_alignment(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Dependabot", content)
        self.assertIn("cooldown", content)
        self.assertIn("default-days", content)
        self.assertIn(".github/dependabot.yml", content)

    def test_readme_mentions_pnpm_config_yaml(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("~/.config/pnpm/config.yaml", content)

    def test_readme_mentions_native_capability_matrix(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("uploaded-prior-to", content)
        self.assertIn("min-release-age", content)
        self.assertIn("minimumReleaseAge", content)
        self.assertIn("~/.bunfig.toml", content)
        self.assertIn("~/.config/pnpm/config.yaml", content)


class LoadConfigTests(unittest.TestCase):
    def test_default_config_path_uses_siberia_namespace(self) -> None:
        self.assertEqual(
            siberia.DEFAULT_CONFIG_PATH,
            Path("~/.config/siberia/config.toml").expanduser(),
        )

    def test_check_cache_path_uses_xdg_cache_home(self) -> None:
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/siberia-cache-home"}, clear=False):
            reloaded = importlib.reload(siberia)

        self.assertEqual(reloaded._CHECK_CACHE_PATH, Path("/tmp/siberia-cache-home/siberia/check-cache.json"))
        importlib.reload(reloaded)

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

    def test_load_config_defaults_enable_bun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertTrue(config.enable_bun)

    def test_load_config_defaults_enable_yarn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.toml")

        self.assertTrue(config.enable_yarn)

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

    def test_load_config_reads_enable_bun_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("enable_bun = false\n", encoding="utf-8")

            config = load_config(config_path)

        self.assertFalse(config.enable_bun)

    def test_load_config_reads_enable_yarn_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text("enable_yarn = false\n", encoding="utf-8")

            config = load_config(config_path)

        self.assertFalse(config.enable_yarn)

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

    def test_env_var_overrides_enable_bun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"SIBERIA_ENABLE_BUN": "0"},
            )

        self.assertFalse(config.enable_bun)

    def test_env_var_overrides_enable_yarn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(
                Path(temp_dir) / "missing.toml",
                env={"SIBERIA_ENABLE_YARN": "0"},
            )

        self.assertFalse(config.enable_yarn)

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
            cmd_config(AppConfig(), home, out, verbosity=1)
            content = out.getvalue()
            self.assertIn("~/.config/pip/pip.conf", content)
            self.assertIn("[write] global.uploaded-prior-to = P7D", content)
            self.assertIn("~/.config/uv/uv.toml", content)
            self.assertIn("[write] exclude-newer = P7D", content)
            self.assertIn("~/.npmrc", content)
            self.assertIn("[write] min-release-age = 7", content)
            self.assertIn("[skip] ignore-scripts (option disabled)", content)
            self.assertIn("~/.bunfig.toml", content)
            self.assertIn("[write] install.minimumReleaseAge = 604800", content)
            self.assertIn("~/.config/pnpm/config.yaml", content)
            self.assertIn("[write] minimumReleaseAge = 10080", content)
            self.assertIn("[write] minimumReleaseAgeStrict = true", content)
            self.assertIn("[write] minimumReleaseAgeIgnoreMissingTime = false", content)
            self.assertIn("[write] blockExoticSubdeps = true", content)
            self.assertIn("[skip] strictDepBuilds (option disabled)", content)

    def test_config_verbose_reports_yarn_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()
            out = io.StringIO()

            cmd_config(AppConfig(), home, out, verbosity=1, project=project)

            content = out.getvalue()
            self.assertIn(str(project / ".yarnrc.yml"), content)
            self.assertIn("[write] npmMinimalAgeGate = 7d", content)

    def test_config_verbose_lists_skipped_fields_for_disabled_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            out = io.StringIO()
            cmd_config(
                AppConfig(
                    enable_pip=False,
                    enable_npm=False,
                    enable_npx=False,
                    enable_uv=False,
                    enable_bun=False,
                    enable_pnpm=False,
                ),
                home,
                out,
                verbosity=1,
            )
            content = out.getvalue()
            self.assertIn("~/.config/pip/pip.conf", content)
            self.assertIn("[skip] global.uploaded-prior-to (tool disabled)", content)
            self.assertIn("~/.config/uv/uv.toml", content)
            self.assertIn("[skip] exclude-newer (tool disabled)", content)
            self.assertIn("~/.npmrc", content)
            self.assertIn("[skip] min-release-age (tool disabled)", content)
            self.assertIn("[skip] ignore-scripts (tool disabled)", content)
            self.assertIn("~/.bunfig.toml", content)
            self.assertIn("[skip] install.minimumReleaseAge (tool disabled)", content)
            self.assertIn("~/.config/pnpm/config.yaml", content)
            self.assertIn("[skip] minimumReleaseAge (tool disabled)", content)
            self.assertIn("[skip] minimumReleaseAgeStrict (tool disabled)", content)
            self.assertIn("[skip] minimumReleaseAgeIgnoreMissingTime (tool disabled)", content)
            self.assertIn("[skip] blockExoticSubdeps (tool disabled)", content)
            self.assertIn("[skip] strictDepBuilds (tool disabled)", content)

    def test_config_writes_bunfig(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            content = (home / ".bunfig.toml").read_text(encoding="utf-8")
            self.assertIn("[install]", content)
            self.assertIn("minimumReleaseAge = 604800", content)

    def test_config_updates_existing_bunfig_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            cmd_config(AppConfig(min_age_days=14), home, io.StringIO())
            content = (home / ".bunfig.toml").read_text(encoding="utf-8")
            self.assertIn("minimumReleaseAge = 1209600", content)
            self.assertNotIn("minimumReleaseAge = 604800", content)

    def test_config_updates_bunfig_without_touching_near_match_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bunfig = home / ".bunfig.toml"
            bunfig.write_text(
                "[install]\nminimumReleaseAgeExtra = 42\nminimumReleaseAge = 604800\n",
                encoding="utf-8",
            )

            cmd_config(AppConfig(min_age_days=14), home, io.StringIO())

            content = bunfig.read_text(encoding="utf-8")
            self.assertIn("minimumReleaseAgeExtra = 42", content)
            self.assertIn("minimumReleaseAge = 1209600", content)
            self.assertNotIn("minimumReleaseAgeExtra = 1209600", content)

    def test_config_skips_bunfig_when_bun_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(enable_bun=False), home, io.StringIO())
            self.assertFalse((home / ".bunfig.toml").exists())

    def test_config_writes_yarnrc_when_project_target_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()

            cmd_config(AppConfig(min_age_days=7), home, io.StringIO(), project=project)

            content = (project / ".yarnrc.yml").read_text(encoding="utf-8")
            self.assertIn("npmMinimalAgeGate: 7d", content)

    def test_config_updates_existing_yarnrc_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()

            cmd_config(AppConfig(min_age_days=7), home, io.StringIO(), project=project)
            cmd_config(AppConfig(min_age_days=14), home, io.StringIO(), project=project)

            content = (project / ".yarnrc.yml").read_text(encoding="utf-8")
            self.assertIn("npmMinimalAgeGate: 14d", content)
            self.assertNotIn("npmMinimalAgeGate: 7d", content)

    def test_config_preserves_unrelated_yarn_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()
            yarnrc = project / ".yarnrc.yml"
            yarnrc.write_text(
                "nodeLinker: node-modules\nnpmRegistries:\n  //registry.npmjs.org:\n    npmAuthToken: secret\nnpmMinimalAgeGate: 1d\n",
                encoding="utf-8",
            )

            cmd_config(AppConfig(min_age_days=7), home, io.StringIO(), project=project)

            content = yarnrc.read_text(encoding="utf-8")
            self.assertIn("nodeLinker: node-modules\n", content)
            self.assertIn("npmRegistries:\n", content)
            self.assertIn("  //registry.npmjs.org:\n", content)
            self.assertIn("    npmAuthToken: secret\n", content)
            self.assertIn("npmMinimalAgeGate: 7d\n", content)
            self.assertNotIn("npmMinimalAgeGate: 1d\n", content)

    def test_config_updates_yarnrc_before_yaml_terminator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()
            yarnrc = project / ".yarnrc.yml"
            yarnrc.write_text("nodeLinker: node-modules\n...\n", encoding="utf-8")

            cmd_config(AppConfig(min_age_days=7), home, io.StringIO(), project=project)

            self.assertEqual(
                yarnrc.read_text(encoding="utf-8"),
                "nodeLinker: node-modules\nnpmMinimalAgeGate: 7d\n...\n",
            )

    def test_config_skips_yarn_when_no_project_target_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            out = io.StringIO()

            cmd_config(AppConfig(), home, out, verbosity=1)

            self.assertFalse((home / ".yarnrc.yml").exists())
            self.assertIn("[skip] npmMinimalAgeGate (no project target supplied)", out.getvalue())

    def test_config_skips_yarn_when_disabled_even_with_project_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()
            out = io.StringIO()

            cmd_config(AppConfig(enable_yarn=False), home, out, verbosity=1, project=project)

            self.assertFalse((project / ".yarnrc.yml").exists())
            self.assertIn("[skip] npmMinimalAgeGate (tool disabled)", out.getvalue())

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

    def test_config_writes_pnpm_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("minimumReleaseAge: 10080", content)
            self.assertIn("minimumReleaseAgeStrict: true", content)
            self.assertIn("minimumReleaseAgeIgnoreMissingTime: false", content)
            self.assertIn("blockExoticSubdeps: true", content)

    def test_config_writes_pnpm_minimum_release_age_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertIn("minimumReleaseAgeStrict: true", content)

    def test_config_writes_pnpm_fail_closed_ignore_missing_time_false_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertIn("minimumReleaseAgeIgnoreMissingTime: false", content)

    def test_config_writes_pnpm_fail_open_ignore_missing_time_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(fail_closed_on_missing_metadata=False), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertIn("minimumReleaseAgeIgnoreMissingTime: true", content)

    def test_config_writes_pnpm_block_exotic_subdeps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertIn("blockExoticSubdeps: true", content)

    def test_config_updates_top_level_pnpm_key_without_touching_nested_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            pnpm_config = home / ".config" / "pnpm" / "config.yaml"
            pnpm_config.parent.mkdir(parents=True, exist_ok=True)
            pnpm_config.write_text(
                "\n".join([
                    "registries:",
                    '  "//registry.npmjs.org/":',
                    "    tokenHelper: /usr/local/bin/helper",
                    "minimumReleaseAge: 1",
                ])
                + "\n",
                encoding="utf-8",
            )

            cmd_config(AppConfig(min_age_days=7), home, io.StringIO())

            content = pnpm_config.read_text(encoding="utf-8")
            self.assertIn("registries:\n", content)
            self.assertIn('  "//registry.npmjs.org/":\n', content)
            self.assertIn("    tokenHelper: /usr/local/bin/helper\n", content)
            self.assertIn("minimumReleaseAge: 10080\n", content)
            self.assertNotIn("minimumReleaseAge: 1\n", content)

    def test_config_omits_pnpm_strict_dep_builds_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertNotIn("strictDepBuilds: true", content)

    def test_config_writes_pnpm_strict_dep_builds_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(pnpm_strict_dep_builds=True), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertIn("strictDepBuilds: true", content)

    def test_config_is_idempotent_for_pnpm_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cmd_config(AppConfig(), home, io.StringIO())
            cmd_config(AppConfig(), home, io.StringIO())
            content = (home / ".config" / "pnpm" / "config.yaml").read_text()
            self.assertEqual(content.count("minimumReleaseAgeStrict"), 1)
            self.assertEqual(content.count("minimumReleaseAgeIgnoreMissingTime"), 1)

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

    def test_main_config_accepts_counted_verbose_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with patch("siberia.cli.load_config", return_value=AppConfig()):
                rc = main(["config", "-vv"], env={"HOME": tmp}, out=out)
            self.assertEqual(rc, 0)
            self.assertIn("[write] global.uploaded-prior-to = P7D", out.getvalue())

    def test_main_config_accepts_project_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / "project"
            project.mkdir()
            out = io.StringIO()

            with patch("siberia.cli.load_config", return_value=AppConfig()):
                rc = main(["config", "--project", str(project)], env={"HOME": tmp}, out=out)

            self.assertEqual(rc, 0)
            self.assertTrue((project / ".yarnrc.yml").exists())

    def test_main_config_rejects_file_project_path_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            project_file = home / "project-file"
            project_file.write_text("not a directory\n", encoding="utf-8")
            out = io.StringIO()
            err = io.StringIO()

            with patch("siberia.cli.load_config", return_value=AppConfig()):
                rc = main(["config", "--project", str(project_file)], env={"HOME": tmp}, out=out, err=err)

            self.assertEqual(rc, 1)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("siberia:", err.getvalue())
            self.assertIn("--project", err.getvalue())
            self.assertFalse((home / ".config" / "pip" / "pip.conf").exists())
            self.assertFalse((home / ".config" / "uv" / "uv.toml").exists())
            self.assertFalse((home / ".npmrc").exists())
            self.assertFalse((home / ".bunfig.toml").exists())
            self.assertFalse((home / ".config" / "pnpm" / "config.yaml").exists())

    def test_main_audit_lock_accepts_counted_verbose_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lockfile = Path(tmp) / "uv.lock"
            lockfile.write_text(
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
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli.load_config", return_value=AppConfig()):
                    with patch("siberia.cli._pypi_published_at", return_value=now):
                        rc = main(["audit-lock", "-vv", str(lockfile)], out=out, err=err, env={})

        self.assertEqual(rc, 1)
        self.assertIn("audit-lock: starting", err.getvalue())

    def test_main_audit_lock_accepts_use_ctime_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lockfile = Path(tmp) / "uv.lock"
            lockfile.write_text(
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
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli.load_config", return_value=AppConfig()):
                    with patch("siberia.cli._pypi_published_at", return_value=now):
                        rc = main(["audit-lock", "--use-ctime", str(lockfile)], out=out, err=err, env={})

        self.assertEqual(rc, 1)

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
    def test_cmd_audit_lock_reports_no_lockfiles(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = siberia.cmd_audit_lock(AppConfig(), [], False, out, err)

        self.assertEqual(rc, 0)
        self.assertIn("siberia audit-lock: no lockfiles found", err.getvalue())

    def test_cmd_audit_lock_supports_uv_lock(self) -> None:
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

    def test_cmd_audit_lock_supports_npm_shrinkwrap(self) -> None:
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

    def test_cmd_audit_lock_supports_bun_lock(self) -> None:
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

    def test_cmd_audit_lock_supports_modern_yarn_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "yarn.lock"
            lockfile.write_text(
                "\n".join([
                    "__metadata:",
                    '  version: 8',
                    '  cacheKey: 10',
                    "",
                    '"react@npm:^19.0.0":',
                    '  resolution: "react@npm:19.0.0"',
                    "",
                    '"@types/react@npm:^19.0.0":',
                    '  resolution: "@types/react@npm:19.0.1"',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_yarn_lock(lockfile, 7, now)

        self.assertEqual(
            [(item.package, item.version) for item in violations],
            [("react", "19.0.0"), ("@types/react", "19.0.1")],
        )
        self.assertEqual(mocked_lookup.call_count, 2)

    def test_cmd_audit_lock_supports_modern_yarn_lock_with_resolution_metadata_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "yarn.lock"
            lockfile.write_text(
                "\n".join([
                    "__metadata:",
                    '  version: 8',
                    '  cacheKey: 10',
                    "",
                    '"react@npm:^19.0.0":',
                    '  resolution: "react@npm:19.0.0::__archiveUrl=https%3A%2F%2Fregistry.npmjs.org%2Freact%2F-%2Freact-19.0.0.tgz"',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_yarn_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("react", "19.0.0")])
        mocked_lookup.assert_called_once_with("react", "19.0.0")

    def test_cmd_audit_lock_ignores_non_registry_yarn_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "yarn.lock"
            lockfile.write_text(
                "\n".join([
                    "__metadata:",
                    '  version: 8',
                    '  cacheKey: 10',
                    "",
                    '"left-pad@workspace:packages/left-pad":',
                    '  resolution: "left-pad@workspace:packages/left-pad"',
                    "",
                    '"app@file:../app":',
                    '  resolution: "app@file:../app"',
                    "",
                    '"react@npm:^19.0.0":',
                    '  resolution: "react@npm:19.0.0"',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli._npm_published_at", return_value=now) as mocked_lookup:
                violations = siberia._check_yarn_lock(lockfile, 7, now)

        self.assertEqual([(item.package, item.version) for item in violations], [("react", "19.0.0")])
        mocked_lookup.assert_called_once_with("react", "19.0.0")

    def test_cmd_audit_lock_supports_deno_lock_npm_entries_only(self) -> None:
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

    def test_cmd_audit_lock_supports_poetry_lock(self) -> None:
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

    def test_cmd_audit_lock_supports_pipfile_lock_default_and_develop(self) -> None:
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

    def test_cmd_audit_lock_scan_finds_new_supported_lockfiles(self) -> None:
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
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        rc = siberia.cmd_audit_lock(AppConfig(), [], True, out, err)
                    finally:
                        os.chdir(cwd)

        self.assertEqual(rc, 1)
        self.assertIn("VIOLATION:", out.getvalue())

    def test_cmd_audit_lock_reports_unsupported_yarn_lock_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "yarn.lock"
            lockfile.write_text(
                "\n".join([
                    '"react@^19.0.0":',
                    '  version "19.0.0"',
                    '  resolved "https://registry.yarnpkg.com/react/-/react-19.0.0.tgz"',
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()

            rc = siberia.cmd_audit_lock(AppConfig(), [str(lockfile)], False, out, err)

        self.assertEqual(rc, 0)
        self.assertNotIn(f"OK {lockfile}", out.getvalue())
        self.assertNotIn("all packages meet", out.getvalue())
        self.assertIn("unsupported yarn.lock format", err.getvalue())

    def test_check_yarn_lock_rejects_unsupported_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "yarn.lock"
            lockfile.write_text(
                "\n".join([
                    '"react@^19.0.0":',
                    '  version "19.0.0"',
                    '  resolved "https://registry.yarnpkg.com/react/-/react-19.0.0.tgz"',
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with self.assertRaises(ValueError) as ctx:
                siberia._check_yarn_lock(lockfile, 7, now)

        self.assertIn("unsupported yarn.lock format", str(ctx.exception))

    def test_cmd_audit_lock_scan_discovers_yarn_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "nested" / "yarn.lock").write_text(
                "\n".join([
                    "__metadata:",
                    '  version: 8',
                    '  cacheKey: 10',
                    "",
                    '"react@npm:^19.0.0":',
                    '  resolution: "react@npm:19.0.0"',
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._npm_published_at", return_value=now):
                    cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        rc = siberia.cmd_audit_lock(AppConfig(), [], True, out, err)
                    finally:
                        os.chdir(cwd)

        self.assertEqual(rc, 1)
        self.assertIn("VIOLATION:", out.getvalue())

    def test_cmd_audit_lock_scan_discovers_candidates_in_one_walk(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch(
                    "siberia.cli.os.walk",
                    return_value=[
                        (str(root), ["nested"], ["uv.lock", "notes.txt"]),
                        (str(root / "nested"), [], ["bun.lock", "package-lock.json", "random.lock"]),
                    ],
                ) as mocked_walk:
                    with patch("pathlib.Path.rglob", side_effect=AssertionError("rglob should not be used")):
                        with patch("siberia.cli._pypi_published_at", return_value=now):
                            with patch("siberia.cli._npm_published_at", return_value=None):
                                cwd = os.getcwd()
                                try:
                                    os.chdir(root)
                                    rc = siberia.cmd_audit_lock(AppConfig(), [], True, out, err)
                                finally:
                                    os.chdir(cwd)

        self.assertEqual(rc, 1)
        mocked_walk.assert_called_once()
        self.assertIn("VIOLATION:", out.getvalue())

    def test_cmd_audit_lock_reports_ok_per_file_on_non_tty(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = TtyStringIO(is_tty=False)
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now - timedelta(days=30)):
                    rc = siberia.cmd_audit_lock(AppConfig(), [str(lockfile)], False, out, err)

        self.assertEqual(rc, 0)
        self.assertIn(f"OK {lockfile}", out.getvalue())

    def test_cmd_audit_lock_reports_failure_per_file_on_non_tty(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = TtyStringIO(is_tty=False)
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    rc = siberia.cmd_audit_lock(AppConfig(), [str(lockfile)], False, out, err)

        self.assertEqual(rc, 1)
        self.assertIn(f"X {lockfile}", out.getvalue())
        self.assertIn("VIOLATION:", out.getvalue())

    def test_cmd_audit_lock_reports_unicode_status_on_tty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok_lockfile = root / "uv.lock"
            bad_lockfile = root / "Pipfile.lock"
            ok_lockfile.write_text(
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
            bad_lockfile.write_text(
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
            out = TtyStringIO(is_tty=True)
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            def fake_pypi(package: str, version: str) -> siberia.datetime:
                if package == "urllib3":
                    return now - timedelta(days=30)
                return now

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", side_effect=fake_pypi):
                    rc = siberia.cmd_audit_lock(AppConfig(), [str(ok_lockfile), str(bad_lockfile)], False, out, err)

        self.assertEqual(rc, 1)
        self.assertIn(f"\x1b[32m✓ {ok_lockfile}\x1b[0m", out.getvalue())
        self.assertIn(f"\x1b[31m✗ {bad_lockfile}\x1b[0m", out.getvalue())

    def test_cmd_audit_lock_verbose_level_one_logs_discovery_and_start(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    cwd = os.getcwd()
                    try:
                        os.chdir(root)
                        rc = siberia.cmd_audit_lock(AppConfig(), [], True, out, err, verbosity=1)
                    finally:
                        os.chdir(cwd)

        self.assertEqual(rc, 1)
        self.assertIn("scan: discovered 1 supported lockfiles", err.getvalue())
        self.assertIn(f"audit-lock: starting {lockfile.name}", err.getvalue())

    def test_cmd_audit_lock_verbose_level_two_logs_elapsed_time(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli.time.perf_counter", side_effect=[1.0, 1.25]):
                    with patch("siberia.cli._pypi_published_at", return_value=now):
                        rc = siberia.cmd_audit_lock(AppConfig(), [str(lockfile)], False, out, err, verbosity=2)

        self.assertEqual(rc, 1)
        self.assertIn("audit-lock: finished", err.getvalue())
        self.assertIn("0.25s", err.getvalue())

    def test_cmd_audit_lock_verbose_level_three_logs_package_lookups(self) -> None:
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
                ]),
                encoding="utf-8",
            )
            out = io.StringIO()
            err = io.StringIO()
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    rc = siberia.cmd_audit_lock(AppConfig(), [str(lockfile)], False, out, err, verbosity=3)

        self.assertEqual(rc, 1)
        self.assertIn("lookup: pypi urllib3@2.2.1", err.getvalue())

    def test_crates_lookup_reuses_cached_publish_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "check-cache.json"
            with patch("siberia.cli._PUBLISHED_AT_CACHE", {}):
                with patch("siberia.cli._KNOWN_OLD_VERSION_FLOORS", {}):
                    with patch("siberia.cli._CHECK_CACHE_PATH", cache_path):
                        with patch("siberia.cli._CHECK_CACHE_LOADED", False):
                            with patch(
                                "siberia.cli._http_get_json",
                                return_value={"version": {"created_at": "2026-05-20T00:00:00Z"}},
                            ) as mocked_get:
                                first = siberia._crates_published_at("serde", "1.0.219")
                                second = siberia._crates_published_at("serde", "1.0.219")

        self.assertEqual(first, second)
        self.assertEqual(mocked_get.call_count, 1)

    def test_persistent_cache_reuses_publish_metadata_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "check-cache.json"
            with patch("siberia.cli._PUBLISHED_AT_CACHE", {}):
                with patch("siberia.cli._KNOWN_OLD_VERSION_FLOORS", {}):
                    with patch("siberia.cli._CHECK_CACHE_PATH", cache_path):
                        with patch(
                            "siberia.cli._http_get_json",
                            return_value={"version": {"created_at": "2026-05-20T00:00:00Z"}},
                        ) as first_get:
                            first = siberia._crates_published_at("serde", "1.0.219")
                        with patch("siberia.cli._PUBLISHED_AT_CACHE", {}):
                            with patch("siberia.cli._KNOWN_OLD_VERSION_FLOORS", {}):
                                with patch("siberia.cli._CHECK_CACHE_LOADED", False):
                                    with patch("siberia.cli._http_get_json") as second_get:
                                        second = siberia._crates_published_at("serde", "1.0.219")

        self.assertEqual(first, second)
        self.assertEqual(first_get.call_count, 1)
        self.assertEqual(second_get.call_count, 0)

    def test_persistent_cache_reuses_known_old_floor_for_lower_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "check-cache.json"
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)
            old_enough = now - timedelta(days=30)
            with patch("siberia.cli._PUBLISHED_AT_CACHE", {}):
                with patch("siberia.cli._KNOWN_OLD_VERSION_FLOORS", {}):
                    with patch("siberia.cli._CHECK_CACHE_PATH", cache_path):
                        with patch("siberia.cli._CHECK_CACHE_LOADED", False):
                            with patch("siberia.cli._CURRENT_CACHE_TTL_SECONDS", 3600):
                                with patch("siberia.cli.datetime") as mocked_datetime:
                                    mocked_datetime.now.return_value = now
                                    mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                                    mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                                    with patch("siberia.cli._http_get_json", return_value={"urls": [{"upload_time_iso_8601": "2026-04-20T00:00:00Z"}]}) as mocked_get:
                                        higher = siberia._pypi_published_at("urllib3", "1.8.0")
                                        lower = siberia._pypi_published_at("urllib3", "1.7.0")

        self.assertEqual(higher, old_enough)
        self.assertEqual(lower, old_enough)
        self.assertEqual(mocked_get.call_count, 1)

    def test_cargo_lock_prefetches_versions_per_crate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "check-cache.json"
            lockfile = Path(tmp) / "Cargo.lock"
            lockfile.write_text(
                "\n".join([
                    "[[package]]",
                    'name = "serde"',
                    'version = "1.0.219"',
                    "",
                    "[[package]]",
                    'name = "serde_derive"',
                    'version = "1.0.219"',
                    "",
                    "[[package]]",
                    'name = "serde"',
                    'version = "1.0.218"',
                    "",
                ]),
                encoding="utf-8",
            )
            now = siberia.datetime(2026, 5, 20, tzinfo=siberia.timezone.utc)
            old_enough = now - timedelta(days=30)
            requested_urls: list[str] = []

            def fake_get(url: str) -> dict:
                requested_urls.append(url)
                if url.endswith("/crates/serde"):
                    return {
                        "versions": [
                            {"num": "1.0.219", "created_at": "2026-04-20T00:00:00Z"},
                            {"num": "1.0.218", "created_at": "2026-04-19T00:00:00Z"},
                        ]
                    }
                if url.endswith("/crates/serde_derive"):
                    return {
                        "versions": [
                            {"num": "1.0.219", "created_at": "2026-04-18T00:00:00Z"},
                        ]
                    }
                raise AssertionError(f"unexpected url: {url}")

            with patch("siberia.cli._PUBLISHED_AT_CACHE", {}) as published_cache:
                with patch("siberia.cli._KNOWN_OLD_VERSION_FLOORS", {}):
                    with patch("siberia.cli._CHECK_CACHE_PATH", cache_path):
                        with patch("siberia.cli._CHECK_CACHE_LOADED", False):
                            with patch("siberia.cli._CURRENT_CACHE_TTL_SECONDS", 3600):
                                with patch("siberia.cli._CURRENT_AGE_THRESHOLD_DAYS", 7):
                                    with patch("siberia.cli._http_get_json", side_effect=fake_get) as mocked_get:
                                        violations = siberia._check_cargo_lock(lockfile, 7, now)
                                        self.assertEqual(published_cache[("crates", "serde", "1.0.219")], old_enough)
                                        self.assertEqual(published_cache[("crates", "serde", "1.0.218")], now - timedelta(days=31))
                                        self.assertEqual(published_cache[("crates", "serde_derive", "1.0.219")], now - timedelta(days=32))

        self.assertEqual(violations, [])
        self.assertEqual(mocked_get.call_count, 2)
        self.assertEqual(
            requested_urls,
            [
                "https://crates.io/api/v1/crates/serde",
                "https://crates.io/api/v1/crates/serde_derive",
            ],
        )

    def test_cmd_audit_lock_use_ctime_skips_lookup_for_old_local_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lockfile = root / "uv.lock"
            artifact = root / ".siberia-ctime" / "urllib3-2.2.1.whl"
            artifact.parent.mkdir()
            artifact.write_text("placeholder", encoding="utf-8")
            lockfile.write_text(
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
            old_stat = unittest.mock.Mock(st_ctime=(now - timedelta(days=30)).timestamp())

            with patch("siberia.cli.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                mocked_datetime.side_effect = lambda *args, **kwargs: siberia.datetime(*args, **kwargs)
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._find_ctime_artifact", return_value=artifact):
                    with patch("pathlib.Path.stat", return_value=old_stat):
                        with patch("siberia.cli._pypi_published_at") as mocked_lookup:
                            rc = siberia.cmd_audit_lock(
                                AppConfig(),
                                [str(lockfile)],
                                False,
                                out,
                                err,
                                use_ctime=True,
                            )

        self.assertEqual(rc, 0)
        self.assertEqual(mocked_lookup.call_count, 0)

    def test_cmd_audit_lock_reports_unsupported_file_type(self) -> None:
        out = io.StringIO()
        err = io.StringIO()

        rc = siberia.cmd_audit_lock(AppConfig(), ["bun.lockb"], False, out, err)

        self.assertEqual(rc, 0)
        self.assertIn("unsupported file type", err.getvalue())

    def test_main_audit_lock_supports_explicit_new_lockfile(self) -> None:
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
                mocked_datetime.fromisoformat.side_effect = siberia.datetime.fromisoformat
                with patch("siberia.cli._pypi_published_at", return_value=now):
                    rc = main(["audit-lock", str(lockfile)], out=out, err=err, env={})

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
