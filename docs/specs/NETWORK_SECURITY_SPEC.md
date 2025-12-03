# Network Security Management System - Security Architecture

**Status**: Draft
**Workstream**: WS6 - Network Security Enhancements (Issue #440)
**Date**: 2025-12-01
**Security Agent**: Security Specialist

---

## Executive Summary

This specification defines a comprehensive network security management system for azlin that provides:

1. **NSG Automation** - Template-based Network Security Group management with 100% validation coverage
2. **Bastion Enhancements** - Secure connection pooling, automatic cleanup, and localhost enforcement
3. **VPN/Private Endpoints** - Secure private connectivity configuration
4. **Security Audit Logging** - Comprehensive, tamper-proof audit trails with zero critical findings
5. **Vulnerability Scanning** - Automated integration with Azure Security Center

**Security Posture**: This system achieves defense-in-depth through multiple security layers, follows principle of least privilege, and ensures fail-secure defaults.

---

## Table of Contents

1. [Threat Model](#threat-model)
2. [Security Requirements](#security-requirements)
3. [System Architecture](#system-architecture)
4. [NSG Template System](#nsg-template-system)
5. [Bastion Security Enhancements](#bastion-security-enhancements)
6. [Audit Logging System](#audit-logging-system)
7. [Vulnerability Scanning Integration](#vulnerability-scanning-integration)
8. [VPN and Private Endpoint Configuration](#vpn-and-private-endpoint-configuration)
9. [Compliance Mappings](#compliance-mappings)
10. [Implementation Roadmap](#implementation-roadmap)

---

## 1. Threat Model

### 1.1 Assets

**Primary Assets**:
- VM instances and their workloads
- Network traffic between VMs
- SSH keys and authentication credentials
- Audit logs containing security decisions
- Bastion tunnel connections
- Azure subscription credentials

**Supporting Assets**:
- NSG rules and configurations
- Bastion host infrastructure
- VPN gateways and private endpoints
- Security templates and policies

### 1.2 Threat Actors

| Actor Type | Motivation | Capability | Likelihood |
|------------|------------|------------|------------|
| External Attacker | Data theft, disruption | High - automated tools, zero-day exploits | High |
| Malicious Insider | Sabotage, data exfiltration | Medium - authorized access | Medium |
| Compromised Credentials | Unauthorized access | Medium - valid credentials | High |
| Accidental Misconfiguration | Unintentional exposure | Low - human error | Very High |

### 1.3 Attack Vectors

#### AV-1: Network Exposure
**Threat**: VM with overly permissive NSG rules exposed to internet
- **Impact**: CRITICAL - Complete VM compromise
- **Likelihood**: HIGH - Human error in NSG configuration
- **Attack Chain**: Port scan → Service exploitation → Lateral movement
- **Mitigation**: NSG template validation, deny-by-default rules

#### AV-2: Bastion Tunnel Hijacking
**Threat**: Attacker gains access to active Bastion tunnel
- **Impact**: HIGH - Unauthorized VM access
- **Likelihood**: MEDIUM - Requires local system access
- **Attack Chain**: Local privilege escalation → Tunnel enumeration → Connection reuse
- **Mitigation**: Localhost-only binding, tunnel cleanup, connection pooling

#### AV-3: Credential Theft
**Threat**: SSH keys or Azure credentials stolen
- **Impact**: CRITICAL - Full infrastructure access
- **Likelihood**: MEDIUM - Phishing, malware
- **Attack Chain**: Credential theft → Authentication → Resource access
- **Mitigation**: Key Vault integration, credential rotation, MFA enforcement

#### AV-4: Audit Log Tampering
**Threat**: Attacker modifies security audit logs
- **Impact**: HIGH - Loss of accountability
- **Likelihood**: LOW - Requires file system access
- **Attack Chain**: System compromise → File modification → Evidence destruction
- **Mitigation**: File permissions (0600), append-only logging, remote backup

#### AV-5: Man-in-the-Middle
**Threat**: Network traffic interception
- **Impact**: HIGH - Data exposure
- **Likelihood**: LOW - Azure VNet provides network isolation
- **Attack Chain**: Network position → Traffic capture → Decryption
- **Mitigation**: Private endpoints, VPN, encrypted channels

#### AV-6: Lateral Movement
**Threat**: Compromised VM used to attack others
- **Impact**: HIGH - Infrastructure-wide compromise
- **Likelihood**: MEDIUM - Post-exploitation technique
- **Attack Chain**: Initial compromise → Network discovery → Additional exploitation
- **Mitigation**: Network segmentation, NSG rules, zero trust

#### AV-7: Configuration Drift
**Threat**: Manual changes violate security policies
- **Impact**: MEDIUM - Compliance violations
- **Likelihood**: HIGH - Operational necessity
- **Attack Chain**: Manual change → Policy violation → Audit finding
- **Mitigation**: Automated scanning, configuration management, alerts

#### AV-8: Resource Exhaustion
**Threat**: DoS through connection/port exhaustion
- **Impact**: MEDIUM - Service disruption
- **Likelihood**: MEDIUM - Operational errors
- **Attack Chain**: Connection flood → Port exhaustion → Service failure
- **Mitigation**: Connection limits, port range management, monitoring

### 1.4 Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│ Internet (Untrusted)                                 │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ NSG Rules (Trust Boundary #1)
                   ▼
┌─────────────────────────────────────────────────────┐
│ Azure VNet (Partially Trusted)                       │
│  ├─ Bastion Subnet (More Trusted)                   │
│  └─ VM Subnets (Segmented)                          │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Bastion/VPN (Trust Boundary #2)
                   ▼
┌─────────────────────────────────────────────────────┐
│ VM Internal Network (Trusted)                        │
│  ├─ localhost (127.0.0.1) - Highly Trusted          │
│  └─ Private IPs - Trusted within VNet               │
└─────────────────────────────────────────────────────┘
                   │
                   │ File Permissions (Trust Boundary #3)
                   ▼
┌─────────────────────────────────────────────────────┐
│ Security Audit Logs (Protected)                      │
└─────────────────────────────────────────────────────┘
```

### 1.5 Risk Matrix

| Threat | Impact | Likelihood | Risk Level | Mitigation Priority |
|--------|--------|------------|------------|---------------------|
| AV-1: Network Exposure | Critical | High | **CRITICAL** | P0 - Immediate |
| AV-2: Bastion Hijacking | High | Medium | **HIGH** | P1 - Sprint 1 |
| AV-3: Credential Theft | Critical | Medium | **CRITICAL** | P0 - Immediate |
| AV-4: Log Tampering | High | Low | **MEDIUM** | P2 - Sprint 2 |
| AV-5: MITM | High | Low | **MEDIUM** | P2 - Sprint 2 |
| AV-6: Lateral Movement | High | Medium | **HIGH** | P1 - Sprint 1 |
| AV-7: Config Drift | Medium | High | **MEDIUM** | P2 - Sprint 2 |
| AV-8: Resource Exhaustion | Medium | Medium | **MEDIUM** | P2 - Sprint 2 |

---

## 2. Security Requirements

### 2.1 Authentication & Authorization

**REQ-AUTH-1**: All Azure operations MUST use Azure CLI authentication
- **Rationale**: Leverage Azure's built-in authentication
- **Implementation**: Delegate to `az` commands
- **Validation**: No hardcoded credentials in code

**REQ-AUTH-2**: SSH keys MUST be retrieved from Azure Key Vault
- **Rationale**: Centralized secret management
- **Implementation**: `az keyvault secret show` integration
- **Validation**: No SSH keys stored locally (except temp use)

**REQ-AUTH-3**: Bastion tunnels MUST require valid Azure credentials
- **Rationale**: Ensure authorized access
- **Implementation**: `az network bastion tunnel` validates credentials
- **Validation**: Authentication failure handling

### 2.2 Network Security

**REQ-NET-1**: All Bastion tunnels MUST bind to localhost (127.0.0.1) only
- **Rationale**: Prevent network-wide tunnel access
- **Implementation**: Enforce in BastionManager.create_tunnel()
- **Validation**: Port binding verification
- **Status**: ✅ IMPLEMENTED (bastion_manager.py:262, 401-404)

**REQ-NET-2**: NSG rules MUST deny all traffic by default
- **Rationale**: Fail-secure, explicit allow only
- **Implementation**: Template validation enforces deny-default
- **Validation**: Rule priority and action checks

**REQ-NET-3**: NSG templates MUST validate against security policies before application
- **Rationale**: Prevent misconfigurations
- **Implementation**: NSGValidator class with policy engine
- **Validation**: 100% template coverage requirement

**REQ-NET-4**: VMs SHOULD use Bastion for SSH access (no public IPs)
- **Rationale**: Minimize attack surface
- **Implementation**: Orchestrator prompts user, logs opt-outs
- **Validation**: Security audit logs
- **Status**: ✅ IMPLEMENTED (security_audit.py)

### 2.3 Data Protection

**REQ-DATA-1**: Audit logs MUST have 0600 permissions (owner-only)
- **Rationale**: Prevent unauthorized access
- **Implementation**: os.chmod() on log file creation
- **Validation**: File permission checks
- **Status**: ✅ IMPLEMENTED (security_audit.py:96)

**REQ-DATA-2**: Sensitive data MUST NOT be logged
- **Rationale**: Prevent credential exposure
- **Implementation**: _sanitize_tunnel_error() sanitizes errors
- **Validation**: Log content inspection
- **Status**: ✅ IMPLEMENTED (bastion_manager.py:83-105)

**REQ-DATA-3**: Network traffic between VMs SHOULD use private IPs
- **Rationale**: Avoid internet exposure
- **Implementation**: ComposeNetworkManager uses private IPs
- **Validation**: Network configuration checks
- **Status**: ✅ IMPLEMENTED (network.py)

### 2.4 Availability

**REQ-AVAIL-1**: Bastion tunnel failures MUST NOT crash application
- **Rationale**: Graceful degradation
- **Implementation**: Exception handling, error messages
- **Validation**: Error handling tests
- **Status**: ✅ IMPLEMENTED (bastion_manager.py exception handling)

**REQ-AVAIL-2**: Connection pooling MUST prevent port exhaustion
- **Rationale**: Service reliability
- **Implementation**: BastionConnectionPool with limits
- **Validation**: Connection limit enforcement

**REQ-AVAIL-3**: Tunnel cleanup MUST occur on process exit
- **Rationale**: Resource cleanup
- **Implementation**: atexit handlers, context managers
- **Validation**: Resource leak tests
- **Status**: ✅ IMPLEMENTED (bastion_manager.py:115, 117-123)

### 2.5 Audit & Compliance

**REQ-AUDIT-1**: Security decisions MUST be logged to audit trail
- **Rationale**: Accountability and compliance
- **Implementation**: SecurityAuditLogger class
- **Validation**: Audit log completeness
- **Status**: ✅ IMPLEMENTED (security_audit.py)

**REQ-AUDIT-2**: Audit logs MUST be tamper-evident
- **Rationale**: Integrity assurance
- **Implementation**: Append-only, checksums, remote backup
- **Validation**: Integrity verification

**REQ-AUDIT-3**: Security scans MUST identify critical findings before deployment
- **Rationale**: Proactive security
- **Implementation**: Azure Security Center integration
- **Validation**: Zero critical findings requirement

---

## 3. System Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     azlin CLI                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Resource Orchestrator                          │  │
│  │  • User interaction                                    │  │
│  │  • Cost transparency                                   │  │
│  │  • Dependency management                               │  │
│  └───────────────┬───────────────────────┬────────────────┘  │
│                  │                       │                    │
│  ┌───────────────▼──────────┐  ┌────────▼─────────────────┐ │
│  │   Bastion Manager         │  │  NSG Manager (NEW)       │ │
│  │  • Tunnel lifecycle       │  │  • Template validation   │ │
│  │  • Connection pooling     │  │  • Rule enforcement      │ │
│  │  • Health checking        │  │  • Policy compliance     │ │
│  └───────────────┬───────────┘  └────────┬─────────────────┘ │
│                  │                       │                    │
│  ┌───────────────▼───────────────────────▼─────────────────┐ │
│  │          Security Audit Logger (Enhanced)                │ │
│  │  • Comprehensive event logging                          │ │
│  │  • Tamper-proof storage                                 │ │
│  │  • Compliance reporting                                 │ │
│  └───────────────┬──────────────────────────────────────────┘ │
│                  │                                             │
└──────────────────┼─────────────────────────────────────────────┘
                   │
                   │ Azure CLI Delegation
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Azure Resources                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Bastion    │  │     NSGs     │  │  Security Center │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Key Vault   │  │     VNets    │  │  Private Endpts  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Security Layers

**Layer 1: Network Perimeter** (NSG Rules)
- Deny-by-default firewall rules
- IP whitelisting for administrative access
- DDoS protection through Azure

**Layer 2: Access Control** (Bastion/VPN)
- Centralized access through Bastion hosts
- VPN tunnels for remote access
- Private endpoints for Azure services

**Layer 3: Authentication** (Azure AD/Key Vault)
- Azure CLI authentication
- Key Vault for secret management
- MFA enforcement (delegated to Azure)

**Layer 4: Application Security** (Input Validation)
- VM resource ID validation
- Port number validation
- Template schema validation

**Layer 5: Audit & Monitoring** (Logging & Scanning)
- Security audit logging
- Azure Security Center integration
- Configuration drift detection

### 3.3 Data Flow - Secure VM Provisioning

```
User Command
    │
    ▼
┌─────────────────────────┐
│ Resource Orchestrator   │
│ • Ensure Bastion exists │
│ • Get user decisions    │
└───────┬─────────────────┘
        │
        ▼
┌─────────────────────────┐
│ NSG Manager             │
│ • Load template         │
│ • Validate rules        │
│ • Check policy          │ ──[FAIL]──> User Notification
│ • Apply NSG             │              Exit
└───────┬─────────────────┘
        │ [PASS]
        ▼
┌─────────────────────────┐
│ VM Provisioning         │
│ • Create VM             │
│ • No public IP          │
└───────┬─────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Bastion Manager         │
│ • Create tunnel         │
│ • Validate localhost    │
│ • Health check          │
└───────┬─────────────────┘
        │
        ▼
┌─────────────────────────┐
│ Security Audit Logger   │
│ • Log decisions         │
│ • Store secure (0600)   │
└─────────────────────────┘
        │
        ▼
User SSH Access via Bastion
```

---

## 4. NSG Template System

### 4.1 Design Overview

**Philosophy**: NSGs are the first line of defense. Misconfiguration is the #1 security risk. Template-based management with validation prevents human error.

**Key Features**:
- Template library for common scenarios (web server, database, etc.)
- Schema validation using JSON Schema
- Policy engine for security compliance
- Dry-run capability for testing
- Idempotent operations

### 4.2 Template Structure

```yaml
# templates/web-server-nsg.yaml
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

default_rules:
  outbound: "Allow"  # Allow all outbound by default
  inbound: "Deny"    # Deny all inbound by default
```

### 4.3 Validation Framework

**NSGValidator Class**:

```python
class NSGValidator:
    """Validates NSG templates against security policies."""

    def validate_template(self, template: Dict[str, Any]) -> ValidationResult:
        """
        Validate NSG template comprehensively.

        Checks:
        1. Schema validation (structure, types)
        2. Policy compliance (CIS, SOC2, etc.)
        3. Best practices (priority ranges, justifications)
        4. Conflict detection (overlapping rules)

        Returns:
            ValidationResult with findings
        """

    def check_deny_default(self, template: Dict[str, Any]) -> bool:
        """Verify deny-by-default rule exists with lowest priority."""

    def check_dangerous_rules(self, template: Dict[str, Any]) -> List[Finding]:
        """
        Flag dangerous rules:
        - Wildcard source + sensitive port (SSH, RDP)
        - Unrestricted administrative access
        - Overly broad CIDR ranges
        """

    def check_policy_compliance(self, template: Dict[str, Any]) -> List[str]:
        """Map rules to compliance requirements (CIS, SOC2, ISO27001)."""
```

**Policy Engine**:

```python
class SecurityPolicy:
    """Security policy rules for NSG validation."""

    FORBIDDEN_RULES = [
        {
            "name": "no-ssh-from-internet",
            "condition": lambda rule: (
                rule["destination_port_range"] == "22" and
                rule["source_address_prefix"] == "Internet" and
                rule["access"] == "Allow"
            ),
            "severity": "CRITICAL",
            "message": "SSH must not be exposed to internet. Use Bastion instead."
        },
        {
            "name": "no-rdp-from-internet",
            "condition": lambda rule: (
                rule["destination_port_range"] == "3389" and
                rule["source_address_prefix"] == "Internet" and
                rule["access"] == "Allow"
            ),
            "severity": "CRITICAL",
            "message": "RDP must not be exposed to internet."
        }
    ]

    REQUIRED_RULES = [
        {
            "name": "deny-default-inbound",
            "condition": lambda rules: any(
                rule["priority"] == 4096 and
                rule["direction"] == "Inbound" and
                rule["access"] == "Deny"
                for rule in rules
            ),
            "severity": "CRITICAL",
            "message": "NSG must have deny-all default rule for inbound traffic."
        }
    ]
```

### 4.4 NSG Manager Implementation

```python
class NSGManager:
    """Manage Azure Network Security Groups with validation."""

    def __init__(self, validator: NSGValidator):
        self.validator = validator

    def apply_template(
        self,
        template_path: str,
        nsg_name: str,
        resource_group: str,
        dry_run: bool = True
    ) -> ApplicationResult:
        """
        Apply NSG template to Azure resource.

        Steps:
        1. Load and parse template
        2. Validate against policies
        3. Check for critical findings (fail if any)
        4. Display planned changes (dry-run)
        5. Apply changes (if approved)
        6. Log to audit trail
        """

    def compare_nsg(self, template_path: str, nsg_name: str) -> ComparisonResult:
        """Compare template against existing NSG (detect drift)."""

    def generate_template_from_nsg(self, nsg_name: str) -> str:
        """Export existing NSG to template format."""
```

### 4.5 Template Library

**Standard Templates**:

1. **locked-down-vm.yaml** - Bastion-only access, no inbound internet
2. **web-server-nsg.yaml** - HTTPS/HTTP allowed, SSH via Bastion
3. **database-nsg.yaml** - Private VNet access only, no internet
4. **nat-gateway-nsg.yaml** - Outbound internet, no inbound
5. **internal-service-nsg.yaml** - VNet-internal communication only

**Template Selection Guide**:
- User provides workload type → System suggests template
- Templates are starting points (user can customize)
- All customizations validated before application

---

## 5. Bastion Security Enhancements

### 5.1 Current Implementation Analysis

**Existing Security Features** (bastion_manager.py):
- ✅ Localhost-only binding (127.0.0.1)
- ✅ Ephemeral port allocation (50000-60000)
- ✅ Process cleanup (atexit handlers)
- ✅ No shell=True in subprocess
- ✅ Input validation (VM resource IDs, ports)
- ✅ Error sanitization (_sanitize_tunnel_error)
- ✅ Timeout protection (threading-based)
- ✅ Health checking (socket connection tests)

**Gaps Identified**:
- ❌ No connection pooling (new tunnel per connection)
- ❌ No tunnel reuse (wasteful resource usage)
- ❌ No connection limits (port exhaustion risk)
- ❌ No idle timeout (leaked resources)
- ❌ No centralized tunnel management

### 5.2 Connection Pooling Design

**Philosophy**: Bastion tunnels are expensive to establish (10-30s). Reuse tunnels when possible, enforce limits to prevent resource exhaustion.

**BastionConnectionPool Class**:

```python
@dataclass
class PooledTunnel:
    """Tunnel with pool management metadata."""
    tunnel: BastionTunnel
    created_at: datetime
    last_used: datetime
    use_count: int = 0
    idle_timeout: int = 300  # 5 minutes default

    def is_expired(self) -> bool:
        """Check if tunnel exceeded idle timeout."""
        return (datetime.now() - self.last_used).seconds > self.idle_timeout

    def is_healthy(self, manager: BastionManager) -> bool:
        """Verify tunnel is still active and healthy."""
        return manager.check_tunnel_health(self.tunnel)


class BastionConnectionPool:
    """Manage pool of reusable Bastion tunnels.

    Features:
    - Tunnel reuse based on (bastion, vm, remote_port)
    - Idle timeout cleanup
    - Connection limits
    - Health monitoring
    - Thread-safe operations
    """

    DEFAULT_MAX_TUNNELS = 10
    DEFAULT_IDLE_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        bastion_manager: BastionManager,
        max_tunnels: int = DEFAULT_MAX_TUNNELS,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT
    ):
        self.manager = bastion_manager
        self.max_tunnels = max_tunnels
        self.idle_timeout = idle_timeout
        self.pool: Dict[Tuple[str, str, int], PooledTunnel] = {}
        self._lock = threading.Lock()

    def get_or_create_tunnel(
        self,
        bastion_name: str,
        resource_group: str,
        target_vm_id: str,
        remote_port: int = 22
    ) -> PooledTunnel:
        """
        Get existing tunnel from pool or create new one.

        Logic:
        1. Check pool for existing tunnel with matching key
        2. Verify tunnel is healthy
        3. If healthy, update last_used and return
        4. If unhealthy or missing, create new tunnel
        5. Enforce max_tunnels limit (evict oldest idle tunnel)
        """
        with self._lock:
            key = (bastion_name, target_vm_id, remote_port)

            # Check for existing tunnel
            if key in self.pool:
                pooled = self.pool[key]

                # Verify health
                if pooled.is_healthy(self.manager):
                    pooled.last_used = datetime.now()
                    pooled.use_count += 1
                    logger.info(f"Reusing tunnel {key} (use_count={pooled.use_count})")
                    return pooled
                else:
                    # Unhealthy - remove and recreate
                    logger.warning(f"Tunnel {key} unhealthy, recreating")
                    self.manager.close_tunnel(pooled.tunnel)
                    del self.pool[key]

            # Create new tunnel
            if len(self.pool) >= self.max_tunnels:
                self._evict_idle_tunnel()

            local_port = self.manager.get_available_port()
            tunnel = self.manager.create_tunnel(
                bastion_name=bastion_name,
                resource_group=resource_group,
                target_vm_id=target_vm_id,
                local_port=local_port,
                remote_port=remote_port
            )

            pooled = PooledTunnel(
                tunnel=tunnel,
                created_at=datetime.now(),
                last_used=datetime.now(),
                idle_timeout=self.idle_timeout
            )

            self.pool[key] = pooled
            logger.info(f"Created new tunnel {key} (pool_size={len(self.pool)})")
            return pooled

    def _evict_idle_tunnel(self) -> None:
        """Evict oldest idle tunnel to make room for new connection."""
        # Find oldest by last_used
        oldest_key = min(self.pool.keys(), key=lambda k: self.pool[k].last_used)
        oldest = self.pool[oldest_key]

        logger.info(f"Evicting idle tunnel {oldest_key} (idle for {oldest.idle_timeout}s)")
        self.manager.close_tunnel(oldest.tunnel)
        del self.pool[oldest_key]

    def cleanup_expired(self) -> int:
        """Remove all expired tunnels from pool."""
        expired = [
            key for key, pooled in self.pool.items()
            if pooled.is_expired()
        ]

        for key in expired:
            logger.info(f"Cleaning up expired tunnel {key}")
            self.manager.close_tunnel(self.pool[key].tunnel)
            del self.pool[key]

        return len(expired)

    def close_all(self) -> None:
        """Close all tunnels in pool."""
        with self._lock:
            for pooled in self.pool.values():
                self.manager.close_tunnel(pooled.tunnel)
            self.pool.clear()
```

**Usage Example**:

```python
# Instead of creating new tunnel each time:
manager = BastionManager()
tunnel = manager.create_tunnel(...)  # 15 seconds

# Use connection pool:
pool = BastionConnectionPool(manager)
pooled = pool.get_or_create_tunnel(...)  # 15 seconds first time
pooled = pool.get_or_create_tunnel(...)  # <1 second on reuse!
```

### 5.3 Automatic Cleanup Enhancements

**Background Cleanup Thread**:

```python
class BastionCleanupDaemon:
    """Background daemon for tunnel maintenance."""

    def __init__(self, pool: BastionConnectionPool, interval: int = 60):
        self.pool = pool
        self.interval = interval
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start cleanup daemon."""
        if self.running:
            return

        self.running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info("Bastion cleanup daemon started")

    def stop(self) -> None:
        """Stop cleanup daemon."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Bastion cleanup daemon stopped")

    def _cleanup_loop(self) -> None:
        """Periodic cleanup of expired tunnels."""
        while self.running:
            try:
                expired_count = self.pool.cleanup_expired()
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired tunnel(s)")
            except Exception as e:
                logger.error(f"Cleanup daemon error: {e}")

            time.sleep(self.interval)
```

### 5.4 Enhanced Security Controls

**Additional Validations**:

```python
def _validate_localhost_binding(self, tunnel: BastionTunnel) -> None:
    """
    Verify tunnel is bound to localhost only.

    Security Critical: Prevents network-wide tunnel access.
    """
    try:
        # Attempt connection from non-localhost IP (should fail)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)

        # Try to connect from different interface
        # If this succeeds, tunnel is not localhost-only
        sock.connect(("0.0.0.0", tunnel.local_port))
        sock.close()

        # Should not reach here
        raise BastionManagerError(
            f"SECURITY VIOLATION: Tunnel {tunnel.local_port} is not localhost-only"
        )
    except (ConnectionRefusedError, OSError):
        # Expected - tunnel is properly restricted to localhost
        pass
```

**Connection Limits**:

```python
def enforce_connection_limit(self, max_connections: int = 50) -> None:
    """
    Enforce maximum concurrent Bastion connections.

    Prevents:
    - Port exhaustion
    - Resource exhaustion
    - Potential DoS scenarios
    """
    if len(self.pool) >= max_connections:
        raise BastionManagerError(
            f"Connection limit reached ({max_connections}). "
            f"Close unused tunnels or increase limit."
        )
```

---

## 6. Audit Logging System

### 6.1 Current Implementation Analysis

**Existing Features** (security_audit.py):
- ✅ Logs Bastion opt-out decisions
- ✅ Secure file permissions (0600)
- ✅ JSON format (machine-readable)
- ✅ Timestamps (UTC)
- ✅ User attribution

**Gaps Identified**:
- ❌ Only logs Bastion opt-outs (incomplete coverage)
- ❌ No log integrity verification
- ❌ No remote backup
- ❌ No compliance reporting
- ❌ No log rotation
- ❌ No structured query interface

### 6.2 Enhanced Audit Logging Design

**Philosophy**: Comprehensive audit logging is essential for security accountability and compliance. Every security-sensitive operation must be logged.

**SecurityAuditLogger Enhancement**:

```python
class AuditEventType(str, Enum):
    """Types of security events to audit."""
    BASTION_OPT_OUT = "bastion_opt_out"
    BASTION_TUNNEL_CREATE = "bastion_tunnel_create"
    BASTION_TUNNEL_CLOSE = "bastion_tunnel_close"
    NSG_RULE_APPLY = "nsg_rule_apply"
    NSG_RULE_MODIFY = "nsg_rule_modify"
    NSG_RULE_DELETE = "nsg_rule_delete"
    NSG_VALIDATION_FAIL = "nsg_validation_fail"
    CREDENTIAL_ACCESS = "credential_access"
    PUBLIC_IP_ASSIGN = "public_ip_assign"
    SECURITY_SCAN_FAIL = "security_scan_fail"
    POLICY_VIOLATION = "policy_violation"
    CONFIGURATION_DRIFT = "configuration_drift"


@dataclass
class AuditEvent:
    """Structured security audit event."""
    event_id: str  # UUID
    timestamp: datetime
    event_type: AuditEventType
    user: str
    resource: str  # VM, NSG, etc.
    action: str
    outcome: str  # "success" or "failure"
    details: Dict[str, Any]
    severity: str  # "info", "warning", "critical"
    compliance_tags: List[str]  # ["CIS-6.1", "SOC2-CC6.6"]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "event_type": self.event_type,
            "user": self.user,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "details": self.details,
            "severity": self.severity,
            "compliance_tags": self.compliance_tags
        }


class SecurityAuditLogger:
    """Enhanced security audit logging with integrity verification."""

    AUDIT_FILE = Path.home() / ".azlin" / "security_audit.jsonl"  # JSONL format
    BACKUP_DIR = Path.home() / ".azlin" / "audit_backups"

    def __init__(self):
        self._ensure_audit_structure()

    def _ensure_audit_structure(self) -> None:
        """Create audit directory structure with secure permissions."""
        self.AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Set directory permissions (owner-only)
        os.chmod(self.AUDIT_FILE.parent, 0o700)
        os.chmod(self.BACKUP_DIR, 0o700)

    def log_event(self, event: AuditEvent) -> None:
        """
        Log security event to audit trail.

        Features:
        - Append-only writes (no modifications)
        - Integrity checksum
        - Automatic backup
        """
        # Add integrity checksum
        event_dict = event.to_dict()
        event_dict["checksum"] = self._compute_checksum(event_dict)

        # Append to audit log (JSONL format)
        with open(self.AUDIT_FILE, "a") as f:
            f.write(json.dumps(event_dict) + "\n")

        # Set secure permissions
        os.chmod(self.AUDIT_FILE, 0o600)

        # Backup periodically
        if self._should_backup():
            self._backup_audit_log()

    def _compute_checksum(self, event_dict: Dict[str, Any]) -> str:
        """Compute integrity checksum for event."""
        # Exclude checksum field itself
        event_copy = {k: v for k, v in event_dict.items() if k != "checksum"}
        event_json = json.dumps(event_copy, sort_keys=True)
        return hashlib.sha256(event_json.encode()).hexdigest()

    def verify_integrity(self) -> Tuple[bool, List[str]]:
        """
        Verify audit log integrity.

        Returns:
            (is_valid, list_of_corrupted_event_ids)
        """
        if not self.AUDIT_FILE.exists():
            return True, []

        corrupted = []

        with open(self.AUDIT_FILE) as f:
            for line_num, line in enumerate(f, 1):
                try:
                    event = json.loads(line)
                    stored_checksum = event.get("checksum")
                    computed_checksum = self._compute_checksum(event)

                    if stored_checksum != computed_checksum:
                        corrupted.append(event.get("event_id", f"line_{line_num}"))

                except json.JSONDecodeError:
                    corrupted.append(f"line_{line_num}")

        return len(corrupted) == 0, corrupted

    def _should_backup(self) -> bool:
        """Determine if audit log should be backed up."""
        # Backup daily
        if not self.AUDIT_FILE.exists():
            return False

        file_age = time.time() - os.path.getmtime(self.AUDIT_FILE)
        return file_age > 86400  # 24 hours

    def _backup_audit_log(self) -> None:
        """Create timestamped backup of audit log."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.BACKUP_DIR / f"security_audit_{timestamp}.jsonl"

        shutil.copy2(self.AUDIT_FILE, backup_path)
        os.chmod(backup_path, 0o600)

        logger.info(f"Audit log backed up to {backup_path}")

    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        user: Optional[str] = None,
        resource: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[str] = None
    ) -> List[AuditEvent]:
        """Query audit events with filters."""
        events = []

        if not self.AUDIT_FILE.exists():
            return events

        with open(self.AUDIT_FILE) as f:
            for line in f:
                event_dict = json.loads(line)

                # Apply filters
                if event_type and event_dict["event_type"] != event_type:
                    continue
                if user and event_dict["user"] != user:
                    continue
                if resource and event_dict["resource"] != resource:
                    continue
                if severity and event_dict["severity"] != severity:
                    continue

                # Parse timestamp
                event_time = datetime.fromisoformat(
                    event_dict["timestamp"].replace("Z", "+00:00")
                )
                if start_time and event_time < start_time:
                    continue
                if end_time and event_time > end_time:
                    continue

                events.append(AuditEvent(**event_dict))

        return events

    def generate_compliance_report(
        self,
        framework: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Generate compliance report for audits.

        Args:
            framework: "CIS", "SOC2", or "ISO27001"
            start_date: Report start date
            end_date: Report end date

        Returns:
            Structured compliance report
        """
        events = self.query_events(start_time=start_date, end_time=end_date)

        # Filter by compliance tags
        relevant_events = [
            e for e in events
            if any(framework in tag for tag in e.compliance_tags)
        ]

        report = {
            "framework": framework,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_events": len(relevant_events),
            "critical_findings": len([e for e in relevant_events if e.severity == "critical"]),
            "policy_violations": len([e for e in relevant_events if e.event_type == AuditEventType.POLICY_VIOLATION]),
            "events_by_type": self._count_by_field(relevant_events, "event_type"),
            "events_by_user": self._count_by_field(relevant_events, "user"),
            "events_by_severity": self._count_by_field(relevant_events, "severity")
        }

        return report
```

### 6.3 Audit Events to Log

| Event Type | When to Log | Severity | Compliance Tags |
|------------|-------------|----------|-----------------|
| `bastion_opt_out` | User opts out of Bastion | WARNING | CIS-6.1, SOC2-CC6.6 |
| `bastion_tunnel_create` | Bastion tunnel created | INFO | SOC2-CC6.6 |
| `bastion_tunnel_close` | Bastion tunnel closed | INFO | SOC2-CC6.6 |
| `nsg_rule_apply` | NSG rule applied | INFO | CIS-6.2, ISO27001-A.13.1 |
| `nsg_rule_modify` | NSG rule modified | WARNING | CIS-6.2, SOC2-CC6.6 |
| `nsg_rule_delete` | NSG rule deleted | WARNING | CIS-6.2, SOC2-CC6.6 |
| `nsg_validation_fail` | NSG validation fails | CRITICAL | CIS-6.2, SOC2-CC6.7 |
| `credential_access` | Key Vault access | INFO | SOC2-CC6.1 |
| `public_ip_assign` | Public IP assigned to VM | WARNING | CIS-6.1 |
| `security_scan_fail` | Security scan finds issues | CRITICAL | SOC2-CC7.2 |
| `policy_violation` | Security policy violated | CRITICAL | All frameworks |
| `configuration_drift` | Detected config drift | WARNING | CIS-6.4, SOC2-CC8.1 |

### 6.4 Usage Examples

```python
# Log NSG rule application
logger = SecurityAuditLogger()
event = AuditEvent(
    event_id=str(uuid.uuid4()),
    timestamp=datetime.now(UTC),
    event_type=AuditEventType.NSG_RULE_APPLY,
    user=os.getenv("USER"),
    resource="web-server-nsg",
    action="apply_template",
    outcome="success",
    details={
        "template": "web-server-nsg.yaml",
        "rules_applied": 5,
        "resource_group": "prod-rg"
    },
    severity="info",
    compliance_tags=["CIS-6.2", "ISO27001-A.13.1"]
)
logger.log_event(event)

# Query critical events
critical_events = logger.query_events(
    severity="critical",
    start_time=datetime.now() - timedelta(days=30)
)

# Generate SOC2 compliance report
report = logger.generate_compliance_report(
    framework="SOC2",
    start_date=datetime(2025, 11, 1),
    end_date=datetime(2025, 11, 30)
)
```

---

## 7. Vulnerability Scanning Integration

### 7.1 Azure Security Center Integration

**Philosophy**: Proactive security through automated scanning. Identify vulnerabilities before they're exploited.

**Key Features**:
- Integration with Azure Security Center (Microsoft Defender for Cloud)
- Pre-deployment security validation
- Continuous configuration scanning
- Automated remediation recommendations

### 7.2 SecurityScanner Class

```python
class ScanSeverity(str, Enum):
    """Security finding severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityFinding:
    """Security scan finding."""
    finding_id: str
    severity: ScanSeverity
    category: str  # "network", "identity", "data", etc.
    resource: str
    title: str
    description: str
    remediation: str
    compliance_impact: List[str]

    def is_blocking(self) -> bool:
        """Check if finding blocks deployment."""
        return self.severity in [ScanSeverity.CRITICAL, ScanSeverity.HIGH]


class SecurityScanner:
    """Integrate with Azure Security Center for vulnerability scanning."""

    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id

    def scan_nsg(self, nsg_name: str, resource_group: str) -> List[SecurityFinding]:
        """
        Scan NSG for security issues using Azure Security Center.

        Checks:
        - Overly permissive rules
        - Missing deny-default rules
        - Exposed management ports
        - Compliance violations
        """
        findings = []

        # Get NSG configuration
        cmd = [
            "az", "network", "nsg", "show",
            "--name", nsg_name,
            "--resource-group", resource_group
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SecurityScannerError(f"Failed to retrieve NSG: {result.stderr}")

        nsg_config = json.loads(result.stdout)

        # Query Azure Security Center for recommendations
        findings.extend(self._query_security_center(nsg_config["id"]))

        # Perform local validation
        findings.extend(self._local_nsg_validation(nsg_config))

        return findings

    def _query_security_center(self, resource_id: str) -> List[SecurityFinding]:
        """Query Azure Security Center for security recommendations."""
        findings = []

        # Use Azure CLI to get security assessments
        cmd = [
            "az", "security", "assessment", "list",
            "--query", f"[?resourceDetails.id=='{resource_id}']"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Security Center query failed: {result.stderr}")
            return findings

        assessments = json.loads(result.stdout)

        for assessment in assessments:
            # Convert to SecurityFinding
            finding = SecurityFinding(
                finding_id=assessment["id"],
                severity=self._map_severity(assessment["status"]["severity"]),
                category=assessment["resourceDetails"]["resourceType"],
                resource=resource_id,
                title=assessment["displayName"],
                description=assessment["description"],
                remediation=assessment.get("remediation", "No remediation available"),
                compliance_impact=assessment.get("complianceRelevance", [])
            )
            findings.append(finding)

        return findings

    def _local_nsg_validation(self, nsg_config: Dict[str, Any]) -> List[SecurityFinding]:
        """Perform local validation of NSG rules."""
        findings = []

        security_rules = nsg_config.get("securityRules", [])

        # Check for wildcard SSH/RDP rules
        for rule in security_rules:
            if (rule["destinationPortRange"] in ["22", "3389"] and
                rule["sourceAddressPrefix"] == "*" and
                rule["access"] == "Allow"):

                findings.append(SecurityFinding(
                    finding_id=f"local-{rule['name']}",
                    severity=ScanSeverity.CRITICAL,
                    category="network",
                    resource=nsg_config["id"],
                    title=f"Management port exposed to internet: {rule['name']}",
                    description=(
                        f"Rule '{rule['name']}' allows {rule['destinationPortRange']} "
                        f"from any source. This exposes management interface to attacks."
                    ),
                    remediation="Restrict source to specific IP ranges or use Azure Bastion",
                    compliance_impact=["CIS-6.1", "SOC2-CC6.6"]
                ))

        # Check for deny-default rule
        has_deny_default = any(
            rule["priority"] == 4096 and
            rule["direction"] == "Inbound" and
            rule["access"] == "Deny"
            for rule in security_rules
        )

        if not has_deny_default:
            findings.append(SecurityFinding(
                finding_id="local-missing-deny-default",
                severity=ScanSeverity.HIGH,
                category="network",
                resource=nsg_config["id"],
                title="Missing deny-all default rule",
                description="NSG does not have explicit deny-all rule for inbound traffic",
                remediation="Add deny-all rule with priority 4096",
                compliance_impact=["CIS-6.2"]
            ))

        return findings

    def scan_vm(self, vm_name: str, resource_group: str) -> List[SecurityFinding]:
        """Scan VM for security issues."""
        findings = []

        # Get VM configuration
        cmd = [
            "az", "vm", "show",
            "--name", vm_name,
            "--resource-group", resource_group
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SecurityScannerError(f"Failed to retrieve VM: {result.stderr}")

        vm_config = json.loads(result.stdout)

        # Check for public IP
        if "publicIpAddress" in vm_config:
            findings.append(SecurityFinding(
                finding_id=f"vm-public-ip-{vm_name}",
                severity=ScanSeverity.HIGH,
                category="network",
                resource=vm_config["id"],
                title="VM has public IP address",
                description=f"VM '{vm_name}' has public IP, increasing attack surface",
                remediation="Use Azure Bastion for SSH access instead of public IP",
                compliance_impact=["CIS-6.1", "SOC2-CC6.6"]
            ))

        # Query Security Center for VM-specific findings
        findings.extend(self._query_security_center(vm_config["id"]))

        return findings

    def pre_deployment_scan(
        self,
        resource_group: str,
        template: Dict[str, Any]
    ) -> Tuple[bool, List[SecurityFinding]]:
        """
        Scan resources before deployment.

        Returns:
            (can_deploy, findings)
            can_deploy is False if any CRITICAL findings exist
        """
        findings = []

        # Scan NSGs in template
        for resource in template.get("resources", []):
            if resource["type"] == "Microsoft.Network/networkSecurityGroups":
                # Validate NSG before deployment
                validator = NSGValidator()
                validation_result = validator.validate_template(resource)

                for issue in validation_result.critical_issues:
                    findings.append(SecurityFinding(
                        finding_id=f"pre-deploy-{resource['name']}",
                        severity=ScanSeverity.CRITICAL,
                        category="network",
                        resource=resource["name"],
                        title=issue["title"],
                        description=issue["description"],
                        remediation=issue["remediation"],
                        compliance_impact=issue.get("compliance_impact", [])
                    ))

        # Determine if deployment should proceed
        critical_findings = [f for f in findings if f.severity == ScanSeverity.CRITICAL]
        can_deploy = len(critical_findings) == 0

        return can_deploy, findings
```

### 7.3 Integration with Deployment Workflow

```python
def deploy_with_security_scan(
    resource_group: str,
    template_path: str
) -> None:
    """Deploy resources with pre-deployment security scan."""

    # Load template
    with open(template_path) as f:
        template = json.load(f)

    # Run security scan
    scanner = SecurityScanner(subscription_id=get_subscription_id())
    can_deploy, findings = scanner.pre_deployment_scan(resource_group, template)

    # Display findings
    if findings:
        print("\n🔍 Security Scan Results:")
        for finding in findings:
            icon = "🚨" if finding.severity == ScanSeverity.CRITICAL else "⚠️"
            print(f"{icon} [{finding.severity.upper()}] {finding.title}")
            print(f"   {finding.description}")
            print(f"   Remediation: {finding.remediation}\n")

    # Check if deployment can proceed
    if not can_deploy:
        print("❌ Deployment blocked due to CRITICAL security findings.")
        print("   Fix issues above before deploying.")
        sys.exit(1)

    # Log scan results
    audit_logger = SecurityAuditLogger()
    audit_logger.log_event(AuditEvent(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC),
        event_type=AuditEventType.SECURITY_SCAN_FAIL if not can_deploy else "security_scan_pass",
        user=os.getenv("USER"),
        resource=resource_group,
        action="pre_deployment_scan",
        outcome="blocked" if not can_deploy else "passed",
        details={"findings_count": len(findings), "critical_count": len([f for f in findings if f.severity == ScanSeverity.CRITICAL])},
        severity="critical" if not can_deploy else "info",
        compliance_tags=["SOC2-CC7.2"]
    ))

    # Proceed with deployment
    print("✅ Security scan passed. Proceeding with deployment...")
    deploy_template(resource_group, template_path)
```

---

## 8. VPN and Private Endpoint Configuration

### 8.1 VPN Gateway Management

**Use Case**: Remote access for development teams without exposing VMs to internet.

**VPNManager Class**:

```python
class VPNManager:
    """Manage Azure VPN Gateway configuration."""

    def __init__(self, resource_group: str):
        self.resource_group = resource_group

    def create_point_to_site_vpn(
        self,
        vnet_name: str,
        vpn_gateway_name: str,
        address_pool: str = "172.16.0.0/24"
    ) -> str:
        """
        Create Point-to-Site VPN for remote access.

        Args:
            vnet_name: Virtual network for VPN
            vpn_gateway_name: Name for VPN gateway
            address_pool: Client address pool (CIDR)

        Returns:
            VPN gateway resource ID
        """
        # Create VPN gateway subnet
        gateway_subnet_cmd = [
            "az", "network", "vnet", "subnet", "create",
            "--name", "GatewaySubnet",
            "--vnet-name", vnet_name,
            "--resource-group", self.resource_group,
            "--address-prefixes", "10.0.255.0/27"
        ]

        subprocess.run(gateway_subnet_cmd, check=True)

        # Create VPN gateway (takes ~30-45 minutes)
        gateway_cmd = [
            "az", "network", "vnet-gateway", "create",
            "--name", vpn_gateway_name,
            "--resource-group", self.resource_group,
            "--vnet", vnet_name,
            "--gateway-type", "Vpn",
            "--vpn-type", "RouteBased",
            "--sku", "VpnGw1",
            "--no-wait"
        ]

        subprocess.run(gateway_cmd, check=True)

        # Configure P2S VPN
        p2s_cmd = [
            "az", "network", "vnet-gateway", "update",
            "--name", vpn_gateway_name,
            "--resource-group", self.resource_group,
            "--client-protocol", "OpenVPN",
            "--address-prefixes", address_pool
        ]

        subprocess.run(p2s_cmd, check=True)

        logger.info(f"VPN gateway '{vpn_gateway_name}' created (provisioning in background)")

        return self._get_gateway_id(vpn_gateway_name)

    def generate_vpn_client_config(self, vpn_gateway_name: str) -> str:
        """Generate VPN client configuration package."""
        cmd = [
            "az", "network", "vnet-gateway", "vpn-client", "generate",
            "--name", vpn_gateway_name,
            "--resource-group", self.resource_group,
            "--processor-architecture", "Amd64"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        config_url = result.stdout.strip().strip('"')

        logger.info(f"VPN client config URL: {config_url}")
        return config_url
```

### 8.2 Private Endpoint Configuration

**Use Case**: Secure access to Azure services (Storage, Key Vault, etc.) without public endpoints.

**PrivateEndpointManager Class**:

```python
class PrivateEndpointManager:
    """Manage Azure Private Endpoints."""

    def create_private_endpoint(
        self,
        endpoint_name: str,
        resource_group: str,
        vnet_name: str,
        subnet_name: str,
        service_resource_id: str,
        group_id: str
    ) -> str:
        """
        Create private endpoint for Azure service.

        Args:
            endpoint_name: Private endpoint name
            resource_group: Resource group
            vnet_name: Virtual network
            subnet_name: Subnet for endpoint
            service_resource_id: Service resource ID (Storage, Key Vault, etc.)
            group_id: Sub-resource group (blob, vault, etc.)

        Returns:
            Private endpoint resource ID
        """
        # Disable private endpoint network policies on subnet
        disable_policies_cmd = [
            "az", "network", "vnet", "subnet", "update",
            "--name", subnet_name,
            "--vnet-name", vnet_name,
            "--resource-group", resource_group,
            "--disable-private-endpoint-network-policies", "true"
        ]

        subprocess.run(disable_policies_cmd, check=True)

        # Create private endpoint
        create_cmd = [
            "az", "network", "private-endpoint", "create",
            "--name", endpoint_name,
            "--resource-group", resource_group,
            "--vnet-name", vnet_name,
            "--subnet", subnet_name,
            "--private-connection-resource-id", service_resource_id,
            "--group-id", group_id,
            "--connection-name", f"{endpoint_name}-connection"
        ]

        subprocess.run(create_cmd, check=True)

        logger.info(f"Private endpoint '{endpoint_name}' created")

        return self._get_endpoint_id(endpoint_name, resource_group)

    def create_private_dns_zone(
        self,
        zone_name: str,
        resource_group: str,
        vnet_name: str
    ) -> None:
        """
        Create Private DNS zone for private endpoint name resolution.

        Example zones:
        - privatelink.blob.core.windows.net (Storage)
        - privatelink.vaultcore.azure.net (Key Vault)
        """
        # Create DNS zone
        create_zone_cmd = [
            "az", "network", "private-dns", "zone", "create",
            "--name", zone_name,
            "--resource-group", resource_group
        ]

        subprocess.run(create_zone_cmd, check=True)

        # Link DNS zone to VNet
        link_cmd = [
            "az", "network", "private-dns", "link", "vnet", "create",
            "--name", f"{vnet_name}-link",
            "--zone-name", zone_name,
            "--resource-group", resource_group,
            "--virtual-network", vnet_name,
            "--registration-enabled", "false"
        ]

        subprocess.run(link_cmd, check=True)

        logger.info(f"Private DNS zone '{zone_name}' created and linked to {vnet_name}")
```

### 8.3 Integration Example

```python
def setup_secure_network_infrastructure(
    resource_group: str,
    vnet_name: str,
    keyvault_name: str
) -> None:
    """Set up complete secure network infrastructure."""

    # 1. Create VPN for remote access
    vpn_manager = VPNManager(resource_group)
    vpn_gateway_id = vpn_manager.create_point_to_site_vpn(
        vnet_name=vnet_name,
        vpn_gateway_name=f"{vnet_name}-vpn-gateway"
    )

    # 2. Create private endpoint for Key Vault
    keyvault_id = get_keyvault_resource_id(keyvault_name, resource_group)

    pe_manager = PrivateEndpointManager()
    pe_id = pe_manager.create_private_endpoint(
        endpoint_name=f"{keyvault_name}-pe",
        resource_group=resource_group,
        vnet_name=vnet_name,
        subnet_name="private-endpoints",
        service_resource_id=keyvault_id,
        group_id="vault"
    )

    # 3. Create Private DNS zone
    pe_manager.create_private_dns_zone(
        zone_name="privatelink.vaultcore.azure.net",
        resource_group=resource_group,
        vnet_name=vnet_name
    )

    # 4. Log security configuration
    audit_logger = SecurityAuditLogger()
    audit_logger.log_event(AuditEvent(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(UTC),
        event_type="secure_network_setup",
        user=os.getenv("USER"),
        resource=vnet_name,
        action="setup_secure_infrastructure",
        outcome="success",
        details={
            "vpn_gateway": vpn_gateway_id,
            "private_endpoint": pe_id,
            "services_secured": ["KeyVault"]
        },
        severity="info",
        compliance_tags=["CIS-6.3", "SOC2-CC6.6"]
    ))

    print("✅ Secure network infrastructure configured")
```

---

## 9. Compliance Mappings

### 9.1 CIS Azure Foundations Benchmark

**Relevant Controls**:

| CIS Control | Requirement | azlin Implementation |
|-------------|-------------|---------------------|
| **6.1** | Ensure that RDP access is restricted from the internet | NSG templates block RDP (3389) from Internet, audit logging for opt-outs |
| **6.2** | Ensure that SSH access is restricted from the internet | NSG templates block SSH (22) from Internet, Bastion-only access |
| **6.3** | Ensure that Network Security Group Flow Log retention period is 'greater than 90 days' | NSG Manager enables flow logs with 90+ day retention |
| **6.4** | Ensure that Network Watcher is 'Enabled' | Network Watcher enabled by default in regions |
| **6.5** | Ensure that Azure Bastion is provisioned for secure remote access | Bastion provisioning workflow, security audit logging |

**Implementation Status**:
- ✅ 6.1 - IMPLEMENTED (NSG templates, validation)
- ✅ 6.2 - IMPLEMENTED (NSG templates, Bastion manager)
- 🚧 6.3 - PLANNED (NSG Manager enhancement)
- 🚧 6.4 - PLANNED (Network Watcher integration)
- ✅ 6.5 - IMPLEMENTED (Resource Orchestrator, Bastion Manager)

### 9.2 SOC 2 Trust Services Criteria

**Relevant Criteria**:

| TSC | Category | Requirement | azlin Implementation |
|-----|----------|-------------|---------------------|
| **CC6.1** | Logical Access | Restrict access to information assets | Key Vault integration, Azure AD authentication |
| **CC6.6** | Network Security | Restrict network access | NSG templates, Bastion tunnels, VPN configuration |
| **CC6.7** | Security Monitoring | Monitor security events | Security audit logging, Azure Security Center |
| **CC7.2** | Risk Assessment | Identify and assess threats | Vulnerability scanning, pre-deployment validation |
| **CC8.1** | Change Management | Track configuration changes | Configuration drift detection, audit logs |

**Implementation Status**:
- ✅ CC6.1 - IMPLEMENTED (Key Vault delegation)
- ✅ CC6.6 - IMPLEMENTED (NSG, Bastion, VPN managers)
- 🚧 CC6.7 - PARTIAL (audit logging exists, alerting planned)
- 🚧 CC7.2 - PLANNED (Security Scanner integration)
- 🚧 CC8.1 - PLANNED (drift detection)

### 9.3 ISO/IEC 27001:2013

**Relevant Controls**:

| Control | Category | Requirement | azlin Implementation |
|---------|----------|-------------|---------------------|
| **A.9.1** | Access Control Policy | Establish access control policy | NSG templates with policy enforcement |
| **A.9.4** | System Access Control | Restrict access to systems | Bastion-only SSH access, localhost binding |
| **A.12.4** | Logging and Monitoring | Log security events | Security audit logging with integrity verification |
| **A.13.1** | Network Security | Network controls | NSG rules, private endpoints, VPN gateways |
| **A.14.2** | Security in Development | Secure development practices | Template validation, pre-deployment scanning |

**Implementation Status**:
- ✅ A.9.1 - IMPLEMENTED (NSG policy engine)
- ✅ A.9.4 - IMPLEMENTED (Bastion Manager)
- 🚧 A.12.4 - PARTIAL (logging exists, alerting planned)
- ✅ A.13.1 - IMPLEMENTED (NSG, VPN, Private Endpoints)
- 🚧 A.14.2 - PLANNED (Security Scanner)

### 9.4 Compliance Reporting

**ComplianceReporter Class**:

```python
class ComplianceReporter:
    """Generate compliance reports for audits."""

    FRAMEWORKS = {
        "CIS": {
            "name": "CIS Azure Foundations Benchmark",
            "version": "1.4.0",
            "controls": ["6.1", "6.2", "6.3", "6.4", "6.5"]
        },
        "SOC2": {
            "name": "SOC 2 Trust Services Criteria",
            "version": "2017",
            "controls": ["CC6.1", "CC6.6", "CC6.7", "CC7.2", "CC8.1"]
        },
        "ISO27001": {
            "name": "ISO/IEC 27001:2013",
            "version": "2013",
            "controls": ["A.9.1", "A.9.4", "A.12.4", "A.13.1", "A.14.2"]
        }
    }

    def generate_report(
        self,
        framework: str,
        start_date: datetime,
        end_date: datetime,
        output_path: Path
    ) -> None:
        """Generate compliance report."""

        # Get audit events
        audit_logger = SecurityAuditLogger()
        events = audit_logger.query_events(start_time=start_date, end_time=end_date)

        # Filter by framework
        framework_events = [
            e for e in events
            if any(framework in tag for tag in e.compliance_tags)
        ]

        # Generate report
        report = {
            "framework": self.FRAMEWORKS[framework],
            "report_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_events": len(framework_events),
                "critical_findings": len([e for e in framework_events if e.severity == "critical"]),
                "policy_violations": len([e for e in framework_events if e.event_type == AuditEventType.POLICY_VIOLATION])
            },
            "events_by_control": self._group_by_control(framework_events),
            "recommendations": self._generate_recommendations(framework_events)
        }

        # Write report
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Compliance report written to {output_path}")
```

---

## 10. Implementation Roadmap

### Phase 1: NSG Automation (Sprint 1, Weeks 1-2)

**Priority**: P0 (CRITICAL - Addresses AV-1)

**Deliverables**:
1. NSG template schema and library
2. NSGValidator class with policy engine
3. NSGManager class for template application
4. Template library (5 standard templates)
5. Integration with Resource Orchestrator
6. Unit tests (100% coverage)
7. Integration tests with Azure CLI mocking

**Acceptance Criteria**:
- [ ] NSG templates validate against security policies
- [ ] Critical policy violations block deployment
- [ ] Template library covers common scenarios
- [ ] 100% template validation coverage
- [ ] Zero critical NSG misconfigurations possible

**Security Impact**: Prevents #1 security risk (network exposure)

---

### Phase 2: Bastion Connection Pooling (Sprint 1, Weeks 3-4)

**Priority**: P1 (HIGH - Addresses AV-2, AV-8)

**Deliverables**:
1. BastionConnectionPool class
2. PooledTunnel dataclass
3. BastionCleanupDaemon for background maintenance
4. Enhanced security validations (localhost enforcement)
5. Connection limit enforcement
6. Integration with existing BastionManager
7. Performance tests

**Acceptance Criteria**:
- [ ] Tunnels reused when possible (15s → <1s)
- [ ] Idle tunnels cleaned up automatically
- [ ] Connection limits prevent port exhaustion
- [ ] Localhost-only binding verified
- [ ] No tunnel leaks on exit

**Security Impact**: Prevents tunnel hijacking, resource exhaustion

---

### Phase 3: Enhanced Audit Logging (Sprint 2, Weeks 5-6)

**Priority**: P2 (MEDIUM - Addresses AV-4, AV-7)

**Deliverables**:
1. Enhanced SecurityAuditLogger class
2. AuditEvent dataclass with all event types
3. Integrity verification (checksums)
4. Audit log backup system
5. Query interface for audit logs
6. Compliance report generation
7. Integration with all security components

**Acceptance Criteria**:
- [ ] All security events logged
- [ ] Audit log integrity verifiable
- [ ] Tamper-proof storage (0600 permissions)
- [ ] Compliance reports generated for CIS, SOC2, ISO27001
- [ ] Zero critical findings in audit log review

**Security Impact**: Accountability, compliance, forensics

---

### Phase 4: Vulnerability Scanning (Sprint 2, Weeks 7-8)

**Priority**: P2 (MEDIUM - Addresses AV-7)

**Deliverables**:
1. SecurityScanner class
2. Azure Security Center integration
3. Pre-deployment validation
4. SecurityFinding dataclass
5. Automated remediation recommendations
6. Integration with deployment workflow
7. Scan result reporting

**Acceptance Criteria**:
- [ ] Pre-deployment scans complete in <30 seconds
- [ ] CRITICAL findings block deployment
- [ ] Scan results logged to audit trail
- [ ] Zero critical findings requirement enforced
- [ ] Remediation guidance provided

**Security Impact**: Proactive vulnerability identification

---

### Phase 5: VPN and Private Endpoints (Sprint 3, Weeks 9-10)

**Priority**: P3 (LOW - Addresses AV-5)

**Deliverables**:
1. VPNManager class
2. PrivateEndpointManager class
3. Private DNS zone configuration
4. VPN client config generation
5. Documentation for remote access setup
6. Integration with network provisioning workflow

**Acceptance Criteria**:
- [ ] Point-to-Site VPN configured
- [ ] Private endpoints created for Key Vault
- [ ] Private DNS resolution working
- [ ] VPN client configs generated
- [ ] Documentation complete

**Security Impact**: Secure remote access, private service connectivity

---

### Testing Strategy

**Unit Tests**:
- NSGValidator: Template validation, policy checks
- BastionConnectionPool: Pool management, eviction
- SecurityAuditLogger: Event logging, integrity checks
- SecurityScanner: Finding detection, severity mapping

**Integration Tests**:
- NSG template application end-to-end
- Bastion tunnel creation with pooling
- Audit log writing and querying
- Security scan with Azure CLI mocking

**Security Tests**:
- NSG misconfiguration attempts (should fail)
- Tunnel hijacking attempts (should fail)
- Audit log tampering attempts (should be detected)
- Port exhaustion scenarios (should be prevented)

**Compliance Tests**:
- CIS control validation
- SOC2 criteria verification
- ISO27001 control mapping

---

## Appendix A: Security Review Checklist

Use this checklist for security reviews:

### Network Security
- [ ] NSG rules deny by default
- [ ] No SSH/RDP exposed to internet
- [ ] Bastion used for VM access
- [ ] VPN configured for remote access
- [ ] Private endpoints for Azure services

### Authentication & Authorization
- [ ] Azure CLI authentication used
- [ ] No hardcoded credentials
- [ ] Key Vault for secret management
- [ ] Bastion tunnels require valid credentials

### Data Protection
- [ ] Audit logs have 0600 permissions
- [ ] Sensitive data not logged
- [ ] Private IPs used for inter-VM traffic
- [ ] Encrypted channels for all communications

### Availability
- [ ] Graceful error handling
- [ ] Connection pooling prevents exhaustion
- [ ] Tunnel cleanup on exit
- [ ] Health monitoring implemented

### Audit & Compliance
- [ ] Security decisions logged
- [ ] Audit logs tamper-evident
- [ ] Pre-deployment security scans
- [ ] Compliance reports generated

---

## Appendix B: Threat Mitigation Summary

| Threat | Mitigation | Implementation | Status |
|--------|-----------|----------------|--------|
| AV-1: Network Exposure | NSG templates with validation | NSGManager, NSGValidator | 🚧 Planned |
| AV-2: Bastion Hijacking | Localhost binding, pooling | BastionConnectionPool | 🚧 Planned |
| AV-3: Credential Theft | Key Vault integration | Existing (Azure CLI) | ✅ Implemented |
| AV-4: Log Tampering | 0600 permissions, checksums | SecurityAuditLogger | 🚧 Partial |
| AV-5: MITM | Private endpoints, VPN | VPNManager, PrivateEndpointManager | 🚧 Planned |
| AV-6: Lateral Movement | NSG segmentation | NSG templates | 🚧 Planned |
| AV-7: Config Drift | Security scanning, alerts | SecurityScanner | 🚧 Planned |
| AV-8: Resource Exhaustion | Connection limits | BastionConnectionPool | 🚧 Planned |

---

## Appendix C: Compliance Requirements Matrix

| Requirement | CIS | SOC2 | ISO27001 | Implementation |
|-------------|-----|------|----------|----------------|
| Restrict SSH from internet | 6.2 | CC6.6 | A.13.1 | NSG templates |
| Bastion for remote access | 6.5 | CC6.6 | A.9.4 | Bastion Manager |
| Security event logging | - | CC6.7 | A.12.4 | Security Audit Logger |
| Pre-deployment validation | - | CC7.2 | A.14.2 | Security Scanner |
| Configuration change tracking | - | CC8.1 | - | Audit logging |
| Network flow logs | 6.3 | - | A.13.1 | NSG Manager |
| Access control policy | - | CC6.1 | A.9.1 | NSG policy engine |

---

**END OF SPECIFICATION**

**Next Steps**:
1. Review and approve this security architecture
2. Begin Phase 1 implementation (NSG Automation)
3. Set up security testing infrastructure
4. Schedule compliance review meetings

**Security Contact**: Security Agent (via amplihack framework)
**Last Updated**: 2025-12-01
