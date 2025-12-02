# Network Security Enhancements

**Status**: Production Ready
**Category**: Security / How-To Guide
**Audience**: DevOps Engineers, Security Teams, Cloud Administrators
**Last Updated**: 2025-12-01

---

## Overview

Ahoy! This guide be showin' ye how to use azlin's comprehensive network security management system. These features provide defense-in-depth security fer yer Azure VMs through automated Network Security Group (NSG) management, enhanced Bastion connectivity, VPN configuration, and security audit logging.

**Key Features**:
- **NSG Automation**: Template-based NSG management with 100% validation coverage
- **Bastion Enhancements**: Connection pooling, automatic cleanup, localhost enforcement
- **VPN/Private Endpoints**: Secure private connectivity configuration
- **Security Audit Logging**: Comprehensive, tamper-proof audit trails
- **Vulnerability Scanning**: Automated integration with Azure Security Center

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [NSG Template System](#nsg-template-system)
3. [Bastion Connection Management](#bastion-connection-management)
4. [Security Audit Logging](#security-audit-logging)
5. [Vulnerability Scanning](#vulnerability-scanning)
6. [VPN and Private Endpoints](#vpn-and-private-endpoints)
7. [Security Workflows](#security-workflows)
8. [CLI Reference](#cli-reference)
9. [Compliance and Best Practices](#compliance-and-best-practices)

---

## Quick Start

### Prerequisites

- Azure CLI authenticated (`az login`)
- azlin installed (`uvx azlin` or from source)
- Azure subscription with appropriate permissions

### Basic Secure VM Creation

```bash
# Create a VM with default security (Bastion + locked-down NSG)
azlin create my-secure-vm \
  --resource-group my-rg \
  --region westus2 \
  --nsg-template locked-down-vm

# Connect via Bastion (automatic tunnel pooling)
azlin connect my-secure-vm
```

**Expected Output**:
```
✅ Validating NSG template 'locked-down-vm'...
✅ Template validated successfully (0 critical findings)
✅ Creating VM 'my-secure-vm' with no public IP...
✅ Applying NSG rules from template...
✅ Creating Bastion tunnel (pooled connection)...
🔐 Connected to my-secure-vm via Bastion on localhost:50123

Security Summary:
  ✓ No public IP assigned
  ✓ SSH access via Bastion only
  ✓ NSG rules: deny-by-default
  ✓ Audit event logged
```

---

## NSG Template System

### Overview

The NSG template system provides pre-validated, secure Network Security Group configurations fer common scenarios. Templates be validated against security policies BEFORE application, preventin' misconfigurations.

**Philosophy**: NSGs be the first line o' defense. Misconfiguration be the #1 security risk. Template-based management with validation prevents human error.

### Using NSG Templates

#### 1. List Available Templates

```bash
azlin nsg list-templates
```

**Output**:
```
Available NSG Templates:

📦 locked-down-vm
   Description: Bastion-only access, no inbound internet
   Use Case: Development VMs, internal services
   Compliance: CIS-6.2, SOC2-CC6.6

📦 web-server-nsg
   Description: HTTPS/HTTP allowed, SSH via Bastion
   Use Case: Public web servers
   Compliance: CIS-6.1, CIS-6.2, ISO27001-A.13.1

📦 database-nsg
   Description: Private VNet access only, no internet
   Use Case: Database servers, data tier
   Compliance: CIS-6.2, SOC2-CC6.6

📦 nat-gateway-nsg
   Description: Outbound internet, no inbound
   Use Case: API clients, batch processors
   Compliance: CIS-6.2

📦 internal-service-nsg
   Description: VNet-internal communication only
   Use Case: Microservices, internal APIs
   Compliance: CIS-6.2, ISO27001-A.13.1
```

#### 2. View Template Details

```bash
azlin nsg show-template web-server-nsg
```

**Output**:
```yaml
name: "web-server-nsg"
description: "NSG for internet-facing web servers"
version: "1.0"

metadata:
  author: "Security Team"
  compliance:
    - "CIS Azure 6.1"
    - "SOC2 CC6.6"
  tags:
    - "web"
    - "public"

security_rules:
  - name: "allow-https-inbound"
    priority: 100
    direction: "Inbound"
    access: "Allow"
    protocol: "Tcp"
    source_port_range: "*"
    destination_port_range: "443"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: "HTTPS traffic for web service"

  - name: "allow-http-redirect"
    priority: 110
    direction: "Inbound"
    access: "Allow"
    protocol: "Tcp"
    source_port_range: "*"
    destination_port_range: "80"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: "HTTP to HTTPS redirect"

  - name: "deny-ssh-from-internet"
    priority: 200
    direction: "Inbound"
    access: "Deny"
    protocol: "Tcp"
    source_port_range: "*"
    destination_port_range: "22"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: "Block direct SSH from internet"

  - name: "deny-all-other-inbound"
    priority: 4096
    direction: "Inbound"
    access: "Deny"
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: "Default deny for inbound traffic"
```

#### 3. Validate Template Before Applying

```bash
azlin nsg validate web-server-nsg --dry-run
```

**Output**:
```
🔍 Validating NSG template 'web-server-nsg'...

✅ Schema Validation: PASSED
✅ Policy Compliance: PASSED
✅ Deny-by-Default: PASSED
✅ Dangerous Rules: NONE FOUND

Security Checks:
  ✓ No SSH/RDP exposed to internet
  ✓ Deny-all default rule present
  ✓ Rule priorities valid (100-4096)
  ✓ All rules have justifications

Compliance Mappings:
  ✓ CIS Azure 6.1: Restrict RDP access
  ✓ CIS Azure 6.2: Restrict SSH access
  ✓ SOC2 CC6.6: Network security controls
  ✓ ISO27001 A.13.1: Network controls

0 CRITICAL findings
0 warnings
```

#### 4. Apply Template to NSG

```bash
# Create new NSG from template
azlin nsg apply web-server-nsg \
  --nsg-name my-web-nsg \
  --resource-group prod-rg

# Update existing NSG
azlin nsg apply web-server-nsg \
  --nsg-name existing-nsg \
  --resource-group prod-rg \
  --update
```

**Output**:
```
🔍 Validating template...
✅ Template validated (0 critical findings)

📋 Planned Changes:
  + allow-https-inbound (priority 100)
  + allow-http-redirect (priority 110)
  + deny-ssh-from-internet (priority 200)
  + deny-all-other-inbound (priority 4096)

Apply these changes? [y/N]: y

✅ NSG 'my-web-nsg' created
✅ Applied 4 security rules
🔐 Security audit event logged

Security Summary:
  NSG: my-web-nsg
  Rules Applied: 4
  Critical Findings: 0
  Compliance: CIS-6.1, CIS-6.2, SOC2-CC6.6
```

### Creating Custom Templates

#### 1. Export Existing NSG as Template

```bash
azlin nsg export my-existing-nsg \
  --resource-group prod-rg \
  --output custom-template.yaml
```

#### 2. Create Template from Scratch

Create a file `my-custom-nsg.yaml`:

```yaml
name: "my-custom-nsg"
description: "Custom NSG for my application"
version: "1.0"

metadata:
  author: "DevOps Team"
  compliance:
    - "CIS Azure 6.2"
  tags:
    - "custom"
    - "application"

security_rules:
  - name: "allow-app-port"
    priority: 100
    direction: "Inbound"
    access: "Allow"
    protocol: "Tcp"
    source_port_range: "*"
    destination_port_range: "8080"
    source_address_prefix: "10.0.0.0/16"  # VNet only
    destination_address_prefix: "*"
    justification: "Application traffic from VNet"

  - name: "deny-all-other-inbound"
    priority: 4096
    direction: "Inbound"
    access: "Deny"
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: "Default deny"

default_rules:
  outbound: "Allow"
  inbound: "Deny"
```

#### 3. Validate Custom Template

```bash
azlin nsg validate my-custom-nsg.yaml --dry-run
```

### NSG Policy Violations

If yer template violates security policies, validation will FAIL:

```bash
azlin nsg validate bad-template.yaml
```

**Output** (example of failure):
```
🔍 Validating NSG template 'bad-template'...

❌ Schema Validation: PASSED
❌ Policy Compliance: FAILED

🚨 CRITICAL FINDINGS:

1. [CRITICAL] SSH exposed to internet
   Rule: allow-ssh-from-anywhere
   Violation: SSH (port 22) allowed from Internet
   Remediation: Remove this rule or use Azure Bastion for SSH access
   Compliance Impact: CIS-6.2, SOC2-CC6.6

2. [CRITICAL] Missing deny-default rule
   NSG does not have explicit deny-all rule for inbound traffic
   Remediation: Add deny-all rule with priority 4096
   Compliance Impact: CIS-6.2

❌ Deployment BLOCKED due to CRITICAL findings
```

---

## Bastion Connection Management

### Overview

azlin provides enhanced Bastion connection management with **connection pooling**, **automatic cleanup**, and **localhost enforcement** fer security and performance.

**Key Benefits**:
- **15x faster reconnections**: Reuse tunnels instead o' creatin' new ones (15s → <1s)
- **Automatic cleanup**: Idle tunnels cleaned up, no resource leaks
- **Security enforced**: All tunnels bound to localhost (127.0.0.1) only
- **Connection limits**: Prevents port exhaustion

### Basic Bastion Connection

```bash
# Connect to VM via Bastion
azlin connect my-vm --resource-group my-rg
```

**Output**:
```
🔍 Finding Bastion host...
✅ Found: my-bastion in my-rg

🔐 Creating Bastion tunnel...
✅ Tunnel established on localhost:50123

🔗 Connecting to VM...
Welcome to my-vm!
```

### Connection Pooling

Connections be automatically pooled based on (bastion, vm, port) tuple:

```bash
# First connection (creates tunnel, ~15 seconds)
azlin connect vm1 --resource-group my-rg

# Second connection to same VM (reuses tunnel, <1 second)
azlin connect vm1 --resource-group my-rg

# Connection to different VM (new tunnel)
azlin connect vm2 --resource-group my-rg
```

**Connection Pool Status**:
```bash
azlin bastion pool-status
```

**Output**:
```
🔐 Bastion Connection Pool Status

Active Tunnels: 2
Max Tunnels: 10
Idle Timeout: 300s

Tunnel #1:
  VM: vm1
  Bastion: my-bastion
  Port: 50123 → 22
  Created: 2 minutes ago
  Last Used: 10 seconds ago
  Use Count: 5
  Status: HEALTHY

Tunnel #2:
  VM: vm2
  Bastion: my-bastion
  Port: 50124 → 22
  Created: 1 minute ago
  Last Used: 30 seconds ago
  Use Count: 2
  Status: HEALTHY
```

### Manual Tunnel Management

```bash
# Create tunnel without connecting
azlin bastion create-tunnel \
  --vm my-vm \
  --resource-group my-rg \
  --local-port 50123

# Close specific tunnel
azlin bastion close-tunnel --port 50123

# Close all tunnels
azlin bastion close-all

# Health check
azlin bastion health-check --port 50123
```

### Security Features

#### Localhost-Only Binding

All Bastion tunnels be bound to `127.0.0.1` (localhost) only. This prevents network-wide access to yer tunnels.

**Verification**:
```bash
# This will connect (localhost)
ssh -p 50123 azureuser@127.0.0.1

# This will FAIL (not localhost)
ssh -p 50123 azureuser@192.168.1.100  # Connection refused
```

**Security Check Output**:
```
🔐 Security Validation: PASSED
  ✓ Tunnel bound to localhost (127.0.0.1)
  ✓ Not accessible from network
  ✓ Connection limit enforced
```

#### Connection Limits

```bash
# Set connection limit (default: 10)
azlin bastion set-limit 20

# View current limit
azlin bastion show-config
```

**Output when limit reached**:
```
❌ Connection limit reached (10/10)
   Close unused tunnels or increase limit:
   azlin bastion close-all
   azlin bastion set-limit 20
```

### Automatic Cleanup

Idle tunnels be automatically cleaned up after 5 minutes (configurable):

```bash
# Configure idle timeout (seconds)
azlin bastion set-idle-timeout 600  # 10 minutes

# Manual cleanup of expired tunnels
azlin bastion cleanup-expired
```

**Cleanup Output**:
```
🧹 Cleaning up expired tunnels...
  Closed tunnel to vm1 (idle for 6 minutes)
  Closed tunnel to vm2 (idle for 8 minutes)
✅ Cleaned up 2 expired tunnels
```

---

## Security Audit Logging

### Overview

All security-sensitive operations be logged to a comprehensive, tamper-proof audit trail. This provides accountability, compliance support, and forensic capabilities.

**Key Features**:
- **Comprehensive event logging**: All security decisions recorded
- **Tamper-evident**: Integrity checksums, 0600 permissions
- **Compliance reports**: CIS, SOC2, ISO27001 support
- **Query interface**: Filter and search audit events

### Audit Log Location

```bash
~/.azlin/security_audit.jsonl
```

**Permissions**: `0600` (owner-only read/write)

### Viewing Audit Events

```bash
# View all recent events
azlin audit list

# View last 10 events
azlin audit list --limit 10

# Filter by event type
azlin audit list --type bastion_tunnel_create

# Filter by severity
azlin audit list --severity critical

# Filter by date range
azlin audit list \
  --start-date 2025-11-01 \
  --end-date 2025-11-30
```

**Example Output**:
```
🔐 Security Audit Events

[2025-12-01 14:23:45] [INFO] BASTION_TUNNEL_CREATE
  User: azureuser
  Resource: my-vm
  Action: create_tunnel
  Outcome: success
  Details:
    bastion: my-bastion
    local_port: 50123
    remote_port: 22
  Compliance: SOC2-CC6.6

[2025-12-01 14:20:12] [WARNING] BASTION_OPT_OUT
  User: azureuser
  Resource: dev-vm
  Action: opt_out_bastion
  Outcome: success
  Details:
    reason: "Development testing"
    public_ip_assigned: true
  Compliance: CIS-6.1, SOC2-CC6.6

[2025-12-01 14:15:33] [INFO] NSG_RULE_APPLY
  User: azureuser
  Resource: web-server-nsg
  Action: apply_template
  Outcome: success
  Details:
    template: web-server-nsg.yaml
    rules_applied: 4
    resource_group: prod-rg
  Compliance: CIS-6.2, ISO27001-A.13.1
```

### Event Types

| Event Type | When Logged | Severity | Compliance |
|------------|-------------|----------|------------|
| `bastion_opt_out` | User opts out of Bastion | WARNING | CIS-6.1, SOC2-CC6.6 |
| `bastion_tunnel_create` | Bastion tunnel created | INFO | SOC2-CC6.6 |
| `bastion_tunnel_close` | Bastion tunnel closed | INFO | SOC2-CC6.6 |
| `nsg_rule_apply` | NSG rule applied | INFO | CIS-6.2, ISO27001-A.13.1 |
| `nsg_rule_modify` | NSG rule modified | WARNING | CIS-6.2, SOC2-CC6.6 |
| `nsg_validation_fail` | NSG validation fails | CRITICAL | CIS-6.2, SOC2-CC6.7 |
| `credential_access` | Key Vault access | INFO | SOC2-CC6.1 |
| `public_ip_assign` | Public IP assigned to VM | WARNING | CIS-6.1 |
| `security_scan_fail` | Security scan finds issues | CRITICAL | SOC2-CC7.2 |
| `policy_violation` | Security policy violated | CRITICAL | All frameworks |

### Audit Log Integrity

Verify audit log integrity (detects tampering):

```bash
azlin audit verify-integrity
```

**Output (success)**:
```
🔐 Verifying audit log integrity...

✅ Audit log integrity: VALID
  Total events: 127
  Corrupted events: 0
  File permissions: 0600 (correct)
  Last backup: 2 hours ago
```

**Output (tampering detected)**:
```
❌ Audit log integrity: COMPROMISED

⚠️ Corrupted events detected:
  - Event ID: abc-123-def (line 45)
  - Event ID: xyz-789-ghi (line 87)

Recommendation: Restore from backup
Backup location: ~/.azlin/audit_backups/
```

### Compliance Reports

Generate compliance reports fer audits:

```bash
# Generate CIS compliance report
azlin audit compliance-report \
  --framework CIS \
  --start-date 2025-11-01 \
  --end-date 2025-11-30 \
  --output cis-report.json

# Generate SOC2 compliance report
azlin audit compliance-report \
  --framework SOC2 \
  --start-date 2025-11-01 \
  --end-date 2025-11-30 \
  --output soc2-report.json
```

**Report Format (JSON)**:
```json
{
  "framework": {
    "name": "CIS Azure Foundations Benchmark",
    "version": "1.4.0",
    "controls": ["6.1", "6.2", "6.3", "6.4", "6.5"]
  },
  "period": {
    "start": "2025-11-01T00:00:00Z",
    "end": "2025-11-30T23:59:59Z"
  },
  "summary": {
    "total_events": 127,
    "critical_findings": 2,
    "policy_violations": 1
  },
  "events_by_type": {
    "bastion_tunnel_create": 45,
    "nsg_rule_apply": 12,
    "bastion_opt_out": 3
  },
  "events_by_user": {
    "azureuser": 98,
    "admin": 29
  },
  "recommendations": [
    "Reduce Bastion opt-out frequency (3 instances)",
    "Enable automated NSG validation"
  ]
}
```

---

## Vulnerability Scanning

### Overview

Integrate with Azure Security Center (Microsoft Defender for Cloud) to proactively identify security vulnerabilities BEFORE deployment.

**Key Features**:
- Pre-deployment security validation
- Azure Security Center integration
- Local NSG validation
- Automated remediation recommendations

### Pre-Deployment Scanning

```bash
# Scan before deploying
azlin security scan-template \
  --template deployment.json \
  --resource-group prod-rg
```

**Output**:
```
🔍 Pre-Deployment Security Scan

Scanning template: deployment.json
Resource Group: prod-rg

✅ Schema Validation: PASSED
✅ NSG Validation: PASSED
✅ VM Configuration: PASSED
⚠️  Network Configuration: 1 warning

Security Findings:

1. [HIGH] VM has public IP address
   Resource: web-server-vm
   Category: network
   Description: VM 'web-server-vm' has public IP, increasing attack surface
   Remediation: Use Azure Bastion for SSH access instead of public IP
   Compliance Impact: CIS-6.1, SOC2-CC6.6

Summary:
  Total Findings: 1
  Critical: 0
  High: 1
  Medium: 0
  Low: 0

✅ Deployment allowed (no CRITICAL findings)
```

### NSG Security Scanning

```bash
# Scan existing NSG
azlin security scan-nsg my-nsg \
  --resource-group prod-rg
```

**Output**:
```
🔍 Scanning NSG 'my-nsg'...

Local Validation:
  ✓ Deny-by-default rule present
  ✓ No SSH/RDP exposed to internet
  ✓ Rule priorities valid

Azure Security Center:
  Querying Microsoft Defender for Cloud...
  ✅ No critical recommendations

0 CRITICAL findings
0 warnings
```

### VM Security Scanning

```bash
# Scan VM configuration
azlin security scan-vm my-vm \
  --resource-group prod-rg
```

**Output** (example with findings):
```
🔍 Scanning VM 'my-vm'...

🚨 CRITICAL FINDINGS:

1. [CRITICAL] Management port exposed to internet
   NSG Rule: allow-ssh-from-anywhere
   Description: Rule 'allow-ssh-from-anywhere' allows port 22 from any source
   Remediation: Restrict source to specific IP ranges or use Azure Bastion
   Compliance Impact: CIS-6.1, SOC2-CC6.6

2. [HIGH] VM has public IP address
   Resource: my-vm
   Description: VM 'my-vm' has public IP, increasing attack surface
   Remediation: Remove public IP and use Azure Bastion
   Compliance Impact: CIS-6.1, SOC2-CC6.6

Azure Security Center Recommendations:
  - Enable Azure Disk Encryption
  - Install endpoint protection
  - Apply system updates

Summary:
  Total Findings: 2
  Critical: 1
  High: 1

❌ VM has CRITICAL security findings
```

### Automated Remediation

Some findings can be auto-remediated:

```bash
# Show remediation steps
azlin security remediate my-vm \
  --resource-group prod-rg \
  --dry-run

# Apply automated fixes
azlin security remediate my-vm \
  --resource-group prod-rg \
  --apply
```

**Output**:
```
🔧 Automated Remediation Plan

Fixes to apply:
  1. Remove public IP from VM
  2. Update NSG rule 'allow-ssh-from-anywhere'
     → Replace with Bastion-only access
  3. Apply 'locked-down-vm' NSG template

Apply these fixes? [y/N]: y

✅ Public IP removed
✅ NSG rule updated
✅ Bastion access configured
🔐 Security audit event logged

VM 'my-vm' is now secure!
```

---

## VPN and Private Endpoints

### Overview

Configure VPN gateways fer remote access and private endpoints fer secure Azure service connectivity.

### Point-to-Site VPN Setup

Create a VPN gateway fer remote team access:

```bash
# Create VPN gateway
azlin vpn create-p2s \
  --vnet my-vnet \
  --resource-group my-rg \
  --gateway-name my-vpn-gateway \
  --address-pool 172.16.0.0/24
```

**Output**:
```
🔐 Creating Point-to-Site VPN Gateway...

⏳ This operation takes 30-45 minutes

Steps:
  ✅ Creating GatewaySubnet (10.0.255.0/27)
  ⏳ Creating VPN gateway 'my-vpn-gateway' (in progress)
  ⏳ Configuring P2S VPN settings

VPN gateway 'my-vpn-gateway' is provisioning in background.
Check status: azlin vpn status my-vpn-gateway
```

**Check VPN Status**:
```bash
azlin vpn status my-vpn-gateway --resource-group my-rg
```

**Generate VPN Client Config**:
```bash
azlin vpn generate-client-config \
  --gateway-name my-vpn-gateway \
  --resource-group my-rg
```

**Output**:
```
🔐 Generating VPN client configuration...

✅ VPN client config generated

Download URL:
https://vpnconfig.blob.core.windows.net/packages/config.zip

Instructions:
  1. Download the configuration package
  2. Extract to local directory
  3. Install OpenVPN client
  4. Import configuration
  5. Connect to VPN

After connecting, you can access VMs via private IPs:
  ssh azureuser@10.0.1.4
```

### Private Endpoint Configuration

Create private endpoints fer Azure services (Storage, Key Vault, etc.):

```bash
# Create private endpoint for Key Vault
azlin private-endpoint create \
  --name keyvault-pe \
  --resource-group my-rg \
  --vnet my-vnet \
  --subnet private-endpoints \
  --service-type keyvault \
  --service-name my-keyvault
```

**Output**:
```
🔐 Creating Private Endpoint...

Steps:
  ✅ Disabling private endpoint network policies on subnet
  ✅ Creating private endpoint 'keyvault-pe'
  ✅ Creating private DNS zone 'privatelink.vaultcore.azure.net'
  ✅ Linking DNS zone to VNet

✅ Private endpoint configured

Service: my-keyvault
Private IP: 10.0.2.5
DNS: my-keyvault.vault.azure.net → 10.0.2.5

Your Key Vault is now accessible via private network only!
```

**Verify Private Endpoint**:
```bash
# From VM inside VNet
nslookup my-keyvault.vault.azure.net
```

**Output**:
```
Server:     168.63.129.16
Address:    168.63.129.16#53

Non-authoritative answer:
Name:   my-keyvault.privatelink.vaultcore.azure.net
Address: 10.0.2.5
```

---

## Security Workflows

### Secure VM Creation Workflow

Complete end-to-end secure VM creation:

```bash
azlin create-secure my-secure-app \
  --resource-group prod-rg \
  --region westus2 \
  --nsg-template web-server-nsg \
  --bastion-required \
  --enable-audit \
  --scan-before-deploy
```

**Workflow Steps**:
```
🔍 Pre-Deployment Security Scan
  ✅ Template validation (0 critical findings)
  ✅ NSG validation (policy compliant)
  ✅ Azure Security Center check

🔐 Creating Bastion Infrastructure
  ✅ Bastion subnet created
  ✅ Bastion host provisioned

🛡️  Applying NSG Template
  ✅ NSG 'my-secure-app-nsg' created
  ✅ Applied 4 security rules
  ✅ Validation: deny-by-default ✓

🖥️  Creating VM
  ✅ VM 'my-secure-app' created
  ✅ No public IP assigned
  ✅ Private IP: 10.0.1.10

🔗 Creating Bastion Tunnel
  ✅ Tunnel established (pooled)
  ✅ Localhost binding verified
  ✅ Port: 50125 → 22

📊 Security Audit
  ✅ All events logged
  ✅ Audit log integrity: VALID

✅ Secure VM deployment complete!

Security Summary:
  ✓ No public IP
  ✓ SSH via Bastion only
  ✓ NSG: deny-by-default
  ✓ Pre-deployment scan passed
  ✓ Audit trail created

Connect: azlin connect my-secure-app
```

### Security Audit Workflow

Monthly security audit workflow:

```bash
# 1. Generate compliance report
azlin audit compliance-report \
  --framework SOC2 \
  --start-date 2025-11-01 \
  --end-date 2025-11-30 \
  --output soc2-november.json

# 2. Verify audit log integrity
azlin audit verify-integrity

# 3. Review critical events
azlin audit list --severity critical

# 4. Scan all VMs
azlin security scan-all --resource-group prod-rg

# 5. Export findings report
azlin security export-report \
  --output security-review.pdf
```

### NSG Drift Detection

Detect configuration drift (manual changes outside templates):

```bash
# Compare NSG against template
azlin nsg compare \
  --nsg-name my-nsg \
  --resource-group prod-rg \
  --template web-server-nsg.yaml
```

**Output** (example with drift):
```
🔍 Comparing NSG 'my-nsg' against template 'web-server-nsg.yaml'...

⚠️  CONFIGURATION DRIFT DETECTED

Differences Found:

1. [ADDED] Rule not in template
   Name: allow-debug-port
   Priority: 150
   Action: Allow
   Port: 8080
   Source: Internet
   ⚠️ WARNING: This rule was added manually

2. [MODIFIED] Rule priority changed
   Name: deny-ssh-from-internet
   Template Priority: 200
   Actual Priority: 250
   ⚠️ WARNING: Manual modification detected

3. [REMOVED] Rule missing from NSG
   Name: allow-http-redirect
   Template Priority: 110
   ⚠️ WARNING: Rule was manually removed

Recommendations:
  - Review manual changes for security impact
  - Re-apply template to restore baseline: azlin nsg apply web-server-nsg
  - Update template if changes should be permanent

🔐 Audit event logged: configuration_drift
```

---

## CLI Reference

### NSG Commands

```bash
# List templates
azlin nsg list-templates

# Show template details
azlin nsg show-template <template-name>

# Validate template
azlin nsg validate <template-name> [--dry-run]

# Apply template
azlin nsg apply <template-name> \
  --nsg-name <name> \
  --resource-group <rg> \
  [--update]

# Export existing NSG
azlin nsg export <nsg-name> \
  --resource-group <rg> \
  --output <file>

# Compare NSG against template
azlin nsg compare \
  --nsg-name <name> \
  --resource-group <rg> \
  --template <template-name>
```

### Bastion Commands

```bash
# Connect to VM
azlin connect <vm-name> [--resource-group <rg>]

# Create tunnel
azlin bastion create-tunnel \
  --vm <vm-name> \
  --resource-group <rg> \
  [--local-port <port>]

# Close tunnel
azlin bastion close-tunnel --port <port>

# Close all tunnels
azlin bastion close-all

# Pool status
azlin bastion pool-status

# Health check
azlin bastion health-check --port <port>

# Configuration
azlin bastion set-limit <max-connections>
azlin bastion set-idle-timeout <seconds>
azlin bastion show-config
```

### Audit Commands

```bash
# List events
azlin audit list \
  [--limit <n>] \
  [--type <event-type>] \
  [--severity <level>] \
  [--start-date <date>] \
  [--end-date <date>]

# Verify integrity
azlin audit verify-integrity

# Compliance report
azlin audit compliance-report \
  --framework <CIS|SOC2|ISO27001> \
  --start-date <date> \
  --end-date <date> \
  --output <file>
```

### Security Scanning Commands

```bash
# Scan template before deployment
azlin security scan-template \
  --template <file> \
  --resource-group <rg>

# Scan NSG
azlin security scan-nsg <nsg-name> \
  --resource-group <rg>

# Scan VM
azlin security scan-vm <vm-name> \
  --resource-group <rg>

# Scan all resources
azlin security scan-all \
  --resource-group <rg>

# Remediate findings
azlin security remediate <vm-name> \
  --resource-group <rg> \
  [--dry-run] \
  [--apply]

# Export report
azlin security export-report \
  --output <file>
```

### VPN Commands

```bash
# Create P2S VPN
azlin vpn create-p2s \
  --vnet <vnet-name> \
  --resource-group <rg> \
  --gateway-name <name> \
  --address-pool <cidr>

# Check status
azlin vpn status <gateway-name> \
  --resource-group <rg>

# Generate client config
azlin vpn generate-client-config \
  --gateway-name <name> \
  --resource-group <rg>
```

### Private Endpoint Commands

```bash
# Create private endpoint
azlin private-endpoint create \
  --name <name> \
  --resource-group <rg> \
  --vnet <vnet-name> \
  --subnet <subnet-name> \
  --service-type <keyvault|storage|sql> \
  --service-name <service-name>

# List private endpoints
azlin private-endpoint list \
  --resource-group <rg>

# Delete private endpoint
azlin private-endpoint delete <name> \
  --resource-group <rg>
```

---

## Compliance and Best Practices

### CIS Azure Foundations Benchmark

**Relevant Controls**:

| Control | Requirement | azlin Implementation |
|---------|-------------|---------------------|
| **6.1** | Ensure RDP access is restricted from internet | NSG templates block RDP, audit logging |
| **6.2** | Ensure SSH access is restricted from internet | NSG templates block SSH, Bastion-only |
| **6.3** | Ensure NSG flow log retention > 90 days | NSG Manager enables flow logs |
| **6.5** | Ensure Azure Bastion is provisioned | Bastion provisioning workflow |

### SOC 2 Trust Services Criteria

| TSC | Requirement | azlin Implementation |
|-----|-------------|---------------------|
| **CC6.1** | Restrict access to information assets | Key Vault integration, Azure AD auth |
| **CC6.6** | Restrict network access | NSG templates, Bastion, VPN |
| **CC6.7** | Monitor security events | Security audit logging |
| **CC7.2** | Identify and assess threats | Vulnerability scanning |

### ISO/IEC 27001:2013

| Control | Requirement | azlin Implementation |
|---------|-------------|---------------------|
| **A.9.1** | Access control policy | NSG templates with policy enforcement |
| **A.9.4** | System access control | Bastion-only SSH access |
| **A.12.4** | Logging and monitoring | Security audit logging |
| **A.13.1** | Network security | NSG rules, private endpoints, VPN |

### Security Best Practices

#### 1. Defense in Depth

```
Layer 1: Network Perimeter (NSG Rules)
  ↓ Deny-by-default firewall rules
  ↓ IP whitelisting for admin access

Layer 2: Access Control (Bastion/VPN)
  ↓ Centralized access through Bastion
  ↓ VPN tunnels for remote access

Layer 3: Authentication (Azure AD/Key Vault)
  ↓ Azure CLI authentication
  ↓ Key Vault for secrets

Layer 4: Application Security (Validation)
  ↓ Input validation
  ↓ Template schema validation

Layer 5: Audit & Monitoring (Logging)
  ↓ Security audit logging
  ↓ Configuration drift detection
```

#### 2. Principle of Least Privilege

- **NSG Rules**: Deny by default, allow only necessary traffic
- **Bastion Access**: Localhost binding only
- **Service Accounts**: Minimum required permissions
- **Audit Logs**: 0600 permissions (owner-only)

#### 3. Fail-Secure Defaults

- **NSG Templates**: Must have deny-default rule
- **VM Creation**: No public IP by default
- **Bastion**: Opt-in required for opt-out
- **Validation**: CRITICAL findings block deployment

#### 4. Continuous Monitoring

- **Audit Logging**: All security events logged
- **Integrity Verification**: Tamper detection
- **Drift Detection**: Compare against baselines
- **Security Scanning**: Regular vulnerability assessments

#### 5. Automated Compliance

- **Pre-Deployment Scanning**: Catch issues before deployment
- **Template Validation**: 100% coverage before application
- **Compliance Reports**: Automated generation (CIS, SOC2, ISO27001)
- **Audit Trail**: Complete history for forensics

---

## Troubleshooting

### NSG Template Validation Failures

**Problem**: Template validation fails with policy violations

**Solution**:
```bash
# View detailed validation errors
azlin nsg validate my-template.yaml --verbose

# Fix common issues:
# 1. Add deny-default rule (priority 4096)
# 2. Remove SSH/RDP rules from Internet
# 3. Add justifications for all rules

# Re-validate
azlin nsg validate my-template.yaml
```

### Bastion Connection Fails

**Problem**: Cannot connect to VM via Bastion

**Solution**:
```bash
# Check Bastion status
az network bastion show \
  --name my-bastion \
  --resource-group my-rg

# Check VM status
azlin show my-vm --resource-group my-rg

# Test tunnel health
azlin bastion health-check --port 50123

# Close and recreate tunnel
azlin bastion close-tunnel --port 50123
azlin connect my-vm --resource-group my-rg
```

### Audit Log Integrity Failure

**Problem**: Audit log integrity verification fails

**Solution**:
```bash
# View corrupted events
azlin audit verify-integrity --verbose

# Restore from backup
azlin audit restore-backup \
  --backup-date 2025-12-01

# If no backup available, archive corrupted log
mv ~/.azlin/security_audit.jsonl \
   ~/.azlin/security_audit_corrupted_$(date +%Y%m%d).jsonl

# New log will be created automatically
```

### Port Exhaustion

**Problem**: "Connection limit reached" error

**Solution**:
```bash
# Close unused tunnels
azlin bastion close-all

# Or increase limit
azlin bastion set-limit 20

# Check pool status
azlin bastion pool-status
```

---

## Advanced Usage

### Custom Security Policies

Create custom security policies fer NSG validation:

```python
# custom_policy.py
class CustomSecurityPolicy:
    FORBIDDEN_RULES = [
        {
            "name": "no-database-from-internet",
            "condition": lambda rule: (
                rule["destination_port_range"] in ["3306", "5432", "1433"] and
                rule["source_address_prefix"] == "Internet" and
                rule["access"] == "Allow"
            ),
            "severity": "CRITICAL",
            "message": "Database ports must not be exposed to internet"
        }
    ]
```

**Apply Custom Policy**:
```bash
azlin nsg validate my-template.yaml \
  --custom-policy custom_policy.py
```

### Programmatic API Usage

Use azlin's Python API fer automation:

```python
from azlin.security import NSGManager, NSGValidator
from azlin.bastion import BastionConnectionPool

# NSG Management
validator = NSGValidator()
manager = NSGManager(validator)

# Validate and apply template
result = manager.apply_template(
    template_path="web-server-nsg.yaml",
    nsg_name="my-nsg",
    resource_group="prod-rg",
    dry_run=False
)

# Bastion Connection Pool
pool = BastionConnectionPool(max_tunnels=20)
tunnel = pool.get_or_create_tunnel(
    bastion_name="my-bastion",
    resource_group="prod-rg",
    target_vm_id="/subscriptions/.../my-vm",
    remote_port=22
)

print(f"Tunnel available at localhost:{tunnel.tunnel.local_port}")
```

---

## Related Documentation

- [BASTION_SECURITY_REQUIREMENTS.md](BASTION_SECURITY_REQUIREMENTS.md) - Detailed Bastion security design
- [BASTION_SECURITY_TESTING.md](BASTION_SECURITY_TESTING.md) - Security testing procedures
- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system architecture
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API reference

---

## Support and Feedback

**Issues**: https://github.com/rysweet/azlin/issues
**Discussions**: https://github.com/rysweet/azlin/discussions
**Security**: security@azlin.dev

---

**Arr! That be the complete guide to azlin's network security features, matey! May yer VMs sail secure across the Azure seas! 🏴‍☠️**
