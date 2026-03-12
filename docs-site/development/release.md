# Release Process

azlin uses semantic versioning and automated CI/CD for releases.

## Versioning

azlin follows [Semantic Versioning](https://semver.org/):

- **Patch** (2.6.x): Bug fixes, documentation updates
- **Minor** (2.x.0): New features, backward-compatible changes
- **Major** (x.0.0): Breaking changes

Version is maintained in both `pyproject.toml` and `rust/Cargo.toml`.

## Release Workflow

1. **Version bump**: Update version in `pyproject.toml` and `rust/Cargo.toml`
2. **Update CHANGELOG.md**: Move items from `[Unreleased]` to the new version section
3. **Create PR**: Submit version bump PR for review
4. **Merge to main**: After approval, merge triggers the release workflow
5. **CI builds binaries**: GitHub Actions builds for Linux (x86_64, aarch64), macOS (x86_64, aarch64), and Windows
6. **GitHub Release**: Binaries are uploaded to a new GitHub Release with release notes
7. **Docs deploy**: Documentation site is rebuilt and deployed to GitHub Pages

## Binary Distribution

Pre-built binaries are published for:

| Platform | Architecture | Artifact |
|----------|-------------|----------|
| Linux | x86_64 | `azlin-linux-x86_64.tar.gz` |
| Linux | aarch64 | `azlin-linux-aarch64.tar.gz` |
| macOS | x86_64 | `azlin-macos-x86_64.tar.gz` |
| macOS | aarch64 | `azlin-macos-aarch64.tar.gz` |
| Windows | x86_64 | `azlin-windows-x86_64.zip` |

Users can update via `azlin self-update` which downloads the latest binary from GitHub Releases.

## Self-Update

The `azlin self-update` command:

1. Queries the GitHub Releases API for the latest version
2. Compares with the current binary version
3. Downloads the appropriate binary for the current platform
4. Replaces the running binary

## Documentation Deployment

Documentation is deployed automatically when changes are pushed to `docs-site/` or `mkdocs.yml` on the `main` branch. The workflow:

1. Installs MkDocs Material and plugins
2. Generates command documentation from CLI help text
3. Builds the static site with `mkdocs build`
4. Deploys to GitHub Pages

## Development Builds

To build locally:

```bash
# Rust binary
cd rust && cargo build --release

# Python bridge
pip install -e .

# Documentation
pip install mkdocs-material mkdocs-minify-plugin mkdocs-git-revision-date-localized-plugin
mkdocs serve  # Local preview at http://localhost:8000
```
