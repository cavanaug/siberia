## Overview

This design defines a local-shell-only supply-chain cooling policy for `pip`, `npm`, `pnpm`, and `npx`.

The goal is to prevent use of package versions published within the last 7 days, reducing exposure to fresh malicious releases while preserving practical daily workflows.

This design intentionally defers `go` and `cargo` because neither toolchain currently offers a useful native package-age control, and the first implementation target is a lower-friction rollout using native controls where possible.

## Scope

In scope:
- Local shell enforcement on one workstation
- `pip`, `npm`, `pnpm`, and `npx`
- Blocking direct and transitive dependencies younger than 7 days
- Automatic cooled-version selection for unpinned `npx` package execution
- A single master shim entrypoint reached through per-command symlinks
- Fail-closed behavior when required age metadata is unavailable

Out of scope for this phase:
- `go` and `cargo`
- CI enforcement
- Organization-wide registry or proxy filtering
- Automatic dependency rewriting for `npm`, `pnpm`, or `pip`

## User-Facing Behavior

The user installs one master executable, referred to below as `cooling-shim`, and places symlinks named `pip`, `npm`, `pnpm`, and `npx` earlier in `PATH`.

Each symlink invokes the same executable. `cooling-shim` detects the impersonated command from `argv[0]`, applies the appropriate policy, and then delegates to the real package manager.

Expected behavior by tool:
- `pip`: disallow candidates uploaded within the last 7 days
- `pnpm`: disallow package versions released within the last 7 days, including transitives
- `npm`: disallow dependency resolution to versions published within the last 7 days
- `npx`: when the requested package is unpinned, select the newest available version that is at least 7 days old and execute that version; if the request is pinned, validate the pinned version and fail if it is too new

## Native Capability Findings

### pip

Modern `pip` includes a native age filter:
- CLI: `--uploaded-prior-to=P7D`
- Environment: `PIP_UPLOADED_PRIOR_TO=P7D`
- Config: `uploaded-prior-to = P7D`

This is the preferred enforcement mechanism for `pip` in this design.

Limitations:
- It depends on the package index exposing upload-time metadata
- It does not provide richer policy controls such as per-package exceptions by itself
- Older `pip` versions may not support it

### pnpm

`pnpm` includes native release-age gating:
- `minimumReleaseAge = 10080`
- `minimumReleaseAgeStrict = true`

This is the preferred enforcement mechanism for `pnpm` in this design because it directly expresses a 7-day cooling window in minutes and applies to transitive dependencies.

Limitations:
- It depends on publish-time metadata being available
- It does not provide a central org-wide enforcement model on its own

### npm

`npm` provides a partial native age filter using an absolute cutoff date:
- CLI/config: `--before=<absolute-date>` or `before=<absolute-date>`

This does not natively express a rolling 7-day window, but a shim can compute `now - 7 days` and inject the corresponding absolute timestamp at runtime.

Limitations:
- The cutoff must be recomputed for each invocation
- The behavior is documented for install/resolution workflows, not as a complete package-age policy system

### npx

No documented native `npx` or `npm exec` cooling-period control was identified.

Because of this gap, `npx` requires custom shim logic in this design.

## Architecture

### Command Entry

One master executable implements all logic.

Example installation layout:
- `~/.local/bin/pip -> cooling-shim`
- `~/.local/bin/npm -> cooling-shim`
- `~/.local/bin/pnpm -> cooling-shim`
- `~/.local/bin/npx -> cooling-shim`

The master executable must:
- determine the logical command name from `argv[0]`
- load shared configuration
- locate the real underlying binary without recursing back into the shim path
- dispatch to per-tool policy code

### Internal Components

- Dispatcher: maps symlink name to tool-specific behavior
- Real binary resolver: finds the original `pip`, `npm`, `pnpm`, or `npx`
- Config loader: reads local policy configuration
- Native-injection layer: adds supported flags or environment variables for `pip`, `pnpm`, and `npm`
- `npx` version selector: resolves available versions and chooses the newest cooled version when the request is unpinned
- Metadata cache: stores package publish-time lookups to reduce repeated registry traffic
- Reporter: prints clear block reasons, including package name, selected version, publish time, and required minimum age

## Data Flow

### pip

1. User runs `pip install ...`.
2. The `pip` symlink invokes `cooling-shim`.
3. The shim identifies the command as `pip`.
4. The shim delegates to the real `pip` binary while injecting `--uploaded-prior-to=P7D` or the equivalent environment/config setting.
5. Native `pip` resolution rejects too-new files.

### pnpm

1. User runs `pnpm add ...` or `pnpm install`.
2. The `pnpm` symlink invokes `cooling-shim`.
3. The shim identifies the command as `pnpm`.
4. The shim delegates to the real `pnpm` binary while injecting `minimumReleaseAge=10080` and `minimumReleaseAgeStrict=true`.
5. Native `pnpm` resolution rejects too-new package versions, including transitive dependencies.

### npm

1. User runs `npm install ...`, `npm ci`, or similar guarded commands.
2. The `npm` symlink invokes `cooling-shim`.
3. The shim computes an absolute cutoff timestamp equal to current time minus 7 days.
4. The shim delegates to the real `npm` binary while injecting `--before=<computed-cutoff>`.
5. Native `npm` resolution is constrained to versions available on or before that cutoff.

### npx

1. User runs `npx <package>`.
2. The `npx` symlink invokes `cooling-shim`.
3. The shim parses the package specifier.
4. If the specifier is unpinned, the shim queries available versions from the npm registry.
5. The shim filters to versions published at least 7 days ago.
6. The shim selects the newest qualifying version.
7. The shim rewrites execution to the pinned cooled version and delegates to the real executor.

Pinned `npx` behavior:
1. If the user runs `npx pkg@1.2.3`, the shim checks that exact version.
2. If the version is at least 7 days old, execution proceeds unchanged.
3. If the version is younger than 7 days, execution fails.

Equivalent logic should apply to `npm exec` when it would acquire an ad hoc package rather than execute a local one.

## Command Classification

The shim should only alter commands that can trigger dependency acquisition or new resolution.

Guarded operations include:
- `pip install`
- `npm install`
- `npm ci`
- `npm update`
- `npm exec` when it would fetch a package
- `pnpm add`
- `pnpm install`
- `pnpm update`
- `npx <package>`

Non-acquiring commands such as `npm run`, `pnpm run`, or `pip list` should be passed through unchanged.

## Configuration

Use a local config file such as `~/.config/cooling/config.toml`.

Initial keys:
- `min_age_days = 7`
- `enable_pip = true`
- `enable_npm = true`
- `enable_pnpm = true`
- `enable_npx = true`
- `fail_closed_on_missing_metadata = true`
- `cache_ttl_seconds = 3600`

The first implementation should avoid adding exception lists unless required by real usage.

## Error Handling

The policy should fail closed for guarded operations when the required metadata cannot be trusted.

Cases that should hard-fail:
- registry metadata does not include publish time needed for evaluation
- network failure prevents checking `npx` package versions for an ad hoc fetch
- no version of an unpinned `npx` package is old enough
- an explicitly pinned `npx` version is too new
- the real binary cannot be resolved safely

Failure messages should include:
- command being executed
- package and version involved
- publish timestamp if known
- required minimum age
- whether the failure is due to age violation or metadata unavailability

## Security Considerations

- The shim directory must appear before system package-manager paths in `PATH`.
- The shim must resolve the real binary without accidentally re-invoking itself.
- Runtime injection should prefer explicit command-line arguments or dedicated environment variables over implicit ambient config when possible.
- `npx` rewriting must preserve user arguments after the package specifier.
- The design assumes that local users can still bypass policy deliberately if they alter `PATH` or call real binaries directly; this phase is for local hardening, not tamper-proof enforcement.

## Testing Strategy

Unit tests:
- symlink-name dispatch
- cutoff timestamp generation for `npm`
- command classification for guarded vs passthrough commands
- `npx` package spec parsing
- cooled-version selection logic
- real-binary resolution

Integration tests:
- `pip` invocation includes the expected age filter
- `pnpm` invocation includes strict minimum release age settings
- `npm` invocation includes a computed `before` cutoff near `now - 7 days`
- unpinned `npx` selects the newest eligible cooled version
- pinned `npx` blocks a version younger than 7 days
- passthrough commands remain unchanged

Fixture or stub-registry tests:
- package newer than 6 days is blocked
- package older than 8 days is allowed
- missing publish time causes fail-closed behavior
- `npx` fails when no cooled version exists

## Deferred Work

Future phases may add:
- `go` support through a wrapper or custom proxy
- `cargo` support through a wrapper or alternate registry strategy
- CI enforcement using the same policy engine
- organization-wide enforcement via internal package proxies or mirrors

## Recommended Next Step

The next planning phase should define:
- the implementation language for `cooling-shim`
- the exact method for injecting native config into each package manager
- the real-binary lookup strategy
- the `npx` registry query and version selection algorithm
- the minimal first test set proving the policy end to end
