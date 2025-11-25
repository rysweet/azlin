# SSH Key Management

Comprehensive SSH key management for enhanced security and access control across your azlin VM fleet.

## Overview

azlin provides powerful SSH key management commands to rotate keys, audit deployments, export keys for external use, and maintain secure backups. These tools help you maintain security best practices and compliance requirements.

## Commands

### Key Operations

| Command | Description |
|---------|-------------|
| [`rotate`](rotate.md) | Rotate SSH keys across all VMs in resource group |
| [`list`](list.md) | List VMs and display SSH key fingerprints |
| [`export`](export.md) | Export public key to file for external deployment |
| [`backup`](backup.md) | Backup SSH keys to secure location |

## Quick Start

```bash
# List current key deployment
azlin keys list

# Rotate keys every 90 days
azlin keys rotate

# Export public key for external systems
azlin keys export --output ~/azlin-key.pub

# Backup keys before rotation
azlin keys backup --encrypt --compress
```

## Common Workflows

### Quarterly Key Rotation

```bash
# 1. Audit current keys
azlin keys list --all-vms --export /tmp/keys-before-rotation.json

# 2. Backup current keys
azlin keys backup --encrypt --compress

# 3. Rotate keys
azlin keys rotate

# 4. Verify rotation
azlin keys list
azlin list  # Test connectivity

# 5. Audit new keys
azlin keys list --all-vms --export /tmp/keys-after-rotation.json
```

### External System Integration

```bash
# Export key for GitHub/GitLab
azlin keys export --output /tmp/azlin-github-key.pub
cat /tmp/azlin-github-key.pub | pbcopy
# Paste into GitHub SSH keys settings

# Deploy to non-azlin VM
azlin keys export --output /tmp/azlin-key.pub
scp /tmp/azlin-key.pub user@external-vm:/tmp/
ssh user@external-vm "cat /tmp/azlin-key.pub >> ~/.ssh/authorized_keys"
```

### Disaster Recovery

```bash
# Regular encrypted backups
azlin keys backup --encrypt --compress --destination /secure/backups/

# Upload to cloud storage
BACKUP_FILE=$(ls -t /secure/backups/*.tar.gz.enc | head -1)
az storage blob upload \
  --account-name mystorage \
  --container-name ssh-backups \
  --name "azlin-keys-$(date +%Y%m%d).tar.gz.enc" \
  --file "$BACKUP_FILE"

# Restore from backup if needed
openssl enc -d -aes-256-cbc -in backup.tar.gz.enc | tar xz
cp backup/id_rsa_azlin ~/.ssh/
chmod 600 ~/.ssh/id_rsa_azlin
```

## Security Best Practices

### Rotation Schedule

- **Development**: Every 90 days
- **Staging**: Every 60 days
- **Production**: Every 30-90 days

### Key Protection

```bash
# Always encrypt backups
azlin keys backup --encrypt --compress

# Restrict key file permissions
chmod 600 ~/.ssh/id_rsa_azlin
chmod 644 ~/.ssh/id_rsa_azlin.pub

# Verify key deployment consistency
azlin keys list | grep "Matching fingerprints"
# Should show all VMs using same key
```

### Audit Trail

```bash
# Monthly security audit
cat > ~/monthly-key-audit.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d)
AUDIT_DIR=~/security-audits/$DATE

mkdir -p $AUDIT_DIR

# Export key inventory
azlin keys list --all-vms --export $AUDIT_DIR/key-inventory.json

# Backup current keys
azlin keys backup --encrypt --destination $AUDIT_DIR/key-backup

# Generate report
azlin keys list > $AUDIT_DIR/key-audit-report.txt

echo "Audit complete: $AUDIT_DIR"
EOF

chmod +x ~/monthly-key-audit.sh
```

## Key Management Architecture

### Key Storage

```
~/.ssh/
├── id_rsa_azlin          # Private key (4096-bit RSA)
├── id_rsa_azlin.pub      # Public key
└── known_hosts           # Host verification

~/.azlin/
└── keys-backup-*/        # Timestamped backups
    ├── id_rsa_azlin
    ├── id_rsa_azlin.pub
    └── backup_metadata.txt
```

### Key Deployment Flow

```
[azlin new]
    ↓
[Generate SSH Keys]
    ↓
[Deploy to VM authorized_keys]
    ↓
[Store in ~/.ssh/id_rsa_azlin*]
    ↓
[Backup to ~/.azlin/keys-backup-*/]
```

### Key Rotation Flow

```
[azlin keys rotate]
    ↓
[Backup old keys]
    ↓
[Generate new key pair]
    ↓
[Update all VMs]
    ↓
[Verify connectivity]
    ↓
[Remove old keys from VMs]
```

## Performance

| Operation | Time (10 VMs) | Time (100 VMs) |
|-----------|---------------|----------------|
| **rotate** | 1-2 minutes | 10-20 minutes |
| **list** | 5-10 seconds | 1-2 minutes |
| **export** | < 1 second | < 1 second |
| **backup** | < 1 second | < 1 second |

## Troubleshooting

### Common Issues

**Cannot connect after rotation**:
```bash
# Restore from backup
cp ~/.azlin/keys-backup-*/id_rsa_azlin ~/.ssh/
chmod 600 ~/.ssh/id_rsa_azlin
azlin list  # Test connectivity
```

**Key fingerprints don't match**:
```bash
# Rotate to ensure consistency
azlin keys rotate
azlin keys list  # Verify all match
```

**Permission denied errors**:
```bash
# Fix key permissions
chmod 600 ~/.ssh/id_rsa_azlin
chmod 644 ~/.ssh/id_rsa_azlin.pub

# Fix backup permissions
chmod 400 ~/.azlin/keys-backup-*/id_rsa_azlin
```

## Compliance & Auditing

### SOC 2 / ISO 27001

```bash
# Quarterly key rotation (required)
azlin keys rotate

# Maintain audit logs
azlin keys list --export /compliance/ssh-keys-$(date +%Y%m%d).json

# Encrypted key backups
azlin keys backup --encrypt --compress --destination /compliance/backups/
```

### Access Reviews

```bash
# Monthly access review
azlin keys list --all-vms > /tmp/key-review.txt

# Identify VMs with inconsistent keys
azlin keys list | grep -v "Matching fingerprints"

# Remediate inconsistencies
azlin keys rotate --vm-prefix <inconsistent-prefix>
```

## Related Documentation

- [VM Management](../vm/index.md)
- [Authentication](../auth/index.md)
- [Security Benefits](../../bastion/security.md)
- [Security Benefits](../../bastion/security.md)

## See Also

- [azlin list](../vm/list.md) - Verify VM connectivity
- [azlin connect](../vm/connect.md) - Test SSH access
- [azlin new](../vm/new.md) - Provision VM with new keys
