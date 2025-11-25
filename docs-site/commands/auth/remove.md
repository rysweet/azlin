# azlin auth remove

**Remove authentication profile**

## Description

The `azlin auth remove` command deletes the specified authentication profile from configuration. This does not affect the actual service principal in Azure - it only removes the azlin configuration.

## Usage

```bash
azlin auth remove [OPTIONS] PROFILE
```

## Arguments

| Argument | Description |
|----------|-------------|
| `PROFILE` | Name of the profile to remove (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `-y, --yes` | Flag | Skip confirmation prompt |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Remove Profile (With Confirmation)

```bash
# Remove profile with prompt
azlin auth remove old-profile
```

**Output:**
```
Remove authentication profile 'old-profile'?
This will delete the stored credentials. [y/N]: y

Removing profile...
✓ Profile 'old-profile' removed successfully
```

### Remove Without Confirmation

```bash
# Force remove (useful for scripts)
azlin auth remove staging --yes

# Remove multiple profiles
azlin auth remove old-dev --yes
azlin auth remove old-test --yes
azlin auth remove archived --yes
```

## Behavior

When you run `azlin auth remove PROFILE`:

1. **Validation** - Checks that profile exists
2. **Confirmation** - Prompts for confirmation (unless `--yes`)
3. **Deletion** - Removes profile from config file
4. **Cleanup** - Clears any cached credentials

**Note:** This does NOT:
- Delete the service principal from Azure
- Revoke any Azure permissions
- Affect other azlin configurations

## Common Workflows

### Clean Up Old Profiles

```bash
# List profiles
azlin auth list

# Remove unused ones
azlin auth remove old-profile-2023 --yes
azlin auth remove temp-testing --yes
azlin auth remove archived-prod --yes

# Verify cleanup
azlin auth list
```

### Rotate Credentials

```bash
# Remove old profile
azlin auth remove production --yes

# Create new profile with rotated secret
azlin auth setup production \
  --client-id SAME-CLIENT-ID \
  --client-secret NEW-SECRET \
  --tenant-id SAME-TENANT-ID

# Test new credentials
azlin auth test --profile production
```

### Reset Authentication

```bash
# Remove all profiles and start fresh
for profile in $(azlin auth list | grep -E "^[a-z]" | awk '{print $1}'); do
  azlin auth remove "$profile" --yes
done

# Create new default profile
azlin auth setup default
```

## Safety Features

### Confirmation Prompt

By default, asks for confirmation:

```bash
$ azlin auth remove production
Remove authentication profile 'production'?
This will delete the stored credentials. [y/N]:
```

Type `y` to proceed, `n` or Enter to cancel.

### Skip Confirmation

Use `--yes` for automation:

```bash
azlin auth remove old-profile --yes
```

## Troubleshooting

### Profile Not Found

**Symptoms:** "Profile 'NAME' not found"

**Solutions:**
```bash
# List available profiles
azlin auth list

# Check for typos
azlin auth list | grep -i NAME
```

### Still Shows After Removal

**Symptoms:** Profile appears after removal

**Solutions:**
```bash
# Check config file directly
cat ~/.azlin/config.toml | grep -A 3 "\[auth\."

# Manually edit if needed
nano ~/.azlin/config.toml

# Or remove config and recreate
mv ~/.azlin/config.toml ~/.azlin/config.toml.backup
azlin auth setup new-profile
```

### Removed Wrong Profile

**Symptoms:** Accidentally deleted needed profile

**Solutions:**
```bash
# Recreate profile (if you have credentials)
azlin auth setup PROFILE-NAME \
  --client-id CLIENT-ID \
  --client-secret SECRET \
  --tenant-id TENANT-ID

# Or restore from backup if you made one
cp ~/.azlin/config.toml.backup ~/.azlin/config.toml
```

## Best Practices

### Backup Before Removal

```bash
# Backup config before removing profiles
cp ~/.azlin/config.toml ~/.azlin/config.toml.backup

# Now safe to remove
azlin auth remove old-profile --yes

# If needed, restore
cp ~/.azlin/config.toml.backup ~/.azlin/config.toml
```

### Document Removals

```bash
# Log profile changes
echo "$(date): Removed profile 'old-prod'" >> ~/.azlin/auth-changes.log
azlin auth remove old-prod --yes
```

### Clean Up Regularly

```bash
# Monthly profile cleanup
azlin auth list
# Review and remove unused profiles
azlin auth remove unused-1 --yes
azlin auth remove unused-2 --yes
```

### Verify Before Removal

```bash
# Before removing, verify not in use
azlin auth show profile-name

# Check if any contexts use it
grep -r "profile-name" ~/.azlin/config.toml

# Then safe to remove
azlin auth remove profile-name --yes
```

## Automation Example

```bash
#!/bin/bash
# Remove old temporary auth profiles

TEMP_PROFILES=$(azlin auth list | grep "temp-" | awk '{print $1}')

for profile in $TEMP_PROFILES; do
  echo "Removing $profile..."
  azlin auth remove "$profile" --yes
done

echo "Cleanup complete"
azlin auth list
```

## Related Commands

- [`azlin auth list`](list.md) - List all profiles
- [`azlin auth show`](show.md) - Show profile details
- [`azlin auth setup`](setup.md) - Create profile
- [`azlin auth test`](test.md) - Test profile

## Source Code

- [auth.py](https://github.com/rysweet/azlin/blob/main/src/azlin/auth.py)
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py)

## See Also

- [All auth commands](index.md)
- [Service Principal](../../authentication/service-principal.md)
