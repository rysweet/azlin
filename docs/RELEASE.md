# Release Pipeline

How azlin gets built, versioned, tagged, and distributed.

## What triggers a release

The GitHub Actions workflow `.github/workflows/rust-release.yml` runs when:

1. **A push to `main` changes any file under `rust/`** — automatic release.
2. **Manual dispatch** — click "Run workflow" in the Actions tab.

The workflow skips entirely if the triggering commit message contains `[skip ci]`
(this prevents the version-bump commit from re-triggering itself).

## What gets built

| Platform        | Target triple                  | Asset name              |
| --------------- | ------------------------------ | ----------------------- |
| Linux x86_64    | `x86_64-unknown-linux-gnu`     | `azlin-linux-x86_64`   |
| Linux aarch64   | `aarch64-unknown-linux-gnu`    | `azlin-linux-aarch64`  |
| macOS x86_64    | `x86_64-apple-darwin`          | `azlin-macos-x86_64`   |
| macOS aarch64   | `aarch64-apple-darwin`         | `azlin-macos-aarch64`  |
| Windows x86_64  | `x86_64-pc-windows-msvc`       | `azlin-windows-x86_64` |

Each platform produces a `.tar.gz` archive containing both `azlin` and `azdoit`
binaries. Python wheels (via maturin) are also built for all platforms.

## Where artifacts go

Every release creates a **GitHub Release** at
`https://github.com/rysweet/azlin/releases` with:

- Platform-specific `.tar.gz` archives (native binaries)
- Python `.whl` files (for `pip install azlin-rs`)

## Version scheme

```
<major>.<minor>.<patch>
```

- **Patch** is auto-incremented by the release workflow on every merge to main.
- **Minor** and **major** bumps are manual (edit `rust/Cargo.toml`).

### Auto-increment logic

The `version-bump` job in the release workflow:

1. Reads the current version from `rust/Cargo.toml` (e.g. `2.6.0`).
2. Queries existing GitHub Release tags for the same `major.minor` prefix.
3. Finds the highest patch number among those tags (e.g. `v2.6.3-rust.abc1234` has patch `3`).
4. Sets the new version to `major.minor.(highest_patch + 1)` (e.g. `2.6.4`).
5. Updates all version files: `rust/Cargo.toml`, `pyproject.toml`, `rust/pyproject.toml`, `src/azlin/__init__.py`.
6. Commits with `[skip ci]` to prevent re-triggering the workflow.
7. Pushes the commit. All subsequent build jobs check out this commit.

If no prior release exists for the current `major.minor`, the patch number from
`Cargo.toml` is used as-is.

## Tag format

```
v<major>.<minor>.<patch>-rust.<short-sha>
```

Examples:
- `v2.6.4-rust.abc1234`
- `v2.7.0-rust.def5678`

The `-rust` suffix distinguishes Rust releases from any legacy Python releases.
The short SHA identifies the exact commit the binaries were built from.

## How `azlin update` works

The `azlin update` command (implemented in `rust/crates/azlin/src/cmd_self_update.rs`):

1. Queries the GitHub Releases API for `rysweet/azlin`:
   - First tries **`gh api`** (authenticated, no rate limits).
   - Falls back to **`curl`** (unauthenticated, 60 req/hr limit).
2. Finds the latest release whose tag contains `-rust`.
3. Matches the platform-specific `.tar.gz` asset (e.g. `azlin-linux-x86_64.tar.gz`).
4. Downloads the archive with `curl`, extracts it with `tar`.
5. Replaces the running binary:
   - Renames current binary to `.old` (backup).
   - Copies new binary into place.
   - Sets executable permissions.
   - Removes backup and temp files.
6. Prints `Updated azlin: <old_version> → <new_version>`.

If the current version already matches the latest release, it prints
"Already at the latest version" and exits.

## How Python-to-Rust migration works

The Python package (`pip install azlin`) ships a thin bridge at
`src/azlin/rust_bridge.py` that **does not contain any CLI logic**. It only
bootstraps the Rust binary:

1. **Probe known locations** (in order):
   - `~/.azlin/bin/azlin` (managed install from GitHub Releases)
   - `~/.cargo/bin/azlin` (cargo install)
   - `/usr/local/bin/azlin` (system package)
2. **If not found, download from GitHub Releases** — same mechanism as
   `azlin update`, using the Releases API to find the latest `-rust` tagged
   release and downloading the platform-specific archive.
3. **If download fails, build from source** — runs
   `cargo install --git https://github.com/rysweet/azlin --bin azlin`.
4. **If all methods fail, exit with error** — prints clear instructions for
   manual installation. There is **no Python fallback**.
5. **exec() the Rust binary** — replaces the Python process entirely.

## How to do a manual version bump

For minor or major bumps, edit the workspace version in `rust/Cargo.toml`:

```toml
[workspace.package]
version = "2.7.0"  # ← change this
```

All crates inherit the workspace version (`version.workspace = true`), so only
the root `Cargo.toml` needs changing. The release workflow will then update the
remaining files (`pyproject.toml`, `rust/pyproject.toml`, `src/azlin/__init__.py`)
automatically during the next release — or you can update them manually for
consistency:

```bash
# Files that contain the version string:
rust/Cargo.toml          # workspace version (source of truth)
pyproject.toml           # Python package version
rust/pyproject.toml      # maturin wheel version
src/azlin/__init__.py    # __version__ string
```

After editing, commit and push to `main`. The release workflow picks up the new
base version and auto-increments from there.

## Platform support

| Platform       | Binary         | Wheel        | Tested |
| -------------- | -------------- | ------------ | ------ |
| linux-x86_64   | yes            | yes          | CI     |
| linux-aarch64  | yes (cross)    | yes (cross)  | CI     |
| macos-x86_64   | yes            | yes          | CI     |
| macos-aarch64  | yes            | yes          | CI     |
| windows-x86_64 | yes            | yes          | CI     |
