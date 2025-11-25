# azlin context rename

**Rename an existing Azure context**

## Description

The `azlin context rename` command changes the name of an existing context. If the context is currently active, the current context pointer is automatically updated to reflect the new name.

This is useful for improving context organization and clarity without needing to delete and recreate contexts.

## Usage

```bash
azlin context rename [OPTIONS] OLD_NAME NEW_NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `OLD_NAME` | Current name of the context (required) |
| `NEW_NAME` | New name for the context (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--config TEXT` | Path | Custom config file path (default: `~/.azlin/config.toml`) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Renaming

```bash
# Rename a context
azlin context rename staging stage

# Rename with clearer naming
azlin context rename old-prod production

# Rename development context
azlin context rename dev development
```

### Using Custom Config

```bash
# Rename context in custom config
azlin context rename staging prod --config ~/custom-config.toml
```

### Common Workflows

```bash
# List contexts to see current names
azlin context list

# Rename for clarity
azlin context rename temp-20241124 experimental-feature

# Verify rename
azlin context list

# Context still works if it was active
azlin new --name test-vm  # Uses renamed context
```

### Organizational Improvements

```bash
# Add prefixes for better organization
azlin context rename prod client-a-prod
azlin context rename dev client-a-dev

# Add region information
azlin context rename production production-us-east
azlin context rename backup production-eu-west

# Add team names
azlin context rename shared team-alpha-shared
azlin context rename testing team-alpha-testing
```

## Behavior

When you run `azlin context rename OLD_NAME NEW_NAME`:

1. **Validation** - Checks that OLD_NAME exists and NEW_NAME doesn't
2. **Rename** - Changes the context name in configuration
3. **Active Update** - If OLD_NAME was active, updates current context to NEW_NAME
4. **Persistence** - Saves changes to config file

## Active Context Handling

If you rename the active context, it remains active with the new name:

```bash
# Current context: production
azlin context current
# Output: production

# Rename it
azlin context rename production prod

# Still active, with new name
azlin context current
# Output: prod
```

## Troubleshooting

### Old Context Not Found

**Symptoms:** Error "Context 'OLD_NAME' not found"

**Solutions:**
```bash
# List available contexts
azlin context list

# Check for typos
azlin context list | grep NAME

# Verify config file
cat ~/.azlin/config.toml | grep "\[contexts\."
```

### New Name Already Exists

**Symptoms:** Error "Context 'NEW_NAME' already exists"

**Solutions:**
```bash
# Choose a different name
azlin context rename old-name new-unique-name

# Or delete the existing context first (if appropriate)
azlin context delete NEW_NAME --force
azlin context rename old-name NEW_NAME
```

### Cannot Find Context After Rename

**Symptoms:** Old context name still appears in commands

**Solutions:**
```bash
# Verify rename succeeded
azlin context list

# Check config file directly
cat ~/.azlin/config.toml

# If needed, manually edit config
nano ~/.azlin/config.toml
```

## Best Practices

### Use Descriptive Names

```bash
# Good: Clearly indicates purpose and environment
azlin context rename ctx1 production-us-east-team-a
azlin context rename test dev-experimental-ml-project

# Less clear
azlin context rename prod p  # Too short
azlin context rename dev x   # Not descriptive
```

### Consistent Naming Conventions

Establish patterns for your team:

```bash
# Pattern: <environment>-<region>-<team>
azlin context rename prod production-us-east-team-alpha
azlin context rename dev development-us-east-team-alpha

# Pattern: <client>-<environment>
azlin context rename a-prod client-a-production
azlin context rename a-dev client-a-development

# Pattern: <project>-<environment>
azlin context rename ml-p ml-training-production
azlin context rename ml-d ml-training-development
```

### Document Renames

```bash
# Keep a changelog for team reference
echo "$(date): Renamed 'staging' to 'stage'" >> ~/.azlin/context-changes.log
azlin context rename staging stage
```

### Backup Before Major Changes

```bash
# Backup config before renaming multiple contexts
cp ~/.azlin/config.toml ~/.azlin/config.toml.backup

# Perform renames
azlin context rename old-name-1 new-name-1
azlin context rename old-name-2 new-name-2
azlin context rename old-name-3 new-name-3

# Verify all changes
azlin context list
```

## Automation Examples

### Batch Renaming

```bash
#!/bin/bash
# Add prefix to all contexts

PREFIX="team-a-"

# Get all context names
CONTEXTS=$(azlin context list | awk '{print $2}' | grep -v "^$")

for ctx in $CONTEXTS; do
  # Skip if already has prefix
  if [[ ! $ctx =~ ^$PREFIX ]]; then
    NEW_NAME="${PREFIX}${ctx}"
    echo "Renaming $ctx to $NEW_NAME"
    azlin context rename "$ctx" "$NEW_NAME"
  fi
done

azlin context list
```

### Interactive Rename Tool

```bash
#!/bin/bash
# Interactively rename contexts

azlin context list

read -p "Enter context to rename: " old_name
read -p "Enter new name: " new_name

azlin context rename "$old_name" "$new_name"

echo "Rename complete:"
azlin context list
```

## Related Commands

- [`azlin context list`](list.md) - List all available contexts
- [`azlin context create`](create.md) - Create a new context
- [`azlin context delete`](delete.md) - Delete a context
- [`azlin context use`](use.md) - Switch to a different context
- [`azlin context current`](show.md) - Show current active context

## Source Code

- [context.py](https://github.com/rysweet/azlin/blob/main/src/azlin/context.py) - Context management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All context commands](index.md)
- [Authentication Profiles](../../authentication/profiles.md)
- [Multi-Tenant Context](../../authentication/multi-tenant.md)
