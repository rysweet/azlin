# Azure Bastion Security Requirements
**Version:** 1.0
**Date:** 2025-10-28
**Issue:** #196 - Azure Bastion Integration
**Classification:** SECURITY CRITICAL

---

## Executive Summary

This document defines the security requirements for Azure Bastion integration into azlin. Azure Bastion provides secure RDP and SSH connectivity to Azure VMs without exposing public IPs, adding a critical layer of security. However, **Bastion integration introduces new attack surfaces** that must be rigorously secured.

**Critical Security Principle:** Azure Bastion is a security boundary. Failures in Bastion authentication, authorization, or tunnel management could expose private VMs to unauthorized access.

**Threat Level:** HIGH - Private VMs are only accessible through Bastion, making it a single point of failure for access control.

---

## 1. Bastion Authentication & Authorization

### 1.1 Authentication Methods

**REQ-AUTH-001: MANDATORY Azure Authentication**
- **Requirement:** All Bastion operations MUST use authenticated Azure credentials
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Reuse existing `AzureAuthenticator` chain (service principal, Azure CLI, managed identity)
  - NO new authentication methods for Bastion
  - Authentication validation BEFORE any Bastion operations
- **Security Control:** Same authentication security as existing azlin (SEC-001 through SEC-010)
- **Test:** Verify Bastion operations fail without valid Azure credentials

**REQ-AUTH-002: Service Principal RBAC Roles**
- **Requirement:** Document minimum required RBAC roles for Bastion operations
- **Priority:** P0 (BLOCKER)
- **Required Roles:**
  - **Bastion Deployment:** `Network Contributor` on resource group OR `Contributor` on subscription
  - **VM SSH Access:** `Virtual Machine User Login` OR `Virtual Machine Administrator Login` on target VM
  - **Tunnel Creation:** `Reader` on Bastion host + appropriate VM role
- **Security Control:** Principle of least privilege - document specific role assignments
- **Documentation:** Include RBAC setup guide in README
- **Test:** Verify operations fail with insufficient permissions

**REQ-AUTH-003: Credential Lifecycle Management**
- **Requirement:** Bastion operations MUST NOT introduce new credential storage
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use existing credential factory and auth chain
  - NO Bastion-specific credentials stored in config
  - Tokens managed by Azure SDK/CLI, never by azlin
- **Security Control:** Maintains existing "no credential storage" principle
- **Test:** Verify no new credential files created after Bastion operations

**REQ-AUTH-004: Authentication Error Handling**
- **Requirement:** Authentication failures MUST NOT leak credential details
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use existing `LogSanitizer` for all error messages
  - Sanitize Azure CLI error output (may contain token hints)
  - Never log subscription IDs in error messages (use partial masking)
- **Security Control:** SEC-010 - Error messages don't leak secrets
- **Test:** Trigger auth failures, verify no credential leakage in logs/errors

---

## 2. VM Access Control

### 2.1 Private-Only VM Security

**REQ-ACCESS-001: Private IP Validation**
- **Requirement:** Private-only VMs MUST have network validation before Bastion connection
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Validate VM has NO public IP (expected state for Bastion VMs)
  - Validate VM has private IP in expected range (RFC 1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
  - Detect and validate Azure-specific ranges (e.g., 100.64.0.0/10)
  - Reject connections to invalid private IPs
- **Security Control:** Prevents misconfiguration attacks
- **Test:** Verify connection fails for invalid private IP ranges

**REQ-ACCESS-002: VNet/Subnet Association Validation**
- **Requirement:** VMs MUST be in same VNet as Bastion or reachable via peering
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Query VM's VNet and subnet
  - Query Bastion's VNet
  - Verify VM is reachable from Bastion (same VNet or peered VNet)
  - Fail fast with clear error if VNet mismatch detected
- **Security Control:** Prevents connection to unreachable VMs (network isolation)
- **Error Message Example:** "VM 'vm-001' is in VNet 'vnet-a', but Bastion 'bastion-westus' is in VNet 'vnet-b'. VNet peering required."
- **Test:** Verify connection fails for VMs in different, unpeered VNets

**REQ-ACCESS-003: Bastion NSG Validation**
- **Requirement:** Bastion subnet MUST have correct NSG rules or no NSG
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Query Bastion subnet for associated NSG
  - If NSG present, validate it allows required Bastion traffic:
    - **Inbound:** TCP 443 from Internet (for Azure control plane)
    - **Outbound:** TCP 22/3389 to VNet (for SSH/RDP to VMs)
    - **Outbound:** TCP 443 to AzureCloud (for Azure control plane)
  - Warn if NSG may block Bastion traffic
  - Document NSG requirements in deployment guide
- **Security Control:** Prevents deployment failures due to NSG misconfiguration
- **Test:** Deploy with overly restrictive NSG, verify warning/error

**REQ-ACCESS-004: VM NSG Validation**
- **Requirement:** Target VM MUST allow SSH from Bastion subnet or AzureBastionSubnet service tag
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Query VM's associated NSG(s)
  - Check for rule allowing TCP 22 from Bastion subnet CIDR OR AzureBastionSubnet service tag
  - Warn if no explicit allow rule detected (may fail at connection time)
  - Provide remediation guidance in error message
- **Security Control:** Prevents silent connection failures
- **Error Message Example:** "VM 'vm-001' NSG does not allow SSH from Bastion. Add rule: Source=AzureBastionSubnet, Dest Port=22, Protocol=TCP, Action=Allow"
- **Test:** Deploy VM with restrictive NSG, verify warning with remediation steps

### 2.2 Multi-VM Access Control

**REQ-ACCESS-005: VM-Bastion Mapping Storage**
- **Requirement:** VM-to-Bastion mappings MUST be stored securely
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Store in `~/.azlin/config.toml` with 0600 permissions
  - NO secrets in mapping (just VM name -> Bastion name)
  - Use existing `ConfigManager` validation logic
- **Configuration Example:**
  ```toml
  [bastion]
  enabled = true
  auto_detect = true  # Auto-detect Bastion in resource group

  [[bastion.vm_mappings]]
  vm_name = "azlin-dev-vm"
  bastion_name = "azlin-bastion-westus"
  resource_group = "network-rg"
  ```
- **Security Control:** SEC-003 - Config file permissions, SEC-009 - Secure file operations
- **Test:** Verify config file created with 0600 permissions

**REQ-ACCESS-006: Bastion Auto-Detection Security**
- **Requirement:** Bastion auto-detection MUST validate resources before use
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Query Azure for Bastion hosts in resource group
  - Validate Bastion state is "Succeeded" (not "Failed" or "Updating")
  - Validate Bastion is Standard SKU (Basic lacks native client support)
  - Prompt user before using auto-detected Bastion: "Found Bastion 'bastion-westus'. Use it? (y/N)"
  - Never auto-use Bastion without user confirmation (avoid surprises)
- **Security Control:** User consent for Bastion usage, prevents using failed/misconfigured Bastion
- **Test:** Deploy failed Bastion, verify azlin rejects it with clear error

---

## 3. Tunnel Security

### 3.1 Local Tunnel Endpoint

**REQ-TUNNEL-001: Localhost-Only Binding**
- **Requirement:** Bastion tunnels MUST bind to localhost (127.0.0.1) ONLY
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - `az network bastion tunnel` command MUST use `--resource-port 22 --port <random>`
  - Never bind to 0.0.0.0 or public interface
  - Validate tunnel binding with socket check after creation
- **Security Control:** Prevents network-wide tunnel exposure
- **Rationale:** Binding to 0.0.0.0 would expose VM SSH access to entire local network
- **Test:** Create tunnel, verify it's not accessible from other machines on local network

**REQ-TUNNEL-002: Random Port Allocation**
- **Requirement:** Local tunnel ports MUST be randomly allocated
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use ephemeral port range (49152-65535)
  - Random selection from available ports
  - Fallback mechanism if port in use
  - NO hardcoded tunnel ports
- **Security Control:** Prevents port collision attacks
- **Rationale:** Predictable ports allow local attackers to hijack tunnels
- **Test:** Create multiple tunnels, verify unique random ports

**REQ-TUNNEL-003: Tunnel Port Validation**
- **Requirement:** Tunnel port MUST be validated before SSH connection
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - After tunnel creation, verify localhost port is listening
  - Timeout: 10 seconds maximum wait
  - Fail fast if tunnel doesn't become available
  - Provide actionable error message
- **Security Control:** Prevents hanging connections, detects tunnel failures early
- **Test:** Mock tunnel failure, verify timeout and clear error

### 3.2 Tunnel Lifecycle Management

**REQ-TUNNEL-004: Tunnel Cleanup on Exit**
- **Requirement:** Bastion tunnels MUST be cleaned up on all exit paths
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Register `atexit` handler to terminate tunnel subprocess
  - Catch SIGINT/SIGTERM and cleanup tunnel
  - Use context manager pattern: `with BastionTunnel(...) as tunnel:`
  - Verify tunnel process is killed on cleanup
- **Security Control:** Prevents orphaned tunnel processes exposing VM access
- **Rationale:** Orphaned tunnels remain active indefinitely, creating persistent attack surface
- **Test:** Kill SSH session abruptly, verify tunnel subprocess terminates

**REQ-TUNNEL-005: Tunnel Process Isolation**
- **Requirement:** Tunnel subprocess MUST be isolated from user shell
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Run `az network bastion tunnel` in separate subprocess
  - Use `subprocess.Popen` with no shell=True (SEC-006)
  - No stdin/stdout inheritance (use PIPE or DEVNULL)
  - Set resource limits if supported by platform
- **Security Control:** Prevents tunnel subprocess interference with SSH session
- **Test:** Verify tunnel subprocess has no access to terminal I/O

**REQ-TUNNEL-006: Tunnel State Tracking**
- **Requirement:** Active tunnels MUST be tracked for management and cleanup
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Track active tunnels in memory (dict of VM name -> tunnel info)
  - Include: subprocess PID, local port, creation time, VM details
  - NO persistent tunnel state (security risk if files left behind)
  - Provide `azlin bastion tunnels --list` command to show active tunnels
- **Security Control:** Visibility into active attack surface
- **Test:** Create multiple tunnels, verify tracking and listing

### 3.3 Tunnel Hijacking Prevention

**REQ-TUNNEL-007: Tunnel Process Ownership Validation**
- **Requirement:** Tunnels MUST be owned by current user, with no privilege escalation
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Verify tunnel subprocess UID matches current user UID
  - Never run tunnel processes as root or with elevated privileges
  - Fail if process ownership check fails
- **Security Control:** Prevents privilege escalation via tunnel hijacking
- **Test:** Attempt to create tunnel with different UID, verify rejection

**REQ-TUNNEL-008: Azure CLI Token Validation**
- **Requirement:** Tunnel creation MUST validate Azure CLI token freshness
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Check `az account get-access-token` before tunnel creation
  - Verify token expiry > 5 minutes remaining
  - Prompt user to re-authenticate if token expired
  - Never cache tokens in azlin (delegated to Azure CLI)
- **Security Control:** Prevents stale token usage, maintains token security
- **Test:** Use expired token, verify re-authentication prompt

---

## 4. Configuration Security

### 4.1 Bastion Configuration Storage

**REQ-CONFIG-001: No Secrets in Bastion Config**
- **Requirement:** Bastion configuration MUST NOT store any secrets
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Store ONLY: Bastion name, resource group, VNet name, location
  - NO: subscription IDs, tenant IDs, client secrets, access tokens
  - Validate config on load, reject any secret-like fields
- **Security Control:** SEC-001 - No secrets in config files
- **Test:** Attempt to save secret in Bastion config, verify rejection

**REQ-CONFIG-002: Bastion Config File Permissions**
- **Requirement:** Bastion config in `~/.azlin/config.toml` MUST have 0600 permissions
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use existing `ConfigManager` (already enforces 0600)
  - Verify permissions on every config write
  - Auto-fix permissions if insecure (warn user)
- **Security Control:** SEC-003 - Certificate permissions, SEC-009 - Secure file operations
- **Test:** Create config with 0644, verify auto-fix to 0600

**REQ-CONFIG-003: Configuration Path Validation**
- **Requirement:** Bastion config paths MUST be validated for path traversal
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use existing `ConfigManager._validate_config_path()`
  - Reject paths with: `..`, shell metacharacters, sensitive directories
  - Only allow paths within `~/.azlin/` or current directory
- **Security Control:** SEC-007 - Input validation
- **Test:** Attempt path traversal (`../../etc/passwd`), verify rejection

### 4.2 Sensitive Data in Config

**REQ-CONFIG-004: Resource ID Masking in Logs**
- **Requirement:** Azure resource IDs in logs MUST be sanitized
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Resource IDs are OK in logs (not secrets)
  - Subscription IDs in logs should be partially masked: `12345678-****-****-****-************`
  - Use existing `LogSanitizer.sanitize_client_id()` for UUID masking
- **Security Control:** SEC-005 - Log sanitization
- **Example:**
  - GOOD: `Using Bastion: azlin-bastion-westus in resource group network-rg`
  - BAD: `Using subscription: 12345678-1234-1234-1234-123456789012` (full ID)
  - GOOD: `Using subscription: 12345678-****-****-****-************` (masked)
- **Test:** Enable debug logging, verify subscription IDs are masked

**REQ-CONFIG-005: Bastion Naming Validation**
- **Requirement:** Bastion names MUST be validated against Azure naming rules
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Azure Bastion name: 1-80 chars, alphanumeric + hyphens, start/end with alphanumeric
  - Pattern: `^[a-zA-Z0-9]([a-zA-Z0-9-]{0,78}[a-zA-Z0-9])?$`
  - Reject invalid names with clear error
- **Security Control:** SEC-007 - Input validation
- **Test:** Attempt invalid names (special chars, too long), verify rejection

---

## 5. Error Handling Security

### 5.1 Error Message Sanitization

**REQ-ERROR-001: No Credential Leakage in Errors**
- **Requirement:** All error messages MUST be sanitized for credential leakage
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Pass ALL error messages through `LogSanitizer.sanitize()`
  - Sanitize Azure CLI stderr output (may contain tokens)
  - Never include raw exception messages in user-facing errors
- **Security Control:** SEC-010 - Error messages don't leak secrets
- **Test:** Trigger auth failures, verify no secrets in error output

**REQ-ERROR-002: Information Disclosure Prevention**
- **Requirement:** Error messages MUST NOT leak internal system information
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Don't expose: internal IPs, file paths, process IDs, Azure ARM endpoints
  - Generic errors for security failures: "Access denied" (not "RBAC role X missing")
  - Detailed errors ONLY in debug mode (opt-in with `--debug` flag)
- **Security Control:** Defense in depth - limit attacker reconnaissance
- **Examples:**
  - BAD: `Failed to connect to internal endpoint: http://169.254.169.254/...`
  - GOOD: `Failed to retrieve VM metadata. Enable --debug for details.`
- **Test:** Trigger various errors in non-debug mode, verify no internal details leaked

**REQ-ERROR-003: Actionable Error Messages**
- **Requirement:** Security-related errors MUST provide remediation guidance
- **Priority:** P1 (HIGH)
- **Implementation:**
  - RBAC errors: Include required role and assignment command
  - NSG errors: Include NSG rule to add
  - Auth errors: Include authentication command (e.g., `az login`)
- **User Experience:** Security doesn't mean user-hostile
- **Examples:**
  - `Permission denied accessing VM. Required role: "Virtual Machine User Login". Grant with: az role assignment create --assignee <user> --role "Virtual Machine User Login" --scope <vm-id>`
- **Test:** Trigger permission errors, verify clear remediation steps

### 5.2 Secure Fallback Behavior

**REQ-ERROR-004: Fail Secure on Bastion Errors**
- **Requirement:** Bastion failures MUST fail secure (deny access, not bypass)
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - If Bastion tunnel fails, DO NOT attempt direct public IP connection
  - If VM configured for Bastion-only, connection MUST fail if Bastion unavailable
  - Clear error message explaining failure
  - Allow override ONLY with explicit `--force-direct` flag
- **Security Control:** Prevents security bypass via failure mode
- **Rationale:** Private-only VMs should NEVER be exposed via fallback to public IPs
- **Test:** Disable Bastion, attempt connection to private VM, verify failure

**REQ-ERROR-005: Tunnel Failure Recovery**
- **Requirement:** Tunnel failures MUST be handled gracefully without hanging
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Timeout on tunnel creation: 30 seconds maximum
  - Retry logic: 3 attempts with exponential backoff
  - Clear error on final failure with troubleshooting guidance
  - Clean up partial tunnel state on failure
- **Security Control:** Prevents denial of service from hung tunnels
- **Test:** Simulate tunnel failures (network issues, auth failures), verify timeout and cleanup

---

## 6. Multi-User Security

### 6.1 Shared Bastion Security

**REQ-MULTIUSER-001: Bastion Host Sharing**
- **Requirement:** Shared Bastion hosts MUST NOT expose cross-user data
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Each user authenticates independently to Azure
  - No shared credentials or tokens
  - Tunnels are per-user, not shared
  - Each user's RBAC roles enforced by Azure (not by azlin)
- **Security Control:** Azure Bastion handles multi-user isolation
- **Documentation:** Include team sharing best practices
- **Test:** Two users with same Bastion, verify independent auth and tunnels

**REQ-MULTIUSER-002: RBAC Documentation for Teams**
- **Requirement:** Team access patterns MUST be documented with RBAC examples
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Document RBAC setup for teams:
    - **Reader** on Bastion host (can use existing Bastion)
    - **VM User Login** on VMs (can SSH but not modify)
    - **VM Admin Login** on VMs (can SSH with sudo)
    - **Network Contributor** on resource group (can deploy Bastion)
  - Include Azure CLI commands for common RBAC scenarios
  - Include Azure AD group assignment examples
- **Documentation:** Add `docs/BASTION_RBAC_GUIDE.md`
- **Test:** Manual verification with test Azure AD users

### 6.2 Audit Trail

**REQ-MULTIUSER-003: Connection Audit Logging**
- **Requirement:** Bastion connections MUST be logged for audit trail
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Log: timestamp, user, VM name, Bastion name, connection result
  - Use existing `ConnectionTracker` mechanism
  - Log to `~/.azlin/connection_history.json` with 0600 permissions
  - NO sensitive data in audit logs (IPs OK, no tokens)
- **Security Control:** Accountability for VM access
- **Configuration Example:**
  ```json
  {
    "timestamp": "2025-10-28T10:30:00Z",
    "user": "user@domain.com",
    "vm_name": "azlin-dev-vm",
    "connection_method": "bastion",
    "bastion_name": "azlin-bastion-westus",
    "result": "success"
  }
  ```
- **Test:** Connect via Bastion, verify audit log entry

**REQ-MULTIUSER-004: Azure Activity Log Integration**
- **Requirement:** Document Azure Activity Log queries for Bastion access
- **Priority:** P2 (MEDIUM)
- **Implementation:**
  - Azure Bastion automatically logs to Azure Activity Log
  - Document KQL queries for:
    - All Bastion SSH sessions
    - Failed authentication attempts
    - Bastion configuration changes
  - Include in `docs/BASTION_SECURITY_MONITORING.md`
- **Example KQL Query:**
  ```kql
  AzureActivity
  | where ResourceProvider == "Microsoft.Network"
  | where ResourceType == "bastionHosts"
  | where OperationNameValue == "Microsoft.Network/bastionHosts/createBastionSharableLink/action"
  | project TimeGenerated, Caller, ResourceId, OperationNameValue, ActivityStatusValue
  ```
- **Documentation:** Include monitoring setup guide

---

## 7. Deployment Security

### 7.1 Bastion Subnet Security

**REQ-DEPLOY-001: AzureBastionSubnet Validation**
- **Requirement:** Bastion subnet MUST be named "AzureBastionSubnet" (Azure requirement)
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Validate subnet name before deployment
  - Minimum subnet size: /26 (64 addresses)
  - Recommend /24 for production (256 addresses)
  - Fail deployment if subnet name or size invalid
- **Security Control:** Follows Azure Bastion security requirements
- **Error Message:** `Bastion subnet must be named "AzureBastionSubnet" with minimum size /26. Current: <subnet-name> (<size>)`
- **Test:** Attempt deployment with wrong subnet name/size, verify rejection

**REQ-DEPLOY-002: Bastion Subnet Isolation**
- **Requirement:** AzureBastionSubnet MUST contain ONLY Bastion resources
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Query subnet for existing resources before deployment
  - Reject deployment if subnet contains non-Bastion resources
  - Warn if subnet is shared (multiple Bastion hosts OK, but unusual)
- **Security Control:** Prevents subnet misconfiguration compromising Bastion
- **Error Message:** `AzureBastionSubnet contains non-Bastion resources: <list>. This violates Azure Bastion security requirements.`
- **Test:** Deploy Bastion to subnet with existing VMs, verify rejection

**REQ-DEPLOY-003: VNet CIDR Validation**
- **Requirement:** VNet CIDR ranges MUST NOT overlap with local network
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Detect local network ranges (via routing table query)
  - Warn if VNet CIDR overlaps with local ranges
  - Allow override with `--force` flag (for advanced users)
  - Recommend non-overlapping ranges in documentation
- **Security Control:** Prevents routing conflicts exposing local network
- **Test:** Deploy VNet with CIDR overlapping local network, verify warning

### 7.2 Public IP Security

**REQ-DEPLOY-004: Bastion Public IP Allocation**
- **Requirement:** Bastion Public IP MUST be Standard SKU with static allocation
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Azure Bastion requires Standard SKU public IP
  - Allocation: Static (not Dynamic)
  - Validate SKU and allocation before deployment
  - Fail deployment if wrong SKU/allocation
- **Security Control:** Follows Azure Bastion requirements
- **Test:** Attempt deployment with Basic SKU IP, verify rejection

**REQ-DEPLOY-005: VM Public IP Removal**
- **Requirement:** VMs using Bastion SHOULD NOT have public IPs (cost + security)
- **Priority:** P1 (HIGH)
- **Implementation:**
  - When deploying VM with `--use-bastion` flag, omit public IP creation
  - When connecting to VM with public IP, prefer public IP over Bastion (performance)
  - Provide `azlin vm remove-public-ip <vm>` command to remove public IP
  - Warn user before removing public IP: "This will make VM accessible only via Bastion. Continue? (y/N)"
- **Security Control:** Reduces attack surface, saves cost
- **User Choice:** Don't force removal, but recommend and provide tooling
- **Test:** Deploy VM with --use-bastion, verify no public IP created

### 7.3 NSG Security

**REQ-DEPLOY-006: Bastion NSG Auto-Configuration**
- **Requirement:** Bastion deployment SHOULD NOT auto-create NSG (use Azure defaults)
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Azure Bastion subnet works WITHOUT NSG (Azure manages traffic internally)
  - If user wants NSG, document required rules (don't auto-create)
  - Warn if user attempts to create NSG on Bastion subnet
- **Security Control:** Follows Azure Bastion best practices
- **Documentation:** Include NSG setup guide for compliance scenarios
- **Test:** Deploy Bastion without NSG, verify functionality

---

## 8. Security Testing Requirements

### 8.1 Unit Tests

**REQ-TEST-001: Security Control Unit Tests**
- **Requirement:** All P0 security controls MUST have unit tests
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Test coverage: 100% of security-critical code paths
  - Test frameworks: pytest
  - Security test file: `tests/unit/test_bastion_security.py`
- **Test Categories:**
  - Authentication failures
  - Authorization failures (RBAC)
  - Tunnel lifecycle (creation, cleanup)
  - Configuration validation
  - Input validation (path traversal, injection)
  - Error message sanitization
- **Examples:**
  ```python
  def test_bastion_tunnel_localhost_only():
      """Verify tunnel binds to localhost only (REQ-TUNNEL-001)"""
      tunnel = BastionTunnel.create(...)
      assert tunnel.host == "127.0.0.1"
      assert tunnel.host != "0.0.0.0"

  def test_bastion_config_no_secrets():
      """Verify config rejects secrets (REQ-CONFIG-001)"""
      with pytest.raises(ConfigError, match="secrets not allowed"):
          BastionConfig.from_dict({"secret": "abc123"})
  ```

**REQ-TEST-002: Integration Tests**
- **Requirement:** Bastion integration tests MUST validate end-to-end security
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Test file: `tests/integration/test_bastion_integration.py`
  - Requires: Azure subscription with test VNet, Bastion, VMs
  - Test scenarios:
    - Deploy Bastion, connect to private VM
    - Connection via Bastion with valid RBAC
    - Connection failure with insufficient RBAC
    - Tunnel cleanup on SSH disconnect
    - Multi-user access (two Azure accounts)
- **Test Environment:** Separate test subscription (don't pollute production)
- **CI/CD:** Run in GitHub Actions with Azure service principal

### 8.2 Security Scanning

**REQ-TEST-003: Credential Scanning**
- **Requirement:** All code and config MUST pass credential scanning
- **Priority:** P0 (BLOCKER)
- **Implementation:**
  - Use `detect-secrets` for pre-commit scanning
  - Use `gitleaks` for CI/CD scanning
  - Fail CI/CD pipeline if secrets detected
- **Exceptions:** Test fixtures with fake credentials (document exceptions)
- **Test:** Add fake credential to code, verify CI/CD failure

**REQ-TEST-004: Dependency Vulnerability Scanning**
- **Requirement:** All dependencies MUST be scanned for known vulnerabilities
- **Priority:** P1 (HIGH)
- **Implementation:**
  - Use `pip-audit` for Python dependency scanning
  - Use Dependabot for GitHub dependency updates
  - Fail CI/CD if high/critical vulnerabilities found
- **Exceptions:** Low-risk vulnerabilities can be exceptions (document)
- **Test:** Add vulnerable dependency, verify CI/CD failure

### 8.3 Penetration Testing Scenarios

**REQ-TEST-005: Attack Scenario Testing**
- **Requirement:** Test common attack scenarios against Bastion integration
- **Priority:** P1 (HIGH)
- **Attack Scenarios:**
  1. **Tunnel Hijacking:** Attempt to connect to another user's tunnel port
  2. **Path Traversal:** Attempt to load config from `/etc/passwd`
  3. **Command Injection:** Inject shell metacharacters in VM name, Bastion name
  4. **Token Replay:** Use expired Azure CLI token
  5. **RBAC Bypass:** Attempt VM access without proper RBAC role
  6. **Tunnel Orphaning:** Kill azlin process, verify tunnel cleanup
  7. **Log Injection:** Include credentials in inputs, verify sanitization
- **Test Framework:** Manual penetration test + automated security tests
- **Documentation:** Include in `docs/BASTION_SECURITY_TESTING.md`

---

## 9. Security Best Practices for Users

### 9.1 Deployment Best Practices

**PRACTICE-001: Use Separate VNet for Bastion**
- **Recommendation:** Deploy Bastion in dedicated network VNet
- **Rationale:** Isolates Bastion from application workloads
- **Cost Impact:** Requires VNet peering (~$0.01/GB)
- **Security Benefit:** Defense in depth - limits Bastion compromise radius

**PRACTICE-002: Minimize Bastion RBAC Scope**
- **Recommendation:** Grant RBAC roles at VM scope, not subscription scope
- **Rationale:** Limits blast radius if credentials compromised
- **Example:**
  ```bash
  # Good: VM-scoped
  az role assignment create \
    --assignee user@domain.com \
    --role "Virtual Machine User Login" \
    --scope /subscriptions/.../resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm

  # Bad: Subscription-scoped (too broad)
  az role assignment create \
    --assignee user@domain.com \
    --role "Virtual Machine User Login" \
    --scope /subscriptions/...
  ```

**PRACTICE-003: Enable Azure Activity Log Monitoring**
- **Recommendation:** Monitor Bastion access via Azure Activity Log
- **Implementation:** Configure Log Analytics workspace, set up alerts
- **Alerts:**
  - Multiple failed SSH attempts from single user
  - Bastion configuration changes
  - SSH sessions outside business hours (if applicable)

### 9.2 Operational Best Practices

**PRACTICE-004: Rotate Azure Credentials Regularly**
- **Recommendation:** Rotate service principal secrets every 90 days
- **Implementation:** Use Azure Key Vault for credential rotation
- **Automation:** Use Azure Managed Identities where possible (no secrets)

**PRACTICE-005: Limit Tunnel Lifespan**
- **Recommendation:** Keep SSH sessions short, disconnect when done
- **Rationale:** Reduces window for tunnel hijacking
- **Implementation:** Document in user guide, consider adding session timeout warning

**PRACTICE-006: Use Jump Box for Sensitive Environments**
- **Recommendation:** For production, use Bastion to jump box, then to other VMs
- **Rationale:** Additional layer of access control and logging
- **Architecture:**
  ```
  User -> Bastion -> Jump Box (hardened) -> Production VMs
  ```

---

## 10. Threat Model & Mitigations

### 10.1 Threats

| Threat ID | Threat | Likelihood | Impact | Mitigation |
|-----------|--------|------------|--------|------------|
| T-001 | Unauthorized VM access via stolen credentials | HIGH | CRITICAL | REQ-AUTH-001, REQ-AUTH-002, PRACTICE-004 |
| T-002 | Tunnel hijacking by local attacker | MEDIUM | HIGH | REQ-TUNNEL-001, REQ-TUNNEL-002, REQ-TUNNEL-007 |
| T-003 | Credential leakage in logs/errors | MEDIUM | CRITICAL | REQ-AUTH-004, REQ-ERROR-001, SEC-005 |
| T-004 | RBAC bypass via misconfiguration | LOW | HIGH | REQ-AUTH-002, REQ-MULTIUSER-001 |
| T-005 | NSG misconfiguration blocking Bastion | HIGH | MEDIUM | REQ-ACCESS-003, REQ-ACCESS-004 |
| T-006 | Orphaned tunnel exposing VM | MEDIUM | MEDIUM | REQ-TUNNEL-004, REQ-TUNNEL-005 |
| T-007 | Path traversal in config files | LOW | HIGH | REQ-CONFIG-003, SEC-007 |
| T-008 | VM exposed via fallback to public IP | LOW | HIGH | REQ-ERROR-004 |
| T-009 | Information disclosure in errors | MEDIUM | MEDIUM | REQ-ERROR-002 |
| T-010 | Bastion subnet misconfiguration | MEDIUM | HIGH | REQ-DEPLOY-001, REQ-DEPLOY-002 |

### 10.2 Mitigation Summary

**Defense in Depth Layers:**
1. **Azure RBAC** - Primary access control (REQ-AUTH-002)
2. **Azure AD Authentication** - Identity verification (REQ-AUTH-001)
3. **Network Isolation** - Private VMs via Bastion (REQ-ACCESS-001, REQ-ACCESS-002)
4. **Tunnel Security** - Localhost-only, random ports (REQ-TUNNEL-001, REQ-TUNNEL-002)
5. **Audit Logging** - Connection tracking (REQ-MULTIUSER-003)
6. **Configuration Security** - No secrets, 0600 permissions (REQ-CONFIG-001, REQ-CONFIG-002)
7. **Error Sanitization** - No credential leakage (REQ-ERROR-001)

**Critical Security Controls (Must Pass):**
- All REQ-AUTH-* requirements (authentication)
- All REQ-TUNNEL-* requirements (tunnel security)
- All REQ-CONFIG-* requirements (configuration security)
- All REQ-ERROR-* requirements (error handling)

---

## 11. Compliance & Standards

### 11.1 Security Standards

**STANDARD-001: CIS Azure Foundations Benchmark**
- **Relevant Controls:**
  - 6.1: Ensure default network access rule for Storage Accounts is set to deny
  - 6.2: Ensure Azure Bastion is used for secure access to VMs
  - 7.1: Ensure VM agent is installed
- **Compliance:** Bastion deployment follows CIS recommendations

**STANDARD-002: NIST Cybersecurity Framework**
- **Relevant Functions:**
  - Identify: Asset inventory (VMs, Bastion hosts)
  - Protect: Access control (RBAC), network segmentation (VNets)
  - Detect: Audit logging (Azure Activity Log)
  - Respond: Incident response procedures (documented in security guide)
  - Recover: Disaster recovery (Bastion redeployment procedures)

### 11.2 Regulatory Compliance

**COMPLIANCE-001: GDPR (General Data Protection Regulation)**
- **Applicability:** If processing EU resident data
- **Requirements:**
  - Access logs for data access tracking (REQ-MULTIUSER-003)
  - Right to access: Provide user their connection history
  - Data minimization: Don't log more than necessary
- **Compliance:** Connection logs contain minimal data, 0600 permissions

**COMPLIANCE-002: HIPAA (Health Insurance Portability and Accountability Act)**
- **Applicability:** If processing healthcare data
- **Requirements:**
  - Access controls: RBAC with least privilege (REQ-AUTH-002)
  - Audit controls: Azure Activity Log + connection tracking (REQ-MULTIUSER-003)
  - Transmission security: TLS for all connections (Azure Bastion provides)
- **Compliance:** Bastion provides HIPAA-compliant access controls

---

## 12. Security Checklist for Implementation

### 12.1 Pre-Implementation Checklist

- [ ] Security threat model review completed
- [ ] All P0 requirements have implementation plans
- [ ] Security test plan written
- [ ] Code review by security-focused engineer scheduled
- [ ] Documentation includes security warnings and best practices

### 12.2 Implementation Checklist

**Authentication & Authorization:**
- [ ] REQ-AUTH-001: Azure authentication delegation implemented
- [ ] REQ-AUTH-002: RBAC role documentation written
- [ ] REQ-AUTH-003: No new credential storage added
- [ ] REQ-AUTH-004: Error message sanitization applied

**Access Control:**
- [ ] REQ-ACCESS-001: Private IP validation implemented
- [ ] REQ-ACCESS-002: VNet association validation implemented
- [ ] REQ-ACCESS-003: Bastion NSG validation implemented (warn only)
- [ ] REQ-ACCESS-004: VM NSG validation implemented (warn with remediation)
- [ ] REQ-ACCESS-005: VM-Bastion mapping stored securely
- [ ] REQ-ACCESS-006: Bastion auto-detection with validation

**Tunnel Security:**
- [ ] REQ-TUNNEL-001: Localhost-only binding enforced
- [ ] REQ-TUNNEL-002: Random port allocation implemented
- [ ] REQ-TUNNEL-003: Tunnel port validation with timeout
- [ ] REQ-TUNNEL-004: Cleanup on all exit paths (atexit, signals)
- [ ] REQ-TUNNEL-005: Tunnel process isolation
- [ ] REQ-TUNNEL-006: Tunnel state tracking
- [ ] REQ-TUNNEL-007: Process ownership validation
- [ ] REQ-TUNNEL-008: Token freshness validation

**Configuration:**
- [ ] REQ-CONFIG-001: No secrets in Bastion config
- [ ] REQ-CONFIG-002: Config file 0600 permissions
- [ ] REQ-CONFIG-003: Path traversal validation
- [ ] REQ-CONFIG-004: Subscription ID masking in logs
- [ ] REQ-CONFIG-005: Bastion naming validation

**Error Handling:**
- [ ] REQ-ERROR-001: Credential sanitization in errors
- [ ] REQ-ERROR-002: No information disclosure in errors
- [ ] REQ-ERROR-003: Actionable error messages
- [ ] REQ-ERROR-004: Fail-secure on Bastion errors
- [ ] REQ-ERROR-005: Tunnel failure recovery

**Multi-User:**
- [ ] REQ-MULTIUSER-001: Independent per-user authentication
- [ ] REQ-MULTIUSER-002: RBAC documentation for teams
- [ ] REQ-MULTIUSER-003: Connection audit logging
- [ ] REQ-MULTIUSER-004: Azure Activity Log query documentation

**Deployment:**
- [ ] REQ-DEPLOY-001: AzureBastionSubnet validation
- [ ] REQ-DEPLOY-002: Bastion subnet isolation check
- [ ] REQ-DEPLOY-003: VNet CIDR overlap detection
- [ ] REQ-DEPLOY-004: Standard SKU public IP enforcement
- [ ] REQ-DEPLOY-005: VM public IP removal tooling
- [ ] REQ-DEPLOY-006: NSG documentation (no auto-create)

**Testing:**
- [ ] REQ-TEST-001: Unit tests for all P0 requirements
- [ ] REQ-TEST-002: Integration tests for end-to-end scenarios
- [ ] REQ-TEST-003: Credential scanning in CI/CD
- [ ] REQ-TEST-004: Dependency vulnerability scanning
- [ ] REQ-TEST-005: Attack scenario testing

### 12.3 Pre-Release Checklist

- [ ] All P0 requirements implemented and tested
- [ ] Security code review completed
- [ ] Security tests passing (unit + integration)
- [ ] Penetration testing completed (manual + automated)
- [ ] Documentation reviewed for security guidance
- [ ] User guide includes security warnings
- [ ] RBAC setup guide completed
- [ ] Security monitoring guide completed
- [ ] Threat model updated with implementation details
- [ ] Known issues documented with severity ratings

---

## 13. Security Contact & Reporting

### 13.1 Security Issue Reporting

**If you discover a security vulnerability:**
1. DO NOT open a public GitHub issue
2. Email security contact: [SECURITY_EMAIL]
3. Include: Description, impact, reproduction steps, suggested fix
4. Allow 90 days for fix before public disclosure

### 13.2 Security Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 7 days
- **Fix development:** Within 30 days (critical), 90 days (high)
- **Release:** As soon as fix is validated
- **Public disclosure:** After fix is released + 90 days (or coordinated disclosure)

---

## 14. Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-28 | Security Agent | Initial security requirements for Azure Bastion integration |

---

## 15. References

**Azure Documentation:**
- [Azure Bastion Security Best Practices](https://learn.microsoft.com/en-us/azure/bastion/bastion-overview)
- [Azure RBAC Best Practices](https://learn.microsoft.com/en-us/azure/role-based-access-control/best-practices)
- [Azure Network Security Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices)

**Security Standards:**
- [CIS Azure Foundations Benchmark v2.0](https://www.cisecurity.org/benchmark/azure)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

**Azlin Documentation:**
- [Existing Security Posture](/Users/ryan/src/TuesdayTmp/azlin/src/azlin/service_principal_auth.py)
- [Log Sanitization](/Users/ryan/src/TuesdayTmp/azlin/src/azlin/log_sanitizer.py)
- [SSH Key Management](/Users/ryan/src/TuesdayTmp/azlin/src/azlin/modules/ssh_keys.py)

---

**END OF SECURITY REQUIREMENTS DOCUMENT**

**CLASSIFICATION: SECURITY CRITICAL**
**REVIEW REQUIRED: Security-focused engineer**
**SIGN-OFF REQUIRED: Before implementation begins**
