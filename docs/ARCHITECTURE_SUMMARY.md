# azlin Architecture Summary

**Quick Reference for Builders**

## The Big Picture

azlin is a CLI tool that automates the creation of Azure Ubuntu VMs with development tools. Think of it as "VM provisioning as a single command."

```
User types: azlin --repo https://github.com/owner/repo
  ↓
3-5 minutes later...
  ↓
User is SSH'd into a VM with tmux, all dev tools installed, repo cloned
```

## The 9 Bricks

Each brick is a self-contained Python module with a single responsibility:

```
┌─────────────────────────────────────────────────────────────────┐
│ Brick 1: Prerequisites Checker                                  │
│ Purpose: Verify az, gh, git, ssh, tmux are installed           │
│ Pattern: Fail-Fast Prerequisite Checking                       │
│ Dependencies: stdlib only                                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 2: Azure Auth Handler                                     │
│ Purpose: Handle 'az login' interactive flow                     │
│ Pattern: Safe Subprocess Wrapper                                │
│ Dependencies: az CLI                                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 3: SSH Key Manager                                        │
│ Purpose: Generate ~/.ssh/azlin_key if needed                    │
│ Pattern: Multi-Layer Security Sanitization                      │
│ Dependencies: ssh-keygen                                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 4: VM Provisioner                                         │
│ Purpose: Create Azure VM with cloud-init for dev tools         │
│ Pattern: Real-time Progress Display                            │
│ Dependencies: az CLI, SSH Key Manager, Azure Auth              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 5: SSH Connector                                          │
│ Purpose: Connect to VM via SSH and start tmux                   │
│ Pattern: Safe Subprocess Wrapper                                │
│ Dependencies: ssh, tmux                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 6: GitHub Setup Handler                                   │
│ Purpose: Run 'gh auth' and 'git clone' on VM                    │
│ Pattern: Safe Subprocess Wrapper                                │
│ Dependencies: gh, git (on remote VM), SSH Connector             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 7: Progress Display                                       │
│ Purpose: Show user-friendly progress during long operations     │
│ Pattern: Modular User Visibility                                │
│ Dependencies: stdlib only                                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 8: Notification Handler                                   │
│ Purpose: Send optional imessR notification on completion        │
│ Pattern: Graceful Environment Adaptation                        │
│ Dependencies: imessR (optional)                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Brick 9: CLI Entry Point                                        │
│ Purpose: Orchestrate all bricks in correct order                │
│ Pattern: Fail-Fast Prerequisite Checking                       │
│ Dependencies: All bricks                                        │
└─────────────────────────────────────────────────────────────────┘
```

## The Workflow

### Base Workflow (`azlin`)

```
CLI Entry Point
    ├─> 1. Prerequisites Check
    ├─> 2. Azure Auth (az login)
    ├─> 3. SSH Key Generation
    ├─> 4. VM Provisioning (3-5 min)
    ├─> 5. SSH Connection
    ├─> 6. Tmux Session
    └─> 7. Notification (optional)
```

### Repo Workflow (`azlin --repo <url>`)

```
CLI Entry Point
    ├─> 1. Prerequisites Check
    ├─> 2. Azure Auth (az login)
    ├─> 3. SSH Key Generation
    ├─> 4. VM Provisioning (3-5 min)
    ├─> 5. SSH Connection
    ├─> 6. Tmux Session
    ├─> 7. GitHub Setup (gh auth + git clone)
    └─> 8. Notification (optional)
```

## Key Design Decisions

### 1. Why Bricks?

Each module can be regenerated independently. If the VM Provisioner needs changes, the Builder can rewrite just that one file without touching the others.

### 2. Why Sequential, Not Parallel?

Each step depends on the previous:
- Can't provision VM without Azure auth
- Can't SSH without VM IP
- Can't clone repo without GitHub auth

Sequential is simpler and matches the actual dependencies.

### 3. Why Standard Library Where Possible?

Modules like Prerequisites and Progress Display have ZERO external dependencies. They work immediately after `pip install azlin`. This prevents circular dependency issues and bootstrap problems.

### 4. Why No Configuration Files?

All config is either:
- CLI arguments (`--repo`, `--region`)
- pyproject.toml defaults
- Environment variables (for advanced users)

No `.azlinrc` or `config.yaml` to maintain. Ruthless simplicity.

### 5. Why Click for CLI?

Click is the standard Python CLI framework. It handles argument parsing, help text, and follows Unix conventions. We don't reinvent this wheel.

## Security By Design

### No Credentials in Code

```
Azure creds   → Managed by az CLI in ~/.azure/
GitHub creds  → Managed by gh CLI in ~/.config/gh/
SSH keys      → Managed by ssh-keygen in ~/.ssh/
```

azlin NEVER reads, stores, or logs credentials. It delegates to standard tools.

### Output Sanitization

Every subprocess output is sanitized before logging:

```python
def sanitize_output(output: str) -> str:
    """Remove sensitive data from output."""
    patterns = [
        r'(?i)(password|token|key|secret)["\s]*[:=]["\s]*[^\s"]+',
        r'-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END',
    ]
    for pattern in patterns:
        output = re.sub(pattern, '[REDACTED]', output, flags=re.DOTALL)
    return output
```

### SSH Key Permissions

```python
private_key: 0o600  # -rw-------
public_key:  0o644  # -rw-r--r--
ssh_dir:     0o700  # drwx------
```

Enforced programmatically, verified in tests.

## Testing Strategy

### The Pyramid (60/30/10)

```
     /\
    /E2E\      10% - 6 tests - Real VMs (expensive)
   /------\
  /  INT  \    30% - 20 tests - Multi-module (mocked Azure)
 /----------\
/    UNIT   \  60% - 80 tests - Single module (heavy mocking)
-------------
```

**Total: 106 tests**

### Test Execution

```bash
# Fast feedback (< 3 seconds)
pytest tests/ -m "not e2e"

# Full suite (5-10 minutes, creates real VMs)
pytest tests/

# Pre-commit hook (< 1 second)
pytest tests/ -m "unit"
```

## Implementation Order

Builder should implement in this order to avoid dependency issues:

### Day 1: Foundation
1. Project setup (pyproject.toml, directory structure)
2. Prerequisites module
3. Progress Display module
4. CLI skeleton

### Day 2: Azure
5. Azure Auth Handler
6. SSH Key Manager
7. VM Provisioner

### Day 3: Connection
8. SSH Connector
9. GitHub Setup Handler
10. Notification Handler

### Day 4: Integration
11. Complete CLI orchestration
12. Integration tests
13. Documentation

### Day 5: Polish
14. E2E tests
15. Error recovery
16. UX refinement

## Error Handling

### Fail Fast

```python
# Step 1: Prerequisites
if not prerequisites.check_all():
    print_installation_help()
    sys.exit(2)  # Exit immediately, no partial work

# Step 2: Azure Auth
try:
    azure_auth.login()
except AuthenticationError:
    print("Azure login failed or cancelled")
    sys.exit(3)  # No cleanup needed yet

# Step 3-4: VM Provisioning
try:
    vm = vm_provisioner.provision(config)
except ProvisioningError as e:
    print(f"VM provisioning failed: {e}")
    cleanup_partial_resources()  # Important!
    sys.exit(4)
```

### Cleanup Strategy

If VM provisioning starts but fails, we MUST clean up:

```python
def cleanup_partial_resources(resource_group: str):
    """Delete resource group and all contained resources."""
    try:
        subprocess.run(['az', 'group', 'delete', '--name', resource_group, '--yes'])
    except Exception as e:
        # Best effort - log but don't fail
        log.error(f"Cleanup failed: {e}. Manual cleanup needed for {resource_group}")
```

## Module Contracts Quick Reference

| Module | Input | Output | Side Effects |
|--------|-------|--------|--------------|
| Prerequisites | - | PrerequisiteResult | None |
| Azure Auth | - | AzureSession | Browser login |
| SSH Key Manager | key_path | SSHKeyPair | Creates ~/.ssh/azlin_key |
| VM Provisioner | VMConfig | VMDetails | Azure resources |
| SSH Connector | SSHConfig | exit_code | SSH session |
| GitHub Setup | repo_url | RepoDetails | Remote commands |
| Progress Display | updates | - | stdout |
| Notifications | message | sent: bool | imessR call |
| CLI | argv | exit_code | Orchestrates all |

## Files to Create

```
src/azlin/
  __init__.py
  cli.py
  modules/
    __init__.py
    prerequisites.py
    azure_auth.py
    ssh_keys.py
    vm_provisioner.py
    ssh_connector.py
    github_setup.py
    progress.py
    notifications.py

tests/
  unit/
    test_prerequisites.py
    test_azure_auth.py
    test_ssh_keys.py
    test_vm_provisioner.py
    test_ssh_connector.py
    test_github_setup.py
    test_progress.py
    test_notifications.py
    test_cli.py
  integration/
    test_workflows.py
    test_error_handling.py
    test_cleanup.py
  e2e/
    test_base_workflow.py
    test_repo_workflow.py

pyproject.toml
README.md
USAGE.md
```

## Cloud-Init Tools List

The VM will have these 9 tools pre-installed:

1. Docker (`docker.io`)
2. Azure CLI (`az`)
3. GitHub CLI (`gh`)
4. Git (`git`)
5. Node.js (`nodejs` via NodeSource)
6. Python 3 (`python3` + pip)
7. Rust (`rustup`)
8. Golang (`go`)
9. .NET 10 RC (`dotnet-install.sh --channel 10.0`)

All installed via cloud-init YAML (see Appendix A in ARCHITECTURE.md).

## Performance Targets

- Prerequisites check: < 2 seconds
- Azure login: ~30 seconds (user-driven)
- VM provisioning: 3-5 minutes (Azure-limited)
- SSH connection: < 10 seconds
- Total time: 4-7 minutes

## Success Criteria

### Must Have
- ✅ `azlin` creates VM and connects
- ✅ `azlin --repo <url>` clones repo
- ✅ All 9 dev tools installed
- ✅ SSH key-based auth works
- ✅ Tmux session persists
- ✅ Zero credentials in code/logs

### Should Have
- ✅ Test coverage > 80%
- ✅ Works on macOS, Linux, WSL, Windows
- ✅ Clear error messages
- ✅ No manual configuration

### Could Have
- imessR notifications
- Custom VM sizes
- Multiple SSH keys

## Questions for User

Before starting implementation, Builder should ask:

1. VM naming convention: `azlin-{timestamp}` or `azlin-{random}`?
2. Resource group: Create new or allow existing?
3. VM lifecycle: Keep running or add `azlin destroy` later?
4. .NET 10 RC: Fallback to .NET 8 if RC unavailable?
5. Log location: `~/.azlin/logs/` or stderr only?

## Common Pitfalls to Avoid

1. **Don't hardcode credentials** - Use CLI tools
2. **Don't skip prerequisite checks** - Fail fast
3. **Don't ignore cleanup on failure** - Leave no zombie VMs
4. **Don't log subprocess output raw** - Sanitize first
5. **Don't make modules depend on each other** - Only via interfaces
6. **Don't skip tests** - TDD from day 1
7. **Don't use async unnecessarily** - Sequential is simpler
8. **Don't create config files** - CLI args + pyproject.toml

## Ready to Build?

Builder agent should:
1. Read full ARCHITECTURE.md for details
2. Create project structure
3. Start with Phase 1 (Prerequisites + Progress Display)
4. Write tests FIRST (TDD)
5. Follow brick philosophy (self-contained modules)
6. Use patterns from PATTERNS.md

Good luck! The architecture is solid. Execute it with ruthless simplicity.
