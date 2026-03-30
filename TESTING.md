# Testing Guide

How to run azlin tests. For detailed specifications, see the linked docs.

## Prerequisites

- **Rust 1.85+** (edition 2021) — install via [rustup](https://rustup.rs/)
- **Azure CLI** (`az`) — for live Azure tests only
- **gadugi-agentic-test** — for YAML scenario tests only

The workspace config at `rust/.cargo/config.toml` automatically sets
`RUST_MIN_STACK=8388608` (8 MB stack), so no manual env setup is needed locally.

## Quick Start

```bash
cd rust
cargo test --all
```

This runs all unit and integration tests (excluding `#[ignore]`-gated live Azure tests).

## Test Categories

### Rust Unit Tests

67 test groups in `rust/crates/azlin/src/tests/` plus 13 handler test groups in
`rust/crates/azlin/src/handlers/tests/`. These test command parsing, output
formatting, config handling, and business logic with mock data.

```bash
cd rust
cargo test --all                       # all unit + integration tests
cargo test --lib                       # unit tests only
cargo test test_group_list             # single test group by name
```

### Rust Integration Tests

18 test files in `rust/crates/azlin/tests/` covering CLI invocation, config
loading, session management, error handling, output formats, and end-to-end
command flows.

```bash
cd rust
cargo test --test cli_integration      # single integration test file
cargo test --test config_integration
```

Key integration test files:

| File | Coverage |
|------|----------|
| `cli_integration.rs` | CLI arg parsing, help, version |
| `config_integration.rs` | Config load/save/defaults |
| `session_integration.rs` | Session persistence |
| `local_e2e.rs` | End-to-end command flows (local, no Azure) |
| `parity_integration.rs` | Python/Rust output parity |
| `azure_live_integration.rs` | Live Azure API calls (ignored) |
| `live_commands_integration.rs` | Live command execution (ignored) |

### Live Azure Tests

Tests in `azure_live_integration.rs` and `live_commands_integration.rs` are
marked `#[ignore]` and require real Azure credentials.

```bash
# Setup
az login

# Run ignored tests explicitly
cd rust
cargo test --test azure_live_integration -- --ignored
cargo test --test live_commands_integration -- --ignored
```

These tests hit real Azure APIs against hardcoded resource groups and VMs.
See [docs/REAL_AZURE_TESTING.md](docs/REAL_AZURE_TESTING.md) for manual
testing procedures.

### Agentic Scenario Tests

YAML-based tests in `tests/agentic-scenarios/` using the gadugi test runner.
These verify CLI behavior through scripted agent interactions.

```bash
# Point AZLIN_BIN at the debug or release binary
export AZLIN_BIN=./rust/target/debug/azlin

# Build first
cd rust && cargo build && cd ..

# Run scenarios
gadugi-test run -d tests/agentic-scenarios
```

Scenarios:
- `ssh-identity-key.yaml` — SSH key auto-resolution
- `new-command-parity.yaml` — `azlin new` command parity checks

See [docs/AGENTIC_INTEGRATION_TESTS.md](docs/AGENTIC_INTEGRATION_TESTS.md)
for the full agentic test case specification.

### E2E Tests

End-to-end YAML scenarios in `tests/e2e/`:

- `test_restore_multi_session.yaml` — Multi-session restore flow

These also use the gadugi runner with `AZLIN_BIN`.

### Benchmarks

Python-based performance benchmarks in `benchmarks/`. These were written for
the original Python implementation and measure Azure API and SSH operation
latency.

```bash
pip install memory-profiler line-profiler pytest-benchmark
python benchmarks/benchmark_vm_list.py
python benchmarks/benchmark_parallel_vm_list.py
```

See [benchmarks/README.md](benchmarks/README.md) for full setup and
baseline comparison workflows.

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `RUST_MIN_STACK` | 8 MB stack for large CLI enum (set automatically by `.cargo/config.toml`) | Auto |
| `AZLIN_BIN` | Path to azlin binary for agentic/E2E tests | Agentic tests |
| `AZLIN_TEST_MODE` | Enables mock data in list commands | Some unit tests |
| `ANTHROPIC_API_KEY` | Anthropic API access for `azlin do` commands | Agentic tests |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription (removed in test helpers to isolate) | Live Azure tests |
| `AZURE_TENANT_ID` | Azure tenant (removed in test helpers to isolate) | Live Azure tests |

## Linting

```bash
cd rust
cargo clippy --all -- -D warnings
```

CI treats all clippy warnings as errors.

## Test Coverage

```bash
cd rust
cargo llvm-cov --all
```

Requires `cargo-llvm-cov` (`cargo install cargo-llvm-cov`).

## CI Pipeline

The GitHub Actions workflow at `.github/workflows/rust-ci.yml` runs on every
push and PR touching `rust/**`:

1. **Build** — `cargo build --release`
2. **Test** — `cargo test --all` (with `RUST_MIN_STACK=8388608`)
3. **Lint** — `cargo clippy --all -- -D warnings`

## Detailed Documentation

- [docs/TEST_SUITE_SPECIFICATION.md](docs/TEST_SUITE_SPECIFICATION.md) — Exhaustive CLI syntax test spec (300+ tests)
- [docs/AGENTIC_INTEGRATION_TESTS.md](docs/AGENTIC_INTEGRATION_TESTS.md) — Agentic "do" mode test cases
- [docs/REAL_AZURE_TESTING.md](docs/REAL_AZURE_TESTING.md) — Manual Azure testing procedures
- [benchmarks/README.md](benchmarks/README.md) — Benchmark setup and comparison workflows
