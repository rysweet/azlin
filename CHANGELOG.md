# Changelog

All notable changes to the azlin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI/CD pipeline with comprehensive testing and security scanning
- Dependabot automation for dependency management
- `--show-all-vms` / `-a` flag for cross-resource-group VM scanning ([#209](https://github.com/rysweet/azlin/pull/209))
- Regression test for config field preservation during updates ([#209](https://github.com/rysweet/azlin/pull/209))
- Helpful error messages when no resource group configured ([#209](https://github.com/rysweet/azlin/pull/209))
- Reminder message about --show-all-vms option in list output ([#209](https://github.com/rysweet/azlin/pull/209))

### Fixed
- Config corruption bug in test_auth_integration.py writing to real ~/.azlin/config.toml ([#209](https://github.com/rysweet/azlin/pull/209))
- NFS configuration being lost during config updates ([#209](https://github.com/rysweet/azlin/pull/209))
- Expensive cross-RG scanning running by default (now requires explicit flag) ([#209](https://github.com/rysweet/azlin/pull/209))

### Changed
- `azlin list` default behavior: now uses configured resource group instead of scanning all RGs ([#209](https://github.com/rysweet/azlin/pull/209))
- `--show-all-vms` flag meaning simplified: cross-RG scan instead of showing unmanaged VMs ([#209](https://github.com/rysweet/azlin/pull/209))

### Removed
- Expensive notification queries from default list path ([#209](https://github.com/rysweet/azlin/pull/209))
- VMManager.list_all_user_vms() method (unused) ([#209](https://github.com/rysweet/azlin/pull/209))
- TagManager.list_all_vms_cross_rg() method (expensive, unused) ([#209](https://github.com/rysweet/azlin/pull/209))
- 4,100 lines of unnecessary code, tests, and planning documents ([#209](https://github.com/rysweet/azlin/pull/209))

### Fixed
- Session name incorrectly used as tmux session name ([#212](https://github.com/rysweet/azlin/issues/212), [#213](https://github.com/rysweet/azlin/pull/213))
  - Default tmux session name is now "azlin" instead of VM/session name
  - Session names are still used for VM identification but not for tmux sessions
  - Use `--tmux-session` to explicitly specify a different tmux session name

## [2.1.0] - 2025-10-19

### Added
- Comprehensive unit tests for CLI components
- CLI decomposition Phase 1 - Foundation established ([#128](https://github.com/rysweet/azlin/pull/128))
- Comprehensive tests for stop and reflection hooks ([#121](https://github.com/rysweet/azlin/pull/121))
- API reference documentation (3,547 lines) ([#127](https://github.com/rysweet/azlin/pull/127))
- Unit tests for vm_lifecycle.py (38 tests, 92% coverage) ([#135](https://github.com/rysweet/azlin/pull/135))
- Unit tests for terminal_launcher.py (29 tests, 100% coverage) ([#133](https://github.com/rysweet/azlin/pull/133))
- Unit tests for vm_lifecycle_control.py (41 tests) ([#136](https://github.com/rysweet/azlin/pull/136))
- Unit tests for status_dashboard.py (39 tests, 98% coverage) ([#134](https://github.com/rysweet/azlin/pull/134))
- Unit tests for connection_tracker.py (82 tests, 94% coverage) ([#111](https://github.com/rysweet/azlin/pull/111))
- CI/CD pipeline with multi-Python testing (3.11, 3.12, 3.13)
- Security scanning with 6 tools (GitGuardian, Bandit, Safety, CodeQL, Trivy, OSSF Scorecard)
- Dependabot automation for weekly dependency updates

### Fixed
- Missing imports in test files across 8 PRs
- Orphaned test files removed
- Merge conflicts and import resolution
- Silent exception handling replaced with proper logging (36 locations) ([#118](https://github.com/rysweet/azlin/pull/118))
- Remove placeholder data from 23 stub functions in codex_transcripts_builder ([#119](https://github.com/rysweet/azlin/pull/119))
- Unused cost calculation now stored and used ([#104](https://github.com/rysweet/azlin/pull/104))
- IP validation security using ipaddress module ([#103](https://github.com/rysweet/azlin/pull/103))

### Changed
- Consolidated duplicate VM listing logic ([#126](https://github.com/rysweet/azlin/pull/126))
- Updated ARCHITECTURE.md to reflect v2.0 reality (15,000 LOC)
- Updated CHANGELOG.md with complete version history

### Security
- Path traversal protection in config_manager.py ([#105](https://github.com/rysweet/azlin/pull/105))
- IP validation using standards-based ipaddress module ([#103](https://github.com/rysweet/azlin/pull/103))

### Removed
- Unused xpia_defense.py module (1,331 lines) ([#129](https://github.com/rysweet/azlin/pull/129))

## [2.0.0] - 2025-10-18

### Added
- NFS Home Directory Support with Azure Files NFS ([#74](https://github.com/rysweet/azlin/pull/74), [#71](https://github.com/rysweet/azlin/pull/71))
- `azlin storage` commands for Azure Files NFS management (create, delete, list, status)
- `--nfs-storage` option for `azlin new` command
- Scheduled VM snapshot functionality ([#75](https://github.com/rysweet/azlin/pull/75))
- `azlin top` command for distributed real-time VM monitoring ([#70](https://github.com/rysweet/azlin/pull/70))
- `azlin prune` command to delete inactive VMs ([#60](https://github.com/rysweet/azlin/pull/60))
- `azlin clone` command for VM cloning with home directory copy ([#56](https://github.com/rysweet/azlin/pull/56))
- `azlin update` command for VM tool updates ([#57](https://github.com/rysweet/azlin/pull/57))
- `azlin os-update` command for package updates ([#55](https://github.com/rysweet/azlin/pull/55))
- `azlin help` command ([#65](https://github.com/rysweet/azlin/pull/65))
- Session naming feature with tmux integration ([#44](https://github.com/rysweet/azlin/pull/44), [#48](https://github.com/rysweet/azlin/pull/48))
- Connect to VMs by session name ([#45](https://github.com/rysweet/azlin/pull/45))
- Interactive VM selection for connect command ([#41](https://github.com/rysweet/azlin/pull/41))
- `azlin batch` command for fleet operations ([#36](https://github.com/rysweet/azlin/pull/36))
- `azlin keys` command for SSH key rotation ([#35](https://github.com/rysweet/azlin/pull/35))
- `azlin template` command for VM configuration templates ([#34](https://github.com/rysweet/azlin/pull/34))
- `azlin snapshot` command for VM backup/restore ([#33](https://github.com/rysweet/azlin/pull/33))
- `azlin env` command for environment variable management ([#32](https://github.com/rysweet/azlin/pull/32))
- `azlin tag` command for resource tagging ([#31](https://github.com/rysweet/azlin/pull/31))
- `azlin cleanup` command for orphaned resources ([#30](https://github.com/rysweet/azlin/pull/30))
- `azlin logs` command for VM log viewing ([#29](https://github.com/rysweet/azlin/pull/29))
- SSH auto-reconnect on disconnect with user prompt ([#19](https://github.com/rysweet/azlin/pull/19))
- `azlin new` command as default for VM provisioning ([#18](https://github.com/rysweet/azlin/pull/18))
- Pre-commit hook enhancements - ALL phases complete ([#73](https://github.com/rysweet/azlin/pull/73))
- Comprehensive project documentation (AI Agent Developer Guide, Command Reference, Cheat Sheet)
- `azlin alias` added to provisioned VMs ([#46](https://github.com/rysweet/azlin/pull/46))
- NFS auto-detection and home directory support
- Security enhancements to session cleanup
- Comprehensive unit tests for multiple modules

### Fixed
- SSH key provisioning and NFS mount issues
- Use cloud-init ssh_authorized_keys for reliable SSH setup
- Azure CLI detection with Homebrew installations ([#90](https://github.com/rysweet/azlin/pull/90))
- NFS mount failure due to dpkg lock contention ([#84](https://github.com/rysweet/azlin/pull/84))
- Storage delete command error handling ([#83](https://github.com/rysweet/azlin/pull/83))
- Storage command attribute access and code quality issues ([#82](https://github.com/rysweet/azlin/pull/82))
- Storage quota display - missing resource_group parameter
- Premium NFS storage creation - use FileStorage not StorageV2
- Storage delete config cleanup bug
- Type hint issue: Replace `callable | None` with `Callable[..., None] | None` ([#77](https://github.com/rysweet/azlin/pull/77))
- Granular Azure security for home directory sync ([#69](https://github.com/rysweet/azlin/pull/69))
- Session mappings cleanup on VM deletion ([#67](https://github.com/rysweet/azlin/pull/67))
- CRITICAL: Prune command deleting VMs with session names ([#63](https://github.com/rysweet/azlin/pull/63))
- Clone command ConfigManager TypeError and SSH key path ([#62](https://github.com/rysweet/azlin/pull/62))
- Clone command rsync remote-to-remote error ([#61](https://github.com/rysweet/azlin/pull/61))
- ConfigManager initialization in clone command ([#59](https://github.com/rysweet/azlin/pull/59))
- AttributeError in SessionManager.get_vm_session() ([#49](https://github.com/rysweet/azlin/pull/49))
- `azlin list` hanging due to Azure API timeout ([#43](https://github.com/rysweet/azlin/pull/43))
- Correct parameter name for VMManager.list_vms ([#42](https://github.com/rysweet/azlin/pull/42))
- Add pyyaml to dependencies ([#40](https://github.com/rysweet/azlin/pull/40))
- Home directory sync buffer overflow with large file sets
- ConfigManager.get_config() replaced with load_config()
- NFS mount manager test patches
- ConfigManager import and mocking in tests
- Duplicate command execution in post_edit_format.py
- Enable verbose rsync progress and allow Azure credentials in home sync

### Changed
- Default Python version updated to 3.12+ in VM provisioning ([#54](https://github.com/rysweet/azlin/pull/54))
- Prune defaults updated to 1 day for daily cleanup workflows
- Default behavior changed to show help message
- Clean up root directory and fix CLI syntax errors ([#39](https://github.com/rysweet/azlin/pull/39))
- Improved installation instructions with proper tooling ([#14](https://github.com/rysweet/azlin/pull/14))

### Security
- Path traversal protection added to config_manager.py ([#105](https://github.com/rysweet/azlin/pull/105))
- IP validation using ipaddress module ([#103](https://github.com/rysweet/azlin/pull/103))
- Comprehensive input validation to NFS mount manager
- Eliminated shell injection in env_manager.py
- Eliminated command injection in terminal_launcher.py
- SSH config validation and error sanitization
- Security theater removed from context_preservation_secure.py

### Performance
- Blocked 2GB+ of dev toolchains from home sync

### Removed
- Unused xpia_defense.py module (1331 lines of dead code)
- Unnecessary files from repository ([#11](https://github.com/rysweet/azlin/pull/11))

## [1.0.0] - 2025-10-14

### Added
- UVX support for zero-install usage ([#13](https://github.com/rysweet/azlin/pull/13))
- AI CLI tools installed by default ([#10](https://github.com/rysweet/azlin/pull/10))
- NPM configured for user-local global installs ([#8](https://github.com/rysweet/azlin/pull/8))
- Initial azlin CLI for Azure VM provisioning ([#2](https://github.com/rysweet/azlin/pull/2))
- `azlin status` command - VM status dashboard ([#3](https://github.com/rysweet/azlin/pull/3))
- Pool provisioning & pre-commit configuration
- Complete v1.0 implementation with core features

### Added - Initial Features
- Azure VM provisioning with cloud-init
- SSH key management and automatic connection
- VM lifecycle management (create, start, stop, delete)
- Resource group and VM listing
- Interactive terminal with tmux integration
- Configuration management
- Home directory synchronization
- Connection tracking
- Status dashboard with VM information

## [0.1.0] - 2025-10-09

### Added
- Initial project setup with Claude Code framework
- Basic project structure
- MIT License
- README with project overview

---

## Release Notes

### v2.0.0 - Major Feature Release

This release represents a significant evolution of azlin with over 90 merged PRs and hundreds of improvements:

**Major Features:**
- **NFS Storage Integration**: Full Azure Files NFS support for shared home directories across VMs
- **Session Management**: Name and manage VM sessions with tmux integration
- **Fleet Operations**: Batch commands for managing multiple VMs simultaneously
- **Enhanced Monitoring**: Distributed top command for real-time fleet monitoring
- **Automated Maintenance**: Prune inactive VMs, scheduled snapshots, and VM cloning

**Security Improvements:**
- Eliminated command injection vulnerabilities
- Added comprehensive input validation
- Implemented path traversal protection
- Secure IP address validation using standard library

**Developer Experience:**
- 20+ new commands for comprehensive VM fleet management
- Interactive VM selection
- Auto-reconnect on SSH disconnect
- Comprehensive documentation and guides
- Pre-commit hooks for code quality

**Quality:**
- Extensive unit test coverage
- Fixed critical bugs in session management
- Improved error handling and logging
- Type safety improvements

### v1.0.0 - Initial Release

First stable release of azlin providing core Azure VM provisioning and management capabilities.

[Unreleased]: https://github.com/rysweet/azlin/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/rysweet/azlin/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/rysweet/azlin/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/rysweet/azlin/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/rysweet/azlin/releases/tag/v0.1.0
