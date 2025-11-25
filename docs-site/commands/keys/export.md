# azlin keys export

Export your azlin SSH public key to a file for sharing or deployment to external systems.

## Description

The `azlin keys export` command exports your current azlin SSH public key (`~/.ssh/id_rsa_azlin.pub`) to a specified file. This is useful for:

- **Manual key deployment**: Add keys to non-azlin VMs
- **Team sharing**: Distribute keys to team members
- **CI/CD pipelines**: Inject keys into automated workflows
- **Backup**: Create standalone key copies
- **External systems**: Deploy azlin keys to GitHub, GitLab, etc.

The exported key is in standard OpenSSH public key format, compatible with all SSH implementations.

## Usage

```bash
azlin keys export [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--output, -o PATH` | Output file path (required) |
| `--format FORMAT` | Output format: `openssh`, `pem`, `authorized_keys` (default: `openssh`) |
| `--overwrite` | Overwrite existing file without confirmation |
| `-h, --help` | Show help message |

## Examples

### Export to File (Basic)

```bash
# Export public key to file
azlin keys export --output ~/my-azlin-key.pub
```

**Output:**
```
Exporting azlin SSH public key...
  Source: ~/.ssh/id_rsa_azlin.pub
  Destination: /Users/ryan/my-azlin-key.pub

✓ Key exported successfully!

File contents:
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X4h5... azlin-generated-key

Use this key to:
  - Add to ~/.ssh/authorized_keys on remote servers
  - Deploy to GitHub/GitLab account settings
  - Share with team members for VM access
```

### Export with Short Option

```bash
# Use -o for output path
azlin keys export -o /tmp/azlin-key.pub
```

### Export to Specific Directory

```bash
# Export to secure directory
azlin keys export --output /secure/keys/azlin-production-key.pub
```

### Export and Overwrite

```bash
# Overwrite existing file without prompt
azlin keys export --output ~/azlin-key.pub --overwrite
```

Without `--overwrite`:
```
Exporting azlin SSH public key...
  Destination file already exists: ~/azlin-key.pub

Overwrite? [y/N]: y
✓ Key exported successfully!
```

### Export in authorized_keys Format

```bash
# Export with comment suitable for authorized_keys
azlin keys export --output ~/azlin-key.pub --format authorized_keys
```

**Output file:**
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... azlin-key-exported-2025-11-24
```

### Export Multiple Copies

```bash
# Export to multiple locations
azlin keys export -o ~/backup/azlin-key-$(date +%Y%m%d).pub
azlin keys export -o /secure/team-keys/azlin-prod-key.pub
azlin keys export -o /tmp/azlin-temp-key.pub
```

## Common Workflows

### Deploy Key to External VM

```bash
# 1. Export key
azlin keys export --output /tmp/azlin-key.pub

# 2. Copy to external VM
scp /tmp/azlin-key.pub user@external-vm:/tmp/

# 3. SSH to external VM and add key
ssh user@external-vm
cat /tmp/azlin-key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 4. Test connection from azlin
ssh -i ~/.ssh/id_rsa_azlin user@external-vm
```

### Share Key with Team

```bash
# 1. Export to shared location
azlin keys export --output /shared/team-keys/azlin-dev-key.pub

# 2. Team members copy and deploy
# Each team member:
scp /shared/team-keys/azlin-dev-key.pub ~/.ssh/
cat ~/.ssh/azlin-dev-key.pub >> ~/.ssh/authorized_keys
```

### Add azlin Key to GitHub

```bash
# 1. Export key
azlin keys export --output /tmp/azlin-github-key.pub

# 2. Copy key contents
cat /tmp/azlin-github-key.pub | pbcopy  # macOS
cat /tmp/azlin-github-key.pub | xclip -selection clipboard  # Linux

# 3. Add to GitHub:
#    - Go to https://github.com/settings/keys
#    - Click "New SSH key"
#    - Paste key and save
```

### CI/CD Pipeline Key Injection

```bash
# Export key for CI/CD
azlin keys export --output /tmp/azlin-ci-key.pub

# Add to CI/CD secrets
# GitHub Actions:
gh secret set AZLIN_SSH_PUBLIC_KEY < /tmp/azlin-ci-key.pub

# GitLab CI:
# Add as CI/CD variable: AZLIN_SSH_PUBLIC_KEY

# Use in pipeline:
# - echo "$AZLIN_SSH_PUBLIC_KEY" >> ~/.ssh/authorized_keys
```

### Create Key Archive

```bash
# Create dated backup archive
BACKUP_DATE=$(date +%Y%m%d)
BACKUP_DIR=~/ssh-key-backups/$BACKUP_DATE

mkdir -p $BACKUP_DIR

# Export public key
azlin keys export --output $BACKUP_DIR/id_rsa_azlin.pub

# Copy private key (careful!)
cp ~/.ssh/id_rsa_azlin $BACKUP_DIR/id_rsa_azlin

# Set strict permissions
chmod 600 $BACKUP_DIR/id_rsa_azlin
chmod 644 $BACKUP_DIR/id_rsa_azlin.pub

# Create archive
tar -czf ~/ssh-key-backups/azlin-keys-$BACKUP_DATE.tar.gz -C ~/ssh-key-backups $BACKUP_DATE

# Secure the archive
chmod 400 ~/ssh-key-backups/azlin-keys-$BACKUP_DATE.tar.gz

echo "Backup created: ~/ssh-key-backups/azlin-keys-$BACKUP_DATE.tar.gz"
```

### Export to Cloud Storage

```bash
# Export and upload to Azure Blob Storage
azlin keys export --output /tmp/azlin-key.pub

az storage blob upload \
  --account-name mystorageaccount \
  --container-name ssh-keys \
  --name azlin-public-key-$(date +%Y%m%d).pub \
  --file /tmp/azlin-key.pub

# Or AWS S3
aws s3 cp /tmp/azlin-key.pub s3://my-bucket/ssh-keys/azlin-key-$(date +%Y%m%d).pub
```

### Verify Exported Key

```bash
# 1. Export key
azlin keys export --output /tmp/azlin-key.pub

# 2. Compare with original
diff ~/.ssh/id_rsa_azlin.pub /tmp/azlin-key.pub

# 3. Check fingerprint
ssh-keygen -lf /tmp/azlin-key.pub
ssh-keygen -lf ~/.ssh/id_rsa_azlin.pub

# Fingerprints should match
```

## Troubleshooting

### Key File Not Found

**Problem**: "Source key file not found" error.

**Solution**:
```bash
# 1. Check if key exists
ls -la ~/.ssh/id_rsa_azlin.pub

# 2. If missing, may need to create VM first
azlin new

# 3. Or generate keys manually
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa_azlin -N "" -C "azlin-generated-key"
```

### Permission Denied

**Problem**: Cannot write to output file.

**Solution**:
```bash
# 1. Check directory permissions
ls -ld $(dirname /path/to/output/file)

# 2. Create directory if needed
mkdir -p $(dirname /path/to/output/file)

# 3. Use writable location
azlin keys export --output ~/azlin-key.pub
```

### File Already Exists

**Problem**: Output file already exists.

**Solution**:
```bash
# Option 1: Use --overwrite flag
azlin keys export --output ~/azlin-key.pub --overwrite

# Option 2: Remove existing file first
rm ~/azlin-key.pub
azlin keys export --output ~/azlin-key.pub

# Option 3: Use different filename
azlin keys export --output ~/azlin-key-new.pub
```

### Invalid Key Format

**Problem**: Exported key doesn't work with external system.

**Solution**:
```bash
# 1. Verify key format
cat /tmp/azlin-key.pub
# Should start with: ssh-rsa AAAA...

# 2. Check for corruption
ssh-keygen -lf /tmp/azlin-key.pub

# 3. Re-export with correct format
azlin keys export --output /tmp/azlin-key.pub --format openssh
```

## Key Formats

### OpenSSH Format (Default)

Standard SSH public key format:
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X4h5... azlin-generated-key
```

**Compatible with:**
- OpenSSH (Linux, macOS, Windows)
- GitHub, GitLab, Bitbucket
- AWS EC2, Azure VMs, GCP instances
- Most SSH implementations

### authorized_keys Format

Same as OpenSSH, but with descriptive comment:
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... azlin-key-exported-2025-11-24
```

**Use for:**
- Direct addition to `~/.ssh/authorized_keys`
- Multiple key deployment
- Key identification in authorized_keys file

### PEM Format (Future)

RFC 4716 format (not yet implemented):
```
---- BEGIN SSH2 PUBLIC KEY ----
Comment: "azlin-generated-key"
AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X4h5...
---- END SSH2 PUBLIC KEY ----
```

## Security Considerations

### Public Key Safety

**Safe to share**:
- Public keys can be freely distributed
- No risk of unauthorized access
- Cannot derive private key from public key

**Safe locations**:
- Email, Slack, shared drives
- Git repositories (in CI/CD configs)
- Cloud storage (Azure Blob, S3)

### Private Key Protection

**Never export private keys** to shared locations!

```bash
# ❌ NEVER DO THIS
cp ~/.ssh/id_rsa_azlin /shared/keys/  # DANGEROUS!

# ✓ Only export public keys
azlin keys export --output /shared/keys/azlin-public-key.pub  # Safe
```

### Key Lifecycle

```bash
# 1. Generate keys during VM creation
azlin new

# 2. Export public key for external use
azlin keys export --output /tmp/azlin-key.pub

# 3. Deploy to external systems
scp /tmp/azlin-key.pub user@external-vm:/tmp/
ssh user@external-vm "cat /tmp/azlin-key.pub >> ~/.ssh/authorized_keys"

# 4. Rotate keys periodically
azlin keys rotate

# 5. Re-export new keys
azlin keys export --output /tmp/azlin-key-new.pub
```

## File Permissions

Recommended permissions for exported keys:

```bash
# Public key (readable by all)
chmod 644 /path/to/azlin-key.pub

# Or restrict to user only
chmod 600 /path/to/azlin-key.pub

# Directory permissions
chmod 700 /path/to/ssh-keys-directory/
```

## Performance

Key export is near-instantaneous:
- File copy operation only
- No network calls
- No Azure API requests

**Average time**: < 1 second

## Related Commands

- [`azlin keys rotate`](rotate.md) - Rotate SSH keys across VMs
- [`azlin keys list`](list.md) - List VMs and their SSH keys
- [`azlin keys backup`](backup.md) - Backup current SSH keys
- [`azlin new`](../vm/new.md) - Create VM (generates keys automatically)

## Deep Links to Source

- [Key export implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L1400-L1450)
- [File operations](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L1300-L1350)

## See Also

- [SSH Key Management Overview](index.md)
- [SSH Key Management](../../advanced/ssh-keys.md)
- [Development](../../development/index.md)
