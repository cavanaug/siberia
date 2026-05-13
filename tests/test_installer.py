from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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
            self.assertEqual(master_link.readlink(), repo_root / "bin" / "cooling-shim")
            self.assertEqual((target_dir / "pip").readlink(), master_link)
            self.assertEqual((target_dir / "npm").readlink(), master_link)
            self.assertEqual((target_dir / "pnpm").readlink(), master_link)
            self.assertEqual((target_dir / "npx").readlink(), master_link)

    def test_install_shims_fails_when_master_source_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            target_dir = root / ".local" / "bin"
            repo_root.mkdir()
            (repo_root / "bin").mkdir()

            with self.assertRaises(FileNotFoundError):
                install_shims(repo_root=repo_root, target_dir=target_dir, tool_names=("pip",))

            self.assertFalse(target_dir.exists())

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

    def test_install_shims_validates_all_targets_before_writing(self) -> None:
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
            (target_dir / "npm").write_text("existing file\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                install_shims(
                    repo_root=repo_root,
                    target_dir=target_dir,
                    tool_names=("pip", "npm"),
                )

            self.assertFalse((target_dir / "cooling-shim").exists())
            self.assertFalse((target_dir / "pip").exists())
            self.assertTrue((target_dir / "npm").is_file())
