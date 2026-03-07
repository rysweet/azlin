# azlin (Rust)

> **Note**: This Rust implementation is the primary version of azlin. The Python version
> (`src/azlin/`) is deprecated and will be removed in a future release. All new development
> happens in Rust.

Azure VM fleet management CLI. Single binary, ~52x faster startup than the Python version.

## Install

**Requires Rust 1.85+** (`rustup update` to get the latest).

### From source (always-latest)

Builds from the latest commit on the branch. Re-run to update.

```bash
# Install from the development branch (always builds latest)
cargo install --git https://github.com/rysweet/azlin --branch rust-rewrite-scaffold --bin azlin

# Install from main (stable)
cargo install --git https://github.com/rysweet/azlin --bin azlin

# Force reinstall to pick up new commits
cargo install --git https://github.com/rysweet/azlin --branch rust-rewrite-scaffold --bin azlin --force
```

This installs both `azlin` and `azdoit` to `~/.cargo/bin/`.

### Pre-built binaries

Download from [GitHub Releases](https://github.com/rysweet/azlin/releases) (built on push to main).

Available for: Linux x86_64/aarch64, macOS x86_64/aarch64, Windows x86_64.

### Python wheel (pip / uvx)

The release workflow publishes Python wheels via maturin:

```bash
pip install azlin-rs
```

### Build from local checkout

```bash
cd rust && cargo install --path crates/azlin
```

## Quick Start

```bash
# First run -- interactive setup wizard configures subscription + resource group
azlin setup

# List your VMs
azlin list

# SSH into a VM (handles bastion routing automatically)
azlin connect my-vm

# Natural language commands (requires ANTHROPIC_API_KEY)
azlin ai "stop all idle VMs"

# Shell completions
azlin completions bash > ~/.bash_completion.d/azlin
```

## Workspace Structure

5-crate workspace, version 2.3.0:

| Crate | Description |
|-------|-------------|
| `azlin-core` | Config (TOML), error types, models, input sanitizer |
| `azlin-azure` | `az` CLI wrappers, auth, retry, rate limiting, costs |
| `azlin-ai` | Anthropic Claude API for NLP commands |
| `azlin-cli` | Clap command definitions, table formatting |
| `azlin` | Main binary (`azlin` + `azdoit`), command handlers, SSH routing |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full details.

**Key design decisions:**

- **Pure `az` CLI** for all Azure operations -- no Azure Rust SDK. The `az` CLI is stable, already authenticated, and avoids the `azure_core` version incompatibility between `azure_identity` 0.22 and `azure_mgmt_*` 0.2.
- **`AzureOps` trait** on `VmManager` for testability without live Azure calls.
- **`VmSshTarget` + `BastionRoute`** -- public IP VMs get direct SSH, private IP VMs route through `az network bastion ssh`. Permission denied triggers automatic key sync via `az vm user update`.
- **60-minute in-memory cache** for VM lists and per-region VM sizes. Bypass with `--no-cache`.
- **`handlers.rs`** and extracted helper modules keep `main.rs` manageable.

## Key Features

- **~52x faster startup** than Python version (14ms vs 730ms)
- **Single binary** -- no runtime dependencies beyond `az` CLI
- **Shell completions** for bash, zsh, fish
- **Interactive setup wizard** on first run
- **Health TUI dashboard** with ratatui
- **Output formats** -- table, JSON, CSV
- **MultiProgress bars** for fleet/batch operations
- **azdoit** -- natural language to azlin command execution (separate binary)

## Dependencies

Key Rust crates:

- `clap` v4 -- CLI parsing (derive macros)
- `comfy-table` -- terminal tables
- `indicatif` -- progress bars
- `ratatui` -- TUI dashboard
- `dialoguer` -- interactive prompts
- `reqwest` -- HTTP client (Anthropic API)
- `serde` + `serde_json` + `toml` -- serialization
- `color-eyre` -- contextual error messages
- `tokio` -- async runtime

## Testing

2,419 tests, 0 failures. 74.7% line / 90.1% function coverage.

```bash
# All tests (increased stack needed for deep az CLI parsing chains)
RUST_MIN_STACK=8388608 cargo test --workspace

# Specific crate
cargo test -p azlin-core

# With coverage
cargo llvm-cov --workspace --summary-only

# Agentic tests (requires gadugi-test)
AZLIN_BIN=./target/debug/azlin gadugi-test run -d ../tests/agentic-scenarios/
```

## CI

Rust CI runs on every push to `rust/**` paths:

- Build (release)
- Test (all workspace crates)
- Clippy (deny warnings)
