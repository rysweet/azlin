# Changelog

All notable changes to azlin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-02-27

### Major Features

#### `azlin logs` - VM Log Viewer (#654)
- View cloud-init, syslog, and custom logs from any VM
- Stream logs in real-time or fetch historical entries

#### VM Health Dashboard with Four Golden Signals (#659)
- Real-time monitoring: latency, traffic, errors, saturation
- Actionable health status for each VM

#### `--os` Option for Ubuntu Version Selection (#715)
- Specify Ubuntu version when creating VMs (e.g., `--os 25.10`)
- Full support for Ubuntu 25.10

#### Separate /tmp Disk Support (#686)
- Add dedicated /tmp disks to new or existing VMs
- Configurable size and mount options

#### Compound VM:Session Naming (#607)
- Address VMs with `hostname:session_name` syntax
- Works across all commands (connect, exec, code, etc.)

#### OS Icon and Distro Column in `azlin list` (#728)
- Detects distro from Azure image reference (Ubuntu, Debian, Windows, RHEL, SUSE)
- OS name includes version (e.g., "Ubuntu 25.10", "Ubuntu 22.04 LTS")

#### Session Save/Load and Active Process Monitoring
- Save and restore session state across VM restarts
- Monitor active processes within sessions

### Performance

- Parallelize CLI tool detection: 15s to 5s startup (#641)
- Batch storage quota queries to eliminate N+1 Azure CLI calls (#649)
- Per-VM incremental cache refresh (#639)
- Fix stale cache hiding newly created VMs (#670)

### Security

- Enable NFS RootSquash to prevent privilege escalation (#624)
- Use Azure AD auth instead of storage keys (#629)
- Use append mode for SSH keys per audit requirement (#632)

### Refactoring

- Decompose vm_connector.py from 976 to 492 LOC (#642)
- Split monitoring.py into focused command modules (#635)
- Split connectivity.py into focused command modules (#636)
- Migrate NFS, Bastion, and storage modules to shared validation utilities (#637)
- Extract 48 helper functions from cli.py to cli_helpers.py (#634)
- Decompose monolithic list_command() into focused helpers (#633)

### Bug Fixes

- Fix WSL SSH config sync for `azlin code` (#731)
- Auto-remediate tmux socket dir on Ubuntu 25.10 VMs during connect (#723)
- Fix cloud-init runcmd YAML parsing failure from version logging (#725)
- Make cloud-init work on Ubuntu 25.10 for npm and ripgrep (#727)
- Always measure SSH latency when `--with-latency` is requested (#721)
- Fix `azlin list -q` not showing quota when VMs are cached (#688)
- Add missing `--mount` flag to disk add help text (#706)
- Azure CLI WSL2 detection and auto-fix (#609)
- Tag-based VM discovery for `azlin w/ps/top` (#610)
- Replace remaining `datetime.utcnow()` deprecations (#707, #703)
- Address quality audit findings (debug logging, ANSI sanitization, timeouts, dead code) (#665)
- Remove disabled SSHFS auto-mount dead code (#643)
- Remove broken test imports from shared validation migration (#645)
- Replace XXX placeholders with descriptive webhook URL examples (#640)

### Testing

- Unit tests for cli_helpers.py (#700)
- Unit tests for key_rotator.py (#698)
- Unit tests for orchestrator.py (#699)
- Unit tests for remote_exec.py and batch_executor.py (#702)
- Unit tests for tag_manager.py and service_principal_auth.py (#701)
- Resolve 6 skipped tests by implementing missing features (#711)
- Update 5 stale test skips to match current implementations (#704)
- Register missing pytest markers (#703)
- Correct mock scopes in integration tests (#697, #712)

### Infrastructure

- Add 8 GitHub Agentic Workflows for continuous improvement and maintenance
- Full system upgrade and gh CLI install in cloud-init (#719)
- Add tmux socket directory permissions for Ubuntu 25.10 (#718)
- Version logging for npm and rg during VM provisioning (#717)

## [2.2.2] - 2026-02-11

### CLI Modularization
- Decomposed cli.py into 11 modular command files
- Reduced cli.py from 10,242 to 6,863 lines (33% reduction)
- Preserved exact list command behavior (fixes #604)

### Quality Audit
- Completed comprehensive quality audit
- Created 9 issues for improvements (#595-603)
- Overall codebase score: 8.8/10

## [2.2.1] - 2026-02-10

### Documentation
- Updated README to focus on user-facing features
- Removed emojis from documentation
- Clarified feature benefits and usage examples

## [2.2.0] - 2026-02-10

### Major Features

#### `azlin restore` - Automatic Session Restoration (#583)
- Launches terminal windows for all active azlin sessions with one command
- Smart platform detection (macOS Terminal, Windows Terminal, WSL, Linux)
- Multi-tab support for Windows Terminal
- User-configurable terminal preferences via `~/.azlin/config.toml`
- 49 comprehensive tests with security hardening

#### iOS PWA for Azlin VM Management (#551)
- Progressive Web App for managing VMs from iPhone
- Start/stop VMs, view status, manage tmux sessions
- Quasi-interactive terminal via Azure Run Command API
- Works with private IP VMs (no public IPs required)
- Azure AD authentication with device code flow
- Installable on iPhone home screen
- Complete cost tracking integration

#### Bastion Tunnel Enhancements (#582, #589)
- VS Code launcher now supports Bastion tunnels for private IP VMs
- Retry logic and rate limiting for tunnel creation
- Improved reliability for VMs without public IPs

#### Intelligent Caching System (#553, #563)
- 60-minute cache TTL (up from 5 minutes)
- Background cache refresh after each `azlin list`
- Tiered caching with mutable/immutable separation
- Dramatically reduces Azure API calls and improves performance

#### Separate /home Disk Support (#515)
- Automatic 100GB managed disk for `/home` directory
- Persistent storage isolated from OS disk
- Customizable with `--home-disk-size` and `--no-home-disk` options
- Cost-effective at ~$4.80/month for default configuration

#### Enhanced List Display (#587)
- Added tmux session count column
- Renamed "Size" to "SKU" for clarity
- Rebalanced column widths for better readability

### Changed
- **BREAKING**: Decomposed monolithic cli.py (10,011 lines) into 11 modular command files
  - Reduced cli.py from 10,011 to 2,527 lines (75% reduction)
  - Created self-contained modules following Bricks & Studs architecture
  - All existing CLI commands preserved with backward compatibility
- Default Ubuntu version updated from 22.04 to 24.04 LTS (#559)
- Various timeout improvements for WSL/Windows compatibility

### Added
- New modular command structure in `src/azlin/commands/`:
  - `batch.py`: Batch operations (stop, start, sync, command)
  - `connectivity.py`: SSH connection, VS Code, sync, cp commands
  - `env.py`: Environment variable management
  - `ip_commands.py`: IP diagnostics commands
  - `keys.py`: SSH key management
  - `lifecycle.py`: VM lifecycle (start, stop, kill, destroy)
  - `nlp.py`: Natural language command execution (do command)
  - `provisioning.py`: VM creation (new, vm, create, clone)
  - `snapshots.py`: Snapshot management
  - `templates.py`: Template CRUD operations
  - `web.py`: PWA development server commands
  - `monitoring.py`: Expanded with list, session, w, top, ps, cost commands
- Shared `get_vm_session_pairs()` function for list/restore consistency
- CodeQL configuration to handle intentional lazy imports
- Automatic Claude Code installation during VM provisioning (#570)

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
