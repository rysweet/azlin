# azlin context migrate

Migrate from legacy config format to contexts.

## Synopsis

```bash
azlin context migrate
```

## Description

Migrates old azlin configuration to new context-based system. Automatically creates default context from existing settings.

## Examples

```bash
# Migrate configuration
azlin context migrate

# Verify migration
azlin context list
```

## What Gets Migrated

- Subscription ID
- Tenant ID
- Resource group
- Region defaults
- Authentication profiles

## Related Commands

- [azlin context list](list.md) - List contexts after migration
