# azlin v2.0 Architecture Overview

## System Architecture

azlin has evolved from a simple VM provisioning tool into a comprehensive Azure development environment management platform. Version 2.0 introduces distributed operations, configuration management, cost tracking, storage orchestration, and advanced lifecycle management.

```
┌─────────────────────────────────────────────────────────────────┐
│                         azlin CLI v2.0                           │
│                    (Multi-Command Interface)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                    CLIOrchestrator                               │
│                  (Workflow Coordinator)                          │
│                                                                   │
│  Enhanced workflow with:                                         │
│    - Config storage and management                               │
│    - Session naming and tracking                                 │
│    - Parallel VM provisioning (pools)                            │
│    - Distributed monitoring                                      │
│    - Batch operations                                            │
│    - Cost tracking                                               │
│    - Storage management (NFS)                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            v
         ┌──────────────────┴──────────────────┐
         │                                      │
         v                                      v
┌────────────────────┐              ┌────────────────────┐
│  Core Services     │              │  Management        │
│  (25 modules)      │              │  Modules (13)      │
└────────────────────┘              └────────────────────┘
```

## Module Inventory

### Core Modules (src/azlin/)

**25 core modules** providing fundamental functionality:

1. **azure_auth.py** - Azure authentication and credential management
2. **batch_executor.py** - Parallel batch operations across multiple VMs
3. **cli.py** - Main CLI orchestrator and command dispatcher (1,400+ lines)
4. **config_manager.py** - Configuration storage and resource group management
5. **connection_tracker.py** - Track and manage VM connections
6. **cost_tracker.py** - Azure cost tracking and analytics
7. **distributed_top.py** - Live distributed VM metrics dashboard
8. **env_manager.py** - Environment variable and configuration management
9. **key_rotator.py** - SSH key rotation and security
10. **log_viewer.py** - Centralized log viewing and analysis
11. **prune.py** - Resource cleanup and pruning
12. **remote_exec.py** - Remote command execution framework
13. **resource_cleanup.py** - Automated resource cleanup
14. **status_dashboard.py** - VM status and health monitoring
15. **tag_manager.py** - Azure resource tagging
16. **template_manager.py** - VM template management and cloning
17. **terminal_launcher.py** - Terminal session management
18. **vm_connector.py** - VM connection orchestration
19. **vm_lifecycle.py** - VM lifecycle management (start, stop, delete)
20. **vm_lifecycle_control.py** - Advanced VM lifecycle controls
21. **vm_manager.py** - VM inventory and management
22. **vm_provisioning.py** - VM provisioning and cloud-init
23. **vm_updater.py** - Development tool updates

### Submodules (src/azlin/modules/)

**13 specialized modules** for specific functionality:

1. **prerequisites.py** - System prerequisites validation
2. **ssh_keys.py** - SSH key generation and management
3. **ssh_connector.py** - SSH connection establishment
4. **ssh_reconnect.py** - Automatic SSH reconnection on disconnect
5. **github_setup.py** - GitHub CLI and repository setup
6. **progress.py** - Real-time progress display
7. **notifications.py** - System notifications (optional)
8. **home_sync.py** - Home directory synchronization with security filters
9. **storage_manager.py** - Azure Storage account management
10. **nfs_mount_manager.py** - NFS mount/unmount for shared storage
11. **snapshot_manager.py** - VM and disk snapshot management
12. **npm_config.py** - Node.js and npm configuration
13. **file_transfer/** - Bidirectional file transfer subsystem (4 modules)
    - **file_transfer.py** - Core file transfer logic
    - **path_parser.py** - VM path parsing
    - **session_manager.py** - Transfer session management
    - **exceptions.py** - Transfer error handling

### Command Groups (src/azlin/commands/)

**1 command group** for extended functionality:

1. **storage.py** - Storage management commands (create, mount, unmount, delete)

### Total Module Count

- **25 core modules** in src/azlin/
- **13 submodules** in src/azlin/modules/
- **4 file_transfer modules** in src/azlin/modules/file_transfer/
- **1 command group** in src/azlin/commands/
- **Total: 43+ Python modules**

## V2.0 Feature Enhancements

### 1. Configuration Management

```
┌─────────────────────────────────────────────────────────────────┐
│                     ConfigManager                                │
│  - Stores config in ~/.azlin/config.toml                        │
│  - Tracks resource groups, regions, VM sizes                     │
│  - Session name mapping (VM name -> friendly name)               │
│  - Default values for all CLI options                            │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- Persistent configuration storage
- Session name aliases for VMs
- Default resource group tracking
- Region and VM size preferences

### 2. Session Management

**Session names** provide friendly aliases for VMs:

```bash
# Set session name
azlin session my-vm my-project

# Connect using session name
azlin connect my-project

# List VMs shows session names
azlin list
# Output:
# SESSION NAME    VM NAME      STATUS     IP
# my-project      my-vm        Running    20.12.34.56
```

Session names are stored in `~/.azlin/config.toml` and don't affect Azure resources.

### 3. VM Cloning with Home Directory

**Template management** enables VM cloning with complete home directory:

```bash
# Clone VM with home directory
azlin clone source-vm --num-replicas 3

# Creates 3 identical VMs with:
# - Same home directory contents
# - Same tool configurations
# - Security filters applied (no SSH keys, credentials)
```

**Architecture:**
```
Source VM → Snapshot → New VMs (parallel)
           → tar.gz of home → rsync to VMs (parallel)
```

### 4. Distributed Monitoring

**Batch operations** across all VMs:

```bash
# Run 'w' on all VMs
azlin w

# Run 'ps' on all VMs
azlin ps

# Live distributed metrics dashboard
azlin top
```

**Components:**
- **BatchExecutor** - Parallel command execution
- **DistributedTopExecutor** - Real-time metrics aggregation
- **ConnectionTracker** - Monitor SSH connections

### 5. Storage Management (NFS)

**Shared home directories** using Azure Files NFS:

```bash
# Create shared storage
azlin storage create team-shared --size 100 --tier Premium

# Provision VMs with shared home
azlin new --nfs-storage team-shared --name worker-1
azlin new --nfs-storage team-shared --name worker-2

# Mount on existing VM
azlin storage mount team-shared --vm existing-vm

# Unmount storage
azlin storage unmount --vm existing-vm
```

**Architecture:**
```
┌───────────────────────────────────┐
│    Azure Files (NFS 4.1)          │
│    Premium or Standard tier       │
└────────────┬──────────────────────┘
             │
    ┌────────┼────────┐
    │        │        │
    v        v        v
┌──────┐ ┌──────┐ ┌──────┐
│ VM-1 │ │ VM-2 │ │ VM-3 │
│/home │ │/home │ │/home │
└──────┘ └──────┘ └──────┘
```

**Components:**
- **StorageManager** - Storage account lifecycle
- **NFSMountManager** - Mount/unmount operations
- **HomeSyncManager** - Initial content sync with security filters

### 6. Cost Tracking

**Azure cost monitoring** with detailed breakdowns:

```bash
# Show total costs
azlin cost

# Break down by VM
azlin cost --by-vm

# Date range
azlin cost --from 2025-01-01 --to 2025-01-31
```

**CostTracker** uses Azure Cost Management API to:
- Query costs by resource group
- Break down by VM
- Track trends over time
- Estimate future costs

### 7. Batch Operations

**Parallel VM operations:**

```bash
# Provision VM pool
azlin new --pool 5

# Clone multiple replicas
azlin clone source --num-replicas 10

# Update all VMs
azlin update --all

# Execute on all VMs
azlin -- nvidia-smi
```

**BatchExecutor** features:
- Parallel execution (configurable workers)
- Progress tracking
- Error handling per-VM
- Result aggregation

### 8. File Transfer System

**Bidirectional file transfer** with security:

```bash
# Copy to VM
azlin cp report.pdf my-vm:~/

# Copy from VM
azlin cp my-vm:~/results.tar.gz ./

# Copy between VMs
azlin cp vm1:~/data.csv vm2:~/backup/

# Recursive directory transfer
azlin cp -r ./project/ my-vm:~/workspace/
```

**Security filters** block:
- SSH keys (.ssh/, id_rsa, etc.)
- Cloud credentials (.aws/, .azure/, etc.)
- Environment files (.env, .env.*)
- Secrets (*.pem, *.key, credentials.json)

**Components:**
- **FileTransfer** - Core transfer logic
- **PathParser** - Parse VM:path syntax
- **SessionManager** - Manage transfer sessions
- **Security validation** - Block sensitive files

### 9. Auto-Reconnect

**Automatic SSH reconnection** on network issues:

```bash
# Connect with auto-reconnect (default)
azlin connect my-vm

# [Network interruption occurs]
# Prompt: "Reconnect? [Y/n]:"
# Automatically attempts reconnection
```

**SSHReconnect** module:
- Detects disconnections
- Prompts user to reconnect
- Configurable retry attempts
- Maintains tmux session state

### 10. Key Rotation

**SSH key lifecycle management:**

```bash
# Rotate SSH keys
azlin rotate-keys --vm my-vm

# Rotate all VM keys
azlin rotate-keys --all
```

**KeyRotator** features:
- Generate new key pairs
- Update Azure VM SSH config
- Backup old keys
- Verify new key access

## Enhanced Data Flow

```
User Input (CLI Args + Config)
         │
         v
┌────────────────────┐
│  Parse Arguments   │
│  + Load Config     │────> ConfigManager
│  + Session Names   │
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Prerequisites     │────> Platform info, Tool versions
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Azure Auth        │────> Subscription ID, Credentials
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  SSH Keys          │────> Public key, Key paths
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  VM Provisioning   │────> VM IP, VM name, Resource group
│  (cloud-init)      │       (parallel if pool)
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Wait for Ready    │────> SSH ready, cloud-init complete
└──────┬─────────────┘
       │
       v (if --nfs-storage)
┌────────────────────┐
│  NFS Mount         │────> Mount shared storage
│  + Home Sync       │       Copy ~/.azlin/home/ contents
└──────┬─────────────┘
       │
       v (if --repo)
┌────────────────────┐
│  GitHub Setup      │────> Repository cloned
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Home Sync         │────> Copy dotfiles from ~/.azlin/home/
│  (if configured)   │       (security filters applied)
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Display Info      │────> VM details, Session name
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  SSH Connection    │────> Interactive tmux session
│  (auto-reconnect)  │       (persistent across disconnects)
└────────────────────┘
```

## Error Handling Flow

```
                    Start Workflow
                         │
                         v
                  ┌──────────────┐
                  │   Try Block  │
                  └──────┬───────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         v               v               v
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │Prerequisites│ │  Azure   │   │   VM     │
  │   Error    │ │   Auth   │   │Provision │
  │  Exit: 2   │ │ Exit: 3  │   │ Exit: 4  │
  └──────────┘   └──────────┘   └──────────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                         v
              ┌─────────────────┐
              │  ConfigManager  │
              │  Save State     │
              └────────┬────────┘
                       │
                       v
              ┌─────────────────┐
              │  Send Error     │
              │  Notification   │
              └────────┬────────┘
                       │
                       v
              ┌─────────────────┐
              │  Show Cleanup   │
              │  Instructions   │
              └────────┬────────┘
                       │
                       v
                   Exit with
                   error code
```

## Module Interaction Matrix

```
                 Pre Auth SSH  VM  Conn GH  Prog Not  Cfg  Stor Cost Batch
Prerequisites     -   ✓   -    -   -    -   ✓    -    ✓    -    -    -
Azure Auth        ✓   -   -    ✓   -    -   ✓    -    ✓    ✓    ✓    -
SSH Keys          ✓   -   -    ✓   ✓    -   ✓    -    ✓    -    -    -
VM Provisioner    ✓   ✓   ✓    -   ✓    -   ✓    -    ✓    ✓    -    ✓
SSH Connector     ✓   -   ✓    ✓   -    ✓   ✓    -    ✓    -    -    ✓
GitHub Setup      ✓   -   -    -   ✓    -   ✓    -    ✓    -    -    -
Progress          -   -   -    -   -    -   -    -    -    -    -    -
Notifications     -   -   -    ✓   -    -   -    -    -    -    -    -
ConfigManager     ✓   ✓   ✓    ✓   ✓    ✓   ✓    ✓    -    ✓    ✓    ✓
StorageManager    ✓   ✓   -    ✓   -    -   ✓    -    ✓    -    -    -
CostTracker       -   ✓   -    -   -    -   -    -    ✓    -    -    -
BatchExecutor     ✓   ✓   ✓    ✓   ✓    -   ✓    -    ✓    -    -    -

Legend:
  ✓ = Uses/Depends on
  - = No dependency
```

## Security Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Security Boundaries                         │
└─────────────────────────────────────────────────────────────────┘

User Space
  │
  ├─> Azure CLI (~/.azure/)
  │   └─> Credentials stored by az CLI (delegated)
  │       - Access tokens
  │       - Refresh tokens
  │       - Subscription info
  │
  ├─> SSH Keys (~/.ssh/)
  │   └─> azlin_key (0600 - read/write owner only)
  │       azlin_key.pub (0644 - readable by all)
  │
  ├─> Config (~/.azlin/)
  │   ├─> config.toml (session names, defaults)
  │   ├─> home/ (dotfiles for sync)
  │   └─> Security: NO credentials stored
  │
  └─> azlin (no credential storage)
      └─> Only uses credentials via:
          - az CLI subprocess calls
          - SSH key file paths
          - Never stores tokens/passwords

Network Communication
  │
  ├─> Azure API
  │   └─> Via az CLI (HTTPS)
  │       - VM provisioning
  │       - Resource management
  │       - Cost queries
  │       - Storage management
  │
  ├─> GitHub API
  │   └─> Via gh CLI (HTTPS)
  │       - Authentication
  │       - Repository operations
  │
  └─> VM SSH
      └─> Via ssh client (SSH protocol)
          - Key-based auth only
          - No password auth
          - Auto-reconnect on disconnect

File Transfer Security
  │
  ├─> Blocked Patterns
  │   ├─> SSH keys: .ssh/, id_rsa, id_ed25519, etc.
  │   ├─> Cloud credentials: .aws/, .azure/, .gcloud/
  │   ├─> Environment files: .env, .env.*, *.env
  │   └─> Secrets: *.pem, *.key, credentials.json
  │
  └─> Applied to:
      ├─> azlin cp (file transfer)
      ├─> azlin sync (home directory sync)
      └─> azlin clone (VM cloning)
```

## File System Layout

```
azlin-v2/
├── src/
│   └── azlin/
│       ├── __init__.py              # Package metadata
│       ├── __main__.py              # Entry point
│       │
│       ├── Core Modules (25 files, ~14,845 lines)
│       ├── cli.py                   # Orchestrator (1,400+ lines)
│       ├── azure_auth.py            # Azure authentication
│       ├── vm_provisioning.py       # VM provisioning
│       ├── vm_manager.py            # VM inventory
│       ├── vm_lifecycle.py          # VM lifecycle (start/stop/delete)
│       ├── vm_lifecycle_control.py  # Advanced lifecycle controls
│       ├── vm_connector.py          # VM connection orchestration
│       ├── vm_updater.py            # Development tool updates
│       ├── config_manager.py        # Configuration storage
│       ├── batch_executor.py        # Parallel batch operations
│       ├── distributed_top.py       # Live distributed metrics
│       ├── connection_tracker.py    # Connection monitoring
│       ├── cost_tracker.py          # Cost tracking
│       ├── env_manager.py           # Environment management
│       ├── key_rotator.py           # SSH key rotation
│       ├── log_viewer.py            # Log viewing
│       ├── prune.py                 # Resource pruning
│       ├── remote_exec.py           # Remote execution framework
│       ├── resource_cleanup.py      # Resource cleanup
│       ├── status_dashboard.py      # Status monitoring
│       ├── tag_manager.py           # Resource tagging
│       ├── template_manager.py      # VM templates and cloning
│       ├── terminal_launcher.py     # Terminal session management
│       │
│       ├── commands/                # Command groups
│       │   ├── __init__.py
│       │   └── storage.py           # Storage commands
│       │
│       └── modules/                 # Specialized modules (13)
│           ├── __init__.py
│           ├── prerequisites.py     # Prerequisites
│           ├── ssh_keys.py          # SSH keys
│           ├── ssh_connector.py     # SSH connector
│           ├── ssh_reconnect.py     # Auto-reconnect
│           ├── github_setup.py      # GitHub setup
│           ├── progress.py          # Progress display
│           ├── notifications.py     # Notifications
│           ├── home_sync.py         # Home directory sync
│           ├── storage_manager.py   # Storage management
│           ├── nfs_mount_manager.py # NFS mount/unmount
│           ├── snapshot_manager.py  # Snapshot management
│           ├── npm_config.py        # npm configuration
│           └── file_transfer/       # File transfer subsystem (4)
│               ├── __init__.py
│               ├── file_transfer.py # Core transfer logic
│               ├── path_parser.py   # Path parsing
│               ├── session_manager.py # Session management
│               └── exceptions.py    # Error handling
│
├── tests/                           # Unit and integration tests
├── docs/                            # Documentation
│   ├── ARCHITECTURE.md              # This file
│   ├── STORAGE_README.md            # Storage documentation
│   └── AI_AGENT_GUIDE.md            # Agent documentation
├── pyproject.toml                   # Package config
├── README.md                        # User documentation
└── .pre-commit-config.yaml          # Code quality hooks
```

## State Machine (Enhanced)

```
┌─────────┐
│  Start  │
└────┬────┘
     │
     v
┌──────────────────┐
│ Load Config      │────> ConfigManager
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ Check Prerequisites │────> [FAIL] ──> Exit 2
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ Azure Auth       │────> [FAIL] ──> Exit 3
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ SSH Key Setup    │────> [FAIL] ──> Exit 4
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ VM Provisioning  │────> [FAIL] ──> Exit 4 + Cleanup
│ (parallel if pool)│
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ Wait for Ready   │────> [FAIL] ──> Exit 5
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ NFS Mount        │────> [FAIL] ──> Continue (optional)
│ (if --nfs-storage)│
└────┬──────────────┘
     │ [PASS/SKIP]
     v
┌──────────────────┐
│ GitHub Setup     │────> [FAIL] ──> Continue (optional)
│ (if --repo)      │
└────┬──────────────┘
     │ [PASS/SKIP]
     v
┌──────────────────┐
│ Home Sync        │────> [FAIL] ──> Continue (optional)
│ (if configured)  │
└────┬──────────────┘
     │ [PASS/SKIP]
     v
┌──────────────────┐
│ Save Config      │────> ConfigManager (session name, etc.)
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ Send Notification│
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ Display Info     │────> Session name, VM details
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ SSH Connect      │────> [FAIL] ──> Retry with reconnect
│ (auto-reconnect) │
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│  tmux Session    │
│  (Interactive)   │
│  Auto-reconnect  │
│  on disconnect   │
└──────────────────┘
```

## Command Categories

### VM Lifecycle
- `azlin new` - Provision new VM
- `azlin clone` - Clone VM with home directory
- `azlin list` - List VMs
- `azlin session` - Manage session names
- `azlin status` - Detailed VM status
- `azlin start` - Start stopped VM
- `azlin stop` - Stop/deallocate VM
- `azlin kill` - Delete VM
- `azlin destroy` - Advanced deletion with dry-run
- `azlin killall` - Delete all VMs

### VM Maintenance
- `azlin update` - Update development tools
- `azlin os-update` - Update Ubuntu packages

### Connection
- `azlin connect` - SSH to VM (auto-reconnect)

### Monitoring
- `azlin w` - Show logged in users
- `azlin ps` - Show running processes
- `azlin top` - Live distributed metrics dashboard

### File Operations
- `azlin cp` - Copy files to/from VMs
- `azlin sync` - Sync dotfiles from ~/.azlin/home/

### Storage Management
- `azlin storage create` - Create NFS storage
- `azlin storage list` - List storage accounts
- `azlin storage status` - Check storage usage
- `azlin storage mount` - Mount storage on VM
- `azlin storage unmount` - Unmount storage
- `azlin storage delete` - Delete storage

### Cost Management
- `azlin cost` - Track VM spending
- `azlin cost --by-vm` - Per-VM cost breakdown

## Workflow Timing (V2.0)

```
Typical Workflow Duration: 4-9 minutes

Single VM:
┌────────────────────────────────────────────────┐
│ Prerequisites Check             │ 0.1s         │
├────────────────────────────────────────────────┤
│ Azure Authentication            │ 0.5s         │
├────────────────────────────────────────────────┤
│ SSH Key Setup                   │ 0.1s         │
├────────────────────────────────────────────────┤
│ VM Provisioning                 │ 3-4 min      │
├────────────────────────────────────────────────┤
│ Wait for SSH Ready              │ 0.5-1 min    │
├────────────────────────────────────────────────┤
│ Wait for cloud-init             │ 2-3 min      │
├────────────────────────────────────────────────┤
│ NFS Mount (if --nfs-storage)    │ 0.2-0.5 min  │
├────────────────────────────────────────────────┤
│ GitHub Setup (if --repo)        │ 0.5-1 min    │
├────────────────────────────────────────────────┤
│ Home Sync (if configured)       │ 0.1-0.5 min  │
├────────────────────────────────────────────────┤
│ Display Info + Notification     │ 0.1s         │
├────────────────────────────────────────────────┤
│ SSH Connection                  │ 0.1s         │
└────────────────────────────────────────────────┘

VM Pool (--pool 5):
  - All VMs provision in parallel: 3-4 min
  - No additional time overhead for multiple VMs!

VM Cloning (--num-replicas 5):
  - Snapshot creation: 1-2 min
  - VMs provision in parallel: 3-4 min
  - Home directory copy in parallel: 1-10 min (depends on size)
  - Total: 5-16 minutes
```

## Concurrency Model (Enhanced)

```
V2.0 Parallel Execution:

VM Pool:
  azlin new --pool 5

  VM-1 ─┐
  VM-2 ─┤
  VM-3 ─┼─> All provision in parallel
  VM-4 ─┤
  VM-5 ─┘

Batch Operations:
  azlin w

  w@VM-1 ─┐
  w@VM-2 ─┤
  w@VM-3 ─┼─> All execute in parallel
  w@VM-4 ─┤
  w@VM-5 ─┘

  Results aggregated and displayed

VM Cloning:
  azlin clone source --num-replicas 3

  Step 1: Create snapshot (sequential)

  Step 2: Provision VMs (parallel)
    VM-1 ─┐
    VM-2 ─┼─> All provision simultaneously
    VM-3 ─┘

  Step 3: Copy home directory (parallel)
    rsync@VM-1 ─┐
    rsync@VM-2 ─┼─> All copy simultaneously
    rsync@VM-3 ─┘
```

## Extension Points

```
Current V2.0 Extensions:

1. Config File Support ✓
   └─> ~/.azlin/config.toml
   └─> Stores defaults, session names

2. Session Management ✓
   └─> Friendly names for VMs
   └─> azlin session command

3. VM Cloning ✓
   └─> Clone with home directory
   └─> Parallel replica creation

4. Shared Storage ✓
   └─> Azure Files NFS
   └─> Shared home directories

5. Cost Tracking ✓
   └─> Azure Cost Management API
   └─> Per-VM breakdowns

Future Extensions:

6. Custom cloud-init Scripts
   └─> Allow user-defined tool installation
   └─> Override default cloud-init

7. Advanced Templates
   └─> Save VM configurations as templates
   └─> Quick launch from saved templates

8. Enhanced Monitoring
   └─> Prometheus/Grafana integration
   └─> Alert on resource thresholds

9. Multi-Cloud Support
   └─> AWS and GCP providers
   └─> Unified interface

10. Team Collaboration
    └─> Shared resource pools
    └─> Access control
```

## Testing Strategy

```
Level 1: Unit Tests
  └─> Individual module methods
  └─> Mock external dependencies
  └─> Fast execution
  └─> Coverage: Core modules

Level 2: Integration Tests
  └─> Module interaction
  └─> Mock Azure/GitHub APIs
  └─> Verify data flow
  └─> Coverage: Workflows

Level 3: File Transfer Tests ✓
  └─> Security validation
  └─> Path parsing
  └─> Transfer operations
  └─> Error handling

Level 4: E2E Tests (Manual)
  └─> Actual Azure provisioning
  └─> Real VM creation
  └─> Cost implications
  └─> V2.0 features validation
```

## Performance Considerations

```
Bottlenecks:
1. VM Provisioning (3-4 min)
   └─> Azure API limits
   └─> Mitigated: Parallel provisioning for pools

2. cloud-init (2-3 min)
   └─> Package installation
   └─> Network bandwidth
   └─> Cannot skip (tools needed)

3. Home Directory Copy (1-10 min)
   └─> Size dependent
   └─> Mitigated: Parallel rsync for cloning

Optimizations:
- Parallel VM provisioning (--pool)
- Parallel batch operations
- Cached prerequisites check
- Reuse SSH keys
- B-series VMs for dev (cheaper, faster)
- Region selection (closer = faster)
- NFS for shared data (avoid multiple copies)
- Smart home sync (skip large files)
```

## Conclusion

azlin v2.0 has evolved from a simple VM provisioning tool into a comprehensive Azure development environment management platform with:

1. **43+ modules** providing extensive functionality
2. **Configuration management** for persistent settings and session tracking
3. **Distributed operations** for parallel VM management
4. **Shared storage** with NFS for team collaboration
5. **Cost tracking** for budget management
6. **Batch operations** for efficient multi-VM management
7. **Auto-reconnect** for reliable SSH connections
8. **File transfer** with security validation
9. **VM cloning** with complete home directory replication
10. **Template management** for repeatable deployments

All modules remain **self-contained bricks** with **clear contracts**, maintaining the system's **maintainability** and **testability** while dramatically expanding capabilities.

The architecture supports:
- **Solo developers** - Quick VM provisioning and management
- **Small teams** - Shared storage and consistent environments
- **Large teams** - Batch operations and cost tracking
- **Enterprise** - Template management and distributed monitoring
