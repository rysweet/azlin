# Documentation Fix Action Plan

**Executive Action Plan for Resolving 47 Documentation Inconsistencies**

---

## Overview

This document provides a **prioritized, actionable roadmap** for fixing all documentation inconsistencies identified in the Deep Analysis Report. Each task is estimated for time and includes specific file locations and exact changes needed.

**Total Estimated Effort:** 10-15 hours
**Recommended Completion:** 4 phases over 2-3 days

---

## Phase 1: Critical Missing Features (P0)
**Priority:** URGENT
**Time Estimate:** 4-6 hours
**Files:** README.md (primary)

### Task 1.1: Add Monitoring Commands Section
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Line 750 (after "Monitoring" header)
**Estimated time:** 45 minutes

Add comprehensive documentation for:

#### `azlin logs` Command
```markdown
### `azlin logs` - View VM logs without SSH

Access VM system logs remotely without SSH connection.

\`\`\`bash
# View system logs
azlin logs my-vm

# View boot logs
azlin logs my-vm --boot

# Follow logs in real-time
azlin logs my-vm --follow

# View logs for specific service
azlin logs my-vm --service sshd
\`\`\`

**Use cases:**
- Debug VM issues remotely
- Monitor system startup
- Track service status
- Troubleshoot without SSH access
```

#### `azlin top` Command
```markdown
### `azlin top` - Distributed real-time monitoring

Monitor CPU, memory, and processes across all VMs in a unified dashboard.

\`\`\`bash
# Default: 10 second refresh
azlin top

# 5 second refresh
azlin top -i 5

# Specific resource group
azlin top --rg my-rg

# Custom timeout
azlin top -i 15 -t 10
\`\`\`

**Output:** Real-time dashboard showing:
- CPU usage per VM
- Memory utilization
- System load averages
- Top processes

**Use cases:**
- Monitor distributed workloads
- Identify resource bottlenecks
- Track performance across fleet
- Real-time capacity planning

Press Ctrl+C to exit.
```

---

### Task 1.2: Add VM Organization Commands
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Line 488 (after `session` command)
**Estimated time:** 30 minutes

#### `azlin tag` Command
```markdown
### `azlin tag` - Manage VM tags

Organize VMs using tags for filtering and batch operations.

\`\`\`bash
# Add tag
azlin tag my-vm --add env=dev

# Add multiple tags
azlin tag my-vm --add env=dev --add team=backend

# List VM tags
azlin tag my-vm --list

# Remove tag
azlin tag my-vm --remove env

# Remove all tags
azlin tag my-vm --clear
\`\`\`

**Tag Format:** `key=value` or `key` (for boolean flags)

**Use with:**
- `azlin list --tag env=dev` - Filter VMs
- `azlin batch stop --tag env=test` - Batch operations

**Use cases:**
- Organize VMs by environment (dev/staging/prod)
- Track VM ownership (team=backend, owner=alice)
- Mark VM purpose (temporary, permanent)
- Enable batch operations by criteria
```

---

### Task 1.3: Add Cleanup and Maintenance Commands
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Line 583 (after `killall` command)
**Estimated time:** 45 minutes

#### `azlin prune` Command
```markdown
### `azlin prune` - Automated VM cleanup

Intelligently identify and delete idle or unused VMs based on age and activity.

\`\`\`bash
# Preview what would be deleted (SAFE)
azlin prune --dry-run

# Delete VMs idle for 1+ days (default)
azlin prune

# Custom thresholds: 7+ days old, 3+ days idle
azlin prune --age-days 7 --idle-days 3

# Include running VMs in cleanup
azlin prune --include-running

# Include named sessions (normally protected)
azlin prune --include-named

# Skip confirmation prompt
azlin prune --force
\`\`\`

**Safety Features:**
- Default excludes running VMs
- Default excludes VMs with session names
- Requires confirmation unless `--force`
- Dry-run mode shows exactly what will be deleted

**Criteria for Deletion:**
- VM older than `--age-days` (default: 1)
- VM idle for `--idle-days` (default: 1)
- VM stopped or deallocated
- VM has no session name (unless `--include-named`)

**Use cases:**
- Automated cost reduction
- Remove forgotten test VMs
- Scheduled cleanup in CI/CD
- Prevent resource sprawl
```

#### `azlin cleanup` Command
```markdown
### `azlin cleanup` - Remove orphaned resources

Find and delete orphaned Azure resources (NICs, disks, IPs) left behind from incomplete VM deletions.

\`\`\`bash
# Preview orphaned resources
azlin cleanup --dry-run

# Remove orphaned resources
azlin cleanup

# Specific resource group
azlin cleanup --rg my-rg

# Skip confirmation
azlin cleanup --force
\`\`\`

**What it removes:**
- Network interfaces not attached to VMs
- Public IP addresses not in use
- Disks not attached to VMs
- Orphaned security groups

**Use cases:**
- Clean up after failed deletions
- Reduce clutter in resource groups
- Eliminate unnecessary costs
- Maintain tidy Azure resources
```

---

### Task 1.4: Add Batch Operations Section
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Line 950 (after cost section, before "Advanced Usage")
**Estimated time:** 60 minutes

```markdown
## Batch Operations

Execute operations on multiple VMs simultaneously using tags, patterns, or select all.

### Selection Methods

1. **By Tag:** `--tag env=dev`
2. **By Pattern:** `--vm-pattern 'test-*'`
3. **All VMs:** `--all`

### `azlin batch stop` - Stop multiple VMs

\`\`\`bash
# Stop all dev VMs
azlin batch stop --tag env=dev

# Stop VMs matching pattern
azlin batch stop --vm-pattern 'test-*'

# Stop all VMs
azlin batch stop --all

# Preview before stopping
azlin batch stop --tag env=dev --dry-run

# Skip confirmation
azlin batch stop --all --yes
\`\`\`

### `azlin batch start` - Start multiple VMs

\`\`\`bash
# Start all staging VMs
azlin batch start --tag env=staging

# Start specific pattern
azlin batch start --vm-pattern 'worker-*'
\`\`\`

### `azlin batch sync` - Sync files to multiple VMs

\`\`\`bash
# Sync dotfiles to all dev VMs
azlin batch sync --tag env=dev

# Sync to all VMs
azlin batch sync --all
\`\`\`

### `azlin batch command` - Execute command on multiple VMs

\`\`\`bash
# Update all test VMs
azlin batch command 'git pull' --tag env=test

# Restart service on all VMs
azlin batch command 'sudo systemctl restart myapp' --all

# Run with timeout
azlin batch command 'long-task.sh' --all --timeout 600
\`\`\`

**Options:**
- `--tag KEY=VALUE` - Select by tag
- `--vm-pattern PATTERN` - Select by name pattern
- `--all` - Select all VMs
- `--dry-run` - Preview selection
- `--yes` - Skip confirmation
- `--timeout SECONDS` - Command timeout

**Use cases:**
- Nightly shutdown of dev environments
- Deploy updates across fleet
- Restart services on multiple VMs
- Synchronized configuration updates
```

---

### Task 1.5: Add Authentication Section
**File:** `/Users/ryan/src/azlin/README.md`
**Insert before:** Line 956 (before "Advanced Usage")
**Estimated time:** 60 minutes

```markdown
## Authentication

Manage service principal authentication for automated Azure operations without interactive login.

### `azlin auth setup` - Create authentication profile

Interactive setup for service principal credentials.

\`\`\`bash
# Create new profile
azlin auth setup --profile production

# Follow prompts to enter:
# - Subscription ID
# - Tenant ID
# - Client ID
# - Client Secret
\`\`\`

**What it does:**
- Securely stores credentials in `~/.azlin/auth/<profile>.json`
- Sets file permissions to 0600 (owner read/write only)
- Validates credentials with test API call

### `azlin auth list` - List profiles

\`\`\`bash
# Show all configured profiles
azlin auth list
\`\`\`

**Output:**
\`\`\`
Available authentication profiles:
  - production (Subscription: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
  - staging (Subscription: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy)
  - development (Subscription: zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz)
\`\`\`

### `azlin auth show` - Show profile details

\`\`\`bash
# View profile configuration
azlin auth show production
\`\`\`

### `azlin auth test` - Test authentication

\`\`\`bash
# Verify credentials work
azlin auth test --profile production
\`\`\`

### `azlin auth remove` - Delete profile

\`\`\`bash
# Remove authentication profile
azlin auth remove production
\`\`\`

**Security:**
- Credentials stored locally in `~/.azlin/auth/`
- File permissions: 0600 (readable only by owner)
- Never logged or transmitted except to Azure
- Use Azure Key Vault in production environments

**Use cases:**
- CI/CD pipeline automation
- Scheduled VM operations
- Multi-tenant management
- Service account authentication

**Creating Service Principal:**
\`\`\`bash
# Azure CLI method
az ad sp create-for-rbac --name azlin-automation --role Contributor --scopes /subscriptions/{subscription-id}

# Save output values for auth setup
\`\`\`
```

---

### Task 1.6: Add SSH Key Management Section
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Authentication section
**Estimated time:** 30 minutes

```markdown
## SSH Key Management

Rotate and manage SSH keys across all VMs for enhanced security.

### `azlin keys rotate` - Rotate SSH keys

Generate new SSH keys and update all VMs in resource group.

\`\`\`bash
# Rotate keys for all VMs
azlin keys rotate

# Specific resource group
azlin keys rotate --rg production

# Backup old keys
azlin keys rotate --backup
\`\`\`

**What happens:**
1. Generates new SSH key pair
2. Backs up existing keys (if `--backup`)
3. Updates all VMs with new public key
4. Verifies SSH access with new keys
5. Removes old keys from VMs

**Safety:** Old keys backed up to `~/.azlin/keys-backup-<timestamp>/`

### `azlin keys list` - List VM SSH keys

\`\`\`bash
# Show SSH keys for all VMs
azlin keys list

# Show all keys (not just azlin VMs)
azlin keys list --all

# Filter by prefix
azlin keys list --vm-prefix production
\`\`\`

### `azlin keys export` - Export public key

\`\`\`bash
# Export to file
azlin keys export --output my-key.pub
\`\`\`

### `azlin keys backup` - Backup current keys

\`\`\`bash
# Backup to default location
azlin keys backup

# Backup to custom location
azlin keys backup --destination /secure/backup/
\`\`\`

**Best Practices:**
- Rotate keys every 90 days
- Backup before rotation
- Test access after rotation
- Store backups securely
```

---

### Task 1.7: Add VM Templates Section
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** SSH Keys section
**Estimated time:** 30 minutes

```markdown
## VM Templates

Save and reuse VM configurations for consistent provisioning.

### `azlin template create` - Create template

Interactive wizard to create a VM configuration template.

\`\`\`bash
# Create new template
azlin template create dev-vm

# Follow prompts for:
# - VM size
# - Region
# - Disk size
# - Network configuration
\`\`\`

**Templates stored at:** `~/.azlin/templates/<name>.yaml`

### `azlin template list` - List templates

\`\`\`bash
# Show all templates
azlin template list
\`\`\`

### `azlin template delete` - Delete template

\`\`\`bash
# Remove template
azlin template delete dev-vm

# Force delete without confirmation
azlin template delete dev-vm --force
\`\`\`

### Using Templates

\`\`\`bash
# Provision VM from template
azlin new --template dev-vm --name my-instance

# Template settings override defaults
# CLI flags override template settings
\`\`\`

### `azlin template export` - Export template

\`\`\`bash
# Export to file
azlin template export dev-vm my-template.yaml
\`\`\`

### `azlin template import` - Import template

\`\`\`bash
# Import from file
azlin template import my-template.yaml
\`\`\`

**Use cases:**
- Standardize VM configurations
- Share configs across team
- Environment-specific templates (dev/staging/prod)
- Consistent onboarding
```

---

### Task 1.8: Update Quick Reference Table
**File:** `/Users/ryan/src/azlin/README.md`
**Line:** 1121-1142 (Quick Reference table)
**Estimated time:** 15 minutes

Add missing commands to table:

```markdown
| `azlin logs` | View logs | `azlin logs my-vm --follow` |
| `azlin tag` | Manage tags | `azlin tag my-vm --add env=dev` |
| `azlin top` | Real-time monitor | `azlin top` |
| `azlin prune` | Auto cleanup | `azlin prune --dry-run` |
| `azlin cleanup` | Remove orphans | `azlin cleanup` |
| `azlin batch` | Batch operations | `azlin batch stop --tag env=test` |
| `azlin auth` | Authentication | `azlin auth setup --profile prod` |
| `azlin keys` | SSH key mgmt | `azlin keys rotate` |
| `azlin template` | VM templates | `azlin template create dev-vm` |
```

---

## Phase 2: Complete Existing Documentation (P1)
**Priority:** HIGH
**Time Estimate:** 3-4 hours
**Files:** README.md, AZDOIT.md

### Task 2.1: Enhance `list` Command Options
**File:** `/Users/ryan/src/azlin/README.md`
**Line:** 449-465
**Estimated time:** 20 minutes

Add missing options:

```markdown
### `azlin list` - List all VMs

\`\`\`bash
# List VMs in default resource group
azlin list

# Show ALL VMs (including stopped)
azlin list --all

# Filter by tag
azlin list --tag env=dev

# Filter by tag key only
azlin list --tag team

# Specific resource group
azlin list --resource-group my-custom-rg
\`\`\`

**Output columns:**
- SESSION NAME - Custom label (if set)
- VM NAME - Azure VM name
- STATUS - Running/Stopped/Deallocated
- IP - Public IP address
- REGION - Azure region
- SIZE - VM size (e.g., Standard_D2s_v3)

**Filtering:**
- Default: Shows only running VMs
- `--all`: Shows stopped/deallocated VMs
- `--tag KEY=VALUE`: Filter by specific tag value
- `--tag KEY`: Filter by tag key existence
```

---

### Task 2.2: Clarify `stop` Command Behavior
**File:** `/Users/ryan/src/azlin/README.md`
**Line:** 519-530
**Estimated time:** 15 minutes

Update to:

```markdown
### `azlin stop` - Stop/deallocate a VM

\`\`\`bash
# Stop VM (stops compute billing)
azlin stop my-vm

# By default, VM is DEALLOCATED (compute fully released)
# Storage charges still apply

# Stop without deallocating (keeps resources allocated)
azlin stop my-vm --no-deallocate

# Specific resource group
azlin stop my-vm --resource-group my-rg
\`\`\`

**Cost Impact:**
- `azlin stop` (default deallocate) → Compute billing STOPS, storage continues
- `azlin stop --no-deallocate` → Full billing continues

**Important:** Always use default (deallocate) for cost savings unless you need guaranteed resource availability.
```

---

### Task 2.3: Add VM Identifier Explanation Box
**File:** `/Users/ryan/src/azlin/README.md`
**Insert at:** Line 658 (beginning of Connect section)
**Estimated time:** 20 minutes

```markdown
### Understanding VM Identifiers

Many azlin commands accept a **VM identifier** in three formats:

1. **VM Name:** Full Azure VM name (e.g., `azlin-vm-12345`)
   - Requires: `--resource-group` or default config
   - Example: `azlin connect azlin-vm-12345 --rg my-rg`

2. **Session Name:** Custom label you assigned (e.g., `my-project`)
   - Automatically resolves to VM name
   - Example: `azlin connect my-project`

3. **IP Address:** Direct connection (e.g., `20.1.2.3`)
   - No resource group needed
   - Example: `azlin connect 20.1.2.3`

**Commands that accept VM identifiers:**
- `connect`, `update`, `os-update`, `stop`, `start`, `kill`, `destroy`

**Tip:** Use session names for easy access:
\`\`\`bash
azlin session azlin-vm-12345 myproject
azlin connect myproject  # Much easier!
\`\`\`
```

---

### Task 2.4: Complete Snapshot Documentation
**File:** `/Users/ryan/src/azlin/README.md`
**Line:** 1290-1293
**Estimated time:** 40 minutes

Expand to include all 8 subcommands:

```markdown
### Snapshot Management

Create point-in-time backups of VM disks and restore VMs to previous states.

#### Manual Snapshots

\`\`\`bash
# Create snapshot manually
azlin snapshot create my-vm

# List snapshots for VM
azlin snapshot list my-vm

# Restore VM from snapshot
azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

# Delete snapshot
azlin snapshot delete my-vm-snapshot-20251015-053000
\`\`\`

#### Automated Snapshot Schedules

\`\`\`bash
# Enable scheduled snapshots (every 24 hours, keep 2)
azlin snapshot enable my-vm --every 24 --keep 2

# Custom schedule (every 12 hours, keep 5)
azlin snapshot enable my-vm --every 12 --keep 5

# View snapshot schedule
azlin snapshot status my-vm

# Trigger snapshot sync now
azlin snapshot sync

# Sync specific VM
azlin snapshot sync --vm my-vm

# Disable scheduled snapshots
azlin snapshot disable my-vm
\`\`\`

**Snapshot Naming:** Automatic format `<vm-name>-snapshot-<timestamp>`

**Schedule Management:**
- Schedules stored in `~/.azlin/config.toml`
- `snapshot sync` checks all VMs with schedules
- Run `sync` in cron for automation

**Retention:**
- Old snapshots automatically deleted when limit reached
- `--keep N` maintains last N snapshots

**Use cases:**
- Disaster recovery
- Pre-update backups
- Experimental changes (restore if needed)
- Compliance/archival requirements
```

---

### Task 2.5: Complete Environment Variables Documentation
**File:** `/Users/ryan/src/azlin/README.md`
**Line:** 1272-1276
**Estimated time:** 30 minutes

Add all 6 subcommands:

```markdown
### Environment Variable Management

Manage environment variables stored in `~/.bashrc` on remote VMs.

#### `azlin env set` - Set variable

\`\`\`bash
# Set environment variable
azlin env set my-vm DATABASE_URL="postgres://localhost/db"

# Set multiple variables
azlin env set my-vm API_KEY="secret123" ENVIRONMENT="production"
\`\`\`

Variables are added to `~/.bashrc` with comment:
\`\`\`bash
# Managed by azlin
export DATABASE_URL="postgres://localhost/db"
\`\`\`

#### `azlin env list` - List variables

\`\`\`bash
# List all azlin-managed variables
azlin env list my-vm

# Show values (default hides)
azlin env list my-vm --show-values
\`\`\`

#### `azlin env delete` - Delete variable

\`\`\`bash
# Remove specific variable
azlin env delete my-vm API_KEY
\`\`\`

#### `azlin env export` - Export to file

\`\`\`bash
# Export to .env format
azlin env export my-vm prod.env

# Contents:
# DATABASE_URL=postgres://localhost/db
# API_KEY=secret123
\`\`\`

#### `azlin env import` - Import from file

\`\`\`bash
# Import variables from .env file
azlin env import my-vm prod.env
\`\`\`

#### `azlin env clear` - Clear all variables

\`\`\`bash
# Remove all azlin-managed variables
azlin env clear my-vm

# Skip confirmation
azlin env clear my-vm --force
\`\`\`

**Security:**
- Variables only in `~/.bashrc` (not system-wide)
- Plaintext storage (use Azure Key Vault for secrets)
- No variables logged by azlin

**Use cases:**
- Configure applications
- Share team configuration
- Environment-specific settings
- Quick deployment configuration
```

---

### Task 2.6: Add Comparison Tables
**File:** `/Users/ryan/src/azlin/README.md`
**Insert after:** Line 565 (destroy section)
**Estimated time:** 20 minutes

```markdown
### Deletion Commands Comparison

| Feature | `kill` | `destroy` | `killall` |
|---------|--------|-----------|-----------|
| Delete single VM | ✓ | ✓ | ✗ |
| Delete multiple VMs | ✗ | ✗ | ✓ |
| Dry-run mode | ✗ | ✓ | ✗ |
| Delete resource group | ✗ | ✓ | ✗ |
| Confirmation | ✓ | ✓ | ✓ |
| Force flag | ✓ | ✓ | ✓ |

**When to use:**
- `kill` - Simple, quick VM deletion
- `destroy` - Advanced with dry-run and RG deletion
- `killall` - Bulk cleanup of multiple VMs
```

Also add after AZDOIT section:

```markdown
### Natural Language Commands Comparison

| Feature | `do` | `doit` |
|---------|------|--------|
| Natural language parsing | ✓ | ✓ |
| Command execution | ✓ | ✓ |
| State persistence | ✗ | ✓ |
| Objective tracking | ✗ | ✓ |
| Audit logging | ✗ | ✓ |
| Multi-strategy (future) | ✗ | ✓ |
| Cost estimation (future) | ✗ | ✓ |

**When to use:**
- `do` - Quick, simple natural language commands
- `doit` - Complex objectives requiring state tracking
```

---

## Phase 3: Examples and Clarifications (P2)
**Priority:** MEDIUM
**Time Estimate:** 2-3 hours
**Files:** README.md, QUICK_REFERENCE.md, AZDOIT.md

### Task 3.1: Add Missing Examples Throughout
**File:** `/Users/ryan/src/azlin/README.md`
**Estimated time:** 60 minutes

Add examples for:

1. **`connect` with custom user** (line 676)
```bash
# Connect with custom SSH user
azlin connect my-vm --user myusername
```

2. **`cost` with estimate flag** (line 936)
```bash
# Show monthly cost estimate for all VMs
azlin cost --estimate

# Per-VM monthly estimates
azlin cost --by-vm --estimate
```

3. **`update` timeout note** (line 588)
```markdown
### `azlin update` - Update development tools on a VM

Updates all programming tools and AI CLI tools. **Default timeout: 300 seconds per tool.**
```

4. **`status` VM filter** (line 490)
```bash
# Show status for specific VM only
azlin status --vm my-vm
```

5. **`new` with template** (line 389)
```bash
# Provision from saved template
azlin new --template dev-vm --name my-instance
```

6. **Storage delete force behavior** (line 887)
```bash
# Delete storage (fails if VMs connected)
azlin storage delete myteam-shared

# Force delete even if VMs connected
azlin storage delete myteam-shared --force
```

---

### Task 3.2: Update QUICK_REFERENCE.md
**File:** `/Users/ryan/src/azlin/docs/QUICK_REFERENCE.md`
**Estimated time:** 45 minutes

Changes needed:

1. **Line 45:** Update main command behavior
```markdown
azlin [OPTIONS]                    # Show help (or no args for help)
```

2. **Line 248:** Fix pool warning example
```markdown
**Warning for large pools (>10):**
\`\`\`
WARNING: Creating 11 VMs
Estimated cost: ~$1.10/hour
Continue? [y/N]:
\`\`\`
```

3. **Add performance section** (end of file)
```markdown
---

## Performance Reference

| Operation | Typical Time |
|-----------|--------------|
| `azlin list` | 2-3 seconds |
| `azlin status` | 3-5 seconds |
| `azlin cost` | 5-10 seconds |
| `azlin new` | 4-7 minutes |
| `azlin clone` | 10-15 minutes |
| `azlin update` | 2-5 minutes |
| `azlin sync` | 30s - 5 minutes |
| `azlin do` | +2s parsing overhead |

**Optimization Tips:**
- Use native commands for frequent operations
- `azlin do` adds 2-3 seconds parsing time
- Batch operations run in parallel
- Pool provisioning parallelized (4-7 min regardless of size)
```

---

### Task 3.3: Standardize AZDOIT.md Examples
**File:** `/Users/ryan/src/azlin/docs/AZDOIT.md`
**Estimated time:** 30 minutes

Standardize natural language patterns:

**Current inconsistency:**
- "create a vm called test"
- "provision a Standard_D4s_v3 vm"
- "show me all my vms"

**Recommendation:** Maintain flexibility but add note:

Insert at line 90:

```markdown
### Natural Language Flexibility

The AI understands multiple phrasings. All of these work:

**VM Creation:**
- "create a vm called test"
- "provision a new vm named test"
- "make me a vm called test"
- "set up a Standard_D4s_v3 vm"

**Listing:**
- "show me all my vms"
- "list my vms"
- "what vms do I have"

**Be as natural as you'd speak - the AI adapts to your style.**
```

---

### Task 3.4: Add Default Behaviors Notes
**File:** `/Users/ryan/src/azlin/README.md`
**Estimated time:** 20 minutes

Add "Defaults" subsection to key commands:

```markdown
**Defaults:**
- `--deallocate`: yes (fully release compute)
- `--timeout`: 300 seconds
- `--every`: 24 hours
- `--keep`: 2 snapshots
- `--prefix`: "azlin" (for killall)
- Date format: YYYY-MM-DD
```

---

## Phase 4: Polish and Consistency (P3)
**Priority:** LOW
**Time Estimate:** 1-2 hours
**Files:** All documentation

### Task 4.1: Standardize Code Block Formatting
**Files:** README.md, QUICK_REFERENCE.md, AZDOIT.md
**Estimated time:** 30 minutes

**Rules:**
1. Always use `bash` language tag for shell commands
2. Always include `$` for shell prompts
3. Use ` ` ` triple backticks, not single backtick for multiline

**Find and replace:**
```bash
# Find: ```$ (without bash tag)
# Replace with: ```bash\n$

# Find: Code blocks without language tags
# Add: bash tag
```

---

### Task 4.2: Standardize Table Formatting
**Files:** README.md, AZDOIT.md
**Estimated time:** 20 minutes

**Standard format:**
```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value    | Value    | Value    |
```

**Rules:**
- Align columns with spaces
- Use `|` for cell separators
- Use `---` for header separator
- Left-align text, right-align numbers

---

### Task 4.3: Standardize Heading Levels
**File:** README.md
**Estimated time:** 20 minutes

**Hierarchy:**
```
# Document Title
## Major Sections (VM Lifecycle, Monitoring, etc.)
### Commands (azlin new, azlin list, etc.)
#### Subsections (Options, Examples, Use Cases)
```

**Review:** Check all sections follow this pattern

---

### Task 4.4: Add Version Numbers
**Files:** README.md, QUICK_REFERENCE.md, AZDOIT.md
**Estimated time:** 10 minutes

Add to each document header:

```markdown
# azlin - Azure Ubuntu VM Provisioning CLI

**Version:** 2.0.0
**Last Updated:** 2025-10-27
```

---

## Validation Checklist

After completing all phases, validate:

### Documentation Completeness
- [ ] All commands from `azlin --help` documented
- [ ] All options for each command documented
- [ ] Examples provided for every command
- [ ] Use cases explained
- [ ] Default behaviors noted

### Cross-References
- [ ] All internal links work
- [ ] Quick reference table includes all commands
- [ ] Command comparison tables accurate
- [ ] Version numbers match across docs

### Example Validation
- [ ] All code examples use correct syntax
- [ ] All examples tested and work
- [ ] All options in examples exist in CLI
- [ ] Output examples match actual output

### Style Consistency
- [ ] Code blocks use `bash` language tag
- [ ] Shell prompts include `$`
- [ ] Tables formatted consistently
- [ ] Heading levels follow hierarchy
- [ ] Emoji usage consistent (or removed)

### Technical Accuracy
- [ ] No CLI options mentioned that don't exist
- [ ] No documentation for removed features
- [ ] Default values match CLI
- [ ] Behavioral descriptions accurate

---

## Automation Setup

Prevent future documentation drift:

### 1. CLI Help Extraction Test
**File:** `tests/test_documentation_sync.py`

```python
"""Test that all CLI commands are documented."""
import subprocess
import re

def test_all_commands_documented():
    # Get commands from CLI
    result = subprocess.run(['azlin', '--help'], capture_output=True)
    cli_commands = extract_commands(result.stdout)

    # Get commands from README
    with open('README.md') as f:
        doc_commands = extract_doc_commands(f.read())

    # Assert all CLI commands documented
    missing = cli_commands - doc_commands
    assert not missing, f"Undocumented commands: {missing}"
```

### 2. Example Validation Test
**File:** `tests/test_examples.py`

```python
"""Test that all documentation examples are valid."""
def test_examples_in_readme():
    examples = extract_code_blocks('README.md')
    for example in examples:
        # Validate syntax (don't execute)
        assert is_valid_azlin_command(example)
```

### 3. Version Sync Check
**File:** `.github/workflows/version-check.yml`

```yaml
name: Version Consistency Check
on: [push, pull_request]
jobs:
  check-versions:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Check version consistency
        run: |
          VERSION=$(grep version pyproject.toml | cut -d'"' -f2)
          grep -q "Version: $VERSION" README.md || exit 1
          grep -q "Version: $VERSION" docs/*.md || exit 1
```

---

## Maintenance Schedule

Going forward:

### On Every Release
1. Update version numbers in all docs
2. Run documentation tests
3. Review new commands for documentation
4. Validate all examples

### Monthly
1. Review for outdated content
2. Check for broken links
3. Validate CLI help matches docs

### Quarterly
1. Full documentation audit
2. User feedback review
3. Example updates
4. Performance benchmarks update

---

**Document Version:** 1.0
**Last Updated:** 2025-10-27
**Estimated Total Effort:** 10-15 hours over 4 phases
