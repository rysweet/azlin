# azlin (Rust)

Rust rewrite of the azlin Azure VM fleet management CLI.

## Quick Start

```bash
# Build
cargo build --release

# Run
./target/release/azlin --help

# Run tests
RUST_MIN_STACK=8388608 cargo test

# Generate shell completions
./target/release/azlin completions bash > ~/.bash_completion.d/azlin
```

## Workspace Structure

| Crate | Description | Coverage |
|-------|-------------|----------|
| `azlin-core` | Config, error types, models, sanitizer | 95%+ |
| `azlin-cli` | 50+ clap derive commands, table rendering | 90%+ |
| `azlin-azure` | Azure auth, VM manager, costs, retry, rate limiter | 80%+ |
| `azlin-ssh` | SSH config, client, connection pool | 82% |
| `azlin-ai` | Anthropic API client | 89% |
| `azlin` | Main binary + azdoit, all command handlers | 74%+ |

Overall: **80%+ line coverage** across 1,870+ tests.

## Key Features

- **~52x faster startup** than Python version (14ms vs 730ms)
- **Single binary** — no Python runtime, no pip install
- **Shell completions** for bash, zsh, fish
- **Interactive setup wizard** on first run
- **Health TUI dashboard** with ratatui
- **Output formats** — table, JSON, CSV
- **MultiProgress bars** for fleet/batch operations

## Dependencies

Key Rust crates:
- `clap` v4 — CLI parsing (derive macros)
- `comfy-table` — Rich-style tables
- `indicatif` — Progress bars
- `ratatui` — TUI dashboard
- `dialoguer` — Interactive prompts
- `azure_identity` + `azure_mgmt_*` — Azure SDK
- `russh` — Native async SSH
- `reqwest` + `serde` — HTTP + JSON
- `color-eyre` — Contextual error messages

## Testing

```bash
# All tests
RUST_MIN_STACK=8388608 cargo test

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
