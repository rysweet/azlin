# Azure Bastion Security Testing Guide
**Version:** 1.0
**Date:** 2025-10-28
**Related:** BASTION_SECURITY_REQUIREMENTS.md

---

## Overview

This document provides specific security test scenarios for Azure Bastion integration. Each test validates a security requirement from BASTION_SECURITY_REQUIREMENTS.md.

**Test Environment Requirements:**
- Azure subscription with Bastion, VNet, and test VMs
- Two Azure AD user accounts (for multi-user tests)
- Service principal with limited RBAC roles (for auth tests)
- Local development environment with azlin installed

---

## 1. Authentication & Authorization Tests

### TEST-AUTH-001: Azure Authentication Required
**Requirement:** REQ-AUTH-001
**Severity:** P0 BLOCKER

**Test Steps:**
1. Logout from Azure CLI: `az logout`
2. Clear service principal environment variables
3. Attempt Bastion operation: `azlin bastion create --resource-group test-rg`
4. **Expected:** Failure with error: "No Azure credentials available. Please run: az login"
5. Login: `az login`
6. Retry Bastion operation
7. **Expected:** Success

**Pass Criteria:**
- Bastion operations fail without valid credentials
- Clear error message with remediation steps
- No credential prompts (batch mode only)

---

### TEST-AUTH-002: Insufficient RBAC Roles
**Requirement:** REQ-AUTH-002
**Severity:** P0 BLOCKER

**Test Scenarios:**

**Scenario 1: No Network Contributor Role**
1. Create service principal with Reader role only
2. Attempt to deploy Bastion: `azlin bastion create --resource-group test-rg`
3. **Expected:** Failure with error mentioning "Network Contributor" role required

**Scenario 2: No VM User Login Role**
1. Service principal has Network Contributor
2. Attempt VM connection via Bastion: `azlin connect test-vm --use-bastion`
3. **Expected:** Failure with error mentioning "Virtual Machine User Login" role required

**Pass Criteria:**
- Clear error messages specifying missing RBAC role
- Error includes Azure CLI command to grant role
- No cryptic Azure ARM error messages

---

### TEST-AUTH-003: Credential Lifecycle Management
**Requirement:** REQ-AUTH-003
**Severity:** P0 BLOCKER

**Test Steps:**
1. Clean environment: remove all credential files
2. Use Azure CLI authentication: `az login`
3. Deploy Bastion: `azlin bastion create --resource-group test-rg`
4. Check filesystem for new credential files:
   ```bash
   find ~/.azlin -type f -name "*cred*" -o -name "*token*" -o -name "*secret*"
   ```
5. **Expected:** No new credential files created
6. Verify config.toml contains no secrets:
   ```bash
   cat ~/.azlin/config.toml | grep -iE "secret|token|password"
   ```
7. **Expected:** No matches

**Pass Criteria:**
- No credential files created by azlin
- Config files contain no secrets
- Credentials delegated to Azure CLI or SDK

---

### TEST-AUTH-004: Error Message Sanitization
**Requirement:** REQ-AUTH-004
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create service principal with invalid client secret
2. Set environment variable: `export AZLIN_SP_CLIENT_SECRET="test-secret-12345"`
3. Attempt Bastion operation with service principal profile
4. Capture error output
5. **Verify:** Error output does NOT contain "test-secret-12345"
6. **Verify:** Error output contains "[REDACTED]" or "****" instead
7. Check logs: `cat ~/.azlin/logs/azlin.log`
8. **Verify:** Logs do NOT contain "test-secret-12345"

**Pass Criteria:**
- No secrets in error messages
- No secrets in log files
- Sanitization markers ([REDACTED] or ****) present

---

## 2. Access Control Tests

### TEST-ACCESS-001: Private IP Validation
**Requirement:** REQ-ACCESS-001
**Severity:** P0 BLOCKER

**Test Scenarios:**

**Scenario 1: Valid Private IP**
1. Create VM with private IP in RFC 1918 range: 10.0.1.4
2. Connect via Bastion: `azlin connect test-vm --use-bastion`
3. **Expected:** Connection proceeds (IP validation passes)

**Scenario 2: Invalid Private IP**
1. Mock VM with invalid private IP: 300.0.1.4
2. Attempt connection: `azlin connect test-vm --use-bastion`
3. **Expected:** Failure with error: "Invalid private IP address: 300.0.1.4"

**Scenario 3: Public IP in Private-Only VM**
1. Create VM without public IP (private-only)
2. Query VM details
3. **Verify:** No public IP returned
4. Connect via Bastion: `azlin connect test-vm --use-bastion`
5. **Expected:** Connection uses private IP through Bastion

**Pass Criteria:**
- Invalid IP addresses rejected
- Clear error messages
- Private-only VMs connect successfully

---

### TEST-ACCESS-002: VNet Association Validation
**Requirement:** REQ-ACCESS-002
**Severity:** P0 BLOCKER

**Test Steps:**
1. Deploy Bastion in VNet-A
2. Deploy VM in VNet-B (different, unpeered VNet)
3. Attempt connection: `azlin connect vm-in-vnetb --use-bastion`
4. **Expected:** Failure with error: "VM 'vm-in-vnetb' is in VNet 'VNet-B', but Bastion 'bastion-westus' is in VNet 'VNet-A'. VNet peering required."
5. Create VNet peering between VNet-A and VNet-B
6. Retry connection: `azlin connect vm-in-vnetb --use-bastion`
7. **Expected:** Connection succeeds

**Pass Criteria:**
- VNet mismatch detected before tunnel creation
- Clear error message with remediation steps
- Connection succeeds after peering established

---

### TEST-ACCESS-003: Bastion NSG Validation
**Requirement:** REQ-ACCESS-003
**Severity:** P1 HIGH

**Test Steps:**
1. Create NSG with overly restrictive rules (deny all inbound)
2. Associate NSG with AzureBastionSubnet
3. Attempt Bastion deployment or connection
4. **Expected:** Warning message: "Bastion subnet NSG may block traffic. Required inbound: TCP 443 from Internet. Required outbound: TCP 22/3389 to VNet."
5. Update NSG with correct rules
6. Retry operation
7. **Expected:** Success, no warnings

**Pass Criteria:**
- NSG misconfigurations detected
- Clear warnings with required rules
- Operations proceed (warn, don't block)

---

### TEST-ACCESS-004: VM NSG Validation
**Requirement:** REQ-ACCESS-004
**Severity:** P1 HIGH

**Test Steps:**
1. Create VM with NSG denying SSH (TCP 22)
2. Attempt Bastion connection: `azlin connect test-vm --use-bastion`
3. **Expected:** Warning: "VM 'test-vm' NSG does not allow SSH from Bastion. Add rule: Source=AzureBastionSubnet, Dest Port=22, Protocol=TCP, Action=Allow"
4. Add NSG rule as instructed
5. Retry connection
6. **Expected:** Connection succeeds

**Pass Criteria:**
- NSG issues detected before connection attempt
- Clear remediation guidance
- Connection succeeds after NSG fix

---

## 3. Tunnel Security Tests

### TEST-TUNNEL-001: Localhost-Only Binding
**Requirement:** REQ-TUNNEL-001
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create Bastion tunnel: `azlin connect test-vm --use-bastion`
2. In tunnel creation logs, capture local port number (e.g., 52341)
3. From **same machine**, verify tunnel is accessible:
   ```bash
   nc -zv 127.0.0.1 52341
   ```
   **Expected:** Connection succeeds
4. From **different machine** on same network, attempt connection:
   ```bash
   nc -zv <machine-ip> 52341
   ```
   **Expected:** Connection refused (port not open to network)
5. Verify tunnel process binding:
   ```bash
   netstat -tuln | grep 52341
   ```
   **Expected:** Shows binding to 127.0.0.1:52341, NOT 0.0.0.0:52341

**Pass Criteria:**
- Tunnel accessible only from localhost
- Not accessible from network
- Binding verified in process list

---

### TEST-TUNNEL-002: Random Port Allocation
**Requirement:** REQ-TUNNEL-002
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create 10 Bastion tunnels in sequence
2. Record local port for each tunnel
3. **Verify:** All ports are unique
4. **Verify:** All ports are in ephemeral range (49152-65535)
5. **Verify:** Ports appear randomly distributed (no sequential pattern)
6. Close all tunnels
7. Create another tunnel
8. **Verify:** Port is different from previous 10

**Pass Criteria:**
- All ports unique
- Ports in ephemeral range
- No predictable pattern

---

### TEST-TUNNEL-003: Tunnel Port Validation
**Requirement:** REQ-TUNNEL-003
**Severity:** P0 BLOCKER

**Test Steps:**
1. Mock `az network bastion tunnel` to hang (no port opened)
2. Attempt connection: `azlin connect test-vm --use-bastion`
3. **Verify:** Connection times out after 10 seconds
4. **Verify:** Error message: "Tunnel creation timed out after 10 seconds"
5. **Verify:** Tunnel process is terminated (no orphans)

**Pass Criteria:**
- Timeout enforced
- Clear error message
- No orphaned processes

---

### TEST-TUNNEL-004: Tunnel Cleanup on Exit
**Requirement:** REQ-TUNNEL-004
**Severity:** P0 BLOCKER

**Test Scenarios:**

**Scenario 1: Normal SSH Exit**
1. Create tunnel and connect: `azlin connect test-vm --use-bastion`
2. Exit SSH session normally (type `exit`)
3. **Verify:** Tunnel process terminates
4. Check process list: `ps aux | grep "az network bastion tunnel"`
5. **Expected:** No tunnel processes

**Scenario 2: SIGINT (Ctrl+C)**
1. Create tunnel and connect
2. Send SIGINT: Press Ctrl+C
3. **Verify:** Tunnel process terminates
4. **Verify:** No orphaned processes

**Scenario 3: SIGTERM**
1. Create tunnel and connect
2. From another terminal, kill SSH process: `kill <ssh-pid>`
3. **Verify:** Tunnel process terminates
4. **Verify:** No orphaned processes

**Scenario 4: SIGKILL (Hard Kill)**
1. Create tunnel and connect
2. From another terminal, force kill: `kill -9 <ssh-pid>`
3. **Verify:** Tunnel process terminates within 5 seconds
4. If not terminated, atexit handler should clean up

**Pass Criteria:**
- Tunnel cleanup on all exit scenarios
- No orphaned tunnel processes
- Cleanup verified in process list

---

### TEST-TUNNEL-005: Tunnel Process Isolation
**Requirement:** REQ-TUNNEL-005
**Severity:** P1 HIGH

**Test Steps:**
1. Create tunnel: `azlin connect test-vm --use-bastion`
2. Inspect tunnel subprocess:
   ```bash
   ps -o pid,ppid,user,args -p <tunnel-pid>
   ```
3. **Verify:** Tunnel process has no stdin/stdout/stderr attached to terminal
4. **Verify:** Tunnel process args do NOT contain `shell=True`
5. **Verify:** Tunnel process is child of azlin process (correct parent)

**Pass Criteria:**
- No terminal I/O inheritance
- No shell=True usage
- Correct process hierarchy

---

### TEST-TUNNEL-006: Tunnel State Tracking
**Requirement:** REQ-TUNNEL-006
**Severity:** P1 HIGH

**Test Steps:**
1. Create 3 tunnels to different VMs
2. Run command: `azlin bastion tunnels --list`
3. **Expected Output:**
   ```
   Active Bastion Tunnels:
   VM Name       Local Port  Bastion Name         Created
   test-vm-1     52341       bastion-westus       2025-10-28 10:30:00
   test-vm-2     52342       bastion-westus       2025-10-28 10:31:00
   test-vm-3     52343       bastion-eastus       2025-10-28 10:32:00
   ```
4. Close one tunnel (exit SSH session)
5. Re-run: `azlin bastion tunnels --list`
6. **Verify:** Closed tunnel no longer listed
7. Restart azlin process
8. Re-run: `azlin bastion tunnels --list`
9. **Expected:** Empty list (state not persisted, as designed)

**Pass Criteria:**
- Active tunnels correctly listed
- Closed tunnels removed from list
- State not persisted across restarts

---

### TEST-TUNNEL-007: Tunnel Process Ownership
**Requirement:** REQ-TUNNEL-007
**Severity:** P0 BLOCKER

**Test Steps:**
1. Run azlin as non-root user
2. Create tunnel
3. Check tunnel process ownership:
   ```bash
   ps -o user,pid,args -p <tunnel-pid>
   ```
4. **Verify:** Process owned by current user (not root)
5. **Verify:** No setuid/setgid bits set
6. Attempt to run azlin with sudo (if supported)
7. **Verify:** Tunnel processes still owned by original user (not root)

**Pass Criteria:**
- Tunnel processes owned by current user
- No privilege escalation
- Runs correctly without root

---

### TEST-TUNNEL-008: Azure CLI Token Validation
**Requirement:** REQ-TUNNEL-008
**Severity:** P1 HIGH

**Test Steps:**
1. Login to Azure CLI: `az login`
2. Wait for token to be near expiration (or mock expired token)
3. Attempt tunnel creation
4. **Expected:** Error or prompt: "Azure CLI token expired or expiring soon. Please re-authenticate: az login"
5. Re-authenticate: `az login`
6. Retry tunnel creation
7. **Expected:** Success

**Pass Criteria:**
- Expired tokens detected
- Clear re-authentication prompt
- Connection succeeds after re-auth

---

## 4. Configuration Security Tests

### TEST-CONFIG-001: No Secrets in Bastion Config
**Requirement:** REQ-CONFIG-001
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create Bastion configuration
2. Attempt to save config with secret field:
   ```python
   config = {
       "bastion": {
           "name": "test-bastion",
           "client_secret": "should-not-save"  # Malicious
       }
   }
   ConfigManager.save_config(config)
   ```
3. **Expected:** Exception raised: "Secrets not allowed in Bastion config"
4. Read config file: `cat ~/.azlin/config.toml`
5. **Verify:** No "client_secret" field present

**Pass Criteria:**
- Secret fields rejected
- Config file contains no secrets
- Clear error message

---

### TEST-CONFIG-002: Config File Permissions
**Requirement:** REQ-CONFIG-002
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create config file with insecure permissions:
   ```bash
   echo "[bastion]" > ~/.azlin/config.toml
   chmod 0644 ~/.azlin/config.toml
   ```
2. Run azlin command that reads config
3. **Expected:** Warning: "Config file has insecure permissions 0644, fixing to 0600"
4. Check permissions:
   ```bash
   stat -c "%a" ~/.azlin/config.toml
   ```
5. **Expected:** 600

**Pass Criteria:**
- Insecure permissions detected
- Auto-fix to 0600
- Warning message displayed

---

### TEST-CONFIG-003: Path Traversal Prevention
**Requirement:** REQ-CONFIG-003
**Severity:** P0 BLOCKER

**Test Scenarios:**

**Scenario 1: Path Traversal in Config Path**
```bash
azlin config load --config-file "../../etc/passwd"
```
**Expected:** Error: "Invalid config path: ../../etc/passwd"

**Scenario 2: Absolute Path to Sensitive File**
```bash
azlin config load --config-file "/etc/shadow"
```
**Expected:** Error: "Config path outside allowed directories"

**Scenario 3: Symlink to Sensitive File**
```bash
ln -s /etc/passwd ~/.azlin/evil-config.toml
azlin config load --config-file ~/.azlin/evil-config.toml
```
**Expected:** Error after symlink resolution

**Pass Criteria:**
- All path traversal attempts blocked
- Symlinks resolved and validated
- Clear error messages

---

### TEST-CONFIG-004: Resource ID Masking in Logs
**Requirement:** REQ-CONFIG-004
**Severity:** P1 HIGH

**Test Steps:**
1. Enable debug logging: `azlin --debug bastion create ...`
2. Capture log output
3. Search for subscription IDs:
   ```bash
   grep -E "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" azlin.log
   ```
4. **Verify:** All subscription IDs are masked: `12345678-****-****-****-************`
5. **Verify:** Bastion names and resource groups are NOT masked (not sensitive)

**Pass Criteria:**
- Subscription IDs masked in logs
- Resource names visible (not overly masked)
- Consistent masking pattern

---

### TEST-CONFIG-005: Bastion Naming Validation
**Requirement:** REQ-CONFIG-005
**Severity:** P1 HIGH

**Test Scenarios:**

**Invalid Names:**
```bash
azlin bastion create --name "bastion_invalid"    # Underscore not allowed
azlin bastion create --name "-bastion"           # Starts with hyphen
azlin bastion create --name "bastion-"           # Ends with hyphen
azlin bastion create --name "a"*81               # Too long (>80 chars)
azlin bastion create --name "bastion@test"       # Special char
```

**Valid Names:**
```bash
azlin bastion create --name "bastion-westus"     # Valid
azlin bastion create --name "Bastion123"         # Valid (alphanumeric)
azlin bastion create --name "b"                  # Valid (1 char)
```

**Pass Criteria:**
- Invalid names rejected with clear error
- Valid names accepted
- Error message explains naming rules

---

## 5. Error Handling Tests

### TEST-ERROR-001: No Credential Leakage in Errors
**Requirement:** REQ-ERROR-001
**Severity:** P0 BLOCKER

**Test Steps:**
1. Set invalid service principal secret
2. Trigger authentication error
3. Capture error output and stack trace
4. Search for secret pattern:
   ```bash
   echo "$ERROR_OUTPUT" | grep -iE "secret|password|token"
   ```
5. **Verify:** No actual secret values found
6. **Verify:** Sanitization markers present ([REDACTED] or ****)

**Pass Criteria:**
- No secrets in error messages
- No secrets in stack traces
- Sanitization applied consistently

---

### TEST-ERROR-002: Information Disclosure Prevention
**Requirement:** REQ-ERROR-002
**Severity:** P1 HIGH

**Test Steps:**
1. Trigger various errors (auth failure, network failure, RBAC failure)
2. Capture error messages in non-debug mode
3. **Verify:** No internal IPs exposed
4. **Verify:** No file paths exposed
5. **Verify:** No process IDs exposed
6. Enable debug mode: `--debug`
7. Re-trigger same errors
8. **Verify:** Internal details NOW visible (debug mode only)

**Pass Criteria:**
- Internal details hidden in normal mode
- Internal details visible in debug mode
- User-friendly error messages

---

### TEST-ERROR-003: Actionable Error Messages
**Requirement:** REQ-ERROR-003
**Severity:** P1 HIGH

**Test Scenarios:**

**Scenario 1: RBAC Error**
Trigger RBAC error, verify error message includes:
- Required role name
- Azure CLI command to grant role
- Link to RBAC documentation

**Scenario 2: NSG Error**
Trigger NSG blocking SSH, verify error message includes:
- NSG rule to add
- Azure CLI command to add rule
- Link to NSG documentation

**Scenario 3: Authentication Error**
Trigger auth error, verify error message includes:
- Authentication command (`az login`)
- Link to authentication docs

**Pass Criteria:**
- All errors include remediation steps
- Azure CLI commands are copy-pasteable
- Links to documentation provided

---

### TEST-ERROR-004: Fail-Secure on Bastion Errors
**Requirement:** REQ-ERROR-004
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create VM with private IP only (no public IP)
2. Configure VM to use Bastion
3. Disable or delete Bastion
4. Attempt connection: `azlin connect test-vm`
5. **Expected:** Connection FAILS with error: "VM 'test-vm' is configured for Bastion-only access, but Bastion 'bastion-westus' is unavailable."
6. **Verify:** No fallback to public IP (there is none)
7. **Verify:** No bypass to direct private IP connection
8. Attempt with force flag: `azlin connect test-vm --force-direct`
9. **Expected:** Still fails (no public IP available)

**Pass Criteria:**
- Bastion failure prevents connection
- No security bypass
- Clear error message
- Force flag documented but respects security

---

### TEST-ERROR-005: Tunnel Failure Recovery
**Requirement:** REQ-ERROR-005
**Severity:** P1 HIGH

**Test Steps:**
1. Mock tunnel creation to fail intermittently
2. Attempt connection: `azlin connect test-vm --use-bastion`
3. **Verify:** Automatic retry with exponential backoff
4. **Verify:** Maximum 3 retry attempts
5. **Verify:** Connection succeeds on 2nd attempt (simulated)
6. Mock all 3 attempts to fail
7. **Verify:** Final error message with troubleshooting tips
8. **Verify:** No orphaned processes left behind

**Pass Criteria:**
- Automatic retries with backoff
- Max 3 attempts
- Clean failure after retries exhausted
- No resource leaks

---

## 6. Multi-User Tests

### TEST-MULTIUSER-001: Independent User Authentication
**Requirement:** REQ-MULTIUSER-001
**Severity:** P0 BLOCKER

**Test Steps:**
1. **User A:** Login: `az login` (user-a@domain.com)
2. **User A:** Create tunnel: `azlin connect test-vm --use-bastion`
3. **User A:** Capture tunnel local port (e.g., 52341)
4. **User B:** Login: `az login` (user-b@domain.com) in separate terminal
5. **User B:** Create tunnel to same VM: `azlin connect test-vm --use-bastion`
6. **User B:** Capture tunnel local port (e.g., 52342)
7. **Verify:** User A and User B have different local ports
8. **Verify:** User A's tunnel NOT accessible to User B (no shared state)
9. **Verify:** Both tunnels use their respective Azure credentials

**Pass Criteria:**
- Each user has independent tunnel
- No shared credentials or state
- Both users can connect simultaneously

---

### TEST-MULTIUSER-002: RBAC Enforcement
**Requirement:** REQ-MULTIUSER-002
**Severity:** P1 HIGH

**Test Steps:**
1. Grant User A "VM User Login" role on test-vm
2. Grant User B "Reader" role only (no VM login)
3. **User A:** Connect: `azlin connect test-vm --use-bastion`
4. **Expected:** Success
5. **User B:** Connect: `azlin connect test-vm --use-bastion`
6. **Expected:** Failure with error: "Insufficient permissions. Required role: 'Virtual Machine User Login'"

**Pass Criteria:**
- RBAC enforced at Azure level
- Clear error for insufficient permissions
- No bypass mechanism

---

### TEST-MULTIUSER-003: Connection Audit Logging
**Requirement:** REQ-MULTIUSER-003
**Severity:** P1 HIGH

**Test Steps:**
1. Connect via Bastion: `azlin connect test-vm --use-bastion`
2. Check audit log: `cat ~/.azlin/connection_history.json`
3. **Verify:** Entry contains:
   - Timestamp
   - User (from Azure credentials)
   - VM name
   - Connection method: "bastion"
   - Bastion name
   - Result: "success"
4. Verify log file permissions:
   ```bash
   stat -c "%a" ~/.azlin/connection_history.json
   ```
5. **Expected:** 600
6. Attempt connection to VM without permission (fail)
7. Check audit log again
8. **Verify:** Entry with result: "failure" and error reason

**Pass Criteria:**
- All connections logged
- Log format includes required fields
- Log file has 0600 permissions
- Both success and failure logged

---

### TEST-MULTIUSER-004: Azure Activity Log Queries
**Requirement:** REQ-MULTIUSER-004
**Severity:** P2 MEDIUM

**Test Steps:**
1. Connect via Bastion multiple times
2. Wait 5 minutes (Activity Log delay)
3. Run KQL query in Azure Portal Log Analytics:
   ```kql
   AzureActivity
   | where ResourceProvider == "Microsoft.Network"
   | where ResourceType == "bastionHosts"
   | where TimeGenerated > ago(1h)
   | project TimeGenerated, Caller, OperationNameValue, ActivityStatusValue, ResourceId
   ```
4. **Verify:** Entries for Bastion tunnel creation
5. **Verify:** Entries include Caller (user identity)
6. Document working KQL queries in `docs/BASTION_SECURITY_MONITORING.md`

**Pass Criteria:**
- KQL queries documented
- Activity Log captures Bastion access
- Queries return expected results

---

## 7. Deployment Security Tests

### TEST-DEPLOY-001: AzureBastionSubnet Validation
**Requirement:** REQ-DEPLOY-001
**Severity:** P0 BLOCKER

**Test Scenarios:**

**Scenario 1: Wrong Subnet Name**
```bash
azlin bastion create --resource-group test-rg --subnet "BastionSubnet"
```
**Expected:** Error: "Bastion subnet must be named 'AzureBastionSubnet'"

**Scenario 2: Subnet Too Small**
Create subnet with /27 prefix (32 addresses), attempt Bastion deployment
**Expected:** Error: "Bastion subnet must be at least /26 (64 addresses). Current: /27"

**Scenario 3: Valid Subnet**
Create subnet named "AzureBastionSubnet" with /26 prefix
**Expected:** Deployment succeeds

**Pass Criteria:**
- Wrong subnet names rejected
- Insufficient subnet size rejected
- Valid configurations accepted

---

### TEST-DEPLOY-002: Bastion Subnet Isolation
**Requirement:** REQ-DEPLOY-002
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create AzureBastionSubnet
2. Deploy VM in same subnet (violation)
3. Attempt Bastion deployment
4. **Expected:** Error: "AzureBastionSubnet contains non-Bastion resources: [vm-name]. Remove resources before deploying Bastion."
5. Remove VM from subnet
6. Retry Bastion deployment
7. **Expected:** Success

**Pass Criteria:**
- Non-Bastion resources detected
- Clear error message
- Deployment proceeds only after cleanup

---

### TEST-DEPLOY-003: VNet CIDR Overlap Detection
**Requirement:** REQ-DEPLOY-003
**Severity:** P1 HIGH

**Test Steps:**
1. Detect local network CIDR (e.g., 192.168.1.0/24)
2. Attempt VNet deployment with overlapping CIDR: 192.168.1.0/24
3. **Expected:** Warning: "VNet CIDR 192.168.1.0/24 overlaps with local network. This may cause routing issues. Use --force to proceed."
4. Proceed without --force
5. **Expected:** Deployment aborted
6. Retry with --force flag
7. **Expected:** Deployment proceeds (user acknowledged risk)

**Pass Criteria:**
- Overlap detection works
- Clear warning with risks explained
- Force flag allows override

---

### TEST-DEPLOY-004: Standard SKU Public IP
**Requirement:** REQ-DEPLOY-004
**Severity:** P0 BLOCKER

**Test Steps:**
1. Attempt Bastion deployment with Basic SKU Public IP (if possible to specify)
2. **Expected:** Error: "Bastion requires Standard SKU Public IP. Basic SKU not supported."
3. Allow auto-creation with correct SKU
4. **Verify:** Public IP created is Standard SKU with Static allocation
5. Query public IP:
   ```bash
   az network public-ip show --name bastion-pip --resource-group test-rg
   ```
6. **Verify:** "sku": "Standard", "publicIPAllocationMethod": "Static"

**Pass Criteria:**
- Incorrect SKU rejected
- Correct SKU auto-selected
- Static allocation enforced

---

### TEST-DEPLOY-005: VM Public IP Removal
**Requirement:** REQ-DEPLOY-005
**Severity:** P1 HIGH

**Test Steps:**
1. Deploy VM with public IP: `azlin new test-vm --size Standard_D2s_v3`
2. Verify VM has public IP:
   ```bash
   az vm show --name test-vm --resource-group test-rg --query "publicIps"
   ```
3. Remove public IP: `azlin vm remove-public-ip test-vm`
4. **Expected:** Confirmation prompt: "This will make VM accessible only via Bastion. Continue? (y/N)"
5. Confirm: y
6. **Verify:** Public IP removed
7. Attempt direct connection: `azlin connect test-vm`
8. **Expected:** Error: "VM has no public IP. Use --use-bastion flag to connect via Bastion."
9. Connect via Bastion: `azlin connect test-vm --use-bastion`
10. **Expected:** Success

**Pass Criteria:**
- Public IP removal requires confirmation
- Clear warning about impact
- Bastion connection works after removal

---

### TEST-DEPLOY-006: NSG Documentation (No Auto-Create)
**Requirement:** REQ-DEPLOY-006
**Severity:** P1 HIGH

**Test Steps:**
1. Deploy Bastion without specifying NSG
2. **Verify:** No NSG auto-created on AzureBastionSubnet
3. **Verify:** Bastion functions correctly (Azure manages traffic)
4. Consult documentation: `docs/BASTION_NSG_GUIDE.md`
5. **Verify:** Documentation includes:
   - Statement: "NSG on Bastion subnet is optional"
   - If NSG required (compliance): rules listed
   - Warning about NSG misconfigurations

**Pass Criteria:**
- No NSG auto-created
- Documentation complete
- Bastion works without NSG

---

## 8. Security Regression Tests

### TEST-REGRESSION-001: Existing Security Controls Intact
**Requirement:** All existing SEC-* requirements
**Severity:** P0 BLOCKER

**Test Steps:**
1. Run existing security test suite: `pytest tests/unit/test_auth_security.py`
2. **Verify:** All existing security tests pass
3. Run SSH key tests: `pytest tests/unit/test_ssh_keys.py`
4. **Verify:** Key permissions still enforced (0600)
5. Run log sanitization tests: `pytest tests/unit/test_log_sanitizer.py`
6. **Verify:** Log sanitization still works
7. Run service principal tests: `pytest tests/unit/test_service_principal_auth.py`
8. **Verify:** Service principal auth unchanged

**Pass Criteria:**
- All existing security tests pass
- No regressions in existing security controls
- Bastion code does not weaken existing security

---

### TEST-REGRESSION-002: Non-Bastion SSH Still Works
**Requirement:** Backward compatibility
**Severity:** P0 BLOCKER

**Test Steps:**
1. Create VM with public IP (traditional setup)
2. Connect without Bastion flag: `azlin connect test-vm`
3. **Expected:** Direct SSH connection (not via Bastion)
4. **Verify:** Connection speed comparable to before Bastion feature
5. **Verify:** No Bastion tunnel created

**Pass Criteria:**
- Direct SSH connections work as before
- No performance degradation
- Bastion opt-in only (not forced)

---

## 9. Penetration Testing Scenarios

### PEN-TEST-001: Tunnel Hijacking Attack
**Attack:** Local attacker attempts to connect to another user's tunnel

**Test Steps:**
1. User A creates tunnel on port 52341
2. User B (different local user) attempts connection:
   ```bash
   ssh -p 52341 azureuser@127.0.0.1
   ```
3. **Expected:** Connection refused (tunnel bound to User A's session)
4. User B attempts to list User A's tunnel:
   ```bash
   azlin bastion tunnels --list  # As User B
   ```
5. **Expected:** Only User B's tunnels listed (no cross-user visibility)

**Pass Criteria:**
- Tunnel not accessible to other local users
- No cross-user state visibility

---

### PEN-TEST-002: Path Traversal Attack
**Attack:** Attacker attempts to read sensitive files via config path manipulation

**Test Steps:**
1. Attempt to load /etc/passwd as config:
   ```bash
   azlin config load --config-file /etc/passwd
   ```
2. **Expected:** Error (path outside allowed directories)
3. Attempt symlink attack:
   ```bash
   ln -s /etc/shadow ~/.azlin/config.toml
   azlin config load
   ```
4. **Expected:** Error after symlink resolution
5. Attempt directory traversal:
   ```bash
   azlin config load --config-file "../../../etc/passwd"
   ```
6. **Expected:** Error (path traversal blocked)

**Pass Criteria:**
- All path traversal attempts blocked
- No sensitive file access

---

### PEN-TEST-003: Command Injection Attack
**Attack:** Inject shell commands via VM/Bastion names

**Test Steps:**
1. Attempt command injection in VM name:
   ```bash
   azlin connect "test-vm; rm -rf /" --use-bastion
   ```
2. **Expected:** Error (invalid VM name format)
3. Attempt in Bastion name:
   ```bash
   azlin bastion create --name "bastion; curl evil.com"
   ```
4. **Expected:** Error (invalid Bastion name format)
5. Verify no shell=True used:
   ```bash
   grep -r "shell=True" src/azlin/
   ```
6. **Expected:** No matches (shell=True prohibited)

**Pass Criteria:**
- All injection attempts blocked
- Input validation prevents shell execution
- No shell=True in codebase

---

### PEN-TEST-004: Token Replay Attack
**Attack:** Reuse expired Azure CLI token

**Test Steps:**
1. Login: `az login`
2. Capture token: `az account get-access-token`
3. Wait for token expiration (or mock expired token)
4. Attempt Bastion operation with expired token
5. **Expected:** Error: "Azure CLI token expired. Please re-authenticate: az login"
6. Use `az account clear` to clear tokens
7. Attempt Bastion operation
8. **Expected:** Error (no credentials available)

**Pass Criteria:**
- Expired tokens rejected
- No token caching by azlin
- Re-authentication required

---

### PEN-TEST-005: RBAC Bypass Attempt
**Attack:** Access VM without proper RBAC role

**Test Steps:**
1. Create service principal with Reader role only (no VM login role)
2. Configure azlin to use this service principal
3. Attempt VM connection: `azlin connect test-vm --use-bastion`
4. **Expected:** Failure at Azure Bastion level (RBAC enforced)
5. Attempt to forge RBAC role in config:
   ```toml
   [auth.profiles.hacker]
   roles = ["VM Administrator Login"]  # Fake role
   ```
6. **Expected:** Ignored (roles not trusted from config)

**Pass Criteria:**
- RBAC enforced by Azure (not bypassable in azlin)
- Config cannot override Azure RBAC

---

### PEN-TEST-006: Tunnel Orphaning Attack
**Attack:** Leave orphaned tunnel processes for persistent access

**Test Steps:**
1. Create tunnel: `azlin connect test-vm --use-bastion`
2. From another terminal, kill azlin process: `kill -9 <azlin-pid>`
3. Wait 10 seconds
4. Check for orphaned tunnel processes:
   ```bash
   ps aux | grep "az network bastion tunnel"
   ```
5. **Expected:** No tunnel processes (atexit cleanup worked)
6. If orphaned, verify they time out within 5 minutes (Azure limit)

**Pass Criteria:**
- Tunnel processes cleaned up on hard kill
- No persistent orphaned tunnels
- Azure timeout as fallback

---

### PEN-TEST-007: Log Injection Attack
**Attack:** Inject credentials into logs via error messages

**Test Steps:**
1. Trigger error with credential in input:
   ```bash
   azlin connect "vm-name-with-secret-abc123" --use-bastion
   ```
2. Check logs: `cat ~/.azlin/logs/azlin.log`
3. **Verify:** "secret-abc123" is masked: "secret-[REDACTED]"
4. Inject credential in Bastion name:
   ```bash
   azlin bastion create --name "bastion-password-12345"
   ```
5. Check logs
6. **Verify:** "password-12345" is masked

**Pass Criteria:**
- Credentials in inputs sanitized in logs
- Pattern-based sanitization catches variants

---

## 10. Performance & DoS Tests

### TEST-DOS-001: Tunnel Resource Limits
**Test:** Create excessive tunnels to exhaust resources

**Test Steps:**
1. Create 100 tunnels in parallel
2. **Verify:** System remains responsive
3. **Verify:** Azlin enforces reasonable limits (e.g., max 10 concurrent tunnels)
4. Attempt to create 11th tunnel
5. **Expected:** Error: "Maximum concurrent tunnels (10) reached. Close existing tunnels."

**Pass Criteria:**
- Resource limits enforced
- System remains stable
- Clear error when limit reached

---

### TEST-DOS-002: Tunnel Cleanup Performance
**Test:** Verify tunnel cleanup doesn't hang

**Test Steps:**
1. Create 10 tunnels
2. Kill all SSH sessions simultaneously
3. **Measure:** Time for all tunnels to clean up
4. **Expected:** All tunnels cleaned up within 10 seconds

**Pass Criteria:**
- Fast cleanup (<10 seconds)
- No hung processes
- No resource leaks

---

## 11. Compliance Tests

### TEST-COMPLIANCE-001: CIS Azure Benchmark
**Test:** Verify CIS control compliance

**Test Steps:**
1. Verify Bastion deployment follows CIS 6.2: "Ensure Azure Bastion is used"
2. Verify VM without public IP (CIS recommendation)
3. Verify NSG rules allow only necessary traffic
4. Generate CIS compliance report (if tooling available)

**Pass Criteria:**
- CIS controls satisfied
- Documented deviations (if any)

---

### TEST-COMPLIANCE-002: Audit Log Requirements
**Test:** Verify audit logging meets regulatory requirements

**Test Steps:**
1. Enable Azure Activity Log
2. Perform Bastion connection
3. Query Activity Log after 5 minutes
4. **Verify:** Log entry includes:
   - Timestamp (accurate)
   - User identity (from Azure AD)
   - Resource accessed (VM ID)
   - Action performed (SSH connection)
   - Result (success/failure)
5. Verify logs retained per retention policy

**Pass Criteria:**
- All required audit fields present
- Logs match regulatory requirements (GDPR, HIPAA, etc.)

---

## 12. Test Automation

### Automated Test Suite

**Unit Tests:**
```bash
pytest tests/unit/test_bastion_security.py -v
```

**Integration Tests:**
```bash
pytest tests/integration/test_bastion_integration.py -v
```

**Full Security Suite:**
```bash
pytest tests/ -k security -v
```

**Coverage Report:**
```bash
pytest --cov=azlin.bastion_manager --cov=azlin.bastion_config --cov-report=html
```

---

## 13. Sign-Off Checklist

Before marking Bastion feature as security-approved:

- [ ] All P0 tests passing
- [ ] All P1 tests passing (or documented exceptions)
- [ ] Penetration tests completed with no critical findings
- [ ] Code review by security-focused engineer
- [ ] Documentation reviewed for security guidance
- [ ] Compliance tests passing (if applicable)
- [ ] Performance tests passing (no DoS vulnerabilities)
- [ ] Security regression tests passing
- [ ] CI/CD pipeline includes security tests
- [ ] Security monitoring configured (Azure Activity Log)

**Security Approval:** _______________________ Date: _______

**Engineering Approval:** _______________________ Date: _______

---

## 14. Known Issues & Limitations

*Document any known security limitations or accepted risks here*

---

## 15. References

- BASTION_SECURITY_REQUIREMENTS.md
- Azure Bastion Security Documentation
- OWASP Testing Guide
- CIS Azure Foundations Benchmark

---

**END OF SECURITY TESTING GUIDE**
