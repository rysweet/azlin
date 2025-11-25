# azlin os-update

Update Ubuntu system packages on azlin VMs for security and stability.

## Description

Run Ubuntu package updates (`apt update && apt upgrade`) on VMs. Apply security patches, update system libraries, and maintain VM health.

## Usage

```bash
azlin os-update VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - VM to update (name, session, or IP)

## Options

| Option | Description |
|--------|-------------|
| `--timeout SECONDS` | Command timeout (default: 300) |
| `--reboot` | Reboot VM after updates if required |
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### Update Single VM

```bash
azlin os-update my-dev-vm
```

**Output:**
```
Updating Ubuntu packages on 'my-dev-vm'...

Connecting to VM...
✓ Connected

Running: sudo apt update
Hit:1 http://azure.archive.ubuntu.com/ubuntu jammy InRelease
Get:2 http://security.ubuntu.com/ubuntu jammy-security InRelease [110 kB]
Fetched 1,234 kB in 2s (617 kB/s)
Reading package lists... Done
Building dependency tree... Done
36 packages can be upgraded.

Running: sudo apt upgrade -y
Reading package lists... Done
Building dependency tree... Done
The following packages will be upgraded:
  libssl3 openssl python3 ...
36 upgraded, 0 newly installed, 0 to remove

Unpacking libssl3 (3.0.2-0ubuntu1.12) ...
Setting up libssl3 (3.0.2-0ubuntu1.12) ...
Processing triggers for libc-bin ...

✓ Update complete!
  Packages upgraded: 36
  Time: 3m 42s

No reboot required.
```

### Update with Reboot

```bash
# Reboot if kernel was updated
azlin os-update prod-vm --reboot
```

**Output:**
```
...
✓ Update complete!
  Packages upgraded: 42
  Kernel updated: 5.15.0-91 -> 5.15.0-92

Reboot required. Rebooting VM...
✓ VM rebooted successfully.
  New kernel: 5.15.0-92
```

### Update with Custom Timeout

```bash
# Allow more time for large updates
azlin os-update my-vm --timeout 600
```

### Update by Session Name

```bash
azlin os-update my-project
```

### Update by IP

```bash
azlin os-update 20.12.34.56
```

## Common Workflows

### Monthly Maintenance

```bash
# Update all VMs
for vm in $(azlin list --format json | jq -r '.[].name'); do
  echo "Updating $vm..."
  azlin os-update $vm
done
```

### Pre-Deployment Updates

```bash
# Update and reboot before deployment
azlin os-update prod-api --reboot

# Wait for VM to come back online
sleep 60
azlin connect prod-api
```

### Security Patch Schedule

```bash
# Create update script
cat > ~/monthly-updates.sh << 'EOF'
#!/bin/bash
# Monthly security updates

REPORT_FILE="/tmp/update-report-$(date +%Y%m%d).txt"

echo "Security Update Report - $(date)" > "$REPORT_FILE"
echo "========================================" >> "$REPORT_FILE"

for vm in $(azlin list --format json | jq -r '.[].name'); do
  echo "Updating $vm..." | tee -a "$REPORT_FILE"
  azlin os-update $vm --timeout 600 >> "$REPORT_FILE" 2>&1
  echo "" >> "$REPORT_FILE"
done

echo "Update complete: $REPORT_FILE"
EOF

chmod +x ~/monthly-updates.sh

# Schedule via cron (first Sunday of month at 2 AM)
# 0 2 1-7 * 0 ~/monthly-updates.sh
```

### Fleet Updates

```bash
# Update all production VMs
azlin list --tag env=production --format json | \
  jq -r '.[].name' | \
  xargs -I {} azlin os-update {} --timeout 600

# Or use fleet command (if available)
azlin fleet update --tag env=production --os-packages
```

## What Gets Updated

The command runs:

```bash
sudo apt update          # Refresh package lists
sudo apt upgrade -y      # Install available updates
```

**Updated components:**
- System libraries (glibc, openssl)
- Linux kernel (if available)
- Development tools (gcc, python3)
- Security patches
- Bug fixes

**NOT updated:**
- azlin development tools (use `azlin update` instead)
- User-installed packages from source
- Docker containers
- Node.js packages
- Python packages

## Reboot Requirements

Some updates require reboot:
- Kernel updates
- Core system libraries
- Security patches affecting running services

Check if reboot needed:
```bash
# On VM
azlin connect my-vm
[ -f /var/run/reboot-required ] && echo "Reboot required"
```

## Performance

| Package Count | Update Time |
|---------------|-------------|
| 0-10 packages | 1-2 minutes |
| 10-50 packages | 2-5 minutes |
| 50-100 packages | 5-10 minutes |
| 100+ packages | 10-20 minutes |

*Includes download and installation time*

## Best Practices

### Update Schedule

- **Development**: Monthly or as needed
- **Staging**: Weekly
- **Production**: Monthly with testing

### Testing

```bash
# Test updates in dev first
azlin os-update dev-vm

# Then staging
azlin os-update staging-vm

# Finally production (off-hours)
azlin os-update prod-vm --reboot
```

### Backup Before Major Updates

```bash
# Create snapshot before updating
azlin snapshot create prod-vm

# Update
azlin os-update prod-vm

# If issues, restore
# azlin snapshot restore prod-vm prod-vm-snapshot-...
```

## Troubleshooting

### Update Timeout

**Problem:** Update times out.

**Solution:**
```bash
# Increase timeout
azlin os-update my-vm --timeout 900

# Or SSH and update manually
azlin connect my-vm
sudo apt update && sudo apt upgrade -y
```

### Package Lock Held

**Problem:** "Could not get lock" error.

**Solution:**
```bash
# Wait for other apt processes to complete
azlin connect my-vm
sudo lsof /var/lib/dpkg/lock-frontend
# Kill if safe, or wait
```

### Failed Package Updates

**Problem:** Some packages fail to update.

**Solution:**
```bash
azlin connect my-vm
sudo apt --fix-broken install
sudo apt update && sudo apt upgrade -y
```

## Related Commands

- [`azlin update`](../vm/update.md) - Update development tools
- [`azlin connect`](../vm/connect.md) - SSH to VM
- [`azlin snapshot create`](../snapshot/create.md) - Backup before updates

## Deep Links

- [OS update implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L3200-L3300)

## See Also

- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Security Benefits](../../bastion/security.md)
