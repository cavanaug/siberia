#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cooling_shim.installer import install_shims


def main() -> int:
    install_shims(
        repo_root=REPO_ROOT,
        target_dir=Path.home() / ".local" / "bin",
        tool_names=("pip", "npm", "pnpm", "npx"),
    )
    print("Installed cooling-shim symlinks into ~/.local/bin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
