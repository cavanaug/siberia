## Overview

This design extends Siberia's existing package-manager hardening so it can enable newer native pnpm supply-chain protections while exposing the closest native controls available in npm.

The goal is to preserve Siberia's current model: prefer native package-manager controls, keep the implementation small, and avoid inventing cross-tool enforcement where the underlying tool does not support it.

## Scope

In scope:
- Keep existing age-gating support for `pip`, `uv`, `npm`, and `pnpm`
- Add pnpm support for `blockExoticSubdeps`
- Add opt-in pnpm support for `strictDepBuilds`
- Add optional npm support for `ignore-scripts`
- Extend `siberia init` env exports and `siberia config` file writes for the new settings
- Add tests for defaults, exports, config writes, and idempotent updates
- Update docs to explain package-manager capability differences

Out of scope:
- Automating `pnpm approve-builds`
- Managing pnpm `allowBuilds`, `onlyBuiltDependencies`, or `ignoredBuiltDependencies`
- Implementing custom Siberia-side script filtering or exotic-source blocking for npm, pip, or uv
- New commands or a higher-level policy abstraction layer

## User-Facing Behavior

### `siberia init`

`siberia init` should continue emitting shell exports for existing age-gating settings and add the following exports when the corresponding tool is enabled:

- `pnpm_config_block_exotic_subdeps=true`
- `pnpm_config_strict_dep_builds=true` only when explicitly enabled in Siberia config
- `npm_config_ignore_scripts=true` only when explicitly enabled in Siberia config

For npm-native settings, Siberia should treat `npm` and `npx` as a shared config surface. If either `enable_npm` or `enable_npx` is enabled, npm-native settings may be exported because the underlying npm config and environment variables affect both tools.

This keeps the shell-based setup aligned with Siberia's current behavior for the other native controls.

### `siberia config`

`siberia config` should continue writing native config files and add:

- `block-exotic-subdeps=true` to pnpm config
- `strict-dep-builds=true` to pnpm config only when explicitly enabled in Siberia config
- `ignore-scripts=true` to `.npmrc` only when explicitly enabled in Siberia config

Existing writes remain unchanged:

- `pip.conf`: `uploaded-prior-to = PnD`
- `uv.toml`: `exclude-newer = "PnD"`
- `.npmrc`: `min-release-age=n`
- pnpm config: `minimum-release-age=<minutes>`

For npm-native settings, `.npmrc` should be treated as shared by `npm` and `npx`. If either `enable_npm` or `enable_npx` is enabled, Siberia may write npm-native settings because both tools read the same config surface.

## Configuration Model

Extend `AppConfig` with three explicit controls:

- `pnpm_block_exotic_subdeps: bool = True`
- `pnpm_strict_dep_builds: bool = False`
- `npm_ignore_scripts: bool = False`

Rationale:

- pnpm hardening should default on because these settings fit Siberia's default security posture and complement the existing pnpm age gate.
- `blockExoticSubdeps` should default on because it complements the existing pnpm age gate without requiring per-project review data.
- `strictDepBuilds` should remain opt-in because it can break common installs unless the user also manages pnpm build approvals or allowlists.
- npm `ignore-scripts` should remain opt-in because it is materially more disruptive and can break legitimate installs.

These settings should be loadable from the same TOML config file and overridable through environment variables using the existing Siberia pattern.

## Capability Mapping

### pnpm

Native protections available and enabled by Siberia by default:

- `minimumReleaseAge`
- `blockExoticSubdeps`

Native protections available as opt-in controls:

- `strictDepBuilds`

Native protections intentionally not automated yet:

- `approve-builds`
- `allowBuilds`
- `onlyBuiltDependencies`
- `ignoredBuiltDependencies`

Those features create project-specific allowlists and review workflows, which do not match Siberia's current baseline-config model. `strictDepBuilds` is only safe as an opt-in control unless that broader approval workflow is also in scope.

### npm

Native protections supported by Siberia:

- age gating via `min-release-age`
- optional script blocking via `ignore-scripts`

Behavioral note:

- npm-native settings affect both `npm` and `npx`
- if `enable_npm = false` and `enable_npx = true`, the shared npm-native settings still apply to support `npx`

Limitations to document clearly:

- no pnpm-style native control to block exotic transitive dependency sources
- no native per-dependency build approval workflow comparable to pnpm's newer controls
- `ignore-scripts` is broad and may disable legitimate dependency install scripts

### pip and uv

Native protections already supported by Siberia:

- `pip`: `uploaded-prior-to`
- `uv`: `exclude-newer`

Limitations to document clearly:

- no pnpm-style exotic-subdependency blocking
- no npm-like general script toggle for dependency lifecycle scripts
- protection remains centered on release-age filtering and index behavior rather than install-script approval

## Implementation Notes

Keep the change inside the existing command surface and helpers.

Expected touch points:

- `AppConfig` fields and env override maps
- `npm_env_overrides()` and `pnpm_env_overrides()`
- `cmd_init()` export emission
- `cmd_config()` file writes
- README usage and security-capability documentation
- `tests/test_siberia.py`

No new modules are required.

## Error Handling And Compatibility

- Existing behavior should remain unchanged for users who only rely on age gating.
- The new pnpm keys should be written idempotently using the same key-value file helper already used for `.npmrc`-style config.
- pnpm's `strict-dep-builds` should only be emitted or persisted when enabled, to avoid surprising breakage.
- npm's `ignore-scripts` should only be emitted or persisted when enabled, to avoid surprising breakage.
- Siberia should not write `ignore-scripts=false`, remove an existing `ignore-scripts` entry, or otherwise override an explicit user decision in `.npmrc`; when Siberia detects an explicit conflicting `ignore-scripts` setting while the feature is disabled, it should leave the file unchanged and emit a warning.
- Siberia should not attempt to detect package-manager versions in this change; docs can note that native setting availability depends on the installed tool version.

## Testing Strategy

Add or update unit tests for:

- loading config defaults for the new fields
- loading TOML values and env overrides for the new fields
- `cmd_init()` output including pnpm hardening exports
- conditional `cmd_init()` output for opt-in pnpm `strict-dep-builds`
- conditional `cmd_init()` output for npm `ignore-scripts`
- `cmd_config()` writing pnpm hardening keys
- `cmd_config()` writing pnpm `strict-dep-builds` only when enabled
- `cmd_config()` writing npm `ignore-scripts` only when enabled
- warnings for explicit conflicting `ignore-scripts` settings that Siberia leaves unchanged
- shared npm/`npx` enablement behavior for npm-native settings
- idempotent updates for the new key-value entries

## Documentation

Update the README to:

- mention pnpm's stronger native hardening support
- describe the new pnpm protections that Siberia enables
- explain that npm has an optional `ignore-scripts` mode with trade-offs
- explain that pip and uv currently offer age-based protection but not the same class of exotic-source or build-approval controls

## Deferred Work

If future work is needed, the next logical extension would be a separate workflow for project-specific build approval in pnpm, likely centered on `pnpm approve-builds` and allowlist persistence. That should be treated as a separate feature rather than folded into Siberia's baseline global config behavior.
