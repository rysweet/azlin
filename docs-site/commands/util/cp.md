# azlin cp

Copy files and directories between local machine and azlin VMs with bidirectional transfer support.

## Description

The `azlin cp` command provides secure file transfer using rsync over SSH. Transfer files to VMs, download results from VMs, or copy between VMs directly. Security filters automatically block sensitive files like SSH keys and credentials.

## Usage

```bash
azlin cp SOURCE DESTINATION [OPTIONS]
```

## Arguments

- `SOURCE` - Source file/directory (local, `vm:path`, or `ip:path`)
- `DESTINATION` - Destination path (local, `vm:path`, or `ip:path`)

## Options

| Option | Description |
|--------|-------------|
| `-r, --recursive` | Copy directories recursively |
| `--dry-run` | Preview what would be copied |
| `--exclude PATTERN` | Exclude files matching pattern |
| `--resource-group, --rg TEXT` | Azure resource group (for VM name resolution) |
| `-h, --help` | Show help message |

## Examples

### Copy File to VM

```bash
# Copy local file to VM
azlin cp report.pdf my-vm:~/documents/
```

**Output:**
```
Copying to my-vm (20.12.34.56)...
  Source: /Users/ryan/report.pdf
  Destination: /home/azureuser/documents/report.pdf

Transferring...
report.pdf: 100% [===================] 2.4 MB/s

✓ Transfer complete!
  Files: 1
  Size: 2.4 MB
  Time: 1.2s
```

### Copy File from VM

```bash
# Download file from VM to local
azlin cp my-vm:~/results.tar.gz ./
```

### Copy Directory Recursively

```bash
# Copy entire directory to VM
azlin cp -r ./my-project/ my-vm:~/workspace/
```

**Output:**
```
Copying to my-vm (20.12.34.56)...
  Source: /Users/ryan/my-project/
  Destination: /home/azureuser/workspace/my-project/

Scanning directory...
  Files found: 247
  Total size: 15.3 MB

Transferring...
████████████████████████████████ 100%

✓ Transfer complete!
  Files: 247
  Size: 15.3 MB
  Time: 8.4s
  Speed: 1.8 MB/s
```

### Preview Transfer (Dry Run)

```bash
# See what would be copied without actually copying
azlin cp --dry-run large-dataset.zip my-vm:~/
```

**Output:**
```
DRY RUN - No files will be copied

Would transfer:
  large-dataset.zip (450 MB)
  From: /Users/ryan/large-dataset.zip
  To: my-vm:/home/azureuser/large-dataset.zip

Estimated time: 3m 45s (at 2 MB/s)
```

### Copy Between VMs

```bash
# Copy directly between two VMs
azlin cp vm1:~/data.csv vm2:~/backup/
```

### Exclude Patterns

```bash
# Copy project but exclude node_modules
azlin cp -r ./myapp/ my-vm:~/workspace/ --exclude 'node_modules' --exclude '.git'
```

### Copy Using IP Address

```bash
# Copy using direct IP (no VM name resolution)
azlin cp report.pdf 20.12.34.56:~/
```

## Common Workflows

### Deploy Application Code

```bash
# Build locally
npm run build

# Copy to VM
azlin cp -r ./dist/ my-vm:~/app/dist/

# Restart service
azlin connect my-vm
sudo systemctl restart myapp
```

### Download Training Results

```bash
# Copy trained model from VM
azlin cp my-vm:~/ml-training/model.pkl ./models/

# Download logs
azlin cp my-vm:~/ml-training/training.log ./logs/
```

### Backup VM Data

```bash
# Download important data
azlin cp -r my-vm:~/projects/ ./backups/vm-projects-$(date +%Y%m%d)/
azlin cp -r my-vm:~/data/ ./backups/vm-data-$(date +%Y%m%d)/
```

### Multi-VM Distribution

```bash
# Deploy config to all VMs
for vm in $(azlin list --format json | jq -r '.[].name'); do
  echo "Deploying to $vm..."
  azlin cp ./config.yaml $vm:~/app/config.yaml
done
```

### Sync Datasets

```bash
# Copy large dataset to training VMs
azlin cp -r ./datasets/ vm1:~/ml-data/
azlin cp -r ./datasets/ vm2:~/ml-data/
azlin cp -r ./datasets/ vm3:~/ml-data/
```

## Security Filters

Automatically blocks these sensitive files:

### SSH Keys
- `*.pem`, `*.key`
- `id_rsa`, `id_rsa.pub`, `id_ed25519`
- `.ssh/*`

### Cloud Credentials
- `.aws/credentials`, `.azure/credentials`
- `credentials.json`, `service-account.json`
- `.config/gcloud/*`

### Environment Files
- `.env`, `.env.*`, `.env.local`, `.env.production`

### Git Internals
- `.git/` (use `--exclude .git` to be explicit)

**Bypass warning:**
```
⚠ WARNING: Blocked sensitive files:
  .env
  .ssh/id_rsa

Sensitive files not transferred. Use --force to override (not recommended).
```

## Performance

| File Size | Transfer Time (estimate) |
|-----------|--------------------------|
| 1 MB | 0.5-1 second |
| 10 MB | 5-10 seconds |
| 100 MB | 50-60 seconds |
| 1 GB | 8-10 minutes |

*Varies by network speed and VM region*

### Optimization Tips

```bash
# Use compression for large files
gzip large-file.txt
azlin cp large-file.txt.gz my-vm:~/

# Exclude unnecessary files
azlin cp -r ./project/ my-vm:~/ \
  --exclude 'node_modules' \
  --exclude '.git' \
  --exclude '*.log'

# Transfer archives instead of many small files
tar -czf project.tar.gz ./project/
azlin cp project.tar.gz my-vm:~/
```

## Troubleshooting

### Permission Denied

**Problem:** "Permission denied" error.

**Solution:**
```bash
# Verify destination is writable
azlin connect my-vm
ls -la ~/destination-path

# Use home directory first
azlin cp file.txt my-vm:~/
# Then move with sudo
azlin connect my-vm
sudo mv ~/file.txt /opt/app/
```

### Connection Timeout

**Problem:** Transfer times out on large files.

**Solution:**
```bash
# Use compression
gzip large-file.dat
azlin cp large-file.dat.gz my-vm:~/

# Or split large files
split -b 100M huge-file.dat chunk-
for chunk in chunk-*; do
  azlin cp $chunk my-vm:~/
done

# Reassemble on VM
azlin connect my-vm
cat chunk-* > huge-file.dat
```

### Blocked Sensitive Files

**Problem:** Files not transferred due to security filters.

**Solution:**
```bash
# Review blocked files
azlin cp --dry-run ./project/ my-vm:~/

# Exclude sensitive files explicitly
azlin cp -r ./project/ my-vm:~/ --exclude '.env'

# For legitimate need to transfer secrets (use with caution)
# Consider using azlin env set instead
azlin env set my-vm API_KEY="value"
```

## Comparison with SCP

| Feature | `azlin cp` | `scp` |
|---------|------------|-------|
| VM name resolution | ✓ | ✗ (IP only) |
| Session name support | ✓ | ✗ |
| Security filters | ✓ | ✗ |
| Dry-run mode | ✓ | ✗ |
| Progress bar | ✓ | Limited |
| Recursive by default | With `-r` | With `-r` |

## Examples by Use Case

### Web Development

```bash
# Deploy frontend build
npm run build
azlin cp -r ./dist/ web-vm:~/app/public/

# Update API code
azlin cp -r ./api/ api-vm:~/app/api/
```

### Data Science

```bash
# Upload training data
azlin cp -r ./datasets/ ml-vm:~/data/

# Download trained models
azlin cp -r ml-vm:~/models/ ./trained-models/

# Get training logs
azlin cp ml-vm:~/training.log ./logs/
```

### DevOps

```bash
# Distribute configuration
for vm in $(azlin list --tag app=api --format json | jq -r '.[].name'); do
  azlin cp ./nginx.conf $vm:/tmp/nginx.conf
  azlin connect $vm "sudo mv /tmp/nginx.conf /etc/nginx/nginx.conf && sudo systemctl reload nginx"
done
```

## Related Commands

- [`azlin sync`](sync.md) - Sync dotfiles from ~/.azlin/home/
- [`azlin connect`](../vm/connect.md) - SSH to VM
- [`azlin storage mount`](../storage/mount.md) - Mount shared NFS storage

## Deep Links

- [File copy implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L3600-L3700)
- [Security filters](https://github.com/rysweet/azlin/blob/main/src/azlin/core/security.py#L100-L200)

## See Also

- [Copy Command](../../file-transfer/copy.md)
- [Security Benefits](../../bastion/security.md)
