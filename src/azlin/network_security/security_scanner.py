"""Security Scanner with Azure Security Center Integration.

Proactive vulnerability scanning and security validation before deployment.
Integrates with Azure Security Center for comprehensive security assessment.

Key features:
- Pre-deployment security validation
- Azure Security Center integration
- Local NSG validation
- Severity-based blocking (CRITICAL/HIGH blocks deployment)
- Compliance impact reporting

Philosophy:
- Proactive: Scan before deploy
- Fail-secure: Critical findings block deployment
- Comprehensive: Multiple validation layers
- Actionable: Clear remediation guidance

Public API:
    SecurityScanner: Main scanner class
    SecurityFinding: Individual security finding
    ScanSeverity: Finding severity levels

Example:
    >>> scanner = SecurityScanner(subscription_id="...")
    >>> findings = scanner.scan_nsg("test-nsg", "test-rg")
    >>> critical = [f for f in findings if f.is_blocking()]
    >>> if critical:
    ...     print("Deployment blocked!")
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SecurityScannerError(Exception):
    """Raised when security scanning operations fail."""

    pass


class ScanSeverity(str, Enum):
    """Security finding severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityFinding:
    """Security scan finding.

    Represents a security vulnerability or misconfiguration found during scanning.
    """

    finding_id: str
    severity: ScanSeverity
    category: str  # "network", "identity", "data", etc.
    resource: str
    title: str
    description: str
    remediation: str
    compliance_impact: list[str]

    def is_blocking(self) -> bool:
        """Check if finding blocks deployment.

        Critical and High severity findings block deployment to prevent
        security vulnerabilities from being deployed to production.

        Returns:
            True if finding severity is CRITICAL or HIGH
        """
        return self.severity in [ScanSeverity.CRITICAL, ScanSeverity.HIGH]


class SecurityScanner:
    """Integrate with Azure Security Center for vulnerability scanning.

    Performs security scanning of Azure resources including:
    - NSG rules (overly permissive, missing deny-default)
    - VM configuration (public IPs, exposed ports)
    - Compliance violations

    Uses Azure CLI for all Azure operations.
    """

    def __init__(self, subscription_id: str):
        """Initialize security scanner.

        Args:
            subscription_id: Azure subscription ID
        """
        self.subscription_id = subscription_id

    def scan_nsg(self, nsg_name: str, resource_group: str) -> list[SecurityFinding]:
        """Scan NSG for security issues.

        Performs comprehensive NSG scanning including:
        1. Retrieve NSG configuration via Azure CLI
        2. Query Azure Security Center for recommendations
        3. Perform local validation checks

        Args:
            nsg_name: NSG name
            resource_group: Resource group name

        Returns:
            List of security findings

        Raises:
            SecurityScannerError: If NSG retrieval fails
        """
        findings = []

        # Get NSG configuration
        cmd = [
            "az",
            "network",
            "nsg",
            "show",
            "--name",
            nsg_name,
            "--resource-group",
            resource_group,
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

    def _query_security_center(self, resource_id: str) -> list[SecurityFinding]:
        """Query Azure Security Center for security recommendations.

        Args:
            resource_id: Azure resource ID

        Returns:
            List of security findings from Security Center
        """
        findings = []

        # Use Azure CLI to get security assessments
        cmd = [
            "az",
            "security",
            "assessment",
            "list",
            "--query",
            f"[?resourceDetails.id=='{resource_id}']",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Security Center query failed: {result.stderr}")
            return findings

        try:
            assessments = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Security Center response")
            return findings

        for assessment in assessments:
            # Convert to SecurityFinding
            finding = SecurityFinding(
                finding_id=assessment["id"],
                severity=self._map_severity(assessment["status"].get("severity", "Info")),
                category=assessment["resourceDetails"].get("resourceType", "unknown"),
                resource=resource_id,
                title=assessment.get("displayName", "Unknown issue"),
                description=assessment.get("description", "No description available"),
                remediation=assessment.get("remediation", "No remediation available"),
                compliance_impact=assessment.get("complianceRelevance", []),
            )
            findings.append(finding)

        return findings

    def _map_severity(self, azure_severity: str) -> ScanSeverity:
        """Map Azure Security Center severity to ScanSeverity.

        Args:
            azure_severity: Azure severity string

        Returns:
            ScanSeverity enum value
        """
        severity_map = {
            "Critical": ScanSeverity.CRITICAL,
            "High": ScanSeverity.HIGH,
            "Medium": ScanSeverity.MEDIUM,
            "Low": ScanSeverity.LOW,
            "Info": ScanSeverity.INFO,
            "Informational": ScanSeverity.INFO,
        }
        return severity_map.get(azure_severity, ScanSeverity.INFO)

    def _local_nsg_validation(self, nsg_config: dict[str, Any]) -> list[SecurityFinding]:
        """Perform local validation of NSG rules.

        This provides immediate feedback without waiting for Azure Security Center.

        Args:
            nsg_config: NSG configuration from Azure CLI

        Returns:
            List of security findings
        """
        findings = []

        security_rules = nsg_config.get("securityRules", [])

        # Check for wildcard SSH/RDP rules
        for rule in security_rules:
            dest_port = str(rule.get("destinationPortRange", ""))
            source_prefix = rule.get("sourceAddressPrefix", "")
            access = rule.get("access", "")
            direction = rule.get("direction", "")
            rule_name = rule.get("name", "unnamed")

            # Check for SSH from any source
            if (
                dest_port == "22"
                and source_prefix in ["*", "0.0.0.0/0", "Internet"]
                and access == "Allow"
                and direction == "Inbound"
            ):
                findings.append(
                    SecurityFinding(
                        finding_id=f"local-ssh-{rule_name}",
                        severity=ScanSeverity.CRITICAL,
                        category="network",
                        resource=nsg_config["id"],
                        title=f"SSH exposed to internet: {rule_name}",
                        description=f"Rule '{rule_name}' allows SSH (port 22) from any source. This exposes management interface to attacks.",
                        remediation="Restrict source to specific IP ranges or use Azure Bastion",
                        compliance_impact=["CIS-6.2", "SOC2-CC6.6"],
                    )
                )

            # Check for RDP from any source
            if (
                dest_port == "3389"
                and source_prefix in ["*", "0.0.0.0/0", "Internet"]
                and access == "Allow"
                and direction == "Inbound"
            ):
                findings.append(
                    SecurityFinding(
                        finding_id=f"local-rdp-{rule_name}",
                        severity=ScanSeverity.CRITICAL,
                        category="network",
                        resource=nsg_config["id"],
                        title=f"RDP exposed to internet: {rule_name}",
                        description=f"Rule '{rule_name}' allows RDP (port 3389) from any source.",
                        remediation="Restrict source to specific IP ranges or use Azure Bastion",
                        compliance_impact=["CIS-6.1", "SOC2-CC6.6"],
                    )
                )

        # Check for deny-default rule
        has_deny_default = any(
            rule.get("priority") == 4096
            and rule.get("direction") == "Inbound"
            and rule.get("access") == "Deny"
            for rule in security_rules
        )

        if not has_deny_default:
            findings.append(
                SecurityFinding(
                    finding_id="local-missing-deny-default",
                    severity=ScanSeverity.HIGH,
                    category="network",
                    resource=nsg_config["id"],
                    title="Missing deny-all default rule",
                    description="NSG does not have explicit deny-all rule for inbound traffic (priority 4096)",
                    remediation="Add deny-all rule with priority 4096, direction=Inbound, access=Deny",
                    compliance_impact=["CIS-6.2", "SOC2-CC6.6"],
                )
            )

        return findings

    def scan_vm(self, vm_name: str, resource_group: str) -> list[SecurityFinding]:
        """Scan VM for security issues.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            List of security findings

        Raises:
            SecurityScannerError: If VM retrieval fails
        """
        findings = []

        # Get VM configuration
        cmd = ["az", "vm", "show", "--name", vm_name, "--resource-group", resource_group]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise SecurityScannerError(f"Failed to retrieve VM: {result.stderr}")

        vm_config = json.loads(result.stdout)

        # Check for public IP (can be at VM level or NIC level)
        has_public_ip = False

        # Check top-level VM config
        if vm_config.get("publicIpAddress"):
            has_public_ip = True

        # Check network interfaces
        network_profile = vm_config.get("networkProfile", {})
        network_interfaces = network_profile.get("networkInterfaces", [])

        for nic in network_interfaces:
            # Get NIC details to check for public IP
            if "publicIpAddress" in str(nic).lower():
                has_public_ip = True
                break

        if has_public_ip:
            findings.append(
                SecurityFinding(
                    finding_id=f"vm-public-ip-{vm_name}",
                    severity=ScanSeverity.HIGH,
                    category="network",
                    resource=vm_config["id"],
                    title="VM has public IP address",
                    description=f"VM '{vm_name}' has public IP, increasing attack surface",
                    remediation="Use Azure Bastion for SSH access instead of public IP",
                    compliance_impact=["CIS-6.1", "SOC2-CC6.6"],
                )
            )

        # Query Security Center for VM-specific findings
        findings.extend(self._query_security_center(vm_config["id"]))

        return findings

    def pre_deployment_scan(
        self, resource_group: str, template: dict[str, Any]
    ) -> tuple[bool, list[SecurityFinding]]:
        """Scan resources before deployment.

        Performs pre-deployment validation to catch security issues before
        resources are created in Azure.

        Args:
            resource_group: Resource group name
            template: Azure Resource Manager template

        Returns:
            Tuple of (can_deploy, findings)
            can_deploy is False if any CRITICAL findings exist
        """
        findings = []

        # Scan NSGs in template
        for resource in template.get("resources", []):
            if resource.get("type") == "Microsoft.Network/networkSecurityGroups":
                # Use NSGValidator for pre-deployment validation
                from azlin.network_security.nsg_validator import NSGValidator

                validator = NSGValidator()

                # Convert ARM template resource to NSG template format
                nsg_template = self._arm_resource_to_nsg_template(resource)
                validation_result = validator.validate_template(nsg_template)

                # Convert validation findings to SecurityFindings
                for finding in validation_result.critical_issues:
                    # Handle both PolicyFinding objects and dict format
                    if hasattr(finding, "name"):
                        # PolicyFinding object
                        finding_name = finding.name
                        finding_message = finding.message
                        finding_remediation = finding.remediation or "Review NSG configuration"
                        finding_compliance = finding.compliance_impact
                    else:
                        # Dict format (for testing/mocking)
                        finding_name = finding.get("name", "unknown")
                        finding_message = finding.get("message") or finding.get(
                            "title", "Security issue"
                        )
                        finding_remediation = finding.get("remediation", "Review NSG configuration")
                        finding_compliance = finding.get("compliance_impact", [])

                    findings.append(
                        SecurityFinding(
                            finding_id=f"pre-deploy-{resource['name']}-{finding_name}",
                            severity=ScanSeverity.CRITICAL,
                            category="network",
                            resource=resource["name"],
                            title=finding_message,
                            description=finding_message,
                            remediation=finding_remediation,
                            compliance_impact=finding_compliance,
                        )
                    )

        # Determine if deployment should proceed
        critical_findings = [f for f in findings if f.severity == ScanSeverity.CRITICAL]
        can_deploy = len(critical_findings) == 0

        return can_deploy, findings

    def _arm_resource_to_nsg_template(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Convert ARM template resource to NSG template format.

        Args:
            resource: ARM template resource

        Returns:
            NSG template dictionary
        """
        properties = resource.get("properties", {})
        security_rules = properties.get("securityRules", [])

        # Convert ARM format to NSG template format
        template_rules = []
        for rule in security_rules:
            rule_props = rule.get("properties", {})
            template_rules.append(
                {
                    "name": rule.get("name", "unnamed"),
                    "priority": rule_props.get("priority", 100),
                    "direction": rule_props.get("direction", "Inbound"),
                    "access": rule_props.get("access", "Allow"),
                    "protocol": rule_props.get("protocol", "*"),
                    "source_port_range": rule_props.get("sourcePortRange", "*"),
                    "destination_port_range": rule_props.get("destinationPortRange", "*"),
                    "source_address_prefix": rule_props.get("sourceAddressPrefix", "*"),
                    "destination_address_prefix": rule_props.get("destinationAddressPrefix", "*"),
                    "justification": rule_props.get("description", "No justification provided"),
                }
            )

        return {
            "name": resource.get("name", "unnamed"),
            "description": properties.get("description", ""),
            "version": "1.0",
            "security_rules": template_rules,
            "default_rules": {"inbound": "Deny", "outbound": "Allow"},
        }


__all__ = ["ScanSeverity", "SecurityFinding", "SecurityScanner", "SecurityScannerError"]
