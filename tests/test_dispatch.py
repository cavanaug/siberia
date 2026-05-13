from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cooling_shim.dispatch import build_passthrough_invocation, should_guard_command
from cooling_shim.models import CommandContext
from cooling_shim.real_bin import resolve_real_binary


class ResolveRealBinaryTests(unittest.TestCase):
    def test_resolve_real_binary_skips_shim_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shim_dir = root / "shim"
            real_dir = root / "real"
            shim_dir.mkdir()
            real_dir.mkdir()

            real_binary = real_dir / "npm"
            real_binary.write_text("#!/bin/sh\n", encoding="utf-8")
            real_binary.chmod(0o755)

            resolved = resolve_real_binary("npm", shim_dir, f"{shim_dir}:{real_dir}")

        self.assertEqual(resolved, real_binary)


class GuardedCommandTests(unittest.TestCase):
    def test_pip_install_is_guarded(self) -> None:
        context = CommandContext("pip", ("install", "requests"), "install")
        self.assertTrue(should_guard_command(context))

    def test_pip_list_is_passthrough(self) -> None:
        context = CommandContext("pip", ("list",), "list")
        self.assertFalse(should_guard_command(context))

    def test_npm_run_is_passthrough(self) -> None:
        context = CommandContext("npm", ("run", "test"), "run")
        self.assertFalse(should_guard_command(context))

    def test_npm_install_is_guarded(self) -> None:
        context = CommandContext("npm", ("install",), "install")
        self.assertTrue(should_guard_command(context))

    def test_npx_is_passthrough_until_task_4(self) -> None:
        context = CommandContext("npx", ("cowsay", "hello"), None)
        self.assertFalse(should_guard_command(context))


class PassthroughInvocationTests(unittest.TestCase):
    def test_build_passthrough_invocation_keeps_arguments_unchanged(self) -> None:
        invocation = build_passthrough_invocation(
            real_binary=Path("/usr/bin/pip"),
            context=CommandContext("pip", ("list",), "list"),
        )

        self.assertEqual(invocation.program, Path("/usr/bin/pip"))
        self.assertEqual(invocation.argv, ("/usr/bin/pip", "list"))
        self.assertEqual(invocation.env_overrides, {})
