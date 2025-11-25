# azlin context current

**Show current active Azure context**

## Description

The `azlin context current` command displays the name and details of the currently active context. This helps you verify which Azure subscription and tenant your azlin commands will operate in.

## Usage

```bash
azlin context current [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--config TEXT` | Path | Custom config file path (default: `~/.azlin/config.toml`) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Usage

```bash
# Show current context
azlin context current

# Example output:
# Current context: production
#   Subscription: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
#   Tenant: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
#   Auth Profile: prod-sp
```

### Using Custom Config

```bash
# Check current context in custom config
azlin context current --config ~/custom-config.toml

# Check current context in team config
azlin context current --config ~/.azlin/team-config.toml
```

### Workflow Integration

```bash
# Verify context before operations
azlin context current
azlin new --name my-vm

# Switch and verify
azlin context use development
azlin context current
azlin new --name dev-vm

# Script usage
CURRENT_CTX=$(azlin context current | head -1 | awk '{print $3}')
echo "Operating in context: $CURRENT_CTX"
```

## Output Format

The command displays full context details:

```
Current context: CONTEXT_NAME
  Subscription: SUBSCRIPTION_ID
  Tenant: TENANT_ID
  [Auth Profile: PROFILE_NAME]
```

Example output:

```
Current context: production
  Subscription: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  Tenant: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
  Auth Profile: prod-sp
```

## What This Means

### Current Context
The active context name determines which Azure environment all azlin commands will target.

### Subscription ID
All Azure resources (VMs, storage, networks) will be created in and managed from this subscription.

### Tenant ID
Authentication will be performed against this Azure Active Directory tenant.

### Auth Profile
(Optional) If set, azlin will use this service principal for authentication instead of interactive Azure CLI login.

## Troubleshooting

### No Active Context

**Symptoms:** "No active context set" or similar error

**Solutions:**
```bash
# List available contexts
azlin context list

# Set an active context
azlin context use CONTEXT-NAME

# Or create and set a default context
azlin context create default \
  --subscription $(az account show --query id -o tsv) \
  --tenant $(az account show --query tenantId -o tsv)
azlin context use default
```

### Wrong Context Active

**Symptoms:** Operating in unexpected subscription/tenant

**Solutions:**
```bash
# Check current context
azlin context current

# List available contexts
azlin context list

# Switch to correct context
azlin context use CORRECT-CONTEXT

# Verify
azlin context current
```

### Context Not Found

**Symptoms:** Error showing current context

**Solutions:**
```bash
# Check config file exists
ls -la ~/.azlin/config.toml

# List contexts to see what's available
azlin context list

# Reset to a known context
azlin context use KNOWN-CONTEXT
```

## Best Practices

### Always Verify Before Operations

Make it a habit to check your context before critical operations:

```bash
# Before creating VMs
azlin context current
azlin new --name important-vm

# Before deleting resources
azlin context current
azlin destroy my-vm

# Before batch operations
azlin context current
azlin batch stop --all
```

### Add to Shell Prompt

Show current context in your shell prompt:

```bash
# Add to ~/.bashrc or ~/.zshrc
function azlin_context() {
  azlin context current 2>/dev/null | head -1 | awk '{print $3}'
}

# Use in prompt
PS1='[$(azlin_context)] $ '
```

### Pre-Flight Scripts

```bash
#!/bin/bash
# Require context confirmation before operations

echo "Current context:"
azlin context current
echo
read -p "Is this the correct context? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Operation cancelled"
  exit 1
fi

# Proceed with operation
azlin "$@"
```

### Context Logging

```bash
# Log context for audit trail
azlin context current >> ~/.azlin/operation-log.txt
echo "$(date): Running azlin new" >> ~/.azlin/operation-log.txt
azlin new --name my-vm
```

## Scripting Examples

### Context Check Function

```bash
#!/bin/bash

check_context() {
  local expected="$1"
  local current=$(azlin context current | head -1 | awk '{print $3}')

  if [ "$current" != "$expected" ]; then
    echo "ERROR: Expected context '$expected', but current is '$current'"
    exit 1
  fi
}

# Use in scripts
check_context "production"
azlin new --name prod-vm
```

### Multi-Context Operations

```bash
#!/bin/bash
# Operate across multiple contexts

CONTEXTS=("dev" "staging" "production")

for ctx in "${CONTEXTS[@]}"; do
  echo "Switching to $ctx..."
  azlin context use "$ctx"

  echo "Current context:"
  azlin context current

  echo "Listing VMs:"
  azlin list
  echo "---"
done
```

### Context Validation

```bash
#!/bin/bash
# Validate context before destructive operations

CURRENT=$(azlin context current | head -1 | awk '{print $3}')

if [ "$CURRENT" == "production" ]; then
  echo "WARNING: You are in PRODUCTION context!"
  echo "This operation could affect production resources."
  read -p "Are you ABSOLUTELY sure? (type 'yes' to proceed): " confirm
  if [ "$confirm" != "yes" ]; then
    echo "Operation cancelled"
    exit 1
  fi
fi

echo "Proceeding with operation..."
```

## Integration Examples

### CI/CD Pipelines

```yaml
# GitHub Actions example
steps:
  - name: Verify Context
    run: |
      azlin context use ci-automation
      azlin context current

  - name: Provision VM
    run: azlin new --name ci-vm-${{ github.run_number }} --yes
```

### Makefile Integration

```makefile
.PHONY: check-context
check-context:
	@echo "Current azlin context:"
	@azlin context current
	@read -p "Press enter to continue..."

.PHONY: deploy
deploy: check-context
	azlin new --name $(VM_NAME)
```

## Related Commands

- [`azlin context list`](list.md) - List all available contexts
- [`azlin context use`](use.md) - Switch to a different context
- [`azlin context create`](create.md) - Create a new context
- [`azlin context delete`](delete.md) - Delete a context
- [`azlin context rename`](rename.md) - Rename a context

## Source Code

- [context.py](https://github.com/rysweet/azlin/blob/main/src/azlin/context.py) - Context management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All context commands](index.md)
- [Authentication Profiles](../../authentication/profiles.md)
- [Multi-Tenant Context](../../authentication/multi-tenant.md)
