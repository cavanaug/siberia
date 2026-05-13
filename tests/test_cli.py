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
