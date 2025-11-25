# azlin keys backup

Backup your azlin SSH keys to a secure location for disaster recovery.

## Description

The `azlin keys backup` command creates a timestamped backup of your azlin SSH keys (both private and public). This is critical for:

- **Disaster recovery**: Restore access if keys are lost or corrupted
- **Key rotation safety**: Preserve old keys before rotation
- **Migration**: Transfer keys to new machines
- **Compliance**: Maintain key audit trail
- **Team continuity**: Share keys securely with authorized team members

The backup includes:
- Private key (`id_rsa_azlin`)
- Public key (`id_rsa_azlin.pub`)
- Metadata file (timestamp, fingerprint, source path)

**Warning**: Backups contain the **private key**. Store them securely!

## Usage

```bash
azlin keys backup [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--destination, -d PATH` | Backup destination directory (default: `~/.azlin/keys-backup-<timestamp>/`) |
| `--encrypt` | Encrypt backup with password (recommended) |
| `--compress` | Create compressed tar.gz archive |
| `--include-passphrase-file` | Include SSH passphrase file if present |
| `-h, --help` | Show help message |

## Examples

### Create Basic Backup (Default)

```bash
# Backup keys to default location
azlin keys backup
```

**Output:**
```
Backing up azlin SSH keys...
  Source: ~/.ssh/id_rsa_azlin*
  Destination: ~/.azlin/keys-backup-20251124-143022/

Copying files...
  ✓ id_rsa_azlin (private key)
  ✓ id_rsa_azlin.pub (public key)
  ✓ backup_metadata.txt

Backup complete!
  Location: ~/.azlin/keys-backup-20251124-143022/
  Files: 3
  Total size: 7.2 KB

⚠ WARNING: Backup contains PRIVATE KEY!
  - Store securely
  - Restrict permissions: chmod 400 ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin
  - Consider encryption for long-term storage
```

### Backup to Custom Location

```bash
# Backup to specific directory
azlin keys backup --destination /secure/backups/azlin-keys
```

**Output:**
```
Backing up azlin SSH keys...
  Destination: /secure/backups/azlin-keys/

✓ Backup complete!
  Location: /secure/backups/azlin-keys/
```

### Create Encrypted Backup (Recommended)

```bash
# Encrypt backup with password
azlin keys backup --encrypt
```

**Interactive prompt:**
```
Backing up azlin SSH keys...
  Destination: ~/.azlin/keys-backup-20251124-143022/

Enter backup encryption password: ********
Confirm password: ********

Encrypting backup...
  Using AES-256-CBC encryption
  ✓ Backup encrypted

✓ Backup complete!
  Location: ~/.azlin/keys-backup-20251124-143022/
  Encrypted file: azlin-keys-backup-20251124-143022.tar.gz.enc

To restore:
  openssl enc -d -aes-256-cbc -in azlin-keys-backup-20251124-143022.tar.gz.enc | tar xz
```

### Create Compressed Archive

```bash
# Create tar.gz archive
azlin keys backup --compress
```

**Output:**
```
Backing up azlin SSH keys...
  Destination: ~/.azlin/keys-backup-20251124-143022/

Creating compressed archive...
  ✓ Archive created: azlin-keys-backup-20251124-143022.tar.gz

✓ Backup complete!
  Location: ~/.azlin/keys-backup-20251124-143022.tar.gz
  Compressed size: 2.1 KB (from 7.2 KB)
```

### Encrypted + Compressed Backup

```bash
# Best practice: encrypt AND compress
azlin keys backup --encrypt --compress --destination /secure/backups/
```

### Include Passphrase File

```bash
# Include SSH passphrase file (if keys are passphrase-protected)
azlin keys backup --include-passphrase-file
```

**Warning**: Only use this if you store passphrases securely!

## Common Workflows

### Pre-Rotation Backup

Always backup before rotating keys:

```bash
# 1. Create secure backup
azlin keys backup --encrypt --compress

# 2. Verify backup
ls -lh ~/.azlin/keys-backup-*/

# 3. Proceed with rotation
azlin keys rotate

# 4. Test new keys
azlin list

# 5. If issues arise, restore from backup
# (see restore procedure below)
```

### Scheduled Backups

Create automated backup schedule:

```bash
# Create backup script
cat > ~/backup-azlin-keys.sh << 'EOF'
#!/bin/bash
# Automated azlin key backup script

BACKUP_DIR="/secure/backups/azlin-keys"
DATE=$(date +%Y%m%d)

# Create backup
azlin keys backup --encrypt --compress --destination "$BACKUP_DIR/backup-$DATE"

# Keep only last 30 days
find "$BACKUP_DIR" -type f -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR/backup-$DATE"
EOF

chmod +x ~/backup-azlin-keys.sh

# Run weekly via cron
crontab -e
# Add: 0 2 * * 0 ~/backup-azlin-keys.sh  # Every Sunday at 2 AM
```

### Off-Site Backup

Backup to cloud storage for disaster recovery:

```bash
# 1. Create encrypted backup
azlin keys backup --encrypt --compress --destination /tmp/azlin-backup

# 2. Upload to Azure Blob Storage
BACKUP_FILE=$(ls -t /tmp/azlin-backup/*.tar.gz.enc | head -1)
az storage blob upload \
  --account-name mystorage \
  --container-name ssh-key-backups \
  --name "azlin-keys-backup-$(date +%Y%m%d).tar.gz.enc" \
  --file "$BACKUP_FILE"

# 3. Clean up local backup
rm -rf /tmp/azlin-backup

echo "Backup uploaded to Azure Storage"

# Or AWS S3
aws s3 cp "$BACKUP_FILE" s3://my-backups/azlin-keys/backup-$(date +%Y%m%d).tar.gz.enc
```

### Multi-Location Backup Strategy

```bash
# Backup to multiple locations for redundancy
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# 1. Local backup (fast recovery)
azlin keys backup --destination ~/.azlin/keys-backup-$TIMESTAMP

# 2. Network backup (team access)
azlin keys backup --encrypt --destination /mnt/network-share/azlin-backups/backup-$TIMESTAMP

# 3. Cloud backup (disaster recovery)
azlin keys backup --encrypt --compress --destination /tmp/azlin-cloud-backup
BACKUP_FILE=$(ls -t /tmp/azlin-cloud-backup/*.tar.gz.enc | head -1)
aws s3 cp "$BACKUP_FILE" s3://disaster-recovery/azlin-keys/

# 4. Archive old backups (> 1 year)
find ~/.azlin/keys-backup-* -mtime +365 -type d -exec tar -czf {}.tar.gz {} \; -exec rm -rf {} \;
```

### Restore from Backup

If you need to restore keys from backup:

```bash
# For unencrypted backup
cp ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin ~/.ssh/
cp ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin.pub ~/.ssh/
chmod 600 ~/.ssh/id_rsa_azlin
chmod 644 ~/.ssh/id_rsa_azlin.pub

# For encrypted backup
openssl enc -d -aes-256-cbc -in azlin-keys-backup-20251124-143022.tar.gz.enc | tar xz
cp azlin-keys-backup-20251124-143022/id_rsa_azlin ~/.ssh/
cp azlin-keys-backup-20251124-143022/id_rsa_azlin.pub ~/.ssh/
chmod 600 ~/.ssh/id_rsa_azlin

# Test restored keys
ssh -i ~/.ssh/id_rsa_azlin azureuser@<vm-ip>
azlin list  # Should work with restored keys
```

### Verify Backup Integrity

```bash
# 1. List backup contents
ls -lh ~/.azlin/keys-backup-20251124-143022/

# 2. Check fingerprints match
ssh-keygen -lf ~/.azlin/keys-backup-20251124-143022/id_rsa_azlin.pub
ssh-keygen -lf ~/.ssh/id_rsa_azlin.pub

# 3. Verify backup metadata
cat ~/.azlin/keys-backup-20251124-143022/backup_metadata.txt

# 4. For compressed backups
tar -tzf azlin-keys-backup-20251124-143022.tar.gz
```

### Team Key Distribution

Share keys securely with authorized team members:

```bash
# 1. Create encrypted backup
azlin keys backup --encrypt --compress --destination /tmp/team-keys

# 2. Share password securely (via 1Password, LastPass, etc.)
# DO NOT email the password!

# 3. Transfer encrypted backup
BACKUP_FILE=$(ls -t /tmp/team-keys/*.tar.gz.enc | head -1)
scp "$BACKUP_FILE" teammate@workstation:/tmp/

# 4. Team member restores:
# openssl enc -d -aes-256-cbc -in azlin-keys-backup-*.tar.gz.enc | tar xz
# cp azlin-keys-backup-*/id_rsa_azlin ~/.ssh/
# chmod 600 ~/.ssh/id_rsa_azlin
```

## Troubleshooting

### Key Files Not Found

**Problem**: "Source key files not found" error.

**Solution**:
```bash
# 1. Verify keys exist
ls -la ~/.ssh/id_rsa_azlin*

# 2. If missing, may need to provision VM first
azlin new

# 3. Or generate keys manually
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_azlin -N "" -C "azlin-generated-key"
```

### Backup Directory Exists

**Problem**: Destination directory already exists.

**Solution**:
```bash
# Option 1: Use different destination
azlin keys backup --destination ~/.azlin/keys-backup-new

# Option 2: Remove existing backup
rm -rf ~/.azlin/keys-backup-20251124-143022
azlin keys backup

# Option 3: Backup will append timestamp automatically
azlin keys backup  # Creates new timestamped directory
```

### Permission Denied

**Problem**: Cannot write to backup destination.

**Solution**:
```bash
# 1. Check directory permissions
ls -ld ~/.azlin/

# 2. Create directory if needed
mkdir -p ~/.azlin

# 3. Use writable location
azlin keys backup --destination ~/azlin-key-backup
```

### Encrypted Backup Restore Fails

**Problem**: Cannot decrypt backup.

**Solution**:
```bash
# 1. Verify password is correct
openssl enc -d -aes-256-cbc -in backup.tar.gz.enc -out test.tar.gz

# 2. Check encryption format
file backup.tar.gz.enc
# Should show: "openssl enc'd data with salted password"

# 3. If password lost, use unencrypted backup if available
```

## Backup Structure

### Default Backup Directory

```
~/.azlin/keys-backup-20251124-143022/
├── id_rsa_azlin              # Private key (4096-bit RSA)
├── id_rsa_azlin.pub          # Public key
└── backup_metadata.txt       # Backup information
```

### Metadata File Contents

```
Backup Date: 2025-11-24 14:30:22
Source: /Users/ryan/.ssh/id_rsa_azlin
Key Type: RSA
Key Size: 4096 bits
Fingerprint: d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8a:9b:0c:1d:2e
Created By: azlin keys backup
```

### Compressed Archive Structure

```
azlin-keys-backup-20251124-143022.tar.gz
└── (contains directory structure above)
```

### Encrypted Archive Structure

```
azlin-keys-backup-20251124-143022.tar.gz.enc
└── (AES-256-CBC encrypted tar.gz)
```

## Security Best Practices

### Backup Storage

**DO**:
- ✓ Encrypt backups for long-term storage
- ✓ Store in secure location with restricted access
- ✓ Use cloud storage with encryption at rest
- ✓ Maintain off-site backups for disaster recovery
- ✓ Set strict permissions: `chmod 400 id_rsa_azlin`

**DON'T**:
- ✗ Store unencrypted backups on shared drives
- ✗ Email private key backups
- ✗ Commit backups to Git repositories
- ✗ Leave backups in /tmp directories
- ✗ Share passwords with backup files

### Backup Retention

```bash
# Keep backups for defined periods
# Development: 30 days
# Production: 1 year minimum

# Auto-cleanup old backups
find ~/.azlin/keys-backup-* -mtime +365 -type d -exec rm -rf {} \;

# Archive very old backups
find ~/.azlin/keys-backup-* -mtime +365 -type d -exec tar -czf {}.tar.gz {} \; -exec rm -rf {} \;
```

### Access Control

```bash
# Restrict backup directory permissions
chmod 700 ~/.azlin/keys-backup-*

# Restrict private key permissions
chmod 400 ~/.azlin/keys-backup-*/id_rsa_azlin

# Verify permissions
ls -la ~/.azlin/keys-backup-*/
# Should show: -r-------- for private key
```

## Performance

| Operation | Time |
|-----------|------|
| Basic backup | < 1 second |
| Encrypted backup | 1-2 seconds |
| Compressed backup | 1-2 seconds |
| Encrypted + Compressed | 2-3 seconds |
| Cloud upload (depends on connection) | 5-30 seconds |

## Related Commands

- [`azlin keys rotate`](rotate.md) - Rotate SSH keys across VMs (auto-backs up)
- [`azlin keys list`](list.md) - List VMs and their SSH keys
- [`azlin keys export`](export.md) - Export public key only
- [`azlin new`](../vm/new.md) - Create VM (generates keys)

## Deep Links to Source

- [Key backup implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L1500-L1600)
- [Encryption logic](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L1400-L1500)
- [Compression utilities](https://github.com/rysweet/azlin/blob/main/src/azlin/core/utils.py#L200-L300)

## See Also

- [SSH Key Management Overview](index.md)
- [Restoring Snapshots](../../snapshots/restore.md)
- [SSH Key Management](../../advanced/ssh-keys.md)
- [Security Benefits](../../bastion/security.md)
