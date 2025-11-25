# Auth Commands

Manage service principal authentication profiles.

## Overview

Service principals enable automated Azure authentication without interactive login. Use these commands to set up and manage authentication profiles for CI/CD, automation, and production access.

## Available Commands

- [**azlin auth setup**](setup.md) - Set up service principal authentication profile
- [**azlin auth list**](list.md) - List available authentication profiles
- [**azlin auth show**](show.md) - Show authentication profile details
- [**azlin auth test**](test.md) - Test service principal authentication
- [**azlin auth remove**](remove.md) - Remove authentication profile

## Quick Start

### Setup Profile

```bash
# Create auth profile
azlin auth setup --profile production

# Test authentication
azlin auth test --profile production
```

### Use with Commands

```bash
# Use profile with any command
azlin list --auth-profile production
azlin new --name prod-vm --auth-profile production

# Or via context
azlin context create prod   --subscription prod-sub   --tenant prod-tenant   --auth-profile production
```

## Use Cases

### CI/CD Integration

```bash
# Set up CI profile
azlin auth setup --profile ci-cd

# In CI pipeline
export AZLIN_AUTH_PROFILE=ci-cd
azlin new --name build-$BUILD_ID
azlin connect build-$BUILD_ID --command './run-tests.sh'
azlin kill build-$BUILD_ID
```

### Production Automation

```bash
# Production profile for automation
azlin auth setup --profile prod-automation

# Automated tasks
azlin batch stop --tag 'env=dev' --auth-profile prod-automation
```

## Related Commands

- [azlin context](../context/index.md) - Multi-tenant context management

## See Also

- [Service Principal](../../authentication/service-principal.md)
- [GitHub Runners](../../advanced/github-runners.md)
