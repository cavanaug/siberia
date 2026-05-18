# siberia

> All new packages are frozen like a cold Siberian winter, but you control the thaw rate...

**Supply-chain hardening for pip, uv, npm, pnpm, and Cargo.**

Siberia enforces a minimum-age policy on packages pulled from external repositories. Before a newly published package can enter your
environment, it must have existed in the registry for at least N days. This one constraint eliminates an entire class of attack.

---

## The problem: supply-chain attacks are accelerating

Every package manager is a trust boundary. When you run `pip install`, `npm install`, or `cargo add`, you are executing arbitrary code
published by strangers. Attackers know this, and they exploit it systematically.

The defining characteristic of modern supply-chain attacks is **speed**: a malicious package is published, developers install it within
minutes or hours, and credentials are exfiltrated before anyone notices. The entire attack surface is the window between publication and
detection.

---

## Recent attacks, by ecosystem

### npm — TanStack (May 2026)

On May 11, 2026, a threat actor known as TeamPCP chained three techniques — a GitHub Actions "Pwn Request," CI cache poisoning across a
fork/base trust boundary, and OIDC token extraction from runner memory — to publish
**84 malicious versions across 42 `@tanstack/*` packages**. The same campaign simultaneously hit `@mistralai/*`, `@uipath/*`, and others,
for a total of over 400 compromised package versions across npm and PyPI. The malware harvested credentials, cloud tokens, and SSH keys from
any environment that ran `npm install` during the exposure window.

> "The attack used a three-step chain: stage a malicious payload in a GitHub fork, inject it into published npm tarballs, then hijack the
> project's own CI/CD pipeline to publish the compromised versions with valid SLSA provenance." —
> [StepSecurity](https://www.stepsecurity.io/blog/mini-shai-hulud-is-back-a-self-spreading-supply-chain-attack-hits-the-npm-ecosystem)

Full postmortem:
[tanstack.com/blog/npm-supply-chain-compromise-postmortem](https://tanstack.com/blog/npm-supply-chain-compromise-postmortem)

---

### npm — axios (2025)

Two compromised versions of `axios` — one of the most downloaded npm packages in existence — were published and remained live for
approximately three hours before removal. During that window, Huntress alone observed **135 endpoints across all operating systems**
contacting the attacker's command-and-control infrastructure. The attack required no user interaction beyond a routine `npm install`.

> [huntress.com/blog/axios-npm-compromise](https://www.huntress.com/blog/axios-npm-compromise)

---

### PyPI — LiteLLM (2026)

LiteLLM, a widely used Python library for interfacing with LLM APIs, was compromised via a malicious PyPI release. The package collected and
exfiltrated **environment variables, SSH keys, and cloud credentials** from any system that installed the affected version. Over 40,000
downloads of the compromised release were recorded before PyPI admins quarantined the project.

> "Anyone who's running the confirmed compromised litellm versions via pip has had all environment variables, SSH keys, cloud credentials,
> and other secrets collected and sent to an attacker-controlled server." —
> [Truesec](https://www.truesec.com/hub/blog/malicious-pypi-package-litellm-supply-chain-compromise)

Coverage: [infoq.com/news/2026/03/litellm-supply-chain-attack](https://www.infoq.com/news/2026/03/litellm-supply-chain-attack/)

---

### PyPI — Ultralytics / YOLO (December 2024)

Ultralytics, the computer vision library behind YOLO with roughly **80 million downloads per month**, was compromised via a GitHub Actions
script injection attack. An attacker used the `pull_request_target` pattern to gain write access to the publishing pipeline, then pushed
malicious releases to PyPI. A second wave followed when the attacker used an unrevoked PyPI API token left over in the project's GitHub
Actions workflow.

> [blog.pypi.org/posts/2024-12-11-ultralytics-attack-analysis](https://blog.pypi.org/posts/2024-12-11-ultralytics-attack-analysis/)

---

### Cargo / crates.io — `faster_log` and `async_println` (May 2025)

Two malicious Rust crates — `faster_log` and `async_println` — were published to crates.io by a threat actor and accumulated
**8,424 downloads** before removal. Both quietly harvested private keys, wallet credentials, and developer secrets and exfiltrated them to
an attacker-controlled endpoint. The crates mimicked the naming conventions of legitimate logging and async utilities to appear routine.

> [thehackernews.com/2025/09/malicious-rust-crates-steal-solana-and.html](https://thehackernews.com/2025/09/malicious-rust-crates-steal-solana-and.html)

Advisory:
[cybersecurefox.com/en/rust-crates-io-supply-chain-attack-faster-log-async-println](https://cybersecurefox.com/en/rust-crates-io-supply-chain-attack-faster-log-async-println/)

---

### Cargo / crates.io — `evm-units` (April 2025)

A crate named `evm-units` was uploaded to crates.io by a user named `ablerust` and accumulated over **7,000 downloads** over eight months
while silently delivering OS-specific malware targeting Web3 developers. The crate impersonated legitimate Ethereum tooling and was designed
to steal cryptocurrency wallet keys.

> [thehackernews.com/2025/12/malicious-rust-crate-delivers-os.html](https://thehackernews.com/2025/12/malicious-rust-crate-delivers-os.html)

---

## Why a minimum-age policy works

Every attack above shares one property: the malicious version was **brand new**. It had to be — the attacker just published it. A policy
that refuses to install any package younger than 7 days would have blocked all of them.

Legitimate packages that matter to your project have history. The `requests` library, `tokio`, `axios` — these have been in registries for
years. A patch release that fixes a real bug will still be there next week. The cost of waiting is low. The benefit is high.

This is the same reasoning behind **default-deny** in firewalls, **quarantine periods** in medicine, and **settlement delays** in financial
systems. When you cannot vet everything that arrives, you impose a waiting period and let the community do the vetting for you. Security
researchers, registry abuse teams, and automated scanners typically catch malicious packages within hours to a few days. A 7-day window is
enough for the ecosystem to respond.

This protection is **especially critical for external package repositories** — registries on the public internet that accept submissions
from anyone with an account. PyPI, npm, crates.io, and similar registries have no pre-publication review. Any registered user can publish a
package with any name at any time. The only gatekeeping is post-hoc. A minimum-age policy at the consumer side compensates for the absence
of gatekeeping at the publisher side.

---

## What siberia does

Siberia provides three tools:

### `siberia shellenv`

Prints shell export statements that configure each tool's native hardening settings via environment variables. Add this to your shell
profile:

```sh
eval "$(siberia shellenv)"
# or with a custom age:
eval "$(siberia shellenv --age 14d)"
eval "$(siberia shellenv --age 2w)"
```

By default, `siberia shellenv` exports:

- `PIP_UPLOADED_PRIOR_TO=P7D` — blocks pip and pipx from installing packages younger than 7 days
- `UV_EXCLUDE_NEWER=P7D` — same for uv and uvx
- `npm_config_min_release_age=7` — same for npm and npx
- `pnpm_config_minimum_release_age=10080` — same for pnpm (in minutes)
- `pnpm_config_block_exotic_subdeps=true` — blocks transitive pnpm dependencies from using exotic sources like git or tarball URLs

Optional exports are included only when their matching config flags are enabled:

- `npm_config_ignore_scripts=true` — optional npm and npx hardening that blocks dependency lifecycle scripts broadly
- `pnpm_config_strict_dep_builds=true` — optional pnpm hardening that fails installs on unreviewed dependency build scripts

### `siberia config`

Writes the same policy persistently to each tool's native config file, so it applies even in environments where your shell profile is not
sourced (CI, Docker, subprocess invocations):

```sh
siberia config
siberia config --age 14d
siberia config --verbose
```

Writes to: `~/.config/pip/pip.conf`, `~/.config/uv/uv.toml`, `~/.npmrc`, `~/.config/pnpm/rc`. All writes are idempotent.

Use `-v` / `--verbose` to list the managed config fields grouped by target file, including both injected values and fields skipped because a
tool or option is disabled.

Additional hardening written by `siberia config`:

- pnpm enables `block-exotic-subdeps=true` by default
- pnpm can opt into `strict-dep-builds=true`
- npm and npx can opt into `ignore-scripts=true`

If `.npmrc` already contains an explicit `ignore-scripts` setting and Siberia is not configured to manage it, Siberia leaves that user
choice in place and prints a warning instead of overriding it.

### `siberia check`

Audits lockfiles for packages that are younger than the age threshold, fetching publish timestamps from registry APIs:

```sh
siberia check                          # checks known lockfiles in current directory
siberia check package-lock.json        # explicit file
siberia check --scan                   # recursively scan the project tree
siberia check --scan --age 30d         # stricter threshold for audit
```

Supported lockfiles:

| File | Registry |
|------|----------|
| `package-lock.json` | registry.npmjs.org |
| `pnpm-lock.yaml` | registry.npmjs.org |
| `requirements.txt` | pypi.org |
| `Cargo.lock` | crates.io |

Exits 1 if any violations are found. Suitable as a CI gate.

---

## Installation

### Persistent install with `uv`

```sh
uv tool install siberia
```

### One-shot use with `uvx`

```sh
uvx siberia check --scan
```

### Install from a published GitHub release artifact

```sh
uv tool install "https://github.com/cavanaug/siberia/releases/download/v0.1.0/siberia-0.1.0-py3-none-any.whl"
```

### Homebrew (macOS)

```sh
brew install cavanaug/tap/siberia
```

GitHub Releases are the canonical published artifacts. Other distribution channels should consume those tagged releases rather than rebuilding their own package.

### From this repo

```sh
python3 siberia shellenv
```

CI and release automation run on standard GitHub-hosted runners. No self-hosted runner setup is required for normal testing, build validation, or tagged release publication.

## Releasing

Tagging `vX.Y.Z` on `master` runs the GitHub-hosted release workflow, builds the wheel and sdist once, and publishes those files as the canonical assets on the GitHub Release page.

Downstream channels such as Homebrew and any later PyPI publish step should consume those published artifacts instead of rebuilding.

Maintainer setup and release steps live in `docs/superpowers/runbooks/github-runners-and-releases.md`, and the Homebrew formula template lives in `docs/homebrew/siberia.rb`.

---

## Configuration

Siberia reads `~/.config/siberia/config.toml` if present. This is a clean break from the old `cooling` name: the current config path and
environment variables use `siberia`/`SIBERIA_` only.

```toml
min_age_days = 7
enable_pip   = true
enable_npm   = true
enable_pnpm  = true
enable_npx   = true
enable_uv    = true
fail_closed_on_missing_metadata = true
pnpm_block_exotic_subdeps = true
pnpm_strict_dep_builds = false
npm_ignore_scripts = false
```

`enable_pip` covers both `pip` and `pipx`. `enable_uv` covers both `uv` and `uvx`. `npm` and `npx` continue to share the same native npm
config surface.

All fields can be overridden via environment variables:

```sh
SIBERIA_MIN_AGE_DAYS=14
SIBERIA_ENABLE_NPM=0
SIBERIA_FAIL_CLOSED_ON_MISSING_METADATA=false
```

The `--age` flag on any subcommand overrides both the config file and environment variables for that invocation.

## Native Capability Differences

- `pnpm` has the strongest native hardening surface in this set: release-age gating, exotic-source blocking, and opt-in strict dependency
  build blocking.
- `npm` supports release-age gating and an opt-in but blunt `ignore-scripts` mode, but not pnpm-style exotic-transitive blocking or
  per-dependency build approvals.
- `pip` and `uv` currently provide age-based controls, but not the same class of native script-approval or exotic-source restrictions.
- `npm` and `npx` share the same native npm config surface, so Siberia's npm-native settings affect both tools.

---

## The default matters

The default age is 7 days. This is intentional.

Most developers will not change it. Most CI pipelines will inherit whatever the developer set up. The protection needs to work without
anyone remembering to turn it on. That is why siberia enforces via native tool config and environment variables rather than wrapping
binaries — the policy is in place even when siberia itself is not running.

A policy that requires active opt-in on every install is not a policy. It is a suggestion.
