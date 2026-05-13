from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from cooling_shim.cache import JsonCache
from cooling_shim.dispatch import build_invocation
from cooling_shim.errors import PolicyError
from cooling_shim.models import AppConfig, CommandContext
from cooling_shim.npx import parse_package_spec, rewrite_package_spec, select_cooled_version


FIXED_NOW = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


PACKUMENT = {
    "name": "create-vite",
    "time": {
        "created": "2024-01-01T00:00:00.000Z",
        "modified": "2026-05-13T11:00:00.000Z",
        "6.0.0": "2026-05-12T10:00:00.000Z",
        "5.4.1": "2026-05-06T12:01:00.000Z",
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
