# Multi-Tenant Context Management

azlin supports kubectl-style context management for seamless switching between multiple Azure tenants and subscriptions.

## What are Contexts?

A context bundles together:
- Azure tenant ID
- Azure subscription ID
- Optional authentication profile
- Resource group and region defaults

This allows you to manage VMs across multiple Azure environments (dev, staging, production) or multiple customer tenants without changing environment variables or running `az account set`.

## Quick Start

```bash
# Create contexts for different environments
azlin context create dev \
  --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

azlin context create prod \
  --subscription zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz \
  --tenant wwwwwwww-wwww-wwww-wwww-wwwwwwwwwwww \
  --auth-profile prod-sp

# List all contexts
azlin context list

# Switch between contexts
azlin context use dev
azlin list  # Shows VMs in dev subscription

azlin context use prod
azlin list  # Shows VMs in prod subscription

# Check current context
azlin context current
```

## All Commands

### azlin context list
List all contexts with rich table formatting showing subscription, tenant, and auth profile.

### azlin context current
Show details of the currently active context.

### azlin context use <name>
Switch to a different context. This updates both azlin's config and Azure CLI's active subscription.

### azlin context create <name>
Create a new context with the specified subscription and tenant.

**Options:**
- `--subscription <uuid>` (required) - Azure subscription ID
- `--tenant <uuid>` (required) - Azure tenant ID
- `--auth-profile <name>` (optional) - Service principal profile to use
- `--description <text>` (optional) - Human-readable description
- `--set-current` (optional) - Set as active context immediately

### azlin context delete <name>
Delete a context. Cannot delete the currently active context.

### azlin context rename <old-name> <new-name>
Rename a context while preserving all configuration.

### azlin context migrate
Auto-migrate from legacy config format (with `default_subscription_id`) to new context format.

## Use Cases

### Multi-Environment Teams

Manage separate dev, staging, and production environments:

```bash
# Setup once
azlin context create dev --subscription <dev-sub> --tenant <tenant>
azlin context create staging --subscription <staging-sub> --tenant <tenant>
azlin context create prod --subscription <prod-sub> --tenant <tenant>

# Daily work: switch as needed
azlin context use dev && azlin new feature-vm
azlin context use staging && azlin sync feature-vm
azlin context use prod && azlin list
```

### Multi-Customer Consultants

Work with different Azure tenants per customer:

```bash
# Different tenants per customer
azlin context create client-a --subscription <a-sub> --tenant <a-tenant>
azlin context create client-b --subscription <b-sub> --tenant <b-tenant> --auth-profile client-b-sp

# Switch between customers
azlin context use client-a
azlin new test-vm  # Creates in client-a's subscription

azlin context use client-b
azlin connect prod-vm  # Connects to VM in client-b's subscription
```

### Cross-Tenant Operations

Search and manage VMs across multiple tenants:

```bash
# Create contexts for each tenant
azlin context create tenant1 --subscription <uuid1> --tenant <tenant1>
azlin context create tenant2 --subscription <uuid2> --tenant <tenant2>

# Switch between them
azlin context use tenant1 && azlin list
azlin context use tenant2 && azlin list
```

## Configuration

Contexts are stored in `~/.azlin/config.toml`:

```toml
# Current active context
[contexts]
current = "production"

# Context definitions
[contexts.definitions.production]
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
tenant_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
auth_profile = "prod-sp"  # Optional - links to service principal

[contexts.definitions.development]
subscription_id = "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
tenant_id = "wwwwwwww-wwww-wwww-wwww-wwwwwwwwwwww"
# No auth_profile = uses Azure CLI authentication
```

## Security

- **No secrets stored**: Only references to auth profiles
- **UUID validation**: All subscription/tenant IDs validated
- **Name sanitization**: Context names restricted to alphanumeric + hyphen/underscore
- **Secure permissions**: Config files enforced to 0600 (owner read/write only)

## Backward Compatibility

Existing configs work without modification. If you have old-style config with `default_subscription_id`, you can optionally run `azlin context migrate` to convert to the new format.

The migration creates a "default" context from your legacy settings and is completely optional.

## Troubleshooting

### Context switching doesn't change subscription

If `azlin context use <name>` doesn't switch the Azure CLI subscription, manually run:
```bash
az account set --subscription <subscription-id>
```

### Context not found error

List available contexts:
```bash
azlin context list
```

Create a new context if needed:
```bash
azlin context create <name> --subscription <uuid> --tenant <uuid>
```
