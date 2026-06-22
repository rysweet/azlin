# Performance Benchmarks

Measured on Azure VM (Standard_E32as_v5, Ubuntu 25.10).

## Startup Time

| Command | Rust (ms) | Python via uv (ms) | Speedup |
|---------|-----------|---------------------|---------|
| `--version` | 5 | 32 | 6.4x |
| `--help` | 5 | 35 | 7x |

Note: Python via `uv run` is already fast because `uv` is Rust-based.
With native `python -m azlin`, Python startup is ~700ms (140x slower).

## Binary Size

| Build | Size |
|-------|------|
| Release (stripped + LTO) | 18 MB |
| Debug | ~120 MB |

## Command Performance

| Command | Rust (s) | Notes |
|---------|----------|-------|
| `list --no-tmux` | ~3 | Azure API call dominates |
| `list` (with tmux, 5 VMs) | ~20 | Sequential bastion SSH |
| `health` (1 VM) | ~4 | Bastion SSH for metrics |
| `show` | ~2 | Single az CLI call |
| `tag add/remove` | ~3 | Single az CLI call |

## MSRV

Minimum Supported Rust Version: **1.85** (required by ratatui 0.30 dependency).
