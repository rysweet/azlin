# Memory and Network Latency Monitoring

Instantly see VM memory allocation and measure network latency to identify performance bottlenecks and plan capacity with the `azlin list` command.

## What is Memory and Latency Monitoring?

The `azlin list` command displays critical resource metrics for all your VMs:

1. **Memory Column (Always Displayed)**: Shows total memory allocated to each VM in GB, helping you understand resource allocation at a glance
2. **Latency Column (Opt-In)**: Measures SSH connection latency in milliseconds when you add the `--with-latency` flag, helping identify network issues

This eliminates the need to check Azure Portal or run separate diagnostic commands to understand your VM resource footprint and connectivity.

## Why Would I Use It?

Memory and latency monitoring solves several operational challenges:

### Problem 1: Unknown Resource Allocation

You're managing multiple VMs and need to quickly see total memory allocation across your fleet.

**Without memory display**: You check Azure Portal for each VM, or manually lookup VM size specifications.

**With memory display**: Run `azlin list` and instantly see memory allocation for every VM in one table.

### Problem 2: Slow Connection Mystery

Your SSH connection to a VM feels sluggish, but you don't know if it's network latency or the VM itself.

**Without latency measurement**: You ping the VM, try traceroute, or just accept the slow connection.

**With latency measurement**: Run `azlin list --with-latency` and see exactly which VMs have high connection latency (e.g., "234ms" vs "45ms").

### Problem 3: Capacity Planning

You need to understand total memory committed across running VMs to plan capacity or optimize costs.

**Without memory display**: Manually sum up VM sizes from Azure Portal or write custom scripts.

**With memory display**: The summary line shows total memory in use: "3 VMs running | 12 vCPUs | 48 GB memory in use".

### Problem 4: Regional Performance Comparison

You have VMs in multiple Azure regions and want to compare connection latency.

**Without latency measurement**: Use third-party tools or manual ping tests.

**With latency measurement**: Run `azlin list --with-latency` and compare latency across regions (e.g., eastus: "45ms", westeurope: "180ms").

## How Does It Work?

### Memory Monitoring

Memory information comes from Azure VM size specifications:

```
VM Size (e.g., Standard_D4s_v3) → Lookup in size catalog → Display "16 GB"
```

The memory column:
- Uses hardcoded VM size mappings (instant, zero API overhead)
- Works for both running and stopped VMs (shows allocated capacity)
- Displays "-" for unknown or custom VM sizes
- Includes memory total in the summary line

### Latency Measurement

Latency measurement works by timing SSH connection establishment:

```
1. Filter to running VMs only
   └─▶ Stopped VMs display "-" (can't measure latency)

2. Connect to VM via SSH in parallel (ThreadPoolExecutor)
   └─▶ Measure time from connection start to successful auth

3. Display result
   ├─▶ Success: "45ms", "123ms", etc.
   ├─▶ Timeout: "timeout" (5-second limit)
   └─▶ Error: "error" (connection failed)
```

**Key Features**:
- **Parallel execution**: Measures all VMs simultaneously (max 10 concurrent)
- **Fast timeout**: 5-second timeout per VM prevents hanging
- **Direct SSH**: Measures SSH connection only, not Bastion tunnel overhead
- **Non-blocking**: Errors on one VM don't affect others

### Performance Characteristics

| Operation | Overhead | Notes |
|-----------|----------|-------|
| Memory column | 0 seconds | Hardcoded lookup, zero API calls |
| Latency measurement | ~5-10 seconds | For 10 VMs in parallel |
| Single VM latency | 45-200ms typical | Depends on network and region |
| Timeout per VM | 5 seconds max | Prevents hanging on unreachable VMs |

## Examples

### Basic VM List (Memory Always Shown)

See memory allocation for all VMs:

```bash
azlin list
```

Output:
```
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Session       ┃ VM Name          ┃ Status   ┃ IP            ┃ Region    ┃ Size            ┃ vCPUs ┃ Memory   ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ dev-session   │ dev-vm-001       │ Running  │ 10.0.1.5      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │
│ test-session  │ test-vm-002      │ Running  │ 10.0.1.8      │ eastus    │ Standard_B2ms   │ 2     │ 8 GB     │
│ prod-session  │ prod-vm-001      │ Running  │ 10.0.2.10     │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │
│ staging       │ staging-vm       │ Stopped  │ N/A           │ eastus    │ Standard_B4ms   │ 4     │ 16 GB    │
└───────────────┴──────────────────┴──────────┴───────────────┴───────────┴─────────────────┴───────┴──────────┘

3 VMs running | 14 vCPUs | 88 GB memory in use
```

**Key Points**:
- Memory displayed for ALL VMs (running and stopped)
- Summary shows total memory for running VMs only
- Unknown VM sizes show "-" for memory

### Measuring Latency for All VMs

Add the `--with-latency` flag to measure network latency:

```bash
azlin list --with-latency
```

Output:
```
Measuring SSH latency for 3 running VMs... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:03

┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Session       ┃ VM Name          ┃ Status   ┃ IP            ┃ Region    ┃ Size            ┃ vCPUs ┃ Memory   ┃ Latency  ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ dev-session   │ dev-vm-001       │ Running  │ 10.0.1.5      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │ 45ms     │
│ test-session  │ test-vm-002      │ Running  │ 10.0.1.8      │ eastus    │ Standard_B2ms   │ 2     │ 8 GB     │ 52ms     │
│ prod-session  │ prod-vm-001      │ Running  │ 10.0.2.10     │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │ 123ms    │
│ staging       │ staging-vm       │ Stopped  │ N/A           │ eastus    │ Standard_B4ms   │ 4     │ 16 GB    │ -        │
└───────────────┴──────────────────┴──────────┴───────────────┴───────────┴─────────────────┴───────┴──────────┴──────────┘

3 VMs running | 14 vCPUs | 88 GB memory in use
```

**Key Points**:
- Latency measured in parallel (completes in ~3-5 seconds for all VMs)
- Running VMs show latency in milliseconds (45ms, 52ms, 123ms)
- Stopped VMs show "-" (can't measure latency when not running)
- Notice: westus2 VM has higher latency (123ms) - might be geographic distance

### Identifying High Latency VMs

Use latency measurement to find problematic VMs:

```bash
azlin list --with-latency
```

Output with a problematic VM:
```
Measuring SSH latency for 4 running VMs... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:05

┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ Session       ┃ VM Name          ┃ Status   ┃ IP            ┃ Region    ┃ Size            ┃ vCPUs ┃ Memory   ┃ Latency  ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ dev-session   │ dev-vm-001       │ Running  │ 10.0.1.5      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │ 45ms     │
│ test-session  │ test-vm-002      │ Running  │ 10.0.1.8      │ eastus    │ Standard_B2ms   │ 2     │ 8 GB     │ 52ms     │
│ prod-session  │ prod-vm-001      │ Running  │ 10.0.2.10     │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │ 123ms    │
│ debug-vm      │ problematic-vm   │ Running  │ 10.0.3.15     │ eastus    │ Standard_B1ms   │ 1     │ 2 GB     │ timeout  │
└───────────────┴──────────────────┴──────────┴───────────────┴───────────┴─────────────────┴───────┴──────────┴──────────┘

4 VMs running | 15 vCPUs | 90 GB memory in use
```

**Analysis**:
- Three VMs have normal latency (45-123ms)
- `problematic-vm` shows "timeout" - SSH connection took more than 5 seconds
- **Action**: Investigate firewall rules, network security groups, or VM health

### Checking Memory Across All Contexts

View memory allocation across all resource groups:

```bash
azlin list --all
```

Output:
```
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Resource Group  ┃ VM Name          ┃ Status   ┃ IP            ┃ Region    ┃ Size            ┃ vCPUs ┃ Memory   ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ dev-rg          │ dev-vm-001       │ Running  │ 10.0.1.5      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │
│ dev-rg          │ dev-vm-002       │ Running  │ 10.0.1.8      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │
│ test-rg         │ test-vm-001      │ Running  │ 10.0.2.5      │ eastus    │ Standard_B2ms   │ 2     │ 8 GB     │
│ prod-rg         │ prod-vm-001      │ Running  │ 10.0.3.10     │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │
│ prod-rg         │ prod-vm-002      │ Stopped  │ N/A           │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │
└─────────────────┴──────────────────┴──────────┴───────────────┴───────────┴─────────────────┴───────┴──────────┘

4 VMs running | 18 vCPUs | 104 GB memory in use
2 VMs stopped | 8 vCPUs | 64 GB memory allocated
Total across all contexts: 6 VMs | 26 vCPUs | 168 GB memory allocated
```

**Use Cases**:
- **Cost Analysis**: See total memory committed (168 GB) across all environments
- **Capacity Planning**: Identify memory over-allocation or under-utilization
- **Resource Optimization**: Find stopped VMs consuming allocated resources

### Combining with Tmux Session Info

Show memory, latency, AND active tmux sessions:

```bash
azlin list --with-latency --with-sessions
```

Output:
```
Measuring SSH latency for 3 running VMs... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:03

┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Session       ┃ VM Name          ┃ Status   ┃ IP            ┃ Region    ┃ Size            ┃ vCPUs ┃ Memory   ┃ Latency  ┃ Tmux Sessions ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ dev-session   │ dev-vm-001       │ Running  │ 10.0.1.5      │ eastus    │ Standard_D4s_v3 │ 4     │ 16 GB    │ 45ms     │ 2 active      │
│ test-session  │ test-vm-002      │ Running  │ 10.0.1.8      │ eastus    │ Standard_B2ms   │ 2     │ 8 GB     │ 52ms     │ 1 active      │
│ prod-session  │ prod-vm-001      │ Running  │ 10.0.2.10     │ westus2   │ Standard_E8as_v5│ 8     │ 64 GB    │ 123ms    │ 0             │
│ staging       │ staging-vm       │ Stopped  │ N/A           │ eastus    │ Standard_B4ms   │ 4     │ 16 GB    │ -        │ -             │
└───────────────┴──────────────────┴──────────┴───────────────┴───────────┴─────────────────┴───────┴──────────┴──────────┴───────────────┘

3 VMs running | 14 vCPUs | 88 GB memory in use | 3 active tmux sessions
```

## Configuration Options

### Disable Latency Progress Bar

If you want silent operation (useful in scripts):

```bash
azlin config set cli.show_progress false
```

### Change Latency Timeout

Adjust the 5-second default timeout:

```bash
# Increase timeout to 10 seconds (for slow networks)
azlin config set ssh.latency_timeout 10

# Decrease timeout to 3 seconds (for fast fail)
azlin config set ssh.latency_timeout 3
```

### Configure Max Parallel Connections

Control how many VMs are measured simultaneously:

```bash
# Default: 10 concurrent connections
azlin config set ssh.latency_max_workers 10

# Reduce for slower networks or fewer VMs
azlin config set ssh.latency_max_workers 5

# Increase for faster networks (not recommended > 20)
azlin config set ssh.latency_max_workers 20
```

### Configuration File

Edit `~/.azlin/config.toml` directly:

```toml
[ssh]
latency_timeout = 5           # Timeout per VM (seconds)
latency_max_workers = 10      # Max parallel measurements

[cli]
show_progress = true          # Show progress bar during measurement
```

### CLI Flags Reference

| Flag | Description | Example |
|------|-------------|---------|
| `--with-latency` | Measure SSH latency for running VMs | `azlin list --with-latency` |
| `--all` | Show VMs from all resource groups | `azlin list --all --with-latency` |
| `--with-sessions` | Include tmux session count | `azlin list --with-latency --with-sessions` |
| `--format=json` | Output as JSON (includes all metrics) | `azlin list --with-latency --format=json` |

## Troubleshooting

### Latency Shows "timeout"

**Symptom:**
```
│ my-vm  │ Running  │ 10.0.1.5  │ eastus  │ Standard_B2s  │ 2  │ 4 GB  │ timeout  │
```

**Cause:** SSH connection took longer than 5 seconds (default timeout).

**Possible Reasons:**
1. **Network firewall blocking SSH** - Check network security group rules
2. **VM firewall blocking SSH** - Check VM-level firewall (iptables/ufw)
3. **VM under heavy load** - High CPU may delay SSH daemon response
4. **Geographic distance** - VMs in distant regions may have high latency
5. **Bastion-only access** - VM configured for Azure Bastion only (direct SSH disabled)

**Solutions:**

1. Verify SSH is allowed in network security group:
   ```bash
   az network nsg rule list \
     --nsg-name my-nsg \
     --resource-group my-rg \
     --query "[?destinationPortRange=='22']"
   ```

2. Increase timeout for slow networks:
   ```bash
   azlin config set ssh.latency_timeout 10
   azlin list --with-latency
   ```

3. Check if Bastion is required:
   ```bash
   # If Bastion is required, latency measurement via direct SSH won't work
   azlin connect my-vm  # Will use Bastion automatically
   ```

4. Test direct SSH connection manually:
   ```bash
   # Get VM IP
   azlin list

   # Test direct SSH
   ssh -o ConnectTimeout=5 azureuser@<vm-ip>
   ```

### Latency Shows "error"

**Symptom:**
```
│ my-vm  │ Running  │ 10.0.1.5  │ eastus  │ Standard_B2s  │ 2  │ 4 GB  │ error  │
```

**Cause:** SSH connection failed with an error.

**Possible Reasons:**
1. **Wrong SSH key** - Key Vault key doesn't match VM
2. **SSH daemon not running** - VM's sshd service crashed
3. **Permission denied** - Wrong username or key
4. **DNS resolution failed** - Can't resolve VM hostname
5. **Network unreachable** - No route to VM

**Solutions:**

1. Check SSH key sync:
   ```bash
   # Enable auto-sync if not already enabled
   azlin config get ssh.auto_sync_keys  # Should be true

   # Connect with auto-sync (will fix key mismatch)
   azlin connect my-vm
   ```

2. Verify SSH daemon is running:
   ```bash
   az vm run-command invoke \
     --name my-vm \
     --resource-group my-rg \
     --command-id RunShellScript \
     --scripts "systemctl status sshd"
   ```

3. Test connection with debug output:
   ```bash
   ssh -vvv -o ConnectTimeout=5 azureuser@<vm-ip>
   ```

4. Check VM system health:
   ```bash
   az vm get-instance-view \
     --name my-vm \
     --resource-group my-rg \
     --query instanceView.statuses
   ```

### Memory Shows "-"

**Symptom:**
```
│ my-vm  │ Running  │ 10.0.1.5  │ eastus  │ Custom_Size  │ 2  │ -  │ 45ms  │
```

**Cause:** VM size is not in the known VM size catalog.

**Reasons:**
1. **Custom VM size** - VM uses a custom or rare size not in catalog
2. **New Azure VM size** - Recently released size not yet added to azlin
3. **VM size format changed** - Azure changed naming convention

**Solutions:**

1. Check actual VM size in Azure:
   ```bash
   az vm show \
     --name my-vm \
     --resource-group my-rg \
     --query hardwareProfile.vmSize -o tsv
   ```

2. Look up memory manually:
   ```bash
   az vm list-sizes --location <region> \
     --query "[?name=='<vm-size>'].[name,memoryInMB]" -o table
   ```

3. File a feature request to add the VM size:
   ```bash
   # Include VM size name and memory (in GB)
   # Example: "Standard_NewSize_v6" with 32 GB
   ```

4. Workaround - use JSON output with Azure API query:
   ```bash
   azlin list --format=json | \
     jq -r '.[] | select(.memory == null) | .vm_size' | \
     xargs -I {} az vm list-sizes --location eastus \
       --query "[?name=='{}'].memoryInMB" -o tsv
   ```

### Latency Measurement Very Slow

**Symptom:**
```
Measuring SSH latency for 20 running VMs... (this is taking a while...)
```

**Cause:** Many VMs or slow network causing measurement to take 30+ seconds.

**Solutions:**

1. Reduce number of parallel workers (if network is saturated):
   ```bash
   azlin config set ssh.latency_max_workers 5
   azlin list --with-latency
   ```

2. Skip latency for quick checks:
   ```bash
   # Just list VMs without latency (instant)
   azlin list
   ```

3. Measure latency for specific VMs only:
   ```bash
   # Use grep or filter by resource group
   azlin list --with-latency | grep production
   ```

4. Check if some VMs are timing out:
   ```bash
   # Reduce timeout to fail faster on unreachable VMs
   azlin config set ssh.latency_timeout 3
   azlin list --with-latency
   ```

### Stopped VM Shows Memory but No Latency

**This is expected behavior.**

**Explanation:**
- **Memory**: Shows allocated resources (even when stopped, VM reserves memory)
- **Latency**: Cannot be measured (VM is not running, SSH unavailable)

**Example:**
```
│ staging-vm  │ Stopped  │ N/A  │ eastus  │ Standard_D4s_v3  │ 4  │ 16 GB  │ -  │
```

This is correct:
- Memory shows "16 GB" (allocated capacity)
- Latency shows "-" (can't measure when stopped)

### Bastion-Only VMs Show "error" for Latency

**This is expected behavior.**

**Explanation:**
- Latency measurement uses direct SSH connection
- Bastion-only VMs don't allow direct SSH (by design)
- Result: latency shows "error"

**Workaround:**
```bash
# Connect via Bastion (azlin handles this automatically)
azlin connect my-bastion-only-vm

# Or use Azure Bastion directly
az network bastion ssh \
  --name my-bastion \
  --resource-group my-rg \
  --target-resource-id /subscriptions/.../my-vm \
  --auth-type ssh-key \
  --username azureuser \
  --ssh-key ~/.ssh/id_rsa
```

**Note:** Adding Bastion tunnel latency measurement is a [planned feature](https://github.com/rysweet/azlin/issues/484).

## Frequently Asked Questions

### Does latency measurement work with Azure Bastion?

No. Latency measurement uses direct SSH connections. VMs that require Azure Bastion will show "error" for latency. This is expected behavior. See [Bastion-Only VMs](#bastion-only-vms-show-error-for-latency) above.

### Why is memory always displayed but latency is opt-in?

Memory information has zero performance overhead (hardcoded lookup, no API calls). Latency measurement requires actual SSH connections, taking 5-10 seconds for 10 VMs, so it's opt-in via `--with-latency`.

### Can I get memory information for custom VM sizes?

Not currently. Memory display uses a hardcoded catalog of Azure VM sizes. Custom or new VM sizes will show "-" for memory. You can look up memory manually using `az vm list-sizes`.

### What does "timeout" mean for latency?

"timeout" means the SSH connection took longer than 5 seconds (default). This usually indicates:
- Network firewall blocking SSH
- VM under very heavy load
- Geographic distance causing high latency
- Bastion-only configuration (direct SSH disabled)

### What's the difference between "timeout" and "error"?

- **timeout**: Connection attempt exceeded 5-second limit (network or firewall issue)
- **error**: Connection failed with an error (wrong key, SSH daemon down, DNS failure)

### Can I measure latency through Azure Bastion?

Not currently. Latency measurement only supports direct SSH connections. Measuring latency through Bastion tunnels is a planned feature.

### How accurate is the latency measurement?

Latency measurement is accurate for SSH connection time (±10-20ms). It measures:
- Network latency (ping time)
- SSH handshake (key exchange, authentication)
- SSH daemon response time

It does NOT include:
- Bastion tunnel creation (if applicable)
- First-packet latency (uses established connection)
- Application-level latency

### Does latency measurement affect VM performance?

No. Latency measurement:
- Establishes SSH connection briefly (< 1 second)
- Closes connection immediately after authentication
- Uses minimal CPU/memory on VM (~0.01%)
- No persistent connections

### Can I export memory and latency data?

Yes, use JSON format:

```bash
azlin list --with-latency --format=json > vm_metrics.json
```

Then process with jq or Python:

```bash
# Extract VMs with high latency (> 100ms)
cat vm_metrics.json | jq '.[] | select(.latency_ms > 100)'

# Calculate total memory
cat vm_metrics.json | jq '[.[] | select(.status == "Running")] | map(.memory_gb) | add'
```

### How do I interpret latency values?

| Latency | Interpretation | Action |
|---------|----------------|--------|
| 0-50ms | Excellent | Same region, optimal network |
| 50-100ms | Good | Same region or nearby regions |
| 100-200ms | Acceptable | Cross-region (e.g., US East to US West) |
| 200-500ms | High | Distant regions (e.g., US to Europe) |
| 500ms+ | Very High | Investigate network issues |
| timeout | Network Issue | Check firewalls, NSG rules |
| error | Configuration Issue | Check SSH keys, VM health |

### What's included in the memory total?

The summary line shows total memory for **running VMs only**:

```
3 VMs running | 14 vCPUs | 88 GB memory in use
```

Stopped VMs are NOT included in the total (they show allocated memory in the table, but don't count toward "in use").

### Can I see memory trends over time?

Not directly. Memory column shows allocated capacity (doesn't change unless you resize VM). For memory utilization trends, use Azure Monitor or VM insights:

```bash
# Memory ALLOCATED (static)
azlin list

# Memory UTILIZATION (dynamic - requires monitoring)
az vm metrics list \
  --resource my-vm \
  --resource-group my-rg \
  --metric "Percentage Memory" \
  --start-time 2025-12-13T00:00:00Z
```

## Advanced Topics

### JSON Output Format

Get structured data for automation:

```bash
azlin list --with-latency --format=json
```

Output:
```json
[
  {
    "session": "dev-session",
    "vm_name": "dev-vm-001",
    "status": "Running",
    "ip": "10.0.1.5",
    "region": "eastus",
    "size": "Standard_D4s_v3",
    "vcpus": 4,
    "memory_gb": 16,
    "latency_ms": 45.3,
    "latency_status": "success"
  },
  {
    "session": "problematic-vm",
    "vm_name": "problem-vm",
    "status": "Running",
    "ip": "10.0.3.5",
    "region": "eastus",
    "size": "Standard_B1ms",
    "vcpus": 1,
    "memory_gb": 2,
    "latency_ms": null,
    "latency_status": "timeout",
    "latency_error": "Connection timed out after 5.0 seconds"
  }
]
```

### Scripting with Memory and Latency Data

Find VMs with high latency:

```bash
#!/bin/bash
# Alert on VMs with > 200ms latency

azlin list --with-latency --format=json | \
  jq -r '.[] | select(.latency_ms > 200) |
    "WARNING: \(.vm_name) has high latency: \(.latency_ms)ms"'
```

Calculate memory utilization rate:

```bash
#!/bin/bash
# Show memory allocation efficiency

total_allocated=$(azlin list --all --format=json | \
  jq '[.[] | .memory_gb] | add')

total_in_use=$(azlin list --format=json | \
  jq '[.[] | select(.status == "Running") | .memory_gb] | add')

echo "Utilization: $((total_in_use * 100 / total_allocated))%"
```

### Performance Analysis

Compare latency across regions:

```bash
# Measure latency for all VMs
azlin list --with-latency --format=json > latency.json

# Group by region and calculate averages
cat latency.json | jq -r '
  group_by(.region) |
  map({
    region: .[0].region,
    avg_latency: (map(.latency_ms) | add / length)
  })
'
```

Output:
```json
[
  {"region": "eastus", "avg_latency": 48.5},
  {"region": "westus2", "avg_latency": 123.0},
  {"region": "westeurope", "avg_latency": 180.2}
]
```

### Memory Capacity Planning

Analyze memory allocation:

```bash
#!/bin/bash
# Generate memory capacity report

echo "Memory Capacity Report"
echo "======================"

# Total allocated
total=$(azlin list --all --format=json | jq '[.[] | .memory_gb] | add')
echo "Total Allocated: ${total} GB"

# By status
running=$(azlin list --format=json | \
  jq '[.[] | select(.status == "Running") | .memory_gb] | add')
echo "Running VMs: ${running} GB ($((running * 100 / total))%)"

stopped=$(azlin list --format=json | \
  jq '[.[] | select(.status == "Stopped") | .memory_gb] | add')
echo "Stopped VMs: ${stopped} GB ($((stopped * 100 / total))%)"

# By resource group
echo ""
echo "By Resource Group:"
azlin list --all --format=json | \
  jq -r 'group_by(.resource_group) |
    map({
      rg: .[0].resource_group,
      memory: (map(.memory_gb) | add)
    }) |
    .[] |
    "\(.rg): \(.memory) GB"'
```

### Monitoring Integration

Export metrics to monitoring system:

```bash
#!/bin/bash
# Export to Prometheus format

azlin list --with-latency --format=json | jq -r '
  .[] |
  "azlin_vm_memory_gb{vm=\"\(.vm_name)\",region=\"\(.region)\"} \(.memory_gb)\n" +
  "azlin_vm_latency_ms{vm=\"\(.vm_name)\",region=\"\(.region)\"} \(.latency_ms // 0)"
' > /var/lib/prometheus/node_exporter/azlin_metrics.prom
```

### Custom VM Size Mapping

If you use custom VM sizes, create a mapping file:

```bash
# ~/.azlin/custom_vm_sizes.json
cat > ~/.azlin/custom_vm_sizes.json <<EOF
{
  "Custom_Size_1": 32,
  "Custom_Size_2": 64,
  "Standard_NewSize_v6": 128
}
EOF

# Tell azlin to use it (feature in development)
azlin config set vm.custom_sizes_file ~/.azlin/custom_vm_sizes.json
```

## Related Documentation

- [VM Lifecycle Automation](./vm-lifecycle-automation.md) - Automatic VM management
- [Auto-Detect Resource Groups](./auto-detect-rg.md) - Automatic resource group discovery
- [Configuration Reference](../reference/config-default-behaviors.md) - Complete configuration options
- [Troubleshooting Connection Issues](../how-to/troubleshoot-connection-issues.md) - Comprehensive troubleshooting guide
- [Azure Monitor Integration](../monitoring.md) - Advanced monitoring and alerting

## Feedback

Found a bug or have a feature request? [Open an issue on GitHub](https://github.com/rysweet/azlin/issues/484).

Have questions? [Start a discussion](https://github.com/rysweet/azlin/discussions).
