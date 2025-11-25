# azlin auth show

**Show authentication profile details**

## Description

The `azlin auth show` command displays complete information about a specific authentication profile. Secrets are masked for security, but all other configuration details are shown.

## Usage

```bash
azlin auth show [OPTIONS] PROFILE
```

## Arguments

| Argument | Description |
|----------|-------------|
| `PROFILE` | Name of the profile to show (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Show Profile Details

```bash
# Show default profile
azlin auth show default

# Show production profile
azlin auth show production
```

**Output:**
```
Profile: production

Authentication Details:
  Client ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  Tenant ID: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
  Client Secret: ********** (masked)

Configuration:
  Created: 2024-10-15 14:32:00
  Last Used: 2024-11-24 09:15:23
  Status: Active

Usage:
  azlin new --auth-profile production
  azlin --auth-profile production list
```

## What Is Shown

- **Client ID** - Service principal application ID
- **Tenant ID** - Azure AD tenant ID
- **Client Secret** - Masked (shows `**********`)
- **Created Date** - When profile was created
- **Last Used** - Last time profile was used (if tracked)
- **Status** - Whether profile is active
- **Usage Examples** - How to use this profile

## Common Workflows

### Verify Profile Configuration

```bash
# Show profile before using
azlin auth show production

# Test it works
azlin auth test --profile production

# Use it
azlin new --auth-profile production --name prod-vm
```

### Troubleshooting Authentication

```bash
# Profile auth failing? Check details
azlin auth show failing-profile

# Verify IDs match Azure Portal
# Compare Client ID and Tenant ID
```

### Profile Documentation

```bash
# Document profile for team
azlin auth show prod-sp > production-auth-profile.txt

# Remove before sharing (contains tenant/client IDs)
# Or share with team who need this info
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

# Create profile if needed
azlin auth setup NEW-PROFILE
```

### Cannot View Secret

**Symptoms:** "Secret is masked"

**Note:** This is intentional for security. Secrets are never displayed.

**If you need the secret:**
- Check password manager where it was stored
- Rotate secret in Azure Portal and update profile
- Contact Azure admin for access

## Best Practices

### Review Before Using

```bash
# Always review profile before critical operations
azlin auth show production
azlin auth test --profile production
azlin new --auth-profile production --name critical-vm
```

### Verify IDs Match Azure

```bash
# Get IDs from profile
azlin auth show myprofile

# Compare with Azure Portal:
# 1. Go to Azure Active Directory
# 2. App registrations
# 3. Find your service principal
# 4. Verify Application (client) ID matches
# 5. Verify Directory (tenant) ID matches
```

## Related Commands

- [`azlin auth list`](list.md) - List all profiles
- [`azlin auth test`](test.md) - Test profile
- [`azlin auth setup`](setup.md) - Create/update profile
- [`azlin auth remove`](remove.md) - Remove profile

## Source Code

- [auth.py](https://github.com/rysweet/azlin/blob/main/src/azlin/auth.py)
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py)

## See Also

- [All auth commands](index.md)
- [Service Principal](../../authentication/service-principal.md)
