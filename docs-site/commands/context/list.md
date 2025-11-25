# azlin context list

**List all available Azure contexts**

## Description

The `azlin context list` command displays all configured contexts with their subscription and tenant IDs. The current active context is marked with an asterisk (*), making it easy to see which context your azlin commands will use.

This command helps you understand what Azure environments you have configured and quickly identify your current working context.

## Usage

```bash
azlin context list [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--config TEXT` | Path | Custom config file path (default: `~/.azlin/config.toml`) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Usage

```bash
# List all contexts
azlin context list

# Example output:
# * production    (subscription: xxxxxxxx..., tenant: yyyyyyyy...)
#   dev           (subscription: aaaaaaaa..., tenant: bbbbbbbb...)
#   staging       (subscription: cccccccc..., tenant: dddddddd...)
```

### Using Custom Config

```bash
# List contexts from custom config file
azlin context list --config ~/custom-config.toml

# List contexts from team config
azlin context list --config ~/.azlin/team-config.toml
```

### Common Workflows

```bash
# Check available contexts before switching
azlin context list

# See current context (marked with *)
azlin context list

# After creating new context, verify it exists
azlin context create newcontext --subscription xxx --tenant yyy
azlin context list

# Check contexts across multiple config files
azlin context list --config ~/.azlin/config-a.toml
azlin context list --config ~/.azlin/config-b.toml
```

## Output Format

The command displays contexts in the following format:

```
[*] NAME    (subscription: SUBSCRIPTION_ID, tenant: TENANT_ID[, profile: AUTH_PROFILE])
```

Where:
- `*` - Indicates the current active context
- `NAME` - Context name
- `SUBSCRIPTION_ID` - Azure subscription ID (first 8 characters shown)
- `TENANT_ID` - Azure tenant ID (first 8 characters shown)
- `AUTH_PROFILE` - (Optional) Associated service principal authentication profile

Example output:

```
* production    (subscription: xxxxxxxx-xxxx-..., tenant: yyyyyyyy-yyyy-..., profile: prod-sp)
  dev           (subscription: aaaaaaaa-aaaa-..., tenant: bbbbbbbb-bbbb-...)
  staging       (subscription: cccccccc-cccc-..., tenant: dddddddd-dddd-...)
  test          (subscription: eeeeeeee-eeee-..., tenant: ffffffff-ffff-...)
```

## Understanding Context Information

### Subscription ID
The subscription ID determines which Azure subscription azlin will use for:
- Creating VMs and resources
- Listing VMs
- Managing storage accounts
- All Azure resource operations

### Tenant ID
The tenant ID determines which Azure Active Directory (AAD) tenant to authenticate against. Important for:
- Multi-tenant organizations
- Guest access scenarios
- Service principal authentication

### Auth Profile
(Optional) The name of a service principal authentication profile to use. If specified:
- azlin will use this profile's credentials
- No interactive Azure CLI login needed
- Useful for CI/CD and automation

## Troubleshooting

### No Contexts Listed

**Symptoms:** Command shows empty list or "No contexts found"

**Solutions:**
```bash
# Create your first context
azlin context create default \
  --subscription $(az account show --query id -o tsv) \
  --tenant $(az account show --query tenantId -o tsv)

# Verify it was created
azlin context list

# Or migrate from legacy config
azlin context migrate
```

### Current Context Not Marked

**Symptoms:** No asterisk (*) shown, or wrong context marked

**Solutions:**
```bash
# Show current context explicitly
azlin context current

# Set a context as current
azlin context use CONTEXT-NAME

# Verify
azlin context list
```

### Config File Not Found

**Symptoms:** Error reading config file

**Solutions:**
```bash
# Check if config file exists
ls -la ~/.azlin/config.toml

# Create config directory if needed
mkdir -p ~/.azlin

# Initialize with a context
azlin context create default \
  --subscription YOUR-SUB-ID \
  --tenant YOUR-TENANT-ID
```

### Truncated IDs Hard to Distinguish

**Symptoms:** Multiple contexts with similar looking IDs

**Solutions:**
```bash
# Show full details for specific context
azlin context current

# Or check config file directly
cat ~/.azlin/config.toml

# Use descriptive context names
azlin context rename xxxxxxxx production
azlin context rename yyyyyyyy development
```

## Best Practices

### Regular Context Checks

```bash
# Before major operations, verify your context
azlin context list
azlin new --name important-vm  # Safe - you know which subscription

# Make it a habit before destructive operations
azlin context list
azlin destroy my-vm  # Safe - confirmed correct context
```

### Naming Contexts

Use clear, descriptive names that indicate purpose:

```bash
# Good examples
production-us-east
dev-team-a
staging-europe
test-ephemeral

# Less clear
context1
temp
my-context
```

### Context Documentation

```bash
# Document your contexts in team wiki or README
azlin context list > contexts.txt

# Share context setup with team
cat ~/.azlin/config.toml | grep -A 3 "\[contexts\."
```

## Integration Examples

### Scripting

```bash
#!/bin/bash
# Check available contexts before operation
echo "Available contexts:"
azlin context list

# Parse current context (example)
CURRENT=$(azlin context list | grep "^\*" | awk '{print $2}')
echo "Operating in context: $CURRENT"

# Proceed with operations
azlin new --name script-vm
```

### Pre-flight Checks

```bash
# Add to your workflow
check_context() {
  echo "Current contexts:"
  azlin context list
  read -p "Proceed with current context? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
}

check_context
azlin new --name safe-vm
```

## Related Commands

- [`azlin context use`](use.md) - Switch to a different context
- [`azlin context current`](show.md) - Show current active context
- [`azlin context create`](create.md) - Create a new context
- [`azlin context delete`](delete.md) - Delete a context
- [`azlin context rename`](rename.md) - Rename a context
- [`azlin auth list`](../auth/list.md) - List authentication profiles

## Source Code

- [context.py](https://github.com/rysweet/azlin/blob/main/src/azlin/context.py) - Context management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All context commands](index.md)
- [Authentication Profiles](../../authentication/profiles.md)
- [Multi-Tenant Context](../../authentication/multi-tenant.md)
