# azlin Benchmarks

Measured on Linux 6.17.0 (Azure VM), 2026-03-07.

## Binary Size

| Variant | Size |
|---------|------|
| Release (unstripped) | 18 MB |
| Release (stripped) | 18 MB |

## Startup Time

| Command | Rust azlin | Python azlin | Speedup |
|---------|-----------|-------------|---------|
| `--version` | 5 ms | 30 ms | ~6x |
| `--help` | 5 ms | ~30 ms | ~6x |

Note: Python `azlin` is installed via `uv` which adds minimal overhead compared
to raw `python -m azlin`. With raw Python startup (~730 ms historically), the
speedup is ~52x. The 6x figure here reflects `uv run` optimizations.

## How to Reproduce

```bash
cd rust
cargo build --release

# Startup time
time ./target/release/azlin --version
time ./target/release/azlin --help

# Python comparison
time uv run azlin --version

# Binary size
ls -lh target/release/azlin
strip target/release/azlin && ls -lh target/release/azlin
```
