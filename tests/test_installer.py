from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cooling_shim.installer import install_shims


class InstallerTests(unittest.TestCase):
    def test_install_shims_creates_master_and_tool_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            target_dir = root / ".local" / "bin"
            repo_root.mkdir()
            (repo_root / "bin").mkdir()
            (repo_root / "bin" / "cooling-shim").write_text(
                "#!/usr/bin/env python3\n",
                encoding="utf-8",
            )

            install_shims(
                repo_root=repo_root,
                target_dir=target_dir,
                tool_names=("pip", "npm", "pnpm", "npx"),
            )

            master_link = target_dir / "cooling-shim"

            self.assertTrue(master_link.is_symlink())
            self.assertEqual((target_dir / "pip").resolve(), master_link.resolve())
            self.assertEqual((target_dir / "npm").resolve(), master_link.resolve())
            self.assertEqual((target_dir / "pnpm").resolve(), master_link.resolve())
            self.assertEqual((target_dir / "npx").resolve(), master_link.resolve())

    def test_install_shims_refuses_to_overwrite_non_symlink_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            target_dir = root / ".local" / "bin"
            repo_root.mkdir()
            (repo_root / "bin").mkdir()
            (repo_root / "bin" / "cooling-shim").write_text(
                "#!/usr/bin/env python3\n",
                encoding="utf-8",
            )
            target_dir.mkdir(parents=True)
            (target_dir / "pip").write_text("existing file\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install_shims(repo_root=repo_root, target_dir=target_dir, tool_names=("pip",))
