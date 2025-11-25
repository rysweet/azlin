# azlin context create

Create a new azlin context for multi-tenant Azure environments.

## Synopsis

```bash
azlin context create NAME [OPTIONS]
```

## Description

Creates a new context with the specified subscription and tenant IDs. Contexts enable seamless switching between different Azure subscriptions, making multi-tenant management simple.

Optionally associates an authentication profile for service principal auth.

## Arguments

**NAME** - Context name (required)

## Options

| Option | Description |
|--------|-------------|
| `--subscription, --subscription-id TEXT` | Azure subscription ID (UUID) (required) |
| `--tenant, --tenant-id TEXT` | Azure tenant ID (UUID) (required) |
| `--auth-profile TEXT` | Service principal auth profile name (optional) |
| `--description TEXT` | Human-readable description (optional) |
| `--set-current` | Set as current context after creation |
| `--config TEXT` | Custom config file path |
| `-h, --help` | Show help message |

## Examples

### Basic Context

```bash
# Create basic context
azlin context create staging \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
```

### With Auth Profile

```bash
# Create context with service principal
azlin context create prod \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
  --auth-profile prod-sp
```

Automatically uses the specified auth profile when switching to this context.

### With Description

```bash
# Add description
azlin context create dev \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
  --description "Development environment" \
  --set-current
```

### Set as Current

```bash
# Create and activate immediately
azlin context create test \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
  --set-current
```

## Use Cases

### Multi-Tenant Management

```bash
# Client A
azlin context create client-a \
  --subscription aaaa-aaaa-aaaa-aaaa \
  --tenant tttt-tttt-tttt-tttt \
  --description "Client A Production"

# Client B
azlin context create client-b \
  --subscription bbbb-bbbb-bbbb-bbbb \
  --tenant uuuu-uuuu-uuuu-uuuu \
  --description "Client B Production"

# Switch between clients
azlin context use client-a
azlin list

azlin context use client-b
azlin list
```

### Environment Segregation

```bash
# Development
azlin context create dev \
  --subscription dev-sub-id \
  --tenant company-tenant-id \
  --description "Development VMs"

# Staging
azlin context create staging \
  --subscription staging-sub-id \
  --tenant company-tenant-id \
  --description "Staging VMs"

# Production
azlin context create prod \
  --subscription prod-sub-id \
  --tenant company-tenant-id \
  --auth-profile prod-sp \
  --description "Production VMs"
```

### Service Principal Integration

```bash
# 1. Set up auth profile
azlin auth setup prod-sp

# 2. Create context with auth
azlin context create prod \
  --subscription prod-sub-id \
  --tenant prod-tenant-id \
  --auth-profile prod-sp

# 3. Switch context (uses service principal automatically)
azlin context use prod
azlin list
```

## Context Configuration

### Storage Location

Contexts are stored in:
```
~/.azlin/contexts.toml
```

### Format

```toml
[contexts.prod]
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
tenant_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
auth_profile = "prod-sp"
description = "Production environment"

[contexts.dev]
subscription_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
tenant_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
description = "Development environment"
```

## Finding IDs

### Subscription ID

```bash
# List subscriptions
az account list --output table

# Get current subscription
az account show --query id -o tsv
```

### Tenant ID

```bash
# Get tenant ID
az account show --query tenantId -o tsv

# List all tenants
az account tenant list --output table
```

## Troubleshooting

### Invalid Subscription ID

```bash
# Verify subscription exists
az account list --output table

# Check access
az account set --subscription your-sub-id
az account show
```

### Invalid Tenant ID

```bash
# List accessible tenants
az account tenant list

# Verify tenant access
az login --tenant your-tenant-id
```

### Auth Profile Not Found

```bash
# List auth profiles
azlin auth list

# Create auth profile first
azlin auth setup my-profile

# Then create context
azlin context create my-context \
  --subscription sub-id \
  --tenant tenant-id \
  --auth-profile my-profile
```

### Context Already Exists

```bash
# List existing contexts
azlin context list

# Use different name or delete existing
azlin context delete old-context
azlin context create new-context ...
```

## Best Practices

### Naming Conventions

```bash
# Environment-based
azlin context create dev
azlin context create staging
azlin context create prod

# Client-based
azlin context create acme-prod
azlin context create contoso-dev

# Purpose-based
azlin context create ci-builds
azlin context create ml-training
```

### Use Descriptions

```bash
# Makes context list more readable
azlin context create prod \
  --subscription ... \
  --tenant ... \
  --description "Production - Client A - US East"
```

### Service Principals for Production

```bash
# Production should use service principal
azlin auth setup prod-sp
azlin context create prod \
  --subscription prod-sub \
  --tenant prod-tenant \
  --auth-profile prod-sp
```

### Set Current for Active Work

```bash
# Immediately activate for new environment
azlin context create dev --subscription ... --set-current

# Start working
azlin list
azlin new --name dev-vm
```

## Related Commands

- [azlin context list](list.md) - List all contexts
- [azlin context use](use.md) - Switch active context
- [azlin context list](list.md) - List all contexts
- [azlin context delete](delete.md) - Delete context
- [azlin auth setup](../auth/setup.md) - Configure service principal

## See Also

- [Multi-Context](../../advanced/multi-context.md)
- [Multi-Tenant Context](../../authentication/multi-tenant.md)
- [Service Principal](../../authentication/service-principal.md)
