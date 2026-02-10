# Changelog

All notable changes to azlin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-02-10

### Changed
- **BREAKING**: Decomposed monolithic cli.py (10,011 lines) into 11 modular command files
  - Reduced cli.py from 10,011 to 2,527 lines (75% reduction)
  - Created self-contained modules following Bricks & Studs architecture
  - All existing CLI commands preserved with backward compatibility

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
- Shared `get_vm_session_pairs()` function for list/restore consistency
- CodeQL configuration to handle intentional lazy imports

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
