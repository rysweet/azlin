# AI-Powered Commands

Natural language interface for azlin using Claude AI.

## Overview

Execute azlin commands using natural language. No need to remember exact syntax - just describe what you want in plain English.

## Available Commands

### Natural Language Interface

- [**azlin do**](do.md) - Execute commands using natural language
  - VM management with plain English
  - Cost analysis and optimization
  - Resource cleanup
  - File operations

## Requirements

Set up your Anthropic API key:

```bash
# Get API key from https://console.anthropic.com/
export ANTHROPIC_API_KEY=your-key-here

# Or add to shell profile
echo 'export ANTHROPIC_API_KEY=your-key-here' >> ~/.bashrc
source ~/.bashrc
```

## Quick Start Examples

### VM Management

```bash
# Create VMs
azlin do "create a new vm called Sam"
azlin do "create 5 test vms"

# Start/stop
azlin do "start my development vm"
azlin do "stop all idle vms"

# Status
azlin do "show me all my vms"
azlin do "what vms are running"
```

### Cost Management

```bash
# View costs
azlin do "what are my azure costs"
azlin do "show me costs by vm"
azlin do "what's my spending this month"

# Optimization
azlin do "stop expensive vms"
azlin do "delete vms costing more than $5/day"
```

### File Operations

```bash
# Sync
azlin do "sync all my vms"
azlin do "sync my home directory to vm Sam"

# Copy
azlin do "copy myproject to the vm"
azlin do "upload this folder to all test vms"
```

### Resource Cleanup

```bash
# Safe deletion with dry-run
azlin do "delete vm called test-123" --dry-run
azlin do "delete vm called test-123"

# Bulk cleanup
azlin do "delete all test vms"
azlin do "remove vms older than 30 days"
```

## How It Works

The `azlin do` command uses Claude AI to:

1. **Parse** your natural language request
2. **Plan** the appropriate azlin commands
3. **Confirm** actions before executing (unless --yes)
4. **Execute** commands
5. **Report** results

## Example Session

```bash
$ azlin do "create a new vm called Sam and sync my code to it"

Understanding request: "create a new vm called Sam and sync my code to it"

Plan:
  1. azlin new --name Sam
  2. azlin batch sync Sam

Confidence: 98%

Execute these commands? [Y/n]: y

Creating VM 'Sam'...
✓ VM created successfully (Sam)
  IP: 20.123.45.67
  Status: Running

Syncing to Sam...
✓ Sync complete (1.2 GB in 45s)

All operations completed successfully.
```

## Safety Features

### Confirmation Required

By default, commands require confirmation:

```bash
$ azlin do "delete all test vms"

Plan:
  1. azlin kill test-vm-1
  2. azlin kill test-vm-2
  3. azlin kill test-vm-3

⚠ This will DELETE 3 VMs permanently!

Confirm deletion? [y/N]:
```

### Dry-Run Mode

Preview without executing:

```bash
$ azlin do "stop all vms" --dry-run

DRY-RUN MODE - No changes will be made

Plan:
  1. azlin stop vm-1
  2. azlin stop vm-2
  3. azlin stop vm-3

Would stop 3 VMs (estimated savings: $12.50/day)
```

### Skip Confirmation

For automation:

```bash
# Skip confirmation prompts
azlin do "start dev-vm" --yes

# Combine with dry-run for safe testing
azlin do "cleanup resources" --dry-run --yes
```

## Supported Operations

### VM Lifecycle

- Create VMs with names and configurations
- Start and stop VMs
- Delete VMs individually or in bulk
- Clone VMs with new names
- List and filter VMs

### Monitoring

- View VM status
- Check running processes
- Monitor resource usage
- View costs and spending

### File Management

- Sync home directories
- Copy files and folders
- Upload and download content
- Batch file operations

### Cost Optimization

- Identify expensive resources
- Stop idle VMs
- Delete unused VMs
- View cost breakdowns

## Best Practices

### Be Specific

```bash
# Good: Specific VM name
azlin do "start vm called dev-server"

# Less specific: May need clarification
azlin do "start the development one"
```

### Use Dry-Run for Destructive Operations

```bash
# Always test deletions first
azlin do "delete old test vms" --dry-run
azlin do "delete old test vms"
```

### Combine Operations

```bash
# Multi-step operations in one command
azlin do "create vm called api-server and sync the backend folder"
```

### Check Costs Regularly

```bash
# Monitor spending
azlin do "show my costs this week"
azlin do "which vms cost the most"
```

## Limitations

### What Works Well

- VM management operations
- Cost queries and analysis
- File sync and copy operations
- Resource listing and status
- Start/stop/delete operations

### What Needs Manual Commands

- Complex networking configuration
- Custom VM sizes with specific requirements
- Advanced storage configuration
- Detailed tagging operations

For complex operations, use direct azlin commands with full control.

## Related Commands

- [azlin doit](../doit/index.md) - Natural language infrastructure deployment
- [azlin autopilot](../autopilot/index.md) - Automated cost optimization
- [azlin new](../vm/new.md) - Direct VM creation
- [azlin batch](../batch/index.md) - Batch operations

## See Also

- [Quick Start](../../getting-started/quickstart.md)
- [Cost Tracking](../../monitoring/cost.md)
- [AI Command Examples](../../examples/ai-commands.md)
