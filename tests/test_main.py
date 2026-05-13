from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_main_reuses_a_single_now_for_default_npx_loading(self) -> None:
        observed_packument_now: list[datetime] = []
        observed_invocation_now: list[datetime] = []

        clock_values = iter(
            [
                datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 13, 12, 0, 1, tzinfo=timezone.utc),
            ]
        )

        packument = {
            "name": "create-vite",
            "time": {
                "created": "2024-01-01T00:00:00.000Z",
                "modified": "2026-05-13T11:00:00.000Z",
                "6.0.0": "2026-05-12T10:00:00.000Z",
                "5.4.0": "2026-05-01T12:00:00.000Z",
            },
        }

        with patch(
            "cooling_shim.cli.npm_registry.load_packument",
            side_effect=lambda package_name, now_utc, ttl_seconds: observed_packument_now.append(now_utc)
            or packument,
        ), patch(
            "cooling_shim.cli.build_invocation",
            side_effect=lambda context, config, real_binary, now_utc, load_packument: observed_invocation_now.append(now_utc)
            or load_packument("create-vite")
            or Invocation(real_binary, (str(real_binary), "create-vite@5.4.0", "demo"), {}),
        ):
            exit_code = main(
                ["/shim/npx", "create-vite", "demo"],
                env={"PATH": "/shim:/real"},
                config=AppConfig(),
                clock=lambda: next(clock_values),
                binary_resolver=lambda tool_name, shim_dir, path_value: Path("/real/npx"),
                runner=lambda invocation: 0,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(observed_packument_now, [FIXED_NOW])
        self.assertEqual(observed_invocation_now, [FIXED_NOW])

    def test_main_returns_one_and_reports_policy_error(self) -> None:
        stderr = StringIO()

        exit_code = main(
            ["/shim/npx", "create-vite", "demo"],
            env={"PATH": "/shim:/real"},
            config=AppConfig(),
            clock=lambda: FIXED_NOW,
            binary_resolver=lambda tool_name, shim_dir, path_value: Path("/real/npx"),
            packument_loader=lambda package_name: {
                "name": package_name,
                "time": {
                    "created": "2024-01-01T00:00:00.000Z",
                    "modified": "2026-05-13T11:00:00.000Z",
                    "6.0.0": "2026-05-12T10:00:00.000Z",
                },
            },
            runner=lambda invocation: 0,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            stderr.getvalue(),
            "cooling-shim: No cooled version is available for create-vite\n",
        )
