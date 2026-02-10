# Changelog

All notable changes to azlin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-02-10

### Major Features

#### 🔄 `azlin restore` - Automatic Session Restoration (#583)
- Launches terminal windows for all active azlin sessions with one command
- Smart platform detection (macOS Terminal, Windows Terminal, WSL, Linux)
- Multi-tab support for Windows Terminal
- User-configurable terminal preferences via `~/.azlin/config.toml`
- 49 comprehensive tests with security hardening

#### 📱 iOS PWA for Azlin VM Management (#551)
- Progressive Web App for managing VMs from iPhone
- Start/stop VMs, view status, manage tmux sessions
- Quasi-interactive terminal via Azure Run Command API
- Works with private IP VMs (no public IPs required)
- Azure AD authentication with device code flow
- Installable on iPhone home screen
- Complete cost tracking integration

#### 🔌 Bastion Tunnel Enhancements (#582, #589)
- VS Code launcher now supports Bastion tunnels for private IP VMs
- Retry logic and rate limiting for tunnel creation
- Improved reliability for VMs without public IPs

#### ⚡ Intelligent Caching System (#553, #563)
- 60-minute cache TTL (up from 5 minutes)
- Background cache refresh after each `azlin list`
- Tiered caching with mutable/immutable separation
- Dramatically reduces Azure API calls and improves performance

#### 💾 Separate /home Disk Support (#515)
- Automatic 100GB managed disk for `/home` directory
- Persistent storage isolated from OS disk
- Customizable with `--home-disk-size` and `--no-home-disk` options
- Cost-effective at ~$4.80/month for default configuration

#### 🎨 Enhanced List Display (#587)
- Added tmux session count column
- Renamed "Size" to "SKU" for clarity
- Rebalanced column widths for better readability

### Changed
- **BREAKING**: Decomposed monolithic cli.py (10,011 lines) into 11 modular command files
  - Reduced cli.py from 10,011 to 2,527 lines (75% reduction)
  - Created self-contained modules following Bricks & Studs architecture
  - All existing CLI commands preserved with backward compatibility
<<<<<<< Updated upstream
=======
- Default Ubuntu version updated from 22.04 to 24.04 LTS (#559)
- Various timeout improvements for WSL/Windows compatibility
>>>>>>> Stashed changes

### Added
- New modular command structure in `src/azlin/commands/`:
  - `batch.py`: Batch operations (stop, start, sync, command)
<<<<<<< Updated upstream
  - `connectivity.py`: SSH connection, VS Code, sync, cp commands
=======
  - `connectivity.py`: SSH connection, VS Code, sync, cp commands (1,615 lines)
>>>>>>> Stashed changes
  - `env.py`: Environment variable management
  - `ip_commands.py`: IP diagnostics commands
  - `keys.py`: SSH key management
  - `lifecycle.py`: VM lifecycle (start, stop, kill, destroy)
  - `nlp.py`: Natural language command execution (do command)
<<<<<<< Updated upstream
  - `provisioning.py`: VM creation (new, vm, create, clone)
  - `snapshots.py`: Snapshot management
  - `templates.py`: Template CRUD operations
  - `web.py`: PWA development server commands
- Shared `get_vm_session_pairs()` function for list/restore consistency
- CodeQL configuration to handle intentional lazy imports
=======
  - `provisioning.py`: VM creation (new, vm, create, clone) (1,234 lines)
  - `snapshots.py`: Snapshot management
  - `templates.py`: Template CRUD operations
  - `web.py`: PWA development server commands
  - `monitoring.py`: Expanded with list, session, w, top, ps, cost commands (1,736 lines)
- Shared `get_vm_session_pairs()` function for list/restore consistency
- CodeQL configuration to handle intentional lazy imports
- Automatic Claude Code installation during VM provisioning (#570)
>>>>>>> Stashed changes

### Fixed
- Security: AppleScript injection vulnerability (CWE-94) in restore.py
- Security: Permission race condition (CWE-732) in auth.py with atomic file creation
- Security: Documented SSH StrictHostKeyChecking tradeoff in cli_helpers.py
- Removed 164 lines of dead code (_doit_old_impl)
- Cleaned up `__all__` exports to not include private functions
- Fixed test mock patch locations for decomposed modules
- Session crossing prevention in azlin restore
- List/restore reliability improvements

### Testing
- 74/74 module extraction tests passing (100%)
- Verified backward compatibility for existing test patches
- UVX installation tested and working
- Real Azure integration tested with 6 VMs
- Concurrent command execution tested (3 simultaneous commands)

## [2.1.0] - 2025-10-19

### Added
- 352 comprehensive tests (vm_lifecycle, terminal_launcher, etc.)
- CI/CD pipeline with 6 security scanning tools
- API reference documentation (3,547 lines)

### Fixed
- Path traversal and IP validation security fixes
- Silent exception handling (36 locations)
- Consolidated duplicate VM listing logic

### Removed
- 1,331 lines of dead code (xpia_defense.py)

## [2.0.0] - 2025-09-15

Initial v2.0 release with config management and enhanced CLI.
