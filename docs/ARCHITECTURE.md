# azlin Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         azlin CLI                                │
│                      (User Entry Point)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                    CLIOrchestrator                               │
│                  (Workflow Coordinator)                          │
│                                                                   │
│  run() -> Executes 9-step workflow:                             │
│    1. Prerequisites Check                                        │
│    2. Azure Authentication                                       │
│    3. SSH Key Setup                                             │
│    4. VM Provisioning                                           │
│    5. Wait for VM Ready                                         │
│    6. GitHub Setup (optional)                                   │
│    7. Notification (optional)                                   │
│    8. Display Info                                              │
│    9. SSH Connection                                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            v
         ┌──────────────────┴──────────────────┐
         │                                      │
         v                                      v
┌────────────────────┐              ┌────────────────────┐
│  Core Modules      │              │  Feature Modules   │
│  (Always Used)     │              │  (Conditional)     │
├────────────────────┤              ├────────────────────┤
│ 1. Prerequisites   │              │ 6. GitHub Setup    │
│ 2. Azure Auth      │              │ 8. Notifications   │
│ 3. SSH Keys        │              └────────────────────┘
│ 4. VM Provisioner  │
│ 5. SSH Connector   │
│ 7. Progress        │
└────────────────────┘

## Module Dependencies

┌─────────────────────────────────────────────────────────────────┐
│                     Prerequisites Checker                        │
│  - Validates: az, gh, git, ssh, tmux                            │
│  - No dependencies                                               │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                     Azure Authenticator                          │
│  - Uses: az CLI                                                  │
│  - Gets: subscription ID, credentials                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                     SSH Key Manager                              │
│  - Generates: ~/.ssh/azlin_key (Ed25519)                        │
│  - Permissions: 0600 (private), 0644 (public)                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                     VM Provisioner                               │
│  - Uses: SSH public key                                          │
│  - Creates: Resource group, VM, Network                          │
│  - Runs: cloud-init (installs 9 dev tools)                      │
│  - Returns: VM details (IP, name, etc)                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v
┌─────────────────────────────────────────────────────────────────┐
│                     SSH Connector                                │
│  - Uses: SSH private key, VM IP                                 │
│  - Waits: For SSH port + cloud-init completion                  │
│  - Connects: With tmux session                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v (if --repo provided)
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Setup Handler                         │
│  - Validates: GitHub URL (HTTPS only)                           │
│  - Runs: gh auth login on VM                                    │
│  - Clones: Repository to ~/repo-name                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v (throughout workflow)
┌─────────────────────────────────────────────────────────────────┐
│                     Progress Display                             │
│  - Shows: Real-time updates                                      │
│  - Tracks: Elapsed time, stages                                 │
│  - Symbols: ►, ..., ✓, ✗, ⚠                                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            v (if available)
┌─────────────────────────────────────────────────────────────────┐
│                     Notification Handler                         │
│  - Uses: imessR (optional)                                       │
│  - Sends: Completion/error notifications                         │
│  - Graceful: Degrades if not available                          │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
User Input (CLI Args)
         │
         v
┌────────────────────┐
│  Parse Arguments   │
│  - repo URL        │
│  - vm-size         │
│  - region          │
│  - resource-group  │
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
│  SSH Keys          │────> Public key content, Key paths
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  VM Provisioning   │────> VM IP, VM name, Resource group
│  (with cloud-init) │
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Wait for Ready    │────> SSH ready, cloud-init status
└──────┬─────────────┘
       │
       v (if --repo)
┌────────────────────┐
│  GitHub Setup      │────> Repository path on VM
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Display Info      │────> VM details to user
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  SSH Connection    │────> Interactive tmux session
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
                 Pre  Auth  SSH  VM   Conn  GH   Prog  Not
Prerequisites     -    ✓    -    -    -     -    ✓     -
Azure Auth        ✓    -    -    ✓    -     -    ✓     -
SSH Keys          ✓    -    -    ✓    ✓     -    ✓     -
VM Provisioner    ✓    ✓    ✓    -    ✓     -    ✓     -
SSH Connector     ✓    -    ✓    ✓    -     ✓    ✓     -
GitHub Setup      ✓    -    -    -    ✓     -    ✓     -
Progress          -    -    -    -    -     -    -     -
Notifications     -    -    -    ✓    -     -    -     -

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
  └─> azlin (no storage)
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
```

## File System Layout

```
azlin-feat-1/
├── src/
│   └── azlin/
│       ├── __init__.py              # Package metadata
│       ├── __main__.py              # Entry point
│       ├── cli.py                   # Orchestrator (648 lines)
│       ├── azure_auth.py            # Azure auth
│       ├── vm_provisioning.py       # VM provisioning
│       └── modules/
│           ├── __init__.py
│           ├── prerequisites.py     # Prerequisites
│           ├── ssh_keys.py          # SSH keys
│           ├── ssh_connector.py     # SSH connector
│           ├── github_setup.py      # GitHub setup
│           ├── progress.py          # Progress display
│           └── notifications.py     # Notifications
│
├── tests/                           # Unit tests
├── pyproject.toml                   # Package config
├── README.md                        # User documentation
├── ORCHESTRATION_COMPLETE.md        # Implementation docs
├── CLI_REFERENCE.md                 # CLI reference
├── INTEGRATION_SUMMARY.md           # Summary
├── ARCHITECTURE.md                  # This file
└── test_orchestration.py            # Integration test
```

## State Machine

```
┌─────────┐
│  Start  │
└────┬────┘
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
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ Wait for Ready   │────> [FAIL] ──> Exit 5
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│ GitHub Setup     │────> [FAIL] ──> Continue (optional)
└────┬──────────────┘
     │ [PASS/SKIP]
     v
┌──────────────────┐
│ Send Notification│
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ Display Info     │
└────┬──────────────┘
     │
     v
┌──────────────────┐
│ SSH Connect      │────> [FAIL] ──> Exit 5 (VM still running)
└────┬──────────────┘
     │ [PASS]
     v
┌──────────────────┐
│  tmux Session    │
│  (Interactive)   │
└──────────────────┘
```

## Workflow Timing

```
Typical Workflow Duration: 7-9 minutes

┌────────────────────────────────────────────────┐
│ Prerequisites Check             │ 0.1s         │
├────────────────────────────────────────────────┤
│ Azure Authentication            │ 0.5s         │
├────────────────────────────────────────────────┤
│ SSH Key Setup                   │ 0.1s         │
├────────────────────────────────────────────────┤
│ VM Provisioning                 │ 4-5 min      │
├────────────────────────────────────────────────┤
│ Wait for SSH Ready              │ 0.5-1 min    │
├────────────────────────────────────────────────┤
│ Wait for cloud-init             │ 2-3 min      │
├────────────────────────────────────────────────┤
│ GitHub Setup (if --repo)        │ 0.5-1 min    │
├────────────────────────────────────────────────┤
│ Display Info + Notification     │ 0.1s         │
├────────────────────────────────────────────────┤
│ SSH Connection                  │ 0.1s         │
└────────────────────────────────────────────────┘

Total: 7-9 minutes
  - VM provisioning: 4-5 min (longest step)
  - cloud-init: 2-3 min (tool installation)
  - Other steps: < 2 min combined
```

## Concurrency Model

```
Sequential Execution (No Parallelism)

Step N ──> Wait for completion ──> Step N+1

Rationale:
- Each step depends on previous step's output
- VM IP needed before SSH connection
- SSH ready needed before GitHub setup
- Clear error handling at each step
```

## Extension Points

```
Future Extensions:

1. Config File Support
   └─> --config flag currently unused
   └─> Could load VM size, region, repos from file

2. Custom cloud-init Scripts
   └─> Allow user-defined tool installation
   └─> Override default cloud-init

3. Multiple Repository Support
   └─> --repo could accept multiple URLs
   └─> Clone multiple repos to VM

4. VM Templates
   └─> Pre-defined VM configurations
   └─> Quick launch for common setups

5. Resource Tagging
   └─> Add tags to Azure resources
   └─> Better organization and cost tracking
```

## Testing Strategy

```
Level 1: Unit Tests
  └─> Individual module methods
  └─> Mock external dependencies
  └─> Fast execution

Level 2: Integration Tests
  └─> Module interaction
  └─> Mock Azure/GitHub APIs
  └─> Verify data flow

Level 3: Orchestration Tests ✓ (COMPLETE)
  └─> Full workflow without provisioning
  └─> Verify all modules load
  └─> Verify workflow steps exist

Level 4: E2E Tests (Manual)
  └─> Actual Azure provisioning
  └─> Real VM creation
  └─> Cost implications
```

## Performance Considerations

```
Bottlenecks:
1. VM Provisioning (4-5 min)
   └─> Azure API limits
   └─> Cannot parallelize

2. cloud-init (2-3 min)
   └─> Package installation
   └─> Network bandwidth
   └─> Cannot skip (tools needed)

Optimizations:
- Use B-series for dev (cheaper, faster)
- Choose region close to user (faster network)
- Cache prerequisites check (already fast)
- Reuse SSH keys (already implemented)
```

## Conclusion

The azlin architecture is designed as a **linear orchestrator** that:

1. **Validates** prerequisites before starting
2. **Authenticates** with Azure securely
3. **Provisions** VMs with all dev tools
4. **Connects** automatically via SSH
5. **Handles** errors gracefully
6. **Cleans up** on failure

All modules are **self-contained bricks** with **clear contracts**, making the system **maintainable** and **testable**.
