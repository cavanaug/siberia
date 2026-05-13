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
