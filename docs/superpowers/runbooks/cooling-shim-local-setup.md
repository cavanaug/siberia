# Cooling Shim Local Setup

## Install

Run:

```bash
python scripts/install_shims.py
```

Install targets `~/.local/bin`. Ensure that directory appears before system package manager paths in `PATH`.

Example shell setup:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Config

Create `~/.config/cooling/config.toml`:

```toml
min_age_days = 7
enable_pip = true
enable_npm = true
enable_pnpm = true
enable_npx = true
fail_closed_on_missing_metadata = true
cache_ttl_seconds = 3600
```

## Local Shell Usage

Start a shell after updating `PATH`, or reload your shell config so `pip`, `npm`, `pnpm`, and `npx` resolve to the installed symlinks in `~/.local/bin`.

## Rollback

Remove the installed symlinks:

```bash
rm -f ~/.local/bin/cooling-shim ~/.local/bin/pip ~/.local/bin/npm ~/.local/bin/pnpm ~/.local/bin/npx
```
