# Session Management

Label VMs with meaningful session names to track your work and connect easily.

## Quick Start

```bash
# Set session name
azlin session my-vm my-project

# View session name
azlin session my-vm

# Connect by session name
azlin connect my-project

# Clear session name
azlin session my-vm --clear
```

## Overview

Session names are human-readable labels that help you:

- **Track what you're working on** - Label VMs by project/purpose
- **Connect easily** - Use `azlin connect my-project` instead of VM IDs
- **Team coordination** - See what teammates are doing on shared VMs
- **Quick identification** - Sessions appear in `azlin list` output

## Command Reference

```bash
azlin session [OPTIONS] VM_NAME [SESSION_NAME]
```

### Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `VM_NAME` | VM name or identifier | Yes |
| `SESSION_NAME` | Label for this VM/work | No (for viewing) |

### Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Resource group |
| `--clear` | Remove session name |

## Common Usage

### Set Session Name

```bash
# Simple project name
azlin session azlin-vm-12345 my-project

# Descriptive name
azlin session dev-vm backend-api-development

# Team/purpose identifier
azlin session worker-1 data-pipeline-v2
```

**What happens:**

1. Session name stored as VM tag
2. Visible in `azlin list` output
3. Usable with `azlin connect`
4. Persists across VM restarts

### View Session Name

```bash
# Check current session
azlin session azlin-vm-12345
```

**Output:**

```
Session name for azlin-vm-12345: my-project
```

### Connect by Session Name

```bash
# Set session name
azlin session azlin-vm-12345 ml-training

# Connect using session name (anywhere)
azlin connect ml-training
```

**What happens:**

1. Resolves session name to VM name
2. Connects normally via SSH
3. Works from any machine with azlin configured

### Clear Session Name

```bash
# Remove session name
azlin session my-vm --clear
```

## Integration with List

Session names appear in `azlin list`:

```bash
azlin list
```

**Output:**

```
╭──────────────────┬─────────┬──────────────┬─────────┬─────────────────╮
│ Name             │ Status  │ IP Address   │ Region  │ Session         │
├──────────────────┼─────────┼──────────────┼─────────┼─────────────────┤
│ azlin-vm-12345   │ Running │ 20.51.23.145 │ eastus  │ my-project      │
│ dev-environment  │ Running │ 10.0.1.5     │ westus  │ backend-api     │
│ worker-1         │ Running │ 10.0.1.6     │ eastus  │ data-pipeline   │
╰──────────────────┴─────────┴──────────────┴─────────┴─────────────────╯
```

## Naming Conventions

Good session names are:

- **Short and memorable** - `my-project`, `api-dev`, `training-v2`
- **Descriptive** - Indicate what work is being done
- **Lowercase with hyphens** - Easier to type and parse
- **Unique** - Don't reuse names across active VMs

**Examples:**

| Good | Bad | Why |
|------|-----|-----|
| `backend-api` | `BackendAPIProject2024` | Too long, hard to type |
| `ml-training` | `vm` | Not descriptive |
| `data-pipeline` | `The new data pipeline` | Spaces, too long |
| `web-scraper` | `scraper1` | Good - clear purpose |

## Use Cases

### Project-Based Development

```bash
# Assign VMs to projects
azlin session vm-1 project-alpha
azlin session vm-2 project-beta
azlin session vm-3 project-gamma

# Connect to project quickly
azlin connect project-alpha
```

### Team Collaboration

```bash
# Each team member labels their work
azlin session dev-vm-1 sarah-frontend
azlin session dev-vm-2 john-backend
azlin session dev-vm-3 maria-database

# See who's working on what
azlin list
```

### ML/Training Workflows

```bash
# Label training runs
azlin session gpu-vm-1 bert-training-run-1
azlin session gpu-vm-2 gpt-training-run-2

# Easy identification
azlin list --tag project=ml
```

### Temporary Work

```bash
# Set temporary session
azlin session test-vm debugging-issue-123

# Clear when done
azlin session test-vm --clear
```

## Technical Details

### Storage Mechanism

Session names are stored as Azure VM tags:

```bash
# View all VM tags (includes session)
azlin tag list my-vm
```

**Output:**

```
Tags for my-vm:
  azlin_session: my-project
  environment: development
  team: backend
```

### Resolution Order

When connecting by identifier, azlin checks:

1. VM name (exact match)
2. Session name (resolves to VM)
3. IP address (direct connection)

### Persistence

Session names persist:

- Across VM restarts
- Across VM stop/start
- Until explicitly cleared
- Even after azlin reinstall (stored in Azure)

## Limitations

- **No spaces allowed** - Use hyphens or underscores
- **Not globally unique** - Different VMs can have same session name (avoid this)
- **Case-sensitive** - `My-Project` ≠ `my-project`
- **Length limit** - Azure tag value limit is 256 characters

## Troubleshooting

### Can't Set Session Name

```bash
# Check VM exists
azlin list --all

# Check resource group
azlin session my-vm my-project --rg <rg>

# Verify Azure permissions
az vm tag -h
```

### Can't Connect by Session Name

```bash
# Verify session name is set
azlin session my-vm

# List all VMs to see sessions
azlin list

# Use VM name instead
azlin connect my-vm
```

### Session Name Conflict

```bash
# If multiple VMs have same session, you'll get error
# Clear duplicate sessions:
azlin session vm-2 --clear

# Or rename:
azlin session vm-2 unique-name
```

## Related Commands

- [`azlin list`](listing.md) - View session names
- [`azlin connect`](connecting.md) - Connect by session
- [`azlin tag`](../commands/vm/tag.md) - Manage all VM tags
- [`azlin new`](creating.md) - Create new VM

## Source Code

- [Session Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L700)
- [Tag Management](https://github.com/rysweet/azlin/blob/main/azlin/tags.py)

---

*Last updated: 2025-11-24*
