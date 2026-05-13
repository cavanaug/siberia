from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import unittest

from cooling_shim.cli import main
from cooling_shim.models import AppConfig, Invocation


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


class MainTests(unittest.TestCase):
    def test_main_builds_guarded_pip_invocation(self) -> None:
        recorded: list[Invocation] = []
        loaded_packages: list[str] = []

        def runner(invocation: Invocation) -> int:
            recorded.append(invocation)
            return 17

        def load_packument(package_name: str) -> dict[str, object]:
            loaded_packages.append(package_name)
            return {}

        exit_code = main(
            ["/shim/pip", "install", "requests"],
            env={"PATH": "/shim:/real"},
            config=AppConfig(),
            clock=lambda: FIXED_NOW,
            binary_resolver=lambda tool_name, shim_dir, path_value: Path("/real/pip"),
            packument_loader=load_packument,
            runner=runner,
        )

        self.assertEqual(exit_code, 17)
        self.assertEqual(loaded_packages, [])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].program, Path("/real/pip"))
        self.assertEqual(recorded[0].argv, ("/real/pip", "install", "requests"))
        self.assertEqual(recorded[0].env_overrides["PIP_UPLOADED_PRIOR_TO"], "P7D")

    def test_main_returns_one_and_reports_policy_error(self) -> None:
        stderr = StringIO()

        exit_code = main(
            ["/shim/npx", "create-vite@latest", "demo"],
            env={"PATH": "/shim:/real"},
            config=AppConfig(),
            clock=lambda: FIXED_NOW,
            binary_resolver=lambda tool_name, shim_dir, path_value: Path("/real/npx"),
            packument_loader=lambda package_name: {
                "name": package_name,
                "time": {
                    "created": "2024-01-01T00:00:00.000Z",
                    "modified": "2026-05-13T11:00:00.000Z",
                },
            },
            runner=lambda invocation: 0,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            stderr.getvalue(),
            "cooling-shim: Unsupported package spec: create-vite@latest\n",
        )
