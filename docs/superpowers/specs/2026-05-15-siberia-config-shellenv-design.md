## Overview

This design aligns the tool's public surface with the `siberia` name and keeps a single global configuration model.

The change has three parts that move together:

- rename the default global config path from `~/.config/cooling/config.toml` to `~/.config/siberia/config.toml`
- rename environment variable overrides from `COOLING_*` to `SIBERIA_*`
- rename the ephemeral shell export subcommand from `siberia init` to `siberia shellenv`

The tool-family model should also be simplified so `pipx` is covered by the pip family and `uvx` is covered by the uv family. Siberia should not expose separate config toggles for those aliases when the underlying native controls are shared.

This is a clean break. Siberia should not continue reading legacy `cooling` names.

## Scope

In scope:

- rename the default config path to `~/.config/siberia/config.toml`
- rename all documented and implemented env overrides from `COOLING_*` to `SIBERIA_*`
- replace the `init` subcommand with `shellenv`
- remove `enable_pipx` from `AppConfig`, config loading, docs, and tests
- document that `enable_pip` governs both `pip` and `pipx`
- document that `enable_uv` governs both `uv` and `uvx`
- keep `config` as the persistent native-config writer
- update README usage, examples, and tests to match the new names

Out of scope:

- compatibility aliases for `siberia init`
- compatibility aliases for `~/.config/cooling/config.toml`
- compatibility aliases for `COOLING_*` environment variables
- adding a project-local config file
- adding separate `enable_uvx` support
- retaining separate `enable_pipx` support
- changing the semantics of `check`

## User-Facing Behavior

### `siberia shellenv`

`siberia shellenv` replaces `siberia init` as the command that prints shell exports for ephemeral activation:

```sh
eval "$(siberia shellenv)"
eval "$(siberia shellenv --age 14d)"
```

The command should keep the current export format and `--age` override behavior. Only the subcommand name changes.

Exports should continue to be emitted by package-manager family:

- pip family: emit `PIP_UPLOADED_PRIOR_TO=P7D` when `enable_pip` is enabled; this is documented as covering both `pip` and `pipx`
- uv family: emit `UV_EXCLUDE_NEWER=P7D` when `enable_uv` is enabled; this is documented as covering both `uv` and `uvx`
- npm family: keep shared npm-native exports for `npm` and `npx`
- pnpm: keep existing pnpm exports

There should be no separate `pipx` or `uvx` export branch in the CLI.

### `siberia config`

`siberia config` remains the persistent writer for native package-manager config files.

Written files remain:

- `~/.config/pip/pip.conf`
- `~/.config/uv/uv.toml`
- `~/.npmrc`
- `~/.config/pnpm/rc`

Behavioral mapping should be documented clearly:

- `pip.conf` is the persistent pip-family policy surface used for both `pip` and `pipx`
- `uv.toml` is the persistent uv-family policy surface used for both `uv` and `uvx`
- `.npmrc` remains the shared npm-native surface for `npm` and `npx`

No new `pipx`-specific or `uvx`-specific config files should be introduced.

### Global Config File

Siberia should read one global TOML file at:

```text
~/.config/siberia/config.toml
```

The sample config should drop `enable_pipx` and keep the remaining fields under the `siberia` namespace:

```toml
min_age_days = 7
enable_pip = true
enable_npm = true
enable_pnpm = true
enable_npx = true
enable_uv = true
fail_closed_on_missing_metadata = true
pnpm_block_exotic_subdeps = true
pnpm_strict_dep_builds = false
npm_ignore_scripts = false
```

### Environment Variable Overrides

All overrides should use the `SIBERIA_*` prefix.

Examples:

- `SIBERIA_MIN_AGE_DAYS=14`
- `SIBERIA_ENABLE_NPM=0`
- `SIBERIA_ENABLE_PIP=0` disables both `pip` and `pipx`
- `SIBERIA_ENABLE_UV=0` disables both `uv` and `uvx`

Legacy `COOLING_*` names are not read.

## Configuration Model

`AppConfig` should represent package-manager families, not every command alias.

Expected fields after the change:

- `min_age_days: int = 7`
- `enable_pip: bool = True`
- `enable_npm: bool = True`
- `enable_pnpm: bool = True`
- `enable_npx: bool = True`
- `enable_uv: bool = True`
- `fail_closed_on_missing_metadata: bool = True`
- `cache_ttl_seconds: int = 3600`
- `pnpm_block_exotic_subdeps: bool = True`
- `pnpm_strict_dep_builds: bool = False`
- `npm_ignore_scripts: bool = False`

Changes from the current model:

- remove `enable_pipx`
- do not add `enable_uvx`
- rename env-override maps to `SIBERIA_*`

Rationale:

- `pipx` should inherit pip-family policy because Siberia only manages pip-native controls for that family
- `uvx` should inherit uv-family policy because Siberia only manages uv-native controls for that family
- this keeps the config surface smaller and avoids switches that imply a level of isolation the underlying tools do not expose through Siberia's current native-config model

## Command-Family Mapping

The user-facing docs and code comments should describe four policy families:

- pip family: `pip`, `pipx`
- uv family: `uv`, `uvx`
- npm family: `npm`, `npx`
- pnpm: `pnpm`

This is a documentation and configuration-model clarification. It does not require new execution paths.

## Implementation Notes

Keep the change inside the existing single-file CLI and existing tests unless a focused test helper is needed.

Expected touch points:

- `DEFAULT_CONFIG_PATH`
- `AppConfig`
- `_BOOL_ENV_VARS` and `_INT_ENV_VARS`
- `load_config()`
- `cmd_init()` rename to `cmd_shellenv()` or equivalent
- `main()` argparse subparser names and dispatch
- README command examples and config documentation
- `tests/test_siberia.py`

No new modules are required.

## Error Handling And Compatibility

- This is a clean break rename. Siberia should not read `~/.config/cooling/config.toml`.
- Siberia should not accept `COOLING_*` environment variables.
- Siberia should not keep `init` as a hidden or documented alias.
- Once users move to the new names, behavior should remain otherwise unchanged.
- `--age` should continue overriding file and environment configuration for `shellenv`, `config`, and `check`.
- `config` should continue writing idempotent native config updates.
- Siberia should not attempt to detect whether `pipx` or `uvx` is installed before writing or exporting family-level settings.

Because the rename is intentionally breaking, the README should make the required migration explicit wherever the config path or env vars are introduced.

## Testing Strategy

Add or update unit tests for:

- config loading with the reduced `AppConfig` shape and no `enable_pipx`
- `SIBERIA_*` env override handling for bool and int fields
- ignoring legacy `COOLING_*` env vars
- `shellenv` output for pip-family exports
- `shellenv` output for uv-family exports
- `shellenv` output still covering npm and pnpm behavior
- `main()` dispatch for `shellenv`
- removal of `init` from command-level tests
- `config` writing the same native files as before
- `enable_pip=False` suppressing pip-family writes and exports
- `enable_uv=False` suppressing uv-family writes and exports

The goal is to prove that the rename changes names and config shape without changing the native policy behavior for users who adopt the new surface.

## Documentation

Update the README to:

- replace `siberia init` examples with `siberia shellenv`
- rename the default config path to `~/.config/siberia/config.toml`
- rename override examples from `COOLING_*` to `SIBERIA_*`
- remove `enable_pipx` from sample config
- explain that `enable_pip` covers both `pip` and `pipx`
- explain that `enable_uv` covers both `uv` and `uvx`
- keep explaining that npm-native settings affect both `npm` and `npx`
- call out the clean-break migration requirement for users on older `cooling` names

## Deferred Work

If a future need appears for compatibility aliases or per-command toggles, that should be treated as a separate feature. This change should stay focused on making the current model coherent under the `siberia` name rather than reintroducing extra compatibility or policy layers.
