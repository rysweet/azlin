# Azlin Project Structure Reconnaissance Report

## Executive Summary

**Project:** azlin v2.0.0 - Azure VM Fleet Management CLI
**Scope:** Complete structure mapping of 36.2K lines of code (21.6K source + 15.6K tests)
**Date:** October 18, 2025

The azlin project implements a comprehensive Azure VM provisioning and management CLI using a **brick architecture pattern** with 30 self-contained modules organized into 4 functional tiers.

---

## Project Metadata

| Metric | Value |
|--------|-------|
| **Version** | 2.0.0 |
| **Python Target** | >=3.11 |
| **Total Source LOC** | 21,610 |
| **Total Test LOC** | 15,550 |
| **Total Classes** | 83 |
| **Total Functions** | 69 |
| **Test Files** | 42 |
| **CLI Commands** | 40+ |
| **Entry Point** | `azlin.cli:main` |

---

## Directory Structure

```
azlin/
├── src/azlin/                    # Main source code (21.6K LOC)
│   ├── __init__.py               # v2.0.0
│   ├── __main__.py               # Entry point
│   ├── cli.py                    # 5409 LOC - Main CLI (40+ commands)
│   ├── azure_auth.py             # Azure auth delegation
│   ├── batch_executor.py         # 500 LOC - Batch operations
│   ├── config_manager.py         # TOML config (~/.azlin/config.toml)
│   ├── distributed_top.py        # 547 LOC - Live metrics dashboard
│   ├── env_manager.py            # 411 LOC - Environment variables
│   ├── key_rotator.py            # SSH key rotation
│   ├── log_viewer.py             # 483 LOC - Remote log viewing
│   ├── remote_exec.py            # 504 LOC - Remote SSH execution
│   ├── resource_cleanup.py       # 458 LOC - Resource cleanup
│   ├── vm_lifecycle.py           # 497 LOC - VM deletion
│   ├── vm_lifecycle_control.py   # 551 LOC - Power state control
│   ├── vm_manager.py             # 475 LOC - VM listing/querying
│   ├── vm_provisioning.py        # 868 LOC - VM creation
│   ├── vm_updater.py             # 433 LOC - OS updates
│   ├── [12 more utility modules]
│   │
│   ├── modules/                  # Feature modules (16 modules)
│   │   ├── file_transfer/        # Secure SCP transfer (submodule)
│   │   ├── github_setup.py       # GitHub auth + cloning
│   │   ├── home_sync.py          # 708 LOC - Rsync home sync
│   │   ├── nfs_mount_manager.py  # 429 LOC - NFS mount ops
│   │   ├── notifications.py      # imessR notifications
│   │   ├── npm_config.py         # User-local npm config
│   │   ├── prerequisites.py      # Tool validation
│   │   ├── progress.py           # Rich progress display
│   │   ├── snapshot_manager.py   # 688 LOC - VM snapshots
│   │   ├── ssh_connector.py      # 451 LOC - SSH + tmux
│   │   ├── ssh_keys.py           # SSH key generation
│   │   ├── ssh_reconnect.py      # SSH reconnect handling
│   │   ├── storage_manager.py    # 594 LOC - Azure Files NFS
│   │   └── [3 more modules]
│   │
│   └── commands/                 # CLI command modules
│       ├── __init__.py
│       └── storage.py            # 515 LOC - Storage CLI
│
├── tests/                        # Test suite (15.6K LOC, 106+ tests)
│   ├── unit/                     # 60% - Fast unit tests
│   ├── integration/              # 30% - Multi-module workflows
│   ├── e2e/                      # 10% - Real Azure VMs
│   ├── fixtures/                 # Test data
│   ├── mocks/                    # Mock objects
│   ├── conftest.py               # Global pytest config
│   └── utils.py                  # Test utilities
│
└── docs/                         # Architecture documentation
    ├── ARCHITECTURE.md           # Detailed architecture
    ├── ARCHITECTURE_SUMMARY.md   # Quick reference
    ├── [8 more docs]
```

---

## Core Module Organization

### Tier 1: CLI Layer
**File:** `cli.py` (5,409 LOC)
**Purpose:** Command dispatching and orchestration

**Command Groups (40+ total):**
- VM Provisioning: `new`, `create`, `vm`
- VM Listing: `list`, `w`, `ps`, `status`
- VM Control: `start`, `stop`, `kill`, `destroy`, `killall`
- VM Monitoring: `top`, `os_update`, `update`, `prune`, `cost`
- Connection: `session`, `connect`, `ssh_reconnect`
- File Operations: `cp`, `sync`, `clone`
- Batch Operations: `batch_*`, `command`
- SSH Keys: `keys_*` (rotate, list, export, backup)
- VM Templates: `template_*` (create, list, delete, export, import)
- VM Snapshots: `snapshot_*` (enable, disable, sync, status, create, list, restore, delete)
- Environment: `env_*` (set, list, delete, export, import, clear)
- Storage: `storage_*` (create, list, status, delete, mount, unmount)

### Tier 2: Orchestration & Execution
**Core Modules:**
- `batch_executor.py` (500 LOC) - Parallel VM operations
- `remote_exec.py` (504 LOC) - SSH command execution
- `vm_manager.py` (475 LOC) - VM discovery & status
- `distributed_top.py` (547 LOC) - Live metrics dashboard

### Tier 3: Infrastructure & Provisioning
**Core Modules:**
- `azure_auth.py` - Azure CLI authentication
- `vm_provisioning.py` (868 LOC) - VM creation with cloud-init
- `ssh_connector.py` (451 LOC) - SSH + tmux connections
- `config_manager.py` - TOML persistence
- `vm_lifecycle.py` (497 LOC) - VM deletion & cleanup
- `vm_lifecycle_control.py` (551 LOC) - Power state control

### Tier 4: Features & Utilities
**Feature Modules (16 total):**

| Module | LOC | Purpose |
|--------|-----|---------|
| `home_sync.py` | 708 | Rsync-based home directory sync |
| `snapshot_manager.py` | 688 | VM snapshot management |
| `storage_manager.py` | 594 | Azure Files NFS storage |
| `env_manager.py` | 411 | VM environment variables |
| `nfs_mount_manager.py` | 429 | NFS mount operations |
| `vm_updater.py` | 433 | OS updates |
| `log_viewer.py` | 483 | Remote log viewing |
| `key_rotator.py` | 502 | SSH key rotation |
| `ssh_keys.py` | - | SSH key generation (Ed25519) |
| `prerequisites.py` | - | Tool validation (az, gh, git, ssh, tmux) |
| `progress.py` | - | Rich-based progress display |
| `notifications.py` | - | imessR notifications |
| `github_setup.py` | - | GitHub auth + cloning |
| `npm_config.py` | - | User-local npm configuration |
| `file_transfer/` | submodule | Secure SCP file transfer |
| `tag_manager.py` | - | Azure resource tagging |

---

## Module Inventory

### Infrastructure Modules (Foundation)

**azure_auth.py**
- Responsibility: Azure CLI authentication delegation
- Classes: `AzureAuthenticator`, `AzureCredentials`
- Security: No credential storage - delegates to az CLI
- Entry: User runs `az login` interactively

**config_manager.py**
- Responsibility: Persistent configuration storage
- Classes: `ConfigManager`, `AzlinConfig`
- Storage: `~/.azlin/config.toml` (permissions: 0600)
- Stores: default_resource_group, default_region, default_vm_size, session_names, vm_storage

**vm_provisioning.py** (868 LOC)
- Responsibility: Azure VM creation with cloud-init
- Classes: `VMProvisioner`, `VMConfig`, `VMDetails`, `PoolProvisioningResult`
- Features: Pool provisioning, partial success handling, cloud-init templating
- Installs: 12 development tools (Docker, Azure CLI, GitHub CLI, Git, Node.js, Python, Rust, Go, .NET, etc.)

### VM Management Modules

**vm_manager.py** (475 LOC)
- Responsibility: VM listing, querying, and status
- Classes: `VMManager`, `VMInfo`
- Operations: `list_vms()`, `get_vm_details()`, `filter_by_status()`

**vm_lifecycle.py** (497 LOC)
- Responsibility: VM deletion and resource cleanup
- Classes: `VMLifecycleManager`, `DeletionResult`, `DeletionSummary`
- Features: Batch deletion, resource tracking, cleanup verification

**vm_lifecycle_control.py** (551 LOC)
- Responsibility: VM power state management
- Classes: `VMLifecycleController`
- Operations: `start()`, `stop()`, `deallocate()`

**resource_cleanup.py** (458 LOC)
- Responsibility: Azure resource cleanup after VM deletion
- Cleans: NICs, disks, public IPs, vNets

### Connection & Execution Modules

**ssh_connector.py** (451 LOC)
- Responsibility: SSH connections with tmux session management
- Classes: `SSHConnector`, `SSHConfig`
- Features: Tmux integration, automatic reconnection, port forwarding

**remote_exec.py** (504 LOC)
- Responsibility: Remote command execution via SSH
- Classes: `RemoteExecutor`, `RemoteResult`
- Features: Parallel execution, timeout enforcement, command sanitization

**batch_executor.py** (500 LOC)
- Responsibility: Parallel batch operations on multiple VMs
- Classes: `BatchExecutor`, `BatchSelector`, `TagFilter`
- Features: Tag-based filtering, progress tracking, per-VM error handling

### Feature Modules

**file_transfer/ (Submodule)**
- Responsibility: Secure SCP-based file transfer
- Classes: `FileTransfer`, `PathParser`, `SessionManager`
- Security: Path traversal prevention, symlink security validation
- Uses: SCP via subprocess

**home_sync.py** (708 LOC)
- Responsibility: Rsync-based home directory synchronization
- Classes: `HomeSyncManager`, `SyncResult`
- Features: Dry-run mode, exclusion patterns, security validation

**storage_manager.py** (594 LOC)
- Responsibility: Azure Files NFS storage account management
- Classes: `StorageManager`, `StorageInfo`, `StorageStatus`
- Operations: create, list, delete, get_status, mount, unmount

**snapshot_manager.py** (688 LOC)
- Responsibility: VM snapshot management
- Classes: `SnapshotManager`, `SnapshotInfo`, `SnapshotSchedule`
- Features: Scheduled snapshots, incremental backups, restore

**distributed_top.py** (547 LOC)
- Responsibility: Live distributed metrics dashboard
- Classes: `DistributedTopExecutor`, `VMMetrics`
- Technology: Rich live dashboard, parallel metric collection
- Displays: CPU, memory, load average, top processes

### Support Modules

**prerequisites.py**
- Validates: az, gh, git, ssh, tmux, uv, python
- Dependencies: stdlib only

**ssh_keys.py**
- Key type: Ed25519
- Permissions: 0600 (private), 0644 (public)
- Storage: ~/.ssh/azlin_key

**progress.py**
- Technology: Rich library
- Displays: Real-time progress with symbols (►, ..., ✓, ✗, ⚠)

**notifications.py**
- Technology: imessR (optional)
- Graceful degradation if tool unavailable

**env_manager.py** (411 LOC)
- Operations: set, get, list, export, import, clear
- Target: Remote VMs via SSH

**cost_tracker.py**
- Features: Per-VM cost estimation, batch summaries

**github_setup.py**
- Operations: gh auth, git clone

**log_viewer.py** (483 LOC)
- Features: Real-time tailing, filtering, format detection

---

## Architecture Patterns

### Overall Pattern: Brick Architecture
**Philosophy:** Each module is self-contained and can be regenerated independently

**Principles:**
1. Ruthless Simplicity - No over-engineering
2. Fail Fast - Errors caught early
3. Security by Design - No credentials in code
4. Clear Boundaries - Each module has single responsibility

### Module Pattern Types

| Pattern | Examples | Characteristics |
|---------|----------|-----------------|
| CLI Command Brick | prerequisites, ssh_keys, progress | Single responsibility, CLI-ready |
| Azure Integration | azure_auth, vm_provisioning | Azure CLI delegation, no creds |
| Remote Execution | remote_exec, ssh_connector | SSH-based, parallel capable |
| Data Persistence | config_manager | TOML storage, secure perms |
| Feature Module | file_transfer, snapshot_manager | Specialized domain logic |

### Layering Approach

```
Layer 1: CLI Interface (cli.py - 5409 LOC)
   ↓
Layer 2: Orchestration (batch_executor, remote_exec, vm_manager)
   ↓
Layer 3: Features (file_transfer, home_sync, snapshots)
   ↓
Layer 4: Infrastructure (azure_auth, ssh_connector, config_manager)
   ↓
Layer 5: System Integration (subprocess, file I/O, networking)
```

### Separation of Concerns

| Concern | Modules |
|---------|---------|
| Azure Operations | vm_provisioning.py, storage_manager.py, vm_lifecycle.py |
| SSH Operations | ssh_connector.py, remote_exec.py, file_transfer/ |
| Configuration | config_manager.py, env_manager.py |
| Monitoring | distributed_top.py, status_dashboard.py, log_viewer.py |
| User Experience | progress.py, notifications.py, terminal_launcher.py |

---

## Dependency Graph

### Tier 1: CLI Entry
**Dependencies:** Everything else

### Tier 2: Direct CLI Dependencies
- azure_auth
- vm_provisioning
- ssh_connector
- config_manager
- batch_executor
- vm_manager
- remote_exec
- distributed_top

### Tier 3: Infrastructure Support
- modules/ssh_keys
- modules/prerequisites
- modules/progress
- resource_cleanup

### Tier 4: Optional/Extended Features
- modules/file_transfer
- modules/home_sync
- modules/storage_manager
- modules/snapshot_manager
- modules/github_setup

### External Dependencies
```
CLI Framework:      click >= 8.1.0
Configuration:      tomli >= 2.0.0, tomli-w >= 1.0.0
Markup:             pyyaml >= 6.0.0
UI:                 rich >= 13.7.0

External Tools:
  - az (Azure CLI)
  - gh (GitHub CLI)
  - git
  - ssh
  - tmux
  - ssh-keygen
  - rsync
  - uv
```

---

## Key Execution Flows

### Flow 1: Basic VM Provisioning
**Entry:** `azlin new`

```
1. CLIOrchestrator.__init__()
   └─> Initialize orchestrator with defaults
2. PrerequisiteChecker.check_all()
   └─> Verify az, gh, git, ssh, tmux installed
3. AzureAuthenticator.authenticate()
   └─> Run 'az login' (interactive)
4. SSHKeyManager.ensure_ssh_key()
   └─> Generate ~/.ssh/azlin_key (Ed25519) if needed
5. VMProvisioner.provision()
   └─> Create VM with cloud-init (3-5 minutes)
6. VMManager.get_vm_details()
   └─> Poll for VM ready (IP, status)
7. SSHConnector.connect()
   └─> SSH into VM with tmux session
8. NotificationHandler.notify()
   └─> Optional: Send completion notification
Duration: 4-7 minutes
```

### Flow 2: List VMs
**Entry:** `azlin list`

```
1. ConfigManager.load()
   └─> Get default resource group from ~/.azlin/config.toml
2. VMManager.list_vms()
   └─> Run 'az vm list --resource-group'
3. Rich table formatting
   └─> Display results in formatted table
Duration: < 5 seconds
```

### Flow 3: Batch Operations
**Entry:** `azlin batch start`

```
1. VMManager.list_vms()
   └─> Get all VMs in resource group
2. BatchSelector.select()
   └─> Filter by tags/pattern/prefix
3. BatchExecutor.execute()
   └─> Parallel execution with ThreadPoolExecutor
4. RemoteExecutor.execute_command()
   └─> SSH on each VM (parallel, timeout-controlled)
5. Aggregation
   └─> Combine per-VM results
Duration: Varies (parallel)
```

### Flow 4: Live Monitoring Dashboard
**Entry:** `azlin top`

```
1. VMManager.list_vms()
   └─> Get running VMs
2. DistributedTopExecutor.collect_metrics()
   └─> Parallel SSH 'top' command collection
3. Rich Live display
   └─> Real-time dashboard with CPU, memory, load
4. 10-second refresh loop
   └─> Continuous updates until Ctrl+C
Duration: Continuous until interrupted
```

---

## Test Structure

### Test Pyramid

| Level | Percentage | Count | Location | Focus |
|-------|-----------|-------|----------|-------|
| **Unit** | 60% | ~63 | tests/unit/ | Single module, heavy mocking |
| **Integration** | 30% | ~31 | tests/integration/ | Multi-module workflows |
| **E2E** | 10% | ~12 | tests/e2e/ | Real Azure VMs (expensive) |
| **Total** | 100% | 106+ | tests/ | - |

### Test Files (42 total)

**Core Tests:**
- test_azure_auth.py
- test_batch_executor.py
- test_cli.py
- test_config_manager.py
- test_distributed_top.py
- test_env_manager.py
- test_key_rotator.py
- test_remote_exec.py
- test_snapshot_manager.py
- test_storage_manager.py
- test_vm_lifecycle.py
- test_vm_manager.py
- test_vm_provisioning.py

**Feature Tests:**
- test_clone_command.py
- test_nfs_mount_manager.py
- test_npm_config.py
- test_prune_command.py
- test_ssh_reconnect.py
- test_tag_manager.py
- test_template_manager.py
- [+16 more test files]

**Test Infrastructure:**
- fixtures/azure_responses.py - Mock Azure responses
- fixtures/ssh_configs.py - Mock SSH config
- fixtures/sample_configs.py - Test data
- mocks/azure_mock.py
- mocks/github_mock.py
- mocks/subprocess_mock.py
- conftest.py - Global fixtures
- utils.py - Test utilities

---

## Security Architecture

### Security Layers

1. **Input Validation**
   - All parameters sanitized before Azure/SSH calls
   - Modules: path_parser.py, config_manager.py

2. **Permission Enforcement**
   - SSH keys: 0600 (private), 0644 (public)
   - Config: 0600 (~/.azlin/config.toml)
   - SSH dir: 0700 (~/.ssh/)

3. **Credential Delegation**
   - No credential storage in code
   - Uses: az CLI, gh CLI, ssh tools
   - Credentials managed by respective tools in ~/.azure/, ~/.config/gh/

4. **Output Sanitization**
   - Logging removes passwords, tokens, keys
   - Regex patterns remove sensitive data before logging

5. **Path Security**
   - File transfer validates no path traversal
   - Symlink validation in path_parser.py

6. **Command Isolation**
   - No shell=True in subprocess calls
   - Uses shlex.quote() for command arguments

---

## Module Responsibilities Matrix

| Responsibility | Module(s) |
|---|---|
| **VM Provisioning** | vm_provisioning.py |
| **VM Listing** | vm_manager.py |
| **VM Power Control** | vm_lifecycle_control.py |
| **VM Deletion** | vm_lifecycle.py |
| **SSH Authentication** | azure_auth.py |
| **SSH Connection** | ssh_connector.py |
| **Remote Execution** | remote_exec.py |
| **File Transfer** | modules/file_transfer/ |
| **Configuration Storage** | config_manager.py |
| **Environment Variables** | env_manager.py |
| **SSH Key Management** | modules/ssh_keys.py |
| **VM Templates** | template_manager.py |
| **VM Snapshots** | snapshot_manager.py |
| **Batch Operations** | batch_executor.py |
| **NFS Storage** | modules/storage_manager.py |
| **NFS Mounting** | modules/nfs_mount_manager.py |
| **Home Sync** | modules/home_sync.py |
| **SSH Key Rotation** | key_rotator.py |
| **Monitoring Dashboard** | distributed_top.py |
| **Log Viewing** | log_viewer.py |
| **Cost Tracking** | cost_tracker.py |

---

## Module Boundary Analysis

### Well-Defined Boundaries
- **azure_auth** - Only responsible for auth, no VM creation
- **ssh_keys** - Only responsible for key generation/management
- **config_manager** - TOML persistence, no business logic
- **prerequisites** - Just checking tools, no fixing

### Somewhat Fluid Boundaries
- **vm_manager, vm_lifecycle, vm_lifecycle_control** - Some overlap in VM state handling
- **ssh_connector, remote_exec** - Both do SSH, divided by purpose (connection vs execution)
- **storage_manager, nfs_mount_manager** - Divide storage creation from mounting

### Clear Abstractions
- **VMInfo dataclass** - VM state representation
- **SSHConfig dataclass** - SSH connection parameters
- **RemoteResult dataclass** - Command execution results
- **VMMetrics dataclass** - Monitoring data

---

## Code Quality Metrics

| Metric | Value | Target |
|--------|-------|--------|
| **Test Coverage** | > 80% | > 80% |
| **Modules Tested** | 25+ | 25+ |
| **Linter** | ruff | ruff (strict) |
| **Type Checker** | pyright | basic mode |
| **Max Complexity** | 15 | <= 15 (mccabe) |
| **Line Length** | 100 | 100 |

### Critical Paths (High Priority Testing)
- VM provisioning (customer-facing)
- SSH connection (security-critical)
- Resource cleanup (cost-critical)
- Azure authentication (user-blocking)

---

## Architectural Strengths

1. **Clear Brick Architecture** - Modules are self-contained and independently testable
2. **Security by Delegation** - No credentials stored; uses standard tools
3. **Fail Fast Pattern** - Errors caught early in execution flow
4. **Comprehensive CLI** - 40+ commands for full VM lifecycle
5. **Extensible Design** - New commands easy to add following established patterns
6. **Rich User Experience** - Progress display, formatted output, live dashboards
7. **Well-Tested** - 106+ tests across unit/integration/e2e
8. **Clear Documentation** - ARCHITECTURE.md, design summaries

---

## Architectural Insights

### Implicit Workflows
1. **Configuration Flow** - Config loaded from ~/.azlin/config.toml, used, potentially saved
2. **SSH Connection Lifecycle** - Key generation → provisioning → connection → execution
3. **Resource Tracking** - Creation → enumeration (list) → manipulation (start/stop) → cleanup
4. **Error Handling** - Local exception types + Azure CLI error parsing

### Design Decisions
1. **Sequential, Not Parallel** - Each step depends on previous (auth → provision → connect)
2. **Standard Library Focus** - Prerequisites and progress modules have zero external deps
3. **CLI Orchestration** - Single entry point (cli.py) dispatches to all features
4. **Exception Hierarchy** - Each module has custom exception types for clarity

---

## File Statistics

| Category | Files | LOC | Avg LOC/File |
|----------|-------|-----|--------------|
| Core modules | 24 | 14,845 | 619 |
| Feature modules | 16 | 6,765 | 423 |
| Tests | 42 | 15,550 | 370 |
| **Total** | **82** | **37,160** | **453** |

### Top 10 Largest Files
1. cli.py - 5,409 LOC
2. vm_provisioning.py - 868 LOC
3. home_sync.py - 708 LOC
4. snapshot_manager.py - 688 LOC
5. storage_manager.py - 594 LOC
6. distributed_top.py - 547 LOC
7. vm_lifecycle_control.py - 551 LOC
8. commands/storage.py - 515 LOC
9. remote_exec.py - 504 LOC
10. batch_executor.py - 500 LOC

---

## Conclusions

### Overall Architecture Quality
The azlin project demonstrates a well-thought-out brick architecture with clear separation of concerns, strong security principles, and comprehensive feature coverage. The 40+ CLI commands are organized logically into command groups, and the underlying modules maintain clear boundaries despite some minor overlap in VM state management.

### Modularity Assessment
- **Modularity Score:** 8/10
- **Strengths:** Clear responsibilities, self-contained bricks, testable units
- **Weaknesses:** Minor overlap in vm_lifecycle modules, some large files (cli.py)

### Testing Coverage
- **Test Quality:** Excellent pyramid structure (60/30/10)
- **Coverage:** > 80% target maintained
- **Test Organization:** Well-separated unit/integration/e2e

### Extensibility
The architecture is designed for easy extension:
- New commands added to cli.py
- New feature modules follow established patterns
- Consistent use of dataclasses for interfaces
- Clear exception hierarchy for error handling

### Maintenance Implications
- **Hot spots:** cli.py (5409 LOC) could benefit from splitting
- **Complexity areas:** VM lifecycle modules (three separate files with state overlap)
- **Well-maintained:** Consistent patterns, clear documentation, comprehensive tests

---

## Recommendations

1. **Consider Refactoring cli.py** - Split into separate command group files
2. **Consolidate VM State Management** - Merge vm_manager, vm_lifecycle, vm_lifecycle_control
3. **Document Module Contracts** - Add module-level docstrings with input/output contracts
4. **Increase Type Coverage** - Move from basic to strict pyright checking
5. **Add Integration Tests** - More integration tests between feature modules

---

**Report Generated:** October 18, 2025
**Analyzed By:** Stream 1A - Reconnaissance Agent
**JSON Report Location:** `/Users/ryan/src/azlin/azlin_structure_report.json`
