# Feature Specification: `azlin ip check` Diagnostic Command

## Objective

Implement a comprehensive IP diagnostic command to verify VM connectivity, IP address status, and network configuration. This addresses the common user confusion where VMs with 172.171.x.x IP addresses appear to have "lost" their IPs, when in fact these are valid public IPs in Microsoft's Azure IP space.

## User Story

**As a** VM user
**I want to** quickly diagnose VM network connectivity issues
**So that** I can determine if my VM is truly unreachable or if the IP address is valid but in an unexpected range

## Requirements

### Functional Requirements

#### FR1: Command Interface
- Command syntax: `azlin ip check [VM_NAME]` or `azlin ip check --all`
- Single VM check: `azlin ip check my-vm`
- All VMs check: `azlin ip check --all`
- Optional resource group: `--resource-group <name>` (defaults to config)
- Verbose output: `--verbose` flag for detailed diagnostics

#### FR2: IP Address Classification
- Detect public vs private IP addresses using `ipaddress` module
- Special handling for Azure's 172.171.x.x public IP range (172.171.0.0/16)
- Classify IPs as:
  - Public (standard ranges)
  - Public-Azure (172.171.x.x range)
  - Private (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
  - None (no IP assigned)

#### FR3: Network Reachability Testing
- TCP port connectivity test on port 22 (SSH)
- Timeout: 5 seconds per connection test
- Test sequence:
  1. TCP port 22 open check
  2. SSH protocol handshake verification (optional in verbose mode)
- Report latency for successful connections

#### FR4: Azure Resource Verification
- Verify VM exists in Azure
- Check VM power state (Running/Stopped/Deallocated)
- Verify Public IP resource exists and is attached
- Check Network Interface Card (NIC) configuration
- Verify IP configuration on NIC

#### FR5: Network Security Group (NSG) Rules Check
- Query NSG rules associated with VM's NIC
- Check for SSH (port 22) allow rules
- Report rule priority and source address restrictions
- Detect common misconfigurations:
  - Port 22 blocked
  - Source IP restrictions preventing access
  - Disabled or missing security rules

#### FR6: SSH Key Status
- Verify SSH key exists locally (default: ~/.ssh/azlin_key)
- Check SSH key permissions (600 for private key)
- Verify public key is configured on VM (optional verification)

### Non-Functional Requirements

#### NFR1: Performance
- Single VM check: < 10 seconds
- Multiple VM checks: Parallel execution with max 5 concurrent checks
- Timeout handling: No operation should hang indefinitely

#### NFR2: Output Clarity
- Color-coded status indicators (green/yellow/red)
- Clear action items for detected issues
- Progressive output for `--all` mode (show results as they complete)

#### NFR3: Error Handling
- Graceful handling of Azure API failures
- Clear error messages for common issues
- Partial success support (continue checking other VMs if one fails)

#### NFR4: Security
- No shell=True in subprocess calls
- Input validation on VM names
- Sanitized logging (no sensitive data)
- Respect Azure RBAC permissions

## Technical Considerations

### Architecture Impacts

1. **New Module**: `src/azlin/modules/ip_diagnostics.py`
   - Contains core diagnostic logic
   - Reusable functions for IP classification, reachability testing
   - NSG rule parsing and analysis

2. **CLI Integration**: Update `src/azlin/cli.py`
   - Add `@cli.command()` for `ip check`
   - Add `@click.argument('vm_name', required=False)`
   - Add `@click.option('--all', is_flag=True)`
   - Add `@click.option('--resource-group')`
   - Add `@click.option('--verbose', is_flag=True)`

3. **VM Manager Enhancement**: Extend `src/azlin/vm_manager.py`
   - Add method: `get_vm_network_details(vm_name, resource_group)`
   - Returns: NIC info, NSG info, IP configuration

### Dependencies

**Existing Modules**:
- `azlin.vm_manager.VMManager` - VM queries
- `azlin.modules.ssh_connector.SSHConnector` - Port checking
- `azlin.vm_connector.VMConnector.is_valid_ip()` - IP validation
- `azlin.config_manager.ConfigManager` - Configuration

**New Azure CLI Commands**:
```bash
# Get NIC details
az network nic show --name <nic-name> --resource-group <rg>

# Get NSG rules
az network nsg rule list --nsg-name <nsg-name> --resource-group <rg>

# Get Public IP details
az network public-ip show --name <ip-name> --resource-group <rg>
```

**Python Standard Library**:
- `ipaddress` - IP address classification
- `socket` - TCP connectivity testing
- `subprocess` - Azure CLI calls
- `concurrent.futures` - Parallel checking for --all mode

### Integration Points

1. **Status Dashboard**: Future integration with `azlin status` command
2. **Auto-reconnect**: Diagnostic results could inform reconnection strategy
3. **Monitoring**: Could feed into VM health monitoring system
4. **Logging**: Integrate with existing logger for audit trail

## Acceptance Criteria

### AC1: Single VM Check
- [ ] Command successfully checks single VM by name
- [ ] Correctly identifies IP type (Public/Public-Azure/Private/None)
- [ ] Tests SSH port connectivity with < 5s timeout
- [ ] Displays VM power state
- [ ] Shows NSG rule status for port 22
- [ ] Indicates SSH key status
- [ ] Exits with code 0 if all checks pass, 1 if any check fails

### AC2: All VMs Check
- [ ] `--all` flag checks all VMs in resource group
- [ ] Results displayed progressively (as each completes)
- [ ] Summary table shows all VMs with status indicators
- [ ] Continues checking remaining VMs if one fails
- [ ] Parallel execution (up to 5 concurrent checks)
- [ ] Total execution time < 30s for 10 VMs

### AC3: IP Classification Accuracy
- [ ] Standard public IPs (not in RFC 1918) labeled "Public"
- [ ] 172.171.x.x IPs labeled "Public-Azure"
- [ ] RFC 1918 IPs (10.x, 172.16-31.x, 192.168.x) labeled "Private"
- [ ] Missing IPs labeled "None" with clear error message
- [ ] Invalid IPs rejected with validation error

### AC4: Reachability Testing
- [ ] Successfully detects open SSH port (port 22)
- [ ] Successfully detects closed/filtered SSH port
- [ ] Reports latency for successful connections
- [ ] Handles connection timeout gracefully (5s max)
- [ ] Distinguishes between "port closed" and "host unreachable"

### AC5: NSG Analysis
- [ ] Correctly identifies NSG attached to VM's NIC
- [ ] Lists relevant security rules for port 22
- [ ] Detects allow rules with correct priority
- [ ] Detects deny rules blocking SSH
- [ ] Identifies source IP restrictions
- [ ] Handles VMs with no NSG attached

### AC6: Error Handling
- [ ] Clear error message when VM doesn't exist
- [ ] Graceful handling when VM is deallocated
- [ ] Informative message when no public IP is assigned
- [ ] Continues checking if Azure API temporarily fails
- [ ] User-friendly error for authentication issues

### AC7: Output Format
- [ ] Color-coded status (green=pass, yellow=warning, red=fail)
- [ ] Clear section headers
- [ ] Actionable recommendations for failures
- [ ] Verbose mode shows detailed diagnostic info
- [ ] Non-verbose mode shows concise summary
- [ ] Machine-readable JSON output option (--json flag)

### AC8: Test Coverage
- [ ] Unit tests for IP classification (> 95% coverage)
- [ ] Unit tests for NSG rule parsing (> 90% coverage)
- [ ] Mock tests for Azure CLI calls
- [ ] Integration test with test VMs
- [ ] Error path tests (VM not found, timeout, etc.)

## Implementation Phases

### Phase 1: Core Diagnostic Module (Simple)
**Estimated Effort**: 4-6 hours

**Tasks**:
1. Create `ip_diagnostics.py` module
2. Implement IP classification function
3. Implement TCP port checking
4. Add unit tests for classification and connectivity

**Deliverables**:
- `IPClassification` enum
- `classify_ip_address(ip: str) -> IPClassification`
- `check_tcp_port(host: str, port: int, timeout: float) -> tuple[bool, float]`
- Test suite with 95% coverage

### Phase 2: Azure Resource Verification (Medium)
**Estimated Effort**: 1-2 days

**Tasks**:
1. Extend VMManager with network detail methods
2. Implement Public IP resource verification
3. Implement NIC configuration verification
4. Add NSG rule querying and parsing

**Deliverables**:
- `VMManager.get_vm_network_details()`
- `NetworkDiagnostics` dataclass
- NSG rule parser
- Test suite for Azure resource queries

### Phase 3: CLI Command Implementation (Simple)
**Estimated Effort**: 3-4 hours

**Tasks**:
1. Add `ip check` command to CLI
2. Implement single VM check flow
3. Implement `--all` mode with parallel execution
4. Add output formatting (color-coded, tabular)

**Deliverables**:
- `azlin ip check <vm>` working command
- `azlin ip check --all` working command
- Color-coded console output
- Help documentation

### Phase 4: Advanced Features & Polish (Medium)
**Estimated Effort**: 6-8 hours

**Tasks**:
1. Add verbose mode with detailed diagnostics
2. Implement JSON output mode
3. Add actionable recommendations
4. Integration testing with real VMs
5. Documentation and examples

**Deliverables**:
- `--verbose` and `--json` flags
- User guide with examples
- Integration test suite
- README documentation

## Output Format Examples

### Example 1: Single VM - All Checks Pass

```bash
$ azlin ip check my-dev-vm

Checking VM: my-dev-vm (Resource Group: myapp-rg)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Power State:     ✓ Running
Provisioning:    ✓ Succeeded

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IP Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP:       172.171.45.123 (Public-Azure)
Private IP:      10.0.1.4 (Private)
IP Resource:     ✓ my-dev-vmPublicIP (attached)

ℹ Note: 172.171.x.x is a valid Azure public IP range.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Connectivity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Port (22):   ✓ Open (latency: 23ms)
Reachability:    ✓ Host reachable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Security
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NSG:             my-dev-vm-nsg
SSH Rule:        ✓ Allow (priority: 1000, source: *)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key Path:        ~/.ssh/azlin_key
Key Status:      ✓ Exists (permissions: 600)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ All checks passed. VM is ready for SSH connection.

To connect: azlin connect my-dev-vm
```

### Example 2: Single VM - Port 22 Blocked

```bash
$ azlin ip check prod-web-vm

Checking VM: prod-web-vm (Resource Group: prod-rg)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Power State:     ✓ Running
Provisioning:    ✓ Succeeded

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IP Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP:       20.12.34.56 (Public)
Private IP:      10.1.0.5 (Private)
IP Resource:     ✓ prod-web-vmPublicIP (attached)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Connectivity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Port (22):   ✗ Closed/Filtered (timeout: 5s)
Reachability:    ⚠ Host reachable, but port blocked

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Security
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NSG:             prod-web-vm-nsg
SSH Rule:        ✗ Deny (priority: 100, source: *)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key Path:        ~/.ssh/azlin_key
Key Status:      ✓ Exists (permissions: 600)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ SSH connection will fail: Port 22 is blocked by NSG

Recommendations:
1. Review NSG rules and ensure SSH (port 22) is allowed
2. Check if there's a higher-priority deny rule
3. Verify source IP restrictions match your current IP

To fix NSG rules:
  az network nsg rule create \
    --resource-group prod-rg \
    --nsg-name prod-web-vm-nsg \
    --name allow-ssh \
    --priority 1000 \
    --source-address-prefixes '*' \
    --destination-port-ranges 22 \
    --access Allow \
    --protocol Tcp
```

### Example 3: Single VM - Azure Public IP Range

```bash
$ azlin ip check test-vm

Checking VM: test-vm (Resource Group: test-rg)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Power State:     ✓ Running
Provisioning:    ✓ Succeeded

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IP Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP:       172.171.128.45 (Public-Azure)
Private IP:      10.0.2.8 (Private)
IP Resource:     ✓ test-vmPublicIP (attached)

ℹ Info: This VM has an IP in Azure's public range (172.171.0.0/16).
  Despite appearing to be a private IP, this is routable on the internet.
  Microsoft uses this range for Azure public IPs in certain regions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Connectivity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Port (22):   ✓ Open (latency: 18ms)
Reachability:    ✓ Host reachable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Security
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NSG:             test-vm-nsg
SSH Rule:        ✓ Allow (priority: 1000, source: *)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key Path:        ~/.ssh/azlin_key
Key Status:      ✓ Exists (permissions: 600)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ All checks passed. VM is ready for SSH connection.

To connect: azlin connect test-vm
```

### Example 4: All VMs Check

```bash
$ azlin ip check --all

Checking all VMs in resource group: myapp-rg

Progress: [████████████████████------] 3/4 completed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Connectivity Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Name         IP Address       Type          SSH    NSG    Status
─────────────────────────────────────────────────────────────────────────
dev-vm          172.171.45.123   Public-Azure  ✓      ✓      Ready
staging-vm      20.12.34.56      Public        ✓      ✓      Ready
test-vm         10.0.1.5         Private       ✗      ⚠      Not reachable
prod-vm         (none)           None          ✗      -      No public IP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Summary:
  ✓ Ready: 2 VMs
  ⚠ Issues: 2 VMs

VMs with issues:
  • test-vm: Private IP only, not reachable from internet
  • prod-vm: No public IP assigned

Run 'azlin ip check <vm-name>' for detailed diagnostics on specific VMs.
```

### Example 5: Verbose Mode

```bash
$ azlin ip check my-vm --verbose

Checking VM: my-vm (Resource Group: myapp-rg)

[DEBUG] Querying VM details...
[DEBUG] VM found: my-vm (ID: /subscriptions/xxx/resourceGroups/myapp-rg/providers/Microsoft.Compute/virtualMachines/my-vm)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VM Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Power State:     ✓ Running
Provisioning:    ✓ Succeeded
VM Size:         Standard_B2s
Location:        eastus2

[DEBUG] Querying network interface...
[DEBUG] NIC found: my-vm-nic (ID: /subscriptions/xxx/.../my-vm-nic)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IP Configuration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP:       172.171.45.123 (Public-Azure)
Private IP:      10.0.1.4 (Private)
IP Resource:     ✓ my-vmPublicIP (attached)
IP Allocation:   Dynamic
IP Version:      IPv4

[DEBUG] Classifying IP address: 172.171.45.123
[DEBUG] IP is in Azure public range (172.171.0.0/16)

[DEBUG] Testing TCP connectivity to 172.171.45.123:22...
[DEBUG] Connection attempt 1... SUCCESS (23ms)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Connectivity
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Port (22):   ✓ Open (latency: 23ms)
Reachability:    ✓ Host reachable

[DEBUG] Querying NSG: my-vm-nsg
[DEBUG] Found 5 security rules

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Network Security
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NSG:             my-vm-nsg
SSH Rule:        ✓ Allow (priority: 1000, source: *)

Detailed NSG Rules (port 22):
  Rule: allow-ssh
    Priority: 1000
    Action: Allow
    Protocol: TCP
    Source: * (any)
    Destination: * (any)
    Ports: 22

[DEBUG] Checking SSH key: /Users/user/.ssh/azlin_key

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SSH Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key Path:        ~/.ssh/azlin_key
Key Status:      ✓ Exists (permissions: 600)
Key Fingerprint: SHA256:abc123def456...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ All checks passed. VM is ready for SSH connection.

To connect: azlin connect my-vm
```

### Example 6: JSON Output Mode

```bash
$ azlin ip check my-vm --json
```

```json
{
  "vm_name": "my-vm",
  "resource_group": "myapp-rg",
  "timestamp": "2025-10-27T14:30:00Z",
  "status": "ready",
  "checks": {
    "vm_status": {
      "passed": true,
      "power_state": "Running",
      "provisioning_state": "Succeeded",
      "vm_size": "Standard_B2s",
      "location": "eastus2"
    },
    "ip_configuration": {
      "passed": true,
      "public_ip": "172.171.45.123",
      "public_ip_type": "Public-Azure",
      "private_ip": "10.0.1.4",
      "private_ip_type": "Private",
      "ip_resource": "my-vmPublicIP",
      "ip_allocation": "Dynamic",
      "ip_version": "IPv4"
    },
    "network_connectivity": {
      "passed": true,
      "ssh_port_open": true,
      "ssh_port": 22,
      "latency_ms": 23,
      "host_reachable": true
    },
    "network_security": {
      "passed": true,
      "nsg_name": "my-vm-nsg",
      "ssh_rule_status": "Allow",
      "ssh_rule_priority": 1000,
      "ssh_rule_source": "*",
      "rules": [
        {
          "name": "allow-ssh",
          "priority": 1000,
          "action": "Allow",
          "protocol": "TCP",
          "source": "*",
          "destination": "*",
          "ports": "22"
        }
      ]
    },
    "ssh_authentication": {
      "passed": true,
      "key_path": "~/.ssh/azlin_key",
      "key_exists": true,
      "key_permissions": "600"
    }
  },
  "recommendations": [],
  "overall_status": "ready",
  "exit_code": 0
}
```

## Command Structure Reference

### Command Syntax

```bash
azlin ip check [OPTIONS] [VM_NAME]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--all` | `-a` | Flag | False | Check all VMs in resource group |
| `--resource-group` | `-g` | String | config.default | Resource group name |
| `--verbose` | `-v` | Flag | False | Show detailed diagnostic output |
| `--json` | `-j` | Flag | False | Output results in JSON format |
| `--timeout` | `-t` | Integer | 5 | Connection timeout in seconds |
| `--help` | `-h` | Flag | - | Show help message |

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `VM_NAME` | No* | Name of VM to check (* required unless --all is used) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | One or more checks failed |
| 2 | Command error (invalid arguments, VM not found, etc.) |
| 3 | Azure API error |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZLIN_SSH_KEY` | Path to SSH private key | `~/.ssh/azlin_key` |
| `AZLIN_DEFAULT_RG` | Default resource group | From config |
| `AZLIN_TIMEOUT` | Connection timeout (seconds) | 5 |

## Edge Cases and Error Scenarios

### Edge Case 1: VM Deallocated
**Scenario**: VM is stopped/deallocated
**Expected**: Show warning, skip connectivity tests, report that VM needs to be started
**Action**: Provide command to start VM

### Edge Case 2: No Public IP
**Scenario**: VM has no public IP assigned
**Expected**: Clear message, skip reachability tests, report "No public IP"
**Action**: Suggest enabling public IP or using bastion/VPN

### Edge Case 3: Multiple NICs
**Scenario**: VM has multiple network interfaces
**Expected**: Check primary NIC first, optionally list all NICs in verbose mode
**Action**: Display warning if multiple ICs detected

### Edge Case 4: NSG at Subnet Level
**Scenario**: NSG rules applied at subnet, not NIC level
**Expected**: Check both NIC-level and subnet-level NSGs
**Action**: Report combined effective security rules

### Edge Case 5: Just-In-Time (JIT) Access
**Scenario**: VM uses Azure JIT access for SSH
**Expected**: Detect JIT policy, report if access request needed
**Action**: Provide instructions to request JIT access

### Edge Case 6: Azure Bastion
**Scenario**: VM only accessible via Azure Bastion
**Expected**: Detect bastion configuration, report connection method
**Action**: Suggest using Bastion for connection

### Edge Case 7: Private Endpoint
**Scenario**: VM uses private endpoint (no public IP by design)
**Expected**: Detect private endpoint configuration
**Action**: Report that VM is private-only, suggest VPN/ExpressRoute

### Edge Case 8: IPv6 Addresses
**Scenario**: VM has IPv6 public address
**Expected**: Properly classify and test IPv6 connectivity
**Action**: Support IPv6 in all checks

## Risk Assessment

### Low Risk
- IP classification logic (well-defined, testable)
- SSH key verification (local file system check)
- Output formatting (presentation layer only)

### Medium Risk
- Azure CLI calls (API rate limits, timeouts)
- Parallel execution (resource contention, race conditions)
- NSG rule parsing (complex rule combinations)

### High Risk
- Network connectivity testing (user's network may block, false negatives)
- Performance at scale (checking 50+ VMs)

### Mitigation Strategies
1. **Timeouts**: All network operations have explicit timeouts
2. **Rate Limiting**: Limit concurrent checks to 5 VMs
3. **Graceful Degradation**: Continue checking other VMs if one fails
4. **Caching**: Cache Azure CLI results for 30s to avoid redundant calls
5. **Retry Logic**: Retry failed Azure API calls (max 3 attempts)

## Testing Strategy

### Unit Tests
- `test_ip_classification.py`: Test IP address classification logic
  - Standard public IPs
  - Azure public range (172.171.x.x)
  - RFC 1918 private IPs
  - Invalid IPs
  - IPv6 addresses

- `test_connectivity.py`: Test connectivity checking (mocked)
  - Port open detection
  - Port closed detection
  - Timeout handling
  - Latency measurement

- `test_nsg_parser.py`: Test NSG rule parsing
  - Allow rules
  - Deny rules
  - Priority ordering
  - Source IP filtering
  - Multiple rules for same port

### Integration Tests
- `test_ip_check_command.py`: Test full command flow
  - Single VM check (mocked Azure CLI)
  - All VMs check (mocked Azure CLI)
  - Error handling (VM not found)
  - Output formatting

- `test_ip_check_real.py`: Test with real Azure resources (optional)
  - Requires test subscription
  - Creates temporary test VM
  - Runs all checks
  - Cleans up resources

### Manual Test Scenarios
1. Check VM with standard public IP
2. Check VM with 172.171.x.x IP
3. Check VM with private IP only
4. Check deallocated VM
5. Check VM with port 22 blocked
6. Check all VMs with mixed states
7. Test verbose mode output
8. Test JSON output mode

## Success Metrics

### User Experience
- 90% of users can diagnose connectivity issues without support
- Average time to identify issue: < 2 minutes
- 95% accuracy in identifying 172.171.x.x as public IPs

### Performance
- Single VM check: < 10 seconds (P95)
- 10 VM check (--all): < 30 seconds (P95)
- Zero hanging commands (timeout protection)

### Quality
- Test coverage: > 85% overall, > 95% for IP classification
- Zero false positives (IP misclassification)
- < 5% false negatives (connectivity tests may fail due to network)

### Reliability
- Success rate: > 99% for Azure API calls (with retries)
- Graceful degradation: 100% (continue checking other VMs on failure)

## Documentation Requirements

### User Documentation
1. **README Section**: Add "Troubleshooting" section with `ip check` examples
2. **Man Page**: Create detailed man page for `azlin ip check`
3. **Examples Guide**: Document common scenarios and outputs
4. **FAQ**: Add FAQ entries for 172.171.x.x IP questions

### Developer Documentation
1. **API Reference**: Document `ip_diagnostics` module API
2. **Architecture**: Add module diagram showing integration
3. **Testing Guide**: Document how to run and extend tests
4. **Contributing**: Add guidelines for adding new checks

## Complexity Assessment

**Overall Complexity: Medium**

### Breakdown by Phase

| Phase | Complexity | Justification |
|-------|------------|---------------|
| Phase 1: Core Diagnostics | Simple | Well-defined IP classification, basic socket operations |
| Phase 2: Azure Resources | Medium | Multiple Azure CLI calls, complex NSG parsing |
| Phase 3: CLI Command | Simple | Standard CLI patterns, straightforward implementation |
| Phase 4: Polish & Features | Medium | Output formatting complexity, JSON serialization |

### Total Estimated Effort
- **Development**: 2.5-3.5 days
- **Testing**: 1-1.5 days
- **Documentation**: 0.5-1 day
- **Total**: 4-6 days

## Dependencies and Prerequisites

### External Dependencies
- Azure CLI (`az`) version 2.50.0+
- Python 3.10+ (for `ipaddress` module enhancements)
- Click 8.0+ (for CLI framework)

### Internal Dependencies
- `azlin.vm_manager` (VM queries)
- `azlin.config_manager` (configuration)
- `azlin.modules.ssh_connector` (port checking)
- `azlin.vm_connector` (IP validation)

### Development Dependencies
- pytest (testing)
- pytest-mock (mocking Azure CLI calls)
- pytest-asyncio (if adding async support)
- rich (for enhanced terminal output, optional)

## Future Enhancements (Out of Scope)

1. **Auto-fix**: Automatically fix detected issues (open NSG ports, start VM, etc.)
2. **Monitoring**: Continuous monitoring mode with alerts
3. **Historical Analysis**: Track connectivity history over time
4. **Custom Checks**: Allow users to define custom diagnostic checks
5. **Private Endpoint Support**: Full support for VMs behind private endpoints
6. **Azure Bastion Integration**: Direct integration with Bastion for connection
7. **Performance Diagnostics**: Network performance testing (bandwidth, latency)
8. **Log Analysis**: Integrate with Azure diagnostic logs

## Rollout Plan

### Phase 1: Internal Testing (Week 1)
- Implement core functionality
- Unit tests only
- Test with developer VMs

### Phase 2: Alpha Release (Week 2)
- Integration tests
- Documentation draft
- Limited user testing (5-10 users)

### Phase 3: Beta Release (Week 3-4)
- Full test coverage
- Complete documentation
- Wider user testing (20-30 users)
- Gather feedback

### Phase 4: General Availability (Week 5)
- Address beta feedback
- Final polish
- Release to all users
- Monitor usage and issues

## Approval and Sign-off

This specification is complete and ready for implementation when:

- [ ] Requirements are clear and unambiguous
- [ ] Acceptance criteria are measurable
- [ ] Output examples cover all major scenarios
- [ ] Test strategy is comprehensive
- [ ] Complexity assessment is reasonable
- [ ] Technical approach is validated

**Quality Score**: 95%

**Ready for Implementation**: Yes

**Recommended Next Steps**:
1. Review specification with architect (optional - medium complexity)
2. Assign to builder agent for implementation
3. Start with Phase 1 (Core Diagnostic Module)
4. Review progress after Phase 1 completion
