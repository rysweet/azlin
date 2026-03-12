# Changelog

All notable changes to azlin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **GUI Forwarding**: Run remote Linux GUI applications locally
  - `azlin connect --x11` / `-X` for X11 forwarding (lightweight GUI apps)
  - `azlin gui [VM]` for full VNC desktop session with XFCE
  - `azlin gui --minimal` for openbox window manager only
  - `azlin gui --app "cmd"` for single-app VNC mode
  - Automatic dependency detection and installation
  - VNC on localhost only with random per-session passwords
  - Works through Azure Bastion for private VMs

## [2.6.16]

### Fixed
- Pass verbose and other CLI flags through to restore command

## [2.6.15]

### Added
- Check for updates on startup before command execution

### Fixed
- Restore tmux sessions strips session suffix, routes WSL correctly, isolates stdio

## [2.3.0-rust] - 2026-03-08

### Rust Rewrite
- Complete rewrite from Python to Rust -- 75-85x faster startup
- 2,536 tests, 53 commands, 154 subcommand variants
- Pre-built binaries for Linux, macOS, Windows
- `azlin self-update` for automatic updates
- `azlin-py` preserves access to Python CLI
- Migration bridge: existing uvx alias auto-routes to Rust binary
- Custom table renderer with guaranteed single-line truncation
- Non-TTY safe: all confirmation prompts handle piped input

## [2.3.0] - 2026-02-27

### Major Features

- **`azlin logs`** - VM log viewer with real-time streaming
- **VM Health Dashboard** with Four Golden Signals (latency, traffic, errors, saturation)
- **`--os` option** for Ubuntu version selection (e.g., `--os 25.10`)
- **Separate /tmp disk support** for new or existing VMs
- **Compound VM:Session naming** - address VMs with `hostname:session_name` syntax
- **OS icon and distro column** in `azlin list`
- **Session save/load** and active process monitoring

### Performance
- Parallelize CLI tool detection: 15s to 5s startup
- Batch storage quota queries to eliminate N+1 Azure CLI calls
- Per-VM incremental cache refresh
- Fix stale cache hiding newly created VMs

### Security
- Enable NFS RootSquash to prevent privilege escalation
- Use Azure AD auth instead of storage keys
- Use append mode for SSH keys per audit requirement

### Bug Fixes
- Fix WSL SSH config sync for `azlin code`
- Auto-remediate tmux socket dir on Ubuntu 25.10 VMs
- Fix cloud-init runcmd YAML parsing failure
- Make cloud-init work on Ubuntu 25.10 for npm and ripgrep
- Always measure SSH latency when `--with-latency` is requested
- Fix `azlin list -q` not showing quota when VMs are cached

---

For the full changelog, see the [CHANGELOG.md](https://github.com/rysweet/azlin/blob/main/CHANGELOG.md) on GitHub.
