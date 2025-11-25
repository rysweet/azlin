# azlin auth test

**Test service principal authentication**

## Description

The `azlin auth test` command validates that an authentication profile works correctly by attempting to authenticate with Azure and optionally test subscription access. This helps verify that service principal credentials are properly configured before using them for VM operations.

## Usage

```bash
azlin auth test [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `-p, --profile TEXT` | Name | Profile name to test (default: test default profile) |
| `--subscription-id TEXT` | ID | Test specific subscription access |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Test Default Profile

```bash
# Test the default authentication profile
azlin auth test
```

**Output:**
```
Testing authentication profile: default

Authenticating...
✓ Authentication successful

Service Principal Details:
  App ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  Tenant ID: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

✓ Authentication test passed!
```

### Test Specific Profile

```bash
# Test production service principal
azlin auth test --profile production

# Test staging service principal
azlin auth test --profile staging
```

### Test with Subscription Validation

```bash
# Verify profile can access specific subscription
azlin auth test --profile prod --subscription-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

**Output:**
```
Testing authentication profile: prod

Authenticating...
✓ Authentication successful

Testing subscription access...
  Subscription ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  Subscription Name: Production Subscription
✓ Subscription access confirmed

✓ All tests passed!
```

## What Gets Tested

When you run `azlin auth test`:

1. **Credential Loading** - Loads service principal credentials from profile
2. **Authentication** - Attempts to authenticate with Azure
3. **Token Retrieval** - Verifies ability to get access tokens
4. **Subscription Access** (optional) - Tests access to specified subscription
5. **Permissions** - Validates basic permissions are available

## Common Workflows

### Pre-Deployment Verification

```bash
# Before deploying, verify authentication works
azlin auth test --profile production
azlin auth test --subscription-id "$PROD_SUBSCRIPTION_ID"

# If successful, proceed with deployment
azlin new --auth-profile production --name prod-vm
```

### Troubleshooting Auth Issues

```bash
# List available profiles
azlin auth list

# Test each profile
azlin auth test --profile profile-1
azlin auth test --profile profile-2
azlin auth test --profile profile-3

# Show details of failing profile
azlin auth show failing-profile
```

### CI/CD Pipeline Validation

```bash
#!/bin/bash
# Verify CI auth before running pipeline

if azlin auth test --profile ci-automation; then
  echo "Authentication OK, proceeding with pipeline"
  azlin new --auth-profile ci-automation --name ci-vm-$BUILD_NUMBER
else
  echo "Authentication failed, aborting pipeline"
  exit 1
fi
```

### Multi-Subscription Setup

```bash
# Test access to multiple subscriptions
azlin auth test --profile shared-sp --subscription-id "$SUB_1"
azlin auth test --profile shared-sp --subscription-id "$SUB_2"
azlin auth test --profile shared-sp --subscription-id "$SUB_3"
```

## Troubleshooting

### Authentication Fails

**Symptoms:** "Authentication failed" error

**Solutions:**
```bash
# Verify profile exists
azlin auth list

# Show profile details
azlin auth show PROFILE-NAME

# Check credentials are valid
# - Service principal may be expired
# - Secret may have been rotated
# - Permissions may have been revoked

# Re-setup profile with new credentials
azlin auth setup PROFILE-NAME \
  --client-id NEW-CLIENT-ID \
  --client-secret NEW-CLIENT-SECRET \
  --tenant-id TENANT-ID
```

### Profile Not Found

**Symptoms:** "Profile 'NAME' not found" error

**Solutions:**
```bash
# List available profiles
azlin auth list

# Check for typos in profile name
azlin auth list | grep -i PARTIAL-NAME

# Create profile if it doesn't exist
azlin auth setup NEW-PROFILE
```

### Subscription Access Denied

**Symptoms:** Subscription test fails with permission error

**Solutions:**
```bash
# Verify service principal has required role
# In Azure Portal:
# 1. Go to Subscriptions
# 2. Select subscription
# 3. Access Control (IAM)
# 4. Check role assignments
# 5. Ensure service principal has Contributor or Owner role

# Test without subscription validation first
azlin auth test --profile PROFILE-NAME

# Then test subscription access separately
azlin auth test --profile PROFILE-NAME --subscription-id SUB-ID
```

### Expired Credentials

**Symptoms:** "Token expired" or "Invalid credentials" error

**Solutions:**
```bash
# Check when credentials expire
azlin auth show PROFILE-NAME

# Rotate credentials in Azure Portal
# Then update profile
azlin auth remove PROFILE-NAME --yes
azlin auth setup PROFILE-NAME \
  --client-id CLIENT-ID \
  --client-secret NEW-SECRET \
  --tenant-id TENANT-ID
```

## Best Practices

### Test Before Using

Always test authentication before critical operations:

```bash
# Test first
azlin auth test --profile production

# Then use
azlin new --auth-profile production --name critical-vm
```

### Regular Validation

```bash
# Create monthly validation script
cat > ~/monthly-auth-check.sh << 'EOF'
#!/bin/bash
# Validate all auth profiles monthly

PROFILES=$(azlin auth list | grep -v "Profile:" | awk '{print $1}')

echo "=== Monthly Auth Profile Validation ==="
echo "Date: $(date)"
echo

for profile in $PROFILES; do
  echo "Testing $profile..."
  if azlin auth test --profile "$profile"; then
    echo "✓ $profile OK"
  else
    echo "✗ $profile FAILED"
  fi
  echo
done
EOF

chmod +x ~/monthly-auth-check.sh
```

### CI/CD Integration

```yaml
# GitHub Actions example
jobs:
  deploy:
    steps:
      - name: Test Authentication
        run: |
          azlin auth test --profile ci-automation
          if [ $? -ne 0 ]; then
            echo "Authentication test failed"
            exit 1
          fi

      - name: Deploy VM
        run: azlin new --auth-profile ci-automation --name ci-vm
```

### Document Profile Status

```bash
# Create profile status report
azlin auth list > auth-profiles.txt
for profile in $(azlin auth list | awk '{print $1}'); do
  echo "Testing $profile..." >> auth-profiles.txt
  azlin auth test --profile "$profile" >> auth-profiles.txt 2>&1
done
```

## Related Commands

- [`azlin auth setup`](setup.md) - Create authentication profile
- [`azlin auth list`](list.md) - List all profiles
- [`azlin auth show`](show.md) - Show profile details
- [`azlin auth remove`](remove.md) - Remove profile
- [`azlin context use`](../context/use.md) - Use context with auth profile

## Source Code

- [auth.py](https://github.com/rysweet/azlin/blob/main/src/azlin/auth.py) - Authentication management logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All auth commands](index.md)
- [Service Principal](../../authentication/service-principal.md)
- [GitHub Runners](../../advanced/github-runners.md)
