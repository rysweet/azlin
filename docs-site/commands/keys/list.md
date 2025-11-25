# azlin keys list

List all VMs and display their SSH key fingerprints for auditing and verification.

## Description

The `azlin keys list` command displays SSH key information for all VMs in your resource group. This helps you:

- **Audit SSH access**: Verify which keys are deployed on VMs
- **Track key rotation**: Identify VMs using old vs. new keys
- **Security compliance**: Generate reports of SSH key deployment
- **Troubleshooting**: Diagnose SSH connection issues

The command shows:
- VM name and status
- SSH public key fingerprint (MD5 hash)
- Key type (RSA, ED25519, etc.)
- Key size (bits)
- Last modified timestamp

## Usage

```bash
azlin keys list [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--all-vms` | Show keys for ALL VMs (not just those with `--vm-prefix`) |
| `--vm-prefix TEXT` | Filter VMs by prefix (default: "azlin") |
| `--show-full-keys` | Display full public keys instead of fingerprints |
| `--export PATH` | Export key list to JSON file |
| `--resource-group, --rg TEXT` | Azure resource group |
| `--config PATH` | Config file path |
| `-h, --help` | Show help message |

## Examples

### List Keys for azlin VMs (Default)

```bash
# Show keys for all VMs with "azlin" prefix
azlin keys list
```

**Output:**
```
SSH Keys for azlin VMs in resource group 'azlin-rg-1234567890':

┌─────────────────────┬──────────┬────────────────────────────────────┬──────────┬──────┐
│ VM NAME             │ STATUS   │ KEY FINGERPRINT (MD5)              │ KEY TYPE │ BITS │
├─────────────────────┼──────────┼────────────────────────────────────┼──────────┼──────┤
│ azlin-vm-001        │ Running  │ d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8 │ RSA      │ 4096 │
│ azlin-vm-002        │ Running  │ d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8 │ RSA      │ 4096 │
│ azlin-vm-003        │ Stopped  │ d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8 │ RSA      │ 4096 │
└─────────────────────┴──────────┴────────────────────────────────────┴──────────┴──────┘

Total VMs: 3
Matching fingerprints: 3 (all VMs use same key)
Last key rotation: 2 days ago (2025-11-22)
```

### List Keys for ALL VMs

```bash
# Show keys for ALL VMs in resource group
azlin keys list --all-vms
```

**Output includes non-azlin VMs:**
```
SSH Keys for ALL VMs in resource group 'azlin-rg-1234567890':

┌─────────────────────┬──────────┬────────────────────────────────────┬──────────┬──────┐
│ VM NAME             │ STATUS   │ KEY FINGERPRINT (MD5)              │ KEY TYPE │ BITS │
├─────────────────────┼──────────┼────────────────────────────────────┼──────────┼──────┤
│ azlin-vm-001        │ Running  │ d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8 │ RSA      │ 4096 │
│ production-server   │ Running  │ a1:2b:3c:4d:5e:6f:7a:8b:9c:0d:1e:2 │ RSA      │ 2048 │
│ custom-vm-123       │ Stopped  │ f9:8e:7d:6c:5b:4a:39:28:17:06:f5:e │ ED25519  │ 256  │
└─────────────────────┴──────────┴────────────────────────────────────┴──────────┴──────┘

Total VMs: 3
Unique keys: 3 (different keys deployed)
```

### List Keys for Specific Prefix

```bash
# Filter by custom prefix
azlin keys list --vm-prefix production
```

**Output:**
```
SSH Keys for 'production' VMs:

┌─────────────────────┬──────────┬────────────────────────────────────┬──────────┬──────┐
│ VM NAME             │ STATUS   │ KEY FINGERPRINT (MD5)              │ KEY TYPE │ BITS │
├─────────────────────┼──────────┼────────────────────────────────────┼──────────┼──────┤
│ production-web-01   │ Running  │ c7:d8:e9:f0:a1:b2:c3:d4:e5:f6:a7:b │ RSA      │ 4096 │
│ production-web-02   │ Running  │ c7:d8:e9:f0:a1:b2:c3:d4:e5:f6:a7:b │ RSA      │ 4096 │
│ production-db-01    │ Running  │ c7:d8:e9:f0:a1:b2:c3:d4:e5:f6:a7:b │ RSA      │ 4096 │
└─────────────────────┴──────────┴────────────────────────────────────┴──────────┴──────┘

Total VMs: 3
Matching fingerprints: 3 (consistent key deployment)
```

### Show Full Public Keys

```bash
# Display complete public keys (useful for verification)
azlin keys list --show-full-keys
```

**Output:**
```
SSH Keys (Full Keys):

VM: azlin-vm-001
Status: Running
Public Key:
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X... azlin-generated-key

VM: azlin-vm-002
Status: Running
Public Key:
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X... azlin-generated-key

VM: azlin-vm-003
Status: Stopped
Public Key:
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDZk8X... azlin-generated-key
```

### Export Key List to JSON

```bash
# Export to JSON for automation/auditing
azlin keys list --export /tmp/azlin-keys-audit.json
```

**Output file (`/tmp/azlin-keys-audit.json`):**
```json
{
  "timestamp": "2025-11-24T14:30:22Z",
  "resource_group": "azlin-rg-1234567890",
  "total_vms": 3,
  "vms": [
    {
      "name": "azlin-vm-001",
      "status": "Running",
      "key_fingerprint": "d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8a:9b:0c:1d:2e",
      "key_type": "RSA",
      "key_size": 4096,
      "public_key": "ssh-rsa AAAAB3NzaC1yc2E...",
      "last_modified": "2025-11-22T10:15:00Z"
    },
    {
      "name": "azlin-vm-002",
      "status": "Running",
      "key_fingerprint": "d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8a:9b:0c:1d:2e",
      "key_type": "RSA",
      "key_size": 4096,
      "public_key": "ssh-rsa AAAAB3NzaC1yc2E...",
      "last_modified": "2025-11-22T10:15:00Z"
    }
  ]
}
```

### List Keys in Specific Resource Group

```bash
azlin keys list --rg azlin-prod-rg
```

## Common Workflows

### Pre-Rotation Audit

Before rotating keys, audit current deployment:

```bash
# 1. List all keys
azlin keys list --all-vms

# 2. Export for records
azlin keys list --all-vms --export /secure/audit/keys-before-rotation-$(date +%Y%m%d).json

# 3. Verify consistency
# All azlin VMs should have same fingerprint
azlin keys list | grep "Matching fingerprints"

# 4. Proceed with rotation
azlin keys rotate
```

### Post-Rotation Verification

After key rotation, verify deployment:

```bash
# 1. List new keys
azlin keys list

# 2. Compare fingerprints
# All should be identical and different from backup
cat ~/.azlin/keys-backup-*/id_rsa_azlin.pub | ssh-keygen -lf -
azlin keys list

# 3. Test connections
azlin list  # Should show all VMs accessible
```

### Security Audit Report

Generate comprehensive security audit:

```bash
# Create audit report
cat > /tmp/ssh-key-audit.sh << 'EOF'
#!/bin/bash
REPORT_DATE=$(date +%Y%m%d)
REPORT_FILE="/secure/audit/ssh-key-audit-$REPORT_DATE.txt"

echo "SSH Key Audit Report - $REPORT_DATE" > "$REPORT_FILE"
echo "=======================================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# List all VM keys
echo "All VM Keys:" >> "$REPORT_FILE"
azlin keys list --all-vms >> "$REPORT_FILE"

# Export to JSON
azlin keys list --all-vms --export "/secure/audit/ssh-keys-$REPORT_DATE.json"

# Check for inconsistencies
echo "" >> "$REPORT_FILE"
echo "Key Consistency Check:" >> "$REPORT_FILE"
azlin keys list | grep "Matching fingerprints" >> "$REPORT_FILE"

# Last rotation date
echo "" >> "$REPORT_FILE"
echo "Last Key Rotation:" >> "$REPORT_FILE"
azlin keys list | grep "Last key rotation" >> "$REPORT_FILE"

echo "Audit complete: $REPORT_FILE"
EOF

chmod +x /tmp/ssh-key-audit.sh
/tmp/ssh-key-audit.sh
```

### Identify VMs with Old Keys

Find VMs that need key updates:

```bash
# 1. Get current key fingerprint
CURRENT_FP=$(ssh-keygen -lf ~/.ssh/id_rsa_azlin.pub | awk '{print $2}')

# 2. List all VM keys
azlin keys list --all-vms

# 3. Identify mismatches
# Look for VMs with different fingerprints than $CURRENT_FP

# 4. Rotate keys for mismatched VMs
azlin keys rotate --vm-prefix <mismatched-prefix>
```

### Compare Keys Across Resource Groups

```bash
# Dev environment
azlin keys list --rg azlin-dev-rg --export /tmp/dev-keys.json

# Staging environment
azlin keys list --rg azlin-staging-rg --export /tmp/staging-keys.json

# Production environment
azlin keys list --rg azlin-prod-rg --export /tmp/prod-keys.json

# Compare fingerprints
jq -r '.vms[].key_fingerprint' /tmp/dev-keys.json | sort | uniq
jq -r '.vms[].key_fingerprint' /tmp/staging-keys.json | sort | uniq
jq -r '.vms[].key_fingerprint' /tmp/prod-keys.json | sort | uniq
```

## Troubleshooting

### No VMs Found

**Problem**: "No VMs found" message.

**Solution**:
```bash
# 1. Check resource group
azlin list --all

# 2. Try listing all VMs
azlin keys list --all-vms

# 3. Verify resource group
azlin list --rg <correct-rg-name>
azlin keys list --rg <correct-rg-name>
```

### Cannot Retrieve Keys

**Problem**: "Failed to retrieve SSH keys" error.

**Solution**:
```bash
# 1. Verify Azure authentication
az account show

# 2. Check VM status
azlin list --all

# 3. Verify permissions
# Ensure you have Reader role on VMs
```

### Fingerprint Mismatch

**Problem**: Fingerprints don't match across VMs.

**Solution**:
```bash
# Rotate keys to ensure consistency
azlin keys rotate

# Verify after rotation
azlin keys list
```

## Understanding Key Fingerprints

### MD5 Fingerprint Format

Default format: `d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8a:9b:0c:1d:2e`

- **Length**: 47 characters (16 hex pairs separated by colons)
- **Hash**: MD5 hash of public key
- **Use**: Quick visual comparison and verification

### Calculate Local Fingerprint

```bash
# Calculate fingerprint of your local public key
ssh-keygen -lf ~/.ssh/id_rsa_azlin.pub

# Example output:
# 4096 SHA256:abc123... azlin-generated-key (RSA)
# 4096 d4:3b:7c:8f:2e:9a:1b:4c:5d:6e:7f:8a:9b:0c:1d:2e azlin-generated-key (RSA)
```

### Key Types

| Type | Size | Security Level | Speed |
|------|------|----------------|-------|
| **RSA** | 4096 bits | High | Moderate |
| **RSA** | 2048 bits | Medium | Fast |
| **ED25519** | 256 bits | Very High | Very Fast |
| **ECDSA** | 521 bits | High | Fast |

**Recommendation**: Use RSA 4096 (azlin default) or ED25519 for new deployments.

## Output Formats

### Table Format (Default)

Clean table with columns:
- VM Name
- Status
- Key Fingerprint
- Key Type
- Bits

### JSON Format (--export)

Structured data for automation:
```json
{
  "timestamp": "ISO-8601",
  "resource_group": "string",
  "total_vms": number,
  "vms": [
    {
      "name": "string",
      "status": "string",
      "key_fingerprint": "string",
      "key_type": "string",
      "key_size": number,
      "public_key": "string",
      "last_modified": "ISO-8601"
    }
  ]
}
```

### Full Keys Format (--show-full-keys)

Complete public keys for verification:
```
VM: vm-name
Status: Running
Public Key:
  ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQ... comment
```

## Performance

| VMs | Listing Time |
|-----|--------------|
| 1-10 | 5-10 seconds |
| 50 | 20-30 seconds |
| 100+ | 1-2 minutes |

*Times assume VMs are running. Stopped VMs may take longer.*

## Related Commands

- [`azlin keys rotate`](rotate.md) - Rotate SSH keys across VMs
- [`azlin keys export`](export.md) - Export public key to file
- [`azlin keys backup`](backup.md) - Backup current SSH keys
- [`azlin list`](../vm/list.md) - List all VMs
- [`azlin connect`](../vm/connect.md) - SSH to VM

## Deep Links to Source

- [Key listing implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L1200-L1300)
- [Fingerprint calculation](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L900-L1000)
- [JSON export logic](https://github.com/rysweet/azlin/blob/main/src/azlin/core/ssh.py#L1100-L1200)

## See Also

- [SSH Key Management Overview](index.md)
- [Security Benefits](../../bastion/security.md)
- [SSH Key Management](../../advanced/ssh-keys.md)
