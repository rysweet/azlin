# azlin help

Show help for azlin commands.

## Synopsis

```bash
azlin help [COMMAND_NAME]
```

## Description

Display general help or detailed help for a specific command. Shows usage, options, examples, and related commands.

## Usage

### General Help

```bash
# Show all azlin commands
azlin help
```

Shows complete command listing with descriptions.

### Command-Specific Help

```bash
# Show help for specific command
azlin help connect
azlin help list
azlin help new
```

Displays detailed information including:
- Command syntax
- Available options
- Usage examples
- Related commands

## Examples

### View All Commands

```bash
azlin help
```

**Output:**
```
azlin - Azure Ubuntu VM provisioning and management

NATURAL LANGUAGE COMMANDS (AI-POWERED):
  do            Execute commands using natural language

VM LIFECYCLE COMMANDS:
  new           Provision a new VM
  clone         Clone a VM with its home directory
  list          List VMs in resource group
  ...
```

### Get Help for Specific Commands

```bash
# VM creation
azlin help new

# SSH connection
azlin help connect

# Resource cleanup
azlin help kill
```

### Quick Reference

```bash
# Alternative: Use --help flag
azlin connect --help
azlin new --help
azlin list --help
```

Both `azlin help <command>` and `azlin <command> --help` show the same information.

## Common Help Queries

### VM Management

```bash
azlin help new        # Create VMs
azlin help list       # List VMs
azlin help status     # VM status
azlin help start      # Start VMs
azlin help stop       # Stop VMs
azlin help kill       # Delete VMs
```

### Connection

```bash
azlin help connect    # SSH to VM
azlin help code       # VS Code integration
azlin help bastion    # Bastion hosts
```

### Storage & Files

```bash
azlin help storage    # NFS storage
azlin help sync       # File sync
azlin help cp         # File copy
```

### Monitoring

```bash
azlin help cost       # Cost estimates
azlin help w          # Who's logged in
azlin help ps         # Running processes
azlin help top        # System resources
```

### Advanced

```bash
azlin help do         # AI commands
azlin help batch      # Batch operations
azlin help compose    # Multi-VM orchestration
```

## Help Output Format

Each command help includes:

1. **Usage** - Command syntax
2. **Description** - What the command does
3. **Arguments** - Required parameters
4. **Options** - Optional flags
5. **Examples** - Common usage patterns

## Related Commands

All commands support the `--help` flag:

```bash
azlin <command> --help
azlin <command> <subcommand> --help
```

## Tips

### Find Commands by Category

Use `azlin help` and search the output:

```bash
azlin help | grep -i "storage"
azlin help | grep -i "cost"
azlin help | grep -i "delete"
```

### Quick Command Reference

```bash
# Most used commands
azlin help new        # Create VM
azlin help list       # List VMs
azlin help connect    # SSH to VM
azlin help stop       # Stop VM
azlin help kill       # Delete VM
```

### Get Started

```bash
# First-time users
azlin help new        # Learn to create VMs
azlin help            # See all commands
```

## See Also

- [Quick Start](../../getting-started/quickstart.md)
- [Command Reference](../index.md)
- [azlin CLI](../../index.md)
