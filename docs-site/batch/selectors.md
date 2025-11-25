# VM Selectors

Advanced techniques for selecting VMs in batch operations.

## Selection Methods

### 1. By Tag

Most flexible - use Azure tags:

```bash
azlin batch command 'uptime' --tag env=dev
azlin batch stop --tag project=ml-training
```

**Best for**: Logical groupings (environment, project, team)

### 2. By Pattern

Glob patterns for VM names:

```bash
azlin batch command 'df -h' --vm-pattern 'web-*'
azlin batch start --vm-pattern '*-worker'
azlin batch stop --vm-pattern 'test-vm-[0-9]'
```

**Best for**: Naming conventions and numbered fleets

### 3. All VMs

Select everything in resource group:

```bash
azlin batch command 'uptime' --all --confirm
```

**Best for**: Fleet-wide operations

## Pattern Syntax

- `*` - Matches any characters
- `?` - Matches single character
- `[0-9]` - Matches digits
- `[a-z]` - Matches lowercase letters

## Examples

```bash
# All web servers
--vm-pattern 'web-*'

# Numbered workers (worker-1, worker-2, ...)
--vm-pattern 'worker-*'

# Test VMs only
--vm-pattern 'test-*'

# Specific range
--vm-pattern 'vm-[1-5]'
```

## Combining with Resource Groups

```bash
# Dev environment VMs in specific RG
azlin batch command 'uptime' --tag env=dev --rg dev-team

# Production web servers
azlin batch command 'systemctl status nginx' \
  --vm-pattern 'web-*' \
  --rg production
```

## Best Practices

1. **Use tags for logical groups**: Environment, project, role
2. **Use patterns for numbered fleets**: web-1, web-2, etc.
3. **Test selection first**: Use `azlin list --tag env=dev` to verify
4. **Combine methods**: Can't use --tag and --vm-pattern together, choose one

## See Also

- [Batch Operations](index.md)
- [Tags Guide](../advanced/tags.md)

---

*Documentation last updated: 2025-11-24*
