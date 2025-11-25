# azlin context use

**Switch to a different Azure context**

## Description

The `azlin context use` command sets the specified context as the current active context. All subsequent azlin commands will use this context's subscription and tenant IDs for Azure operations.

Contexts provide kubectl-style multi-tenant Azure access, allowing you to easily switch between different Azure subscriptions, tenants, and authentication profiles without changing environment variables or configuration files.

## Usage

```bash
azlin context use [OPTIONS] NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `NAME` | Name of the context to activate (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--config TEXT` | Path | Custom config file path (default: `~/.azlin/config.toml`) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Context Switching

```bash
# Switch to production context
azlin context use production

# Switch to development context
azlin context use dev

# Switch to staging context
azlin context use staging
```

### Using Custom Config File

```bash
# Use context from custom config location
azlin context use production --config ~/custom-config.toml

# Switch between team configs
azlin context use team-a --config ~/.azlin/team-a-config.toml
```

### Workflow Examples

```bash
# List available contexts
azlin context list

# Switch to production
azlin context use production

# Verify current context
azlin context current

# Provision VM in production subscription
azlin new --name prod-vm

# Switch back to dev
azlin context use dev

# Provision VM in dev subscription
azlin new --name dev-vm
```

## How It Works

When you run `azlin context use NAME`:

1. **Validation** - Checks that the context exists in configuration
2. **Activation** - Sets the context as the current active context
3. **Persistence** - Saves the current context selection to config file
4. **Immediate Effect** - All subsequent commands use the new context

The context configuration is stored in `~/.azlin/config.toml` under the `[contexts]` section.

## Context Structure

Each context contains:

- **subscription_id** - Azure subscription ID
- **tenant_id** - Azure tenant ID
- **auth_profile** - (Optional) Service principal authentication profile name

Example context in config:

```toml
[contexts.production]
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
tenant_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
auth_profile = "prod-sp"

[contexts.dev]
subscription_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
tenant_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
```

## Troubleshooting

### Context Not Found

**Symptoms:** Error "Context 'NAME' not found"

**Solutions:**
```bash
# List available contexts
azlin context list

# Create the context first
azlin context create NAME \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
```

### Authentication Fails After Switching

**Symptoms:** Azure authentication errors after switching contexts

**Solutions:**
```bash
# Verify context is set correctly
azlin context current

# Test authentication
azlin auth test

# If using service principal, verify auth profile exists
azlin auth list

# Re-authenticate with Azure CLI
az login --tenant YOUR-TENANT-ID
```

### Wrong Resources Appearing

**Symptoms:** Seeing VMs or resources from wrong subscription

**Solutions:**
```bash
# Verify current context
azlin context current

# Check which subscription Azure CLI is using
az account show

# Switch to correct context
azlin context use CORRECT-CONTEXT

# Verify again
azlin context current
```

## Best Practices

### Naming Conventions

Use clear, descriptive context names:

```bash
# Good naming
azlin context use prod-us-east
azlin context use dev-team-a
azlin context use staging-europe

# Avoid ambiguous names
azlin context use context1  # Bad
azlin context use temp      # Bad
```

### Team Workflows

```bash
# Personal contexts
azlin context use personal-dev
azlin context use personal-test

# Team contexts
azlin context use team-shared-dev
azlin context use team-shared-staging
azlin context use team-shared-prod
```

### Multi-Tenant Organizations

```bash
# Client A contexts
azlin context use clienta-prod
azlin context use clienta-dev

# Client B contexts
azlin context use clientb-prod
azlin context use clientb-dev

# Internal contexts
azlin context use internal-prod
azlin context use internal-dev
```

## Related Commands

- [`azlin context list`](list.md) - List all available contexts
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
