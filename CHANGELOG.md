# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Path traversal protection in config_manager.py ([#105](https://github.com/rysweet/azlin/pull/105))
- Comprehensive quality improvements resolving 8 critical issues
- Archive analysis reports to .claude/analysis/

### Changed
- Store and expose cost calculation in vm_lifecycle_control

### Fixed
- Use ipaddress module for secure IP validation ([#103](https://github.com/rysweet/azlin/pull/103))
- Resolve merge conflict preserving public is_valid_ip method with IPv6 support

### Security
- Enhanced IP validation using ipaddress module instead of regex patterns
- Path traversal protection for configuration file operations

## [2.1.0] - 2025-10-10

### Added
- Home directory sync functionality with `azlin sync` command
- Bidirectional file transfer with `azlin cp` command
- Azure Files NFS integration for shared home directories ([#68](https://github.com/rysweet/azlin/pull/68))
- NFS auto-detection and home directory support
- Storage management CLI commands (create, list, delete, status)
- `--nfs-storage` option to `azlin new` command for persistent home directories
- Distributed `top` command for real-time VM monitoring ([#70](https://github.com/rysweet/azlin/pull/70))
- Scheduled VM snapshot functionality ([#75](https://github.com/rysweet/azlin/pull/75))
- `azlin prune` command to delete inactive VMs ([#60](https://github.com/rysweet/azlin/pull/60))
- `azlin clone` command for VM cloning with home directory copy ([#56](https://github.com/rysweet/azlin/pull/56))
- `azlin update` command for VM tool updates ([#57](https://github.com/rysweet/azlin/pull/57))
- `azlin os-update` command for VM package updates ([#55](https://github.com/rysweet/azlin/pull/55))
- `azlin help` command to CLI ([#65](https://github.com/rysweet/azlin/pull/65))
- Display azlin session name in tmux status bar ([#48](https://github.com/rysweet/azlin/pull/48))

### Changed
- Updated default Python version to 3.12+ in VM provisioning ([#54](https://github.com/rysweet/azlin/pull/54))
- Prune defaults to 1 day for daily cleanup workflows
- Block 2GB+ of dev toolchains from home sync for performance

### Fixed
- Azure CLI detection with Homebrew installations ([#90](https://github.com/rysweet/azlin/pull/90))
- NFS mount failure due to dpkg lock contention ([#84](https://github.com/rysweet/azlin/pull/84))
- Storage delete command error handling ([#83](https://github.com/rysweet/azlin/pull/83))
- Premium NFS storage creation - use FileStorage not StorageV2
- Storage command attribute access and improve code quality
- Clone command rsync remote-to-remote error ([#61](https://github.com/rysweet/azlin/pull/61))
- ConfigManager initialization in clone command ([#59](https://github.com/rysweet/azlin/pull/59))
- AttributeError in SessionManager.get_vm_session() ([#49](https://github.com/rysweet/azlin/pull/49))
- Home directory sync buffer overflow with large file sets
- Two critical bugs in clone command ([#62](https://github.com/rysweet/azlin/pull/62))

### Security
- Pre-commit hook enhancements - ALL phases complete ([#73](https://github.com/rysweet/azlin/pull/73))
- Granular Azure security for home directory sync ([#69](https://github.com/rysweet/azlin/pull/69))
- SSH config validation and error sanitization
- Security enhancements to session cleanup

### Removed
- Unnecessary files from repository ([#11](https://github.com/rysweet/azlin/pull/11))

## [2.0.0] - 2025-10-09

### Added
- Complete multi-VM management platform
- Pool provisioning with resource group management
- Pre-commit configuration for code quality
- `azlin status` command - VM status dashboard ([#3](https://github.com/rysweet/azlin/pull/3))
- `azlin stop` and `azlin start` commands for VM lifecycle management
- VM connector module for SSH connections
- Comprehensive test suite with integration tests
- Smart error-based retry for SKU availability
- uvx support for direct GitHub installation
- Connection tracking and cost monitoring
- Tag management for VM organization
- Template management for VM configurations

### Changed
- Converted to uv project with uvx support
- Documentation organization into docs/ directory structure ([#5](https://github.com/rysweet/azlin/pull/5))
- npm configured for user-local global installs ([#8](https://github.com/rysweet/azlin/pull/8))

### Fixed
- SKU availability issues and notification command typo
- Case-sensitive VM size validation
- Stop/start commands - use get-instance-view for power state

### Removed
- Slow SKU pre-flight checking in favor of smart error-based retry

## [1.0.0] - 2025-10-08

### Added
- Initial CLI implementation for Azure VM provisioning ([#1](https://github.com/rysweet/azlin/pull/1))
- One-command VM creation with `azlin new`
- Ubuntu 24.04 VM provisioning on Azure
- Automated installation of 12 essential development tools:
  - Docker
  - Azure CLI (az)
  - GitHub CLI (gh)
  - Git
  - Node.js with user-local npm
  - Python 3.12+ from deadsnakes PPA
  - Rust
  - Golang
  - .NET 10 RC
  - GitHub Copilot CLI
  - OpenAI Codex CLI
  - Claude Code CLI
- SSH key-based authentication setup
- Persistent tmux session configuration
- Optional GitHub repository cloning with `--repo` flag
- Azure authentication integration
- astral-uv (uv package manager) provisioning
- Claude Code framework and project setup
- Comprehensive security review report
- Requirements and design documentation

[Unreleased]: https://github.com/rysweet/azlin/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/rysweet/azlin/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/rysweet/azlin/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/rysweet/azlin/releases/tag/v1.0.0
