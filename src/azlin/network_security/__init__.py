"""Network Security Management System for azlin.

This package provides comprehensive network security management including:
- NSG template validation and policy enforcement
- Bastion connection pooling for tunnel reuse
- Enhanced security audit logging with integrity verification
- Vulnerability scanning integration with Azure Security Center
- VPN and Private Endpoint configuration

Philosophy:
- Security-first design with defense in depth
- Fail-secure defaults (deny by default)
- Comprehensive audit logging for accountability
- Ruthless simplicity in implementation

Public API:
    NSGValidator: Validate NSG templates against security policies
    SecurityPolicy: Security policy engine for NSG rules
    BastionConnectionPool: Manage reusable Bastion tunnels
    SecurityAuditLogger: Enhanced audit logging with integrity checks
    SecurityScanner: Vulnerability scanning integration
    VPNManager: VPN gateway configuration
    PrivateEndpointManager: Private endpoint management
"""

# Import all public APIs
from azlin.network_security.bastion_connection_pool import (
    BastionCleanupDaemon,
    BastionConnectionPool,
    PooledTunnel,
)
from azlin.network_security.nsg_manager import NSGManager
from azlin.network_security.nsg_validator import (
    NSGValidator,
    PolicyFinding,
    RuleSeverity,
    ValidationResult,
)
from azlin.network_security.private_endpoint_manager import (
    PrivateEndpointManager,
    PrivateEndpointManagerError,
)
from azlin.network_security.security_audit import (
    AuditEvent,
    AuditEventType,
    SecurityAuditLogger,
)
from azlin.network_security.security_policy import SecurityPolicy
from azlin.network_security.security_scanner import (
    ScanSeverity,
    SecurityFinding,
    SecurityScanner,
    SecurityScannerError,
)
from azlin.network_security.vpn_manager import VPNManager, VPNManagerError

__all__ = [
    # Security Audit
    "AuditEvent",
    "AuditEventType",
    # Bastion Connection Pool
    "BastionCleanupDaemon",
    "BastionConnectionPool",
    # NSG Validation & Management
    "NSGManager",
    "NSGValidator",
    "PolicyFinding",
    "PooledTunnel",
    # VPN & Private Endpoints
    "PrivateEndpointManager",
    "PrivateEndpointManagerError",
    "RuleSeverity",
    # Security Scanner
    "ScanSeverity",
    "SecurityAuditLogger",
    "SecurityFinding",
    "SecurityPolicy",
    "SecurityScanner",
    "SecurityScannerError",
    # VPN & Private Endpoints
    "VPNManager",
    "VPNManagerError",
    "ValidationResult",
]
