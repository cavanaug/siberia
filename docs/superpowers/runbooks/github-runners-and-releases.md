# GitHub Runners And Releases

## GitHub-hosted runner setup

No machine provisioning is required. This repository uses GitHub-hosted `ubuntu-latest` runners for both CI and release jobs.

Repository settings to verify:

1. Actions are enabled for the repository.
2. Workflow permissions allow `Read and write permissions` so the release workflow can create GitHub Releases.
3. Tag pushes are allowed from the release branch.

## CI behavior

- Pushes to `master` and pull requests run unit tests.
- Successful CI also validates that the project builds a wheel and sdist.
- Build outputs are uploaded as workflow artifacts for inspection.

## Release behavior

1. Bump the version in `src/siberia/cli.py` and `pyproject.toml`.
2. Run `python -m unittest tests.test_siberia -v` locally.
3. Run `python -m build` locally.
4. Commit the version bump.
5. Create and push tag `vX.Y.Z`.
6. Wait for `.github/workflows/release.yml` to publish the wheel and sdist to GitHub Releases.
7. Copy the wheel URL or source tarball URL from the published release page for downstream consumers.

## Optional PyPI publish from the published GitHub artifact

If you later add PyPI publication, download the wheel and sdist from the GitHub Release page and publish those exact files instead of rebuilding locally or in another workflow.

## Homebrew update flow

1. Download the `vX.Y.Z` source tarball from GitHub Releases.
2. Compute its SHA256.
3. Update the Homebrew tap formula URL and SHA256.
4. Run `brew install --build-from-source ./Formula/siberia.rb` in the tap repository.
5. Push the tap update.
