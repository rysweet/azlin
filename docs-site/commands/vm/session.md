# azlin session

**Set and manage named sessions for VMs**

## Description

The `azlin session` command assigns human-readable session names to VMs, making it easier to remember and connect to VMs by project or purpose rather than auto-generated VM names. Session names appear in `azlin list` output and can be used directly with `azlin connect`.

**Use cases:**
- Associate VMs with project names for easy recall
- Team collaboration - standardize VM naming across team
- Multi-VM workflows - quickly identify VM purposes
- Long-running work sessions - label VMs by current task

**Session names enable:**
```bash
# Instead of:
azlin connect azlin-vm-1732145234

# Use:
azlin connect my-project
```

## Usage

```bash
azlin session [OPTIONS] VM_NAME [SESSION_NAME]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM to label |
| `SESSION_NAME` | Optional. Session name to set. Omit to view current session |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group containing the VM (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--clear` | Flag | Clear/remove session name from VM |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Set Session Name

```bash
# Set session name for a VM
azlin session azlin-vm-12345 myproject

# Set session name with explicit resource group
azlin session azlin-vm-12345 backend-api --rg my-rg

# Set descriptive session name
azlin session azlin-vm-98765 ml-training-experiment-1
```

### View Session Name

```bash
# View current session name (omit SESSION_NAME argument)
azlin session azlin-vm-12345

# Example output:
# Current session: myproject
```

### Clear Session Name

```bash
# Remove session name from VM
azlin session azlin-vm-12345 --clear

# Verify cleared
azlin session azlin-vm-12345
# Example output:
# No session set
```

### Workflow Examples

```bash
# Provision VM and immediately set session name
azlin new --name myvm
azlin session myvm my-project

# Connect using session name
azlin connect my-project

# List VMs shows session names
azlin list
# Output includes session column:
# VM Name    | Session     | Status  | ...
# myvm       | my-project  | Running | ...
```

## Session Naming Best Practices

### Good Session Names

```bash
# Project-based
azlin session vm1 webapp-frontend
azlin session vm2 api-backend
azlin session vm3 ml-training

# Task-based
azlin session vm1 bug-fix-issue-123
azlin session vm2 performance-testing
azlin session vm3 database-migration

# Team-based
azlin session vm1 alice-dev
azlin session vm2 bob-experiment
azlin session vm3 shared-team-env
```

### Avoid

```bash
# Too generic
azlin session vm1 dev  # Not descriptive

# Special characters that may cause issues
azlin session vm1 my@project  # Avoid @ # $ etc.

# Extremely long names
azlin session vm1 this-is-a-very-long-session-name-that-will-be-hard-to-type
```

**Recommended format:**
- Use hyphens (`-`) not underscores
- Keep under 30 characters
- Use lowercase
- Be descriptive but concise

## How Session Resolution Works

When you use `azlin connect <identifier>`:

1. **Check if IP address** - If yes, connect directly
2. **Check if session name exists** - If yes, resolve to VM name
3. **Check if VM name exists** - If yes, connect
4. **Show interactive menu** - If no matches

**Example:**
```bash
# Set session
azlin session azlin-vm-12345 myproject

# Connect by session name
azlin connect myproject

# azlin resolves: myproject → azlin-vm-12345 → connects
```

## Team Collaboration Workflows

### Shared VM Organization

```bash
# Team members label their VMs
azlin session azlin-vm-001 alice-dev
azlin session azlin-vm-002 bob-dev
azlin session azlin-vm-003 shared-staging

# Anyone can list and see who owns what
azlin list
# VM Name        | Session         | Status  | ...
# azlin-vm-001   | alice-dev       | Running | ...
# azlin-vm-002   | bob-dev         | Running | ...
# azlin-vm-003   | shared-staging  | Running | ...

# Connect to teammate's VM (if needed)
azlin connect bob-dev
```

### Project-Based Organization

```bash
# Multiple VMs for one project
azlin session vm1 webapp-frontend
azlin session vm2 webapp-backend
azlin session vm3 webapp-db

# Quick access by component
azlin connect webapp-frontend
azlin connect webapp-backend
```

### Experiment Tracking

```bash
# Label VMs by experiment
azlin session vm1 exp-baseline
azlin session vm2 exp-variant-a
azlin session vm3 exp-variant-b

# Connect to specific experiment
azlin connect exp-variant-a

# Clear when experiment completes
azlin session vm2 --clear
```

## Troubleshooting

### Session Name Conflict

**Symptoms:** Two VMs have same session name.

**Problem:** Session names should be unique within resource group.

**Solutions:**
```bash
# List all VMs to see conflicts
azlin list

# Rename one of the conflicting sessions
azlin session vm1 project-v1
azlin session vm2 project-v2

# Or clear one session name
azlin session vm2 --clear
```

### Session Not Found

**Symptoms:** `azlin connect myproject` says "Session not found".

**Solutions:**
```bash
# List all VMs and session names
azlin list

# Check spelling
azlin session myvm  # View current session name

# Re-set session name
azlin session myvm myproject
```

### Session Name Shows in Wrong Place

**Symptoms:** Session name appears as VM name or vice versa.

**Solutions:**
```bash
# Session names are stored as Azure VM tags
# View tags: azlin tag list myvm

# Clear and re-set session
azlin session myvm --clear
azlin session myvm correct-session-name
```

### Cannot Clear Session

**Symptoms:** `--clear` flag doesn't remove session name.

**Solutions:**
```bash
# Verify resource group is correct
azlin session myvm --clear --rg correct-rg

# Check Azure permissions
az vm show --name myvm --resource-group my-rg

# Manually remove tag
azlin tag remove myvm azlin-session
```

## Technical Details

### Storage Mechanism

Session names are stored as Azure VM tags:
- **Tag key**: `azlin-session`
- **Tag value**: Your session name

```bash
# View session tag
azlin tag list myvm | grep azlin-session

# Manually set (alternative)
azlin tag add myvm azlin-session=myproject

# Manually remove (alternative)
azlin tag remove myvm azlin-session
```

### Persistence

- Session names persist across VM stop/start
- Session names persist across deallocation
- Session names persist across reboots
- Session names are lost if VM is destroyed
- Session names can be backed up by exporting tags

## Advanced Usage

### Bulk Session Setup

```bash
# Set sessions for multiple VMs
vms=("vm1:frontend" "vm2:backend" "vm3:database")
for entry in "${vms[@]}"; do
    vm="${entry%%:*}"
    session="${entry##*:}"
    azlin session $vm $session
done
```

### Session Name Rotation

```bash
# Rotate session names for experiments
OLD_SESSION="exp-v1"
NEW_SESSION="exp-v2"

# Find VM with old session and rename
VM=$(azlin list | grep $OLD_SESSION | awk '{print $1}')
azlin session $VM $NEW_SESSION
```

### Export Session Mappings

```bash
# Export all session mappings
azlin list | awk 'NR>2 {if ($2 != "") print $1","$2}' > sessions.csv

# Example output:
# azlin-vm-12345,myproject
# azlin-vm-98765,backend-dev
```

### Import Session Mappings

```bash
# Import session mappings from CSV
while IFS=, read -r vm session; do
    azlin session $vm $session
done < sessions.csv
```

## Integration Examples

### CI/CD Pipeline

```bash
# Set session name based on branch
- name: Label VM
  run: |
    BRANCH=$(echo $GITHUB_REF | cut -d/ -f3)
    azlin session deploy-vm ci-$BRANCH
```

### Dynamic Session Names

```bash
# Use Git branch as session name
BRANCH=$(git rev-parse --abbrev-ref HEAD)
azlin session myvm $BRANCH

# Use date-based sessions
SESSION="experiment-$(date +%Y%m%d)"
azlin session myvm $SESSION
```

### Slack/Teams Notifications

```bash
# Announce session creation
SESSION="ml-training-round-5"
azlin session myvm $SESSION
notify_slack "New training session started: $SESSION (VM: myvm)"
```

## Related Commands

- [`azlin list`](list.md) - View session names for all VMs
- [`azlin connect`](connect.md) - Connect using session name
- [`azlin tag`](tag.md) - Manage VM tags (sessions are stored as tags)
- [`azlin new`](new.md) - Provision VM (set session name after)

## Source Code

- [session_manager.py](https://github.com/rysweet/azlin/blob/main/src/azlin/session_manager.py) - Session management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All VM commands](index.md)
- [Tag Management](tag.md)
- [Shared Home Directories](../../storage/shared-home.md)
