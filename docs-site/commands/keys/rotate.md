# azlin keys rotate

Rotate SSH keys across all VMs for enhanced security and compliance.

## Description

The `azlin keys rotate` command generates new SSH key pairs and updates all matching VMs with the new keys. This is essential for:

- **Security best practices**: Regular key rotation reduces compromise risk
- **Compliance requirements**: Meet security policies requiring periodic key changes
- **Access control**: Revoke old keys and ensure only new keys work
- **Audit trail**: Maintain timestamped backups of previous keys

The command automatically:
1. Generates a new SSH key pair (`~/.ssh/id_rsa_azlin`)
2. Backs up existing keys (unless `--no-backup`)
3. Updates authorized_keys on all matching VMs
4. Verifies SSH access with new keys
5. Removes old keys from VMs

**Default behavior**: Only rotates keys for VMs with "azlin" prefix.

## Usage

```bash
azlin keys rotate [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--all-vms` | Rotate keys for ALL VMs, not just those matching `--vm-prefix` |
| `--vm-prefix TEXT` | Only rotate keys for VMs with this prefix (default: "azlin") |
| `--no-backup` | Skip backing up old keys (not recommended) |
| `--resource-group, --rg TEXT` | Azure resource group |
| `--config PATH` | Config file path |
| `-h, --help` | Show help message |

## Examples

### Rotate Keys for azlin VMs (Default)

```bash
# Rotate keys for all VMs starting with "azlin"
azlin keys rotate
```

**Output:**
```
Rotating SSH keys for azlin VMs...

Backing up current keys...
  Backup location: ~/.azlin/keys-backup-20251124-143022/
  ✓ Private key backed up
  ✓ Public key backed up

Generating new SSH key pair...
  ✓ New key pair created: ~/.ssh/id_rsa_azlin

Updating VMs...
  [1/3] azlin-vm-001... ✓
  [2/3] azlin-vm-002... ✓
  [3/3] azlin-vm-003... ✓

Verifying new keys...
  [1/3] azlin-vm-001... ✓ Connected
  [2/3] azlin-vm-002... ✓ Connected
  [3/3] azlin-vm-003... ✓ Connected

Removing old keys from VMs...
  [1/3] azlin-vm-001... ✓
  [2/3] azlin-vm-002... ✓
  [3/3] azlin-vm-003... ✓

SSH key rotation complete!
  VMs updated: 3
  Old keys backed up to: ~/.azlin/keys-backup-20251124-143022/
```

### Rotate Keys for ALL VMs

```bash
# Rotate keys for ALL VMs in resource group
azlin keys rotate --all-vms
```

This updates **every VM** in your resource group, including non-azlin VMs.

### Rotate Keys for Specific Prefix

```bash
# Only rotate keys for production VMs
azlin keys rotate --vm-prefix production

# Example: Updates production-vm-001, production-vm-002, etc.
```

### Rotate Keys in Specific Resource Group

```bash
azlin keys rotate --rg azlin-prod-rg
```

### Rotate Without Backup (Not Recommended)

```bash
# Skip key backup (only for testing environments)
azlin keys rotate --no-backup
```

**Warning**: You won't be able to recover old keys if something goes wrong!

### Combine Options

```bash
# Rotate ALL VMs in prod resource group without backup
azlin keys rotate --all-vms --rg azlin-prod-rg --no-backup
```

## Common Workflows

### Quarterly Security Rotation

Set up a quarterly rotation schedule:

```bash
# Create rotation script
cat > ~/rotate-azlin-keys.sh << 'EOF'
#!/bin/bash
# Quarterly SSH key rotation for azlin VMs

echo "Starting quarterly SSH key rotation..."
azlin keys rotate --rg azlin-prod-rg

echo "Rotation complete on $(date)"
EOF

chmod +x ~/rotate-azlin-keys.sh

# Run manually every 90 days, or set up a reminder
```

### Emergency Key Rotation

If you suspect key compromise:

```bash
# 1. Immediately rotate keys for ALL VMs
azlin keys rotate --all-vms --rg azlin-prod-rg

# 2. Verify access to all VMs
azlin list --all

# 3. Check for unauthorized access
azlin w --rg azlin-prod-rg

# 4. Secure old key backups
chmod 400 ~/.azlin/keys-backup-*/id_rsa_azlin
```

### Pre-Rotation Verification

Before rotating, verify current key access:

```bash
# 1. List all VMs and their key fingerprints
azlin keys list

# 2. Test current SSH access
azlin list

# 3. Perform rotation
azlin keys rotate

# 4. Verify new key access
azlin keys list
```

### Multi-Environment Rotation

```bash
# Rotate dev environment
azlin keys rotate --vm-prefix dev --rg azlin-dev-rg

# Rotate staging environment
azlin keys rotate --vm-prefix staging --rg azlin-staging-rg

# Rotate production environment (with extra caution)
azlin keys rotate --vm-prefix prod --rg azlin-prod-rg
```

## Troubleshooting

### VM Update Failed

**Problem**: Some VMs failed to update during rotation.

**Solution**:
```bash
# 1. Check which VMs are running
azlin list --all

# 2. Start stopped VMs
azlin start vm-name

# 3. Retry rotation
azlin keys rotate
```

### Cannot Connect After Rotation

**Problem**: SSH connection fails after key rotation.

**Solution**:
```bash
# 1. Check if backup exists
ls -la ~/.azlin/keys-backup-*/

# 2. Restore old keys temporarily
cp ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin ~/.ssh/id_rsa_azlin
cp ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin.pub ~/.ssh/id_rsa_azlin.pub

# 3. Try connecting
azlin connect vm-name

# 4. Re-run rotation if needed
azlin keys rotate
```

### Missing Backup Directory

**Problem**: Backup directory not found after rotation.

**Cause**: Used `--no-backup` flag or backup failed.

**Solution**:
```bash
# Always keep backups during rotation
azlin keys rotate  # Never use --no-backup in production
```

### Permission Denied After Rotation

**Problem**: "Permission denied (publickey)" error.

**Solution**:
```bash
# 1. Verify new keys exist
ls -la ~/.ssh/id_rsa_azlin*

# 2. Check key permissions
chmod 600 ~/.ssh/id_rsa_azlin
chmod 644 ~/.ssh/id_rsa_azlin.pub

# 3. Test SSH manually
ssh -i ~/.ssh/id_rsa_azlin azureuser@<vm-ip>
```

## Security Best Practices

### Rotation Schedule

- **Development**: Every 90 days
- **Staging**: Every 60 days
- **Production**: Every 30-90 days (depends on compliance requirements)

### Key Backup Management

```bash
# Keep backups secure
chmod 400 ~/.azlin/keys-backup-*/id_rsa_azlin

# Archive old backups (after 1 year)
tar -czf azlin-key-backups-2025.tar.gz ~/.azlin/keys-backup-2025*
mv azlin-key-backups-2025.tar.gz /secure/archive/

# Remove old backups older than 1 year
find ~/.azlin/keys-backup-* -mtime +365 -type d -exec rm -rf {} \;
```

### Access Verification

Always verify access after rotation:

```bash
# 1. Test connection to each VM
azlin list

# 2. Verify authorized_keys
azlin connect vm-name
cat ~/.ssh/authorized_keys

# 3. Check for old keys
# Should only show new key fingerprint
```

### Audit Trail

Maintain logs of all rotations:

```bash
# Create rotation log
cat > ~/key-rotation-log.txt << EOF
$(date): Rotated keys for azlin VMs
  Resource Group: azlin-prod-rg
  VMs Updated: $(azlin list | wc -l)
  Backup Location: ~/.azlin/keys-backup-$(date +%Y%m%d-%H%M%S)/
EOF
```

## Key Backup Structure

After rotation with backup (default), keys are saved:

```
~/.azlin/keys-backup-20251124-143022/
├── id_rsa_azlin           # Private key backup
├── id_rsa_azlin.pub       # Public key backup
└── rotation_info.txt      # Metadata (timestamp, VMs updated)
```

**Important**: These backups are **unencrypted**. Store them securely and delete after verification.

## Performance

| VMs | Rotation Time |
|-----|---------------|
| 1-5 | 30-60 seconds |
| 10 | 1-2 minutes |
| 50 | 5-10 minutes |
| 100+ | 10-20 minutes |

*Times assume VMs are running and responsive*

## Related Commands

- [`azlin keys list`](list.md) - List VMs and their SSH keys
- [`azlin keys export`](export.md) - Export public key to file
- [`azlin keys backup`](backup.md) - Backup current SSH keys
- [`azlin list`](../vm/list.md) - Verify VM access after rotation
- [`azlin connect`](../vm/connect.md) - Test SSH connection

## Deep Links to Source

- [SSH key rotation implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L1000-L1100)
- [Key backup logic](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L500-L600)
- [VM key update procedure](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L700-L800)

## See Also

- [SSH Key Management Overview](index.md)
- [Security Benefits](../../bastion/security.md)
- [Authentication Setup](../../authentication/index.md)
