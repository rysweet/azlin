# azlin do

Execute natural language azlin commands using AI.

## Synopsis

```bash
azlin do "<natural language request>" [OPTIONS]
```

## Description

AI-powered natural language interface for azlin. Understands plain English and automatically translates to appropriate azlin commands.

Requires: `ANTHROPIC_API_KEY` environment variable

## Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview actions without executing |
| `--yes, -y` | Skip confirmation prompts |
| `--verbose, -v` | Show detailed parsing |
| `--rg NAME` | Specify resource group |
| `-h, --help` | Show help |

## Examples

### VM Management

```bash
# Create VMs
azlin do "create a new vm called Sam"
azlin do "create 5 test vms"

# List and status
azlin do "show me all my vms"
azlin do "what is the status of my vms"

# Start/stop
azlin do "start my development vm"
azlin do "stop all test vms"
```

### Cost & Monitoring

```bash
# Costs
azlin do "what are my azure costs"
azlin do "show me costs by vm"
azlin do "what's my spending this month"

# Monitoring
azlin do "show me running processes"
azlin do "which vms are idle"
```

### File Operations

```bash
# Sync
azlin do "sync all my vms"
azlin do "sync my home directory to vm Sam"

# Copy
azlin do "copy myproject to the vm"
```

### Resource Cleanup

```bash
# With dry-run first
azlin do "delete vm called test-123" --dry-run
azlin do "delete vm called test-123"

# Bulk operations
azlin do "delete all test vms"
azlin do "stop idle vms to save costs"
```

### Complex Operations

```bash
azlin do "create 5 test vms and sync them all"
azlin do "set up a new development environment"
azlin do "show costs and stop any idle vms"
```

## How It Works

1. **Parse**: AI parses natural language request
2. **Plan**: Identifies required azlin commands
3. **Confirm**: Shows plan (unless --yes)
4. **Execute**: Runs commands
5. **Report**: Shows results

## Output Example

```
Understanding request: "create a new vm called Sam"

Plan:
  1. azlin new --name Sam

Confidence: 98%

Execute these commands? [Y/n]: y

Creating VM 'Sam'...
✓ VM created successfully

VM Details:
  Name: Sam
  IP: 20.123.45.67
  Status: Running
```

## Safety Features

- **Confirmation**: Shows plan before executing (unless --yes)
- **High Accuracy**: 95-100% confidence on VM operations
- **Dry-run Mode**: Preview without executing
- **Graceful Errors**: Clear error messages for invalid requests

## API Key Setup

```bash
# Get API key from https://console.anthropic.com/
export ANTHROPIC_API_KEY=your-key-here

# Or add to ~/.bashrc
echo 'export ANTHROPIC_API_KEY=your-key-here' >> ~/.bashrc
```

## Related Commands

- [azlin doit](../doit/index.md) - Natural language infrastructure deployment
- [azlin autopilot](../autopilot/index.md) - Automated cost optimization
