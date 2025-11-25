# azlin auth list

**List all authentication profiles**

## Description

The `azlin auth list` command shows all configured service principal profiles with their details. Secrets and sensitive information are automatically masked for security.

## Usage

```bash
azlin auth list [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `-h, --help` | Flag | Show command help and exit |

## Examples

### List All Profiles

```bash
azlin auth list
```

**Output:**
```
Authentication Profiles:

default
  Client ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  Tenant ID: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
  Secret: ********** (masked)

production
  Client ID: aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  Tenant ID: bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
  Secret: ********** (masked)

staging
  Client ID: cccccccc-cccc-cccc-cccc-cccccccccccc
  Tenant ID: dddddddd-dddd-dddd-dddd-dddddddddddd
  Secret: ********** (masked)

Total profiles: 3
```

## Output Format

Each profile shows:
- **Profile Name** - Identifier for the auth profile
- **Client ID** - Application (service principal) ID
- **Tenant ID** - Azure AD tenant ID
- **Secret** - Masked for security (shows `**********`)

## Common Workflows

### Profile Inventory

```bash
# List all profiles
azlin auth list

# Count profiles
azlin auth list | grep "Total profiles"

# Extract profile names
azlin auth list | grep -E "^[a-z]" | awk '{print $1}'
```

### Before Creating New Profile

```bash
# Check if profile already exists
azlin auth list | grep production

# If exists, remove and recreate
azlin auth remove production --yes
azlin auth setup production
```

### Audit Profiles

```bash
# Document configured profiles
azlin auth list > ~/auth-profiles-$(date +%Y%m%d).txt

# Review regularly
cat ~/auth-profiles-*.txt
```

## Troubleshooting

### No Profiles Listed

**Symptoms:** Empty list or "No profiles configured"

**Solutions:**
```bash
# Create your first profile
azlin auth setup default

# Verify
azlin auth list
```

### Profile Missing

**Symptoms:** Expected profile doesn't appear

**Solutions:**
```bash
# Check config file directly
cat ~/.azlin/config.toml | grep -A 3 "\[auth\."

# Recreate profile
azlin auth setup PROFILE-NAME
```

## Best Practices

### Regular Audits

```bash
# Weekly profile review
azlin auth list
azlin auth test --profile profile-1
azlin auth test --profile profile-2
```

### Documentation

```bash
# Document profiles for team
azlin auth list > team-auth-profiles.txt
# Share documentation (secrets are masked)
```

## Related Commands

- [`azlin auth setup`](setup.md) - Create profile
- [`azlin auth show`](show.md) - Show profile details
- [`azlin auth test`](test.md) - Test profile
- [`azlin auth remove`](remove.md) - Remove profile

## Source Code

- [auth.py](https://github.com/rysweet/azlin/blob/main/src/azlin/auth.py)
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py)

## See Also

- [All auth commands](index.md)
- [Service Principal](../../authentication/service-principal.md)
