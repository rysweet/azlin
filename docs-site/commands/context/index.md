# Context Commands

Manage kubectl-style contexts for multi-tenant Azure access.

## Overview

Contexts allow you to switch between different Azure subscriptions and tenants without changing environment variables or config files. Perfect for multi-tenant management and environment segregation.

## Available Commands

- [**azlin context create**](create.md) - Create a new context
- [**azlin context list**](list.md) - List all contexts (shows current with *)
- [**azlin context use**](use.md) - Switch to a different context
- [**azlin context delete**](delete.md) - Delete a context
- [**azlin context rename**](rename.md) - Rename a context

## Quick Start

### Create and Use

```bash
# Create production context
azlin context create prod   --subscription xxxx-xxxx-xxxx-xxxx   --tenant yyyy-yyyy-yyyy-yyyy   --auth-profile prod-sp

# Create development context
azlin context create dev   --subscription aaaa-aaaa-aaaa-aaaa   --tenant bbbb-bbbb-bbbb-bbbb

# Switch contexts
azlin context use prod
azlin list  # Shows production VMs

azlin context use dev
azlin list  # Shows development VMs
```

### View Contexts

```bash
# List all contexts
azlin context list

# Show current context
azlin context current
```

## Use Cases

### Multi-Tenant Management

```bash
# Client A
azlin context create client-a   --subscription client-a-sub   --tenant client-a-tenant

# Client B
azlin context create client-b   --subscription client-b-sub   --tenant client-b-tenant

# Switch between clients
azlin context use client-a
azlin context use client-b
```

### Environment Separation

```bash
# Create contexts for each environment
azlin context create dev --subscription dev-sub --tenant company-tenant
azlin context create staging --subscription staging-sub --tenant company-tenant
azlin context create prod --subscription prod-sub --tenant company-tenant --auth-profile prod-sp
```

## Related Commands

- [azlin auth](../auth/index.md) - Service principal authentication
- [azlin list](../vm/list.md) - List VMs in current context

## See Also

- [Multi-Context](../../advanced/multi-context.md)
- [Multi-Tenant Context](../../authentication/multi-tenant.md)
