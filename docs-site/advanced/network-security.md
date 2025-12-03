# Network Security Enhancements

Advanced network security features including NSG automation, Bastion pooling, and comprehensive audit logging.

## Overview

azlin v0.4.0 provides enterprise-grade network security features to protect your Azure VM infrastructure.

**Key Features:**

- **NSG Automation**: Automatically configure Network Security Groups
- **Bastion Pooling**: Share Bastion hosts across multiple VMs for cost savings
- **Security Audit Logging**: Comprehensive logging of all network access
- **Threat Detection**: Identify suspicious network activity
- **Compliance Reporting**: Generate security compliance reports
- **Zero Trust Architecture**: Implement zero-trust network policies

## Quick Start

### Auto-Configure NSG

```bash
# Automatically configure NSG for a VM
azlin security nsg auto-configure myvm

# Configure with custom rules
azlin security nsg configure myvm \
  --allow-ssh \
  --allow-https \
  --deny-all-inbound

# Review NSG rules
azlin security nsg show myvm
```

### Enable Bastion Pooling

```bash
# Share Bastion host across VMs
azlin bastion pool create \
  --name prod-bastion-pool \
  --vms vm-web*,vm-db*

# View pool status
azlin bastion pool status prod-bastion-pool

# Estimated savings: 60% vs. individual Bastion hosts
```

### Enable Security Auditing

```bash
# Enable comprehensive audit logging
azlin security audit enable myvm \
  --log-ssh-access \
  --log-network-traffic \
  --log-file-access

# View audit log
azlin security audit show myvm --last 24h
```

## NSG Management

### Automated NSG Configuration

```bash
# Create NSG with best practices
azlin security nsg create myvm-nsg \
  --template secure-web-server

# Available templates:
# - secure-web-server: Allow 80, 443, SSH from specific IPs
# - secure-database: Allow database ports only from app servers
# - secure-bastion: Bastion-optimized rules
# - zero-trust: Deny all, explicit allow only
```

### Dynamic NSG Rules

```bash
# Add temporary access rule (auto-expires)
azlin security nsg add-temp myvm \
  --allow-ssh-from 203.0.113.10 \
  --duration 2h

# Rule will automatically be removed after 2 hours
```

## Bastion Pooling

### Cost Optimization

Share a single Bastion host across multiple VMs:

```bash
# Create Bastion pool (shared across 10 VMs)
azlin bastion pool create production \
  --region eastus \
  --vms vm-*

# Cost comparison:
# Individual Bastion: 10 VMs × $140/month = $1,400/month
# Bastion Pool: 1 Bastion × $140/month = $140/month
# Savings: $1,260/month (90%)
```

### Pool Management

```bash
# Add VM to pool
azlin bastion pool add production vm-new-01

# Remove VM from pool
azlin bastion pool remove production vm-old-01

# View pool metrics
azlin bastion pool metrics production
```

## Security Audit Logging

### Comprehensive Logging

```bash
# Enable all security logging
azlin security audit enable myvm --all

# Logs captured:
# - SSH login attempts (successful and failed)
# - Sudo command execution
# - File access to sensitive directories
# - Network connections (inbound and outbound)
# - Process execution
# - System configuration changes
```

### Log Analysis

```bash
# Search audit logs
azlin security audit search \
  --vm myvm \
  --event ssh-login \
  --last 7d

# Generate security report
azlin security audit report myvm \
  --format pdf \
  --output security-report.pdf
```

## Threat Detection

```bash
# Enable threat detection
azlin security threat-detection enable myvm

# View detected threats
azlin security threats list --severity high

# Configure threat response
azlin security threat-response configure \
  --auto-block-suspicious-ips \
  --notify security@company.com
```

## Compliance Reporting

```bash
# Generate compliance report
azlin security compliance-report \
  --standard CIS \
  --vms vm-*

# Supported standards:
# - CIS (Center for Internet Security)
# - NIST (National Institute of Standards and Technology)
# - PCI-DSS (Payment Card Industry Data Security Standard)
# - HIPAA (Health Insurance Portability and Accountability Act)
```

## Best Practices

1. **Implement Zero Trust**
   - Deny all traffic by default
   - Explicitly allow only required traffic
   - Use temporary access rules

2. **Use Bastion Pooling**
   - Significant cost savings
   - Centralized access management
   - Easier audit compliance

3. **Enable Comprehensive Logging**
   - Log all security-relevant events
   - Store logs securely off-VM
   - Review logs regularly

4. **Automate NSG Management**
   - Use templates for consistency
   - Automate rule updates
   - Regular review and cleanup

## See Also

- [Bastion Overview](../bastion/index.md)
- [VM Lifecycle Automation](../vm-lifecycle/automation.md)
- [Multi-Region Orchestration](./multi-region.md)
- [Security Commands](../commands/security/index.md)

---

*Documentation last updated: 2025-12-03*

!!! note "Full Documentation Coming Soon"
    Complete examples, configuration guides, and API reference will be added in the next documentation update.
