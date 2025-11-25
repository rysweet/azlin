# azlin context delete

**Remove an Azure context from configuration**

## Description

The `azlin context delete` command removes the specified context from the configuration file. If the context being deleted is currently active, the current context pointer will be unset, and you'll need to select a new active context before running other azlin commands.

This command only removes the context configuration - it does not affect any Azure resources or subscriptions.

## Usage

```bash
azlin context delete [OPTIONS] NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `NAME` | Name of the context to delete (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--config TEXT` | Path | Custom config file path (default: `~/.azlin/config.toml`) |
| `-f, --force` | Flag | Skip confirmation prompt |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Deletion

```bash
# Delete a context (with confirmation prompt)
azlin context delete staging

# Force delete without confirmation
azlin context delete old-context --force

# Delete from custom config
azlin context delete test --config ~/custom-config.toml
```

### Common Workflows

```bash
# List contexts to see what exists
azlin context list

# Delete unused context
azlin context delete old-dev

# If it was active, set new active context
azlin context use production

# Verify deletion
azlin context list
```

### Cleaning Up Multiple Contexts

```bash
# Remove old/unused contexts
azlin context delete old-prod --force
azlin context delete temp-test --force
azlin context delete archived-2024 --force

# Verify cleanup
azlin context list
```

## Behavior

When you run `azlin context delete NAME`:

1. **Validation** - Checks that the context exists
2. **Confirmation** - Prompts for confirmation (unless `--force` used)
3. **Active Check** - Detects if deleting the active context
4. **Deletion** - Removes context from config file
5. **Active Reset** - Unsets current context if it was the deleted one

## Safety Features

### Confirmation Prompt

By default, the command prompts for confirmation:

```bash
$ azlin context delete production
Delete context 'production'? This cannot be undone. [y/N]:
```

Type `y` to proceed or `n` to cancel.

### Skip Confirmation

Use `--force` to skip the prompt (useful for scripting):

```bash
azlin context delete old-context --force
```

## Troubleshooting

### Context Not Found

**Symptoms:** Error "Context 'NAME' not found"

**Solutions:**
```bash
# List available contexts
azlin context list

# Check for typos in context name
azlin context list | grep NAME

# Verify config file location
cat ~/.azlin/config.toml
```

### Cannot Use Commands After Deletion

**Symptoms:** "No active context" errors after deleting a context

**Solutions:**
```bash
# This happens when you delete the active context
# Set a new active context
azlin context list
azlin context use CONTEXT-NAME

# Or create a new default context
azlin context create default \
  --subscription $(az account show --query id -o tsv) \
  --tenant $(az account show --query tenantId -o tsv)
```

### Deleted Wrong Context

**Symptoms:** Accidentally deleted the wrong context

**Solutions:**
```bash
# Recreate the context (if you have the IDs)
azlin context create CONTEXT-NAME \
  --subscription YOUR-SUB-ID \
  --tenant YOUR-TENANT-ID

# Restore from config backup if you made one
cp ~/.azlin/config.toml.backup ~/.azlin/config.toml

# Recreate from Azure CLI
azlin context create CONTEXT-NAME \
  --subscription $(az account show --query id -o tsv) \
  --tenant $(az account show --query tenantId -o tsv)
```

## Best Practices

### Backup Before Deletion

```bash
# Backup config before major changes
cp ~/.azlin/config.toml ~/.azlin/config.toml.backup

# Now safe to delete
azlin context delete old-context --force

# If needed, restore
cp ~/.azlin/config.toml.backup ~/.azlin/config.toml
```

### Clean Up Regularly

```bash
# Review contexts periodically
azlin context list

# Remove contexts for decommissioned projects
azlin context delete archived-project-2023
azlin context delete temp-testing
azlin context delete old-dev-environment
```

## Related Commands

- [`azlin context list`](list.md) - List all available contexts
- [`azlin context create`](create.md) - Create a new context
- [`azlin context use`](use.md) - Switch to a different context
- [`azlin context rename`](rename.md) - Rename a context
- [`azlin context current`](show.md) - Show current active context

## Source Code

- [context.py](https://github.com/rysweet/azlin/blob/main/src/azlin/context.py) - Context management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All context commands](index.md)
- [Authentication Profiles](../../authentication/profiles.md)
