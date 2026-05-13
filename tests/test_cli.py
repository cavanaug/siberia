from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cooling_shim.cli import build_context, main
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

    def test_load_config_reads_values_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "min_age_days = 14",
                        "enable_pip = false",
                        "enable_npm = true",
                        "enable_pnpm = false",
                        "enable_npx = true",
                        "fail_closed_on_missing_metadata = false",
                        "cache_ttl_seconds = 90",
                    ]
                ),
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


class MainTests(unittest.TestCase):
    def test_main_signature_does_not_expose_config_loader(self) -> None:
        self.assertNotIn("config_loader", inspect.signature(main).parameters)

    def test_main_signature_uses_explicit_runner_type(self) -> None:
        self.assertEqual(
            inspect.signature(main).parameters["runner"].annotation,
            "Callable[[Invocation], int] | None",
        )

    def test_main_builds_passthrough_invocation_for_supported_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shim_dir = root / "shim"
            real_dir = root / "real"
            shim_dir.mkdir()
            real_dir.mkdir()

            shim_binary = shim_dir / "pip"
            shim_binary.write_text("#!/bin/sh\n", encoding="utf-8")
            shim_binary.chmod(0o755)

            real_binary = real_dir / "pip"
            real_binary.write_text("#!/bin/sh\n", encoding="utf-8")
            real_binary.chmod(0o755)

            recorded: list[object] = []

            def runner(invocation: object) -> int:
                recorded.append(invocation)
                return 17

            with patch("cooling_shim.cli.load_config"):
                exit_code = main(
                    [str(shim_binary), "install", "requests"],
                    env={"PATH": f"{shim_dir}:{real_dir}"},
                    runner=runner,
                )

        self.assertEqual(exit_code, 17)
        self.assertEqual(len(recorded), 1)
        invocation = recorded[0]
        self.assertEqual(invocation.program, real_binary)
        self.assertEqual(invocation.argv, (str(real_binary), "install", "requests"))
        self.assertEqual(invocation.env_overrides, {})

    def test_main_returns_two_for_unsupported_tool(self) -> None:
        with patch("cooling_shim.cli.load_config"):
            exit_code = main(["/usr/bin/python", "-V"])

        self.assertEqual(exit_code, 2)
