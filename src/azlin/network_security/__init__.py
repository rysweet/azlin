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
from azlin.network_security.nsg_validator import (
    NSGValidator,
    ValidationResult,
    PolicyFinding,
    RuleSeverity,
)
from azlin.network_security.security_policy import SecurityPolicy
from azlin.network_security.bastion_connection_pool import (
    BastionConnectionPool,
    PooledTunnel,
    BastionCleanupDaemon,
)
from azlin.network_security.security_audit import (
    SecurityAuditLogger,
    AuditEvent,
    AuditEventType,
)
from azlin.network_security.security_scanner import (
    SecurityScanner,
    SecurityFinding,
    ScanSeverity,
    SecurityScannerError,
)
from azlin.network_security.vpn_manager import VPNManager, VPNManagerError
from azlin.network_security.private_endpoint_manager import (
    PrivateEndpointManager,
    PrivateEndpointManagerError,
)
from azlin.network_security.nsg_manager import NSGManager

__all__ = [
    # NSG Validation & Management
    "NSGValidator",
    "NSGManager",
    "SecurityPolicy",
    "ValidationResult",
    "PolicyFinding",
    "RuleSeverity",
    # Bastion Connection Pool
    "BastionConnectionPool",
    "PooledTunnel",
    "BastionCleanupDaemon",
    # Security Audit
    "SecurityAuditLogger",
    "AuditEvent",
    "AuditEventType",
    # Security Scanner
    "SecurityScanner",
    "SecurityFinding",
    "ScanSeverity",
    "SecurityScannerError",
    # VPN & Private Endpoints
    "VPNManager",
    "VPNManagerError",
    "PrivateEndpointManager",
    "PrivateEndpointManagerError",
]
