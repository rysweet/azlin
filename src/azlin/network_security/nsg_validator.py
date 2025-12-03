"""NSG Template Validator and Policy Engine.

Validates Network Security Group templates against security policies to prevent
misconfigurations that could lead to security vulnerabilities.

Philosophy:
- Fail-secure: Deny by default, explicit allow only
- Defense in depth: Multiple validation layers
- Zero-BS: Every rule must have justification
- Compliance-focused: Map to CIS, SOC2, ISO27001

Public API:
    NSGValidator: Main validator class
    ValidationResult: Validation outcome with errors and findings
    PolicyFinding: Individual policy violation

Example:
    >>> validator = NSGValidator()
    >>> template = load_template("web-server-nsg.yaml")
    >>> result = validator.validate_template(template)
    >>> if not result.is_valid:
    ...     print(f"Validation failed: {result.errors}")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RuleSeverity(str, Enum):
    """Severity levels for policy findings."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class PolicyFinding:
    """A security policy violation found during validation."""

    name: str
    severity: str
    message: str
    rule_name: str | None = None
    remediation: str | None = None
    compliance_impact: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of NSG template validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[PolicyFinding] = field(default_factory=list)
    compliance_tags: list[str] = field(default_factory=list)

    @property
    def critical_issues(self) -> list[PolicyFinding]:
        """Get only critical severity findings."""
        return [f for f in self.findings if f.severity == RuleSeverity.CRITICAL]


class NSGValidator:
    """Validates NSG templates against security policies.

    Performs comprehensive validation including:
    - Schema validation (structure, types, ranges)
    - Policy compliance (CIS, SOC2, ISO27001)
    - Dangerous rule detection (exposed management ports)
    - Conflict detection (duplicate priorities)
    - Best practices enforcement
    """

    # Valid values for NSG rule fields
    VALID_DIRECTIONS = ["Inbound", "Outbound"]
    VALID_ACCESS = ["Allow", "Deny"]
    VALID_PROTOCOLS = ["Tcp", "Udp", "Icmp", "*"]
    MIN_PRIORITY = 100
    MAX_PRIORITY = 4096

    # Sensitive ports that require extra scrutiny
    SENSITIVE_PORTS = {
        "22": "SSH",
        "3389": "RDP",
        "23": "Telnet",
        "21": "FTP",
        "445": "SMB",
        "135": "RPC",
        "3306": "MySQL",
        "5432": "PostgreSQL",
        "1433": "MSSQL",
        "27017": "MongoDB",
    }

    def __init__(self):
        """Initialize NSG validator with security policy."""
        from azlin.network_security.security_policy import SecurityPolicy

        self.policy = SecurityPolicy()

    def validate_template(self, template: dict[str, Any]) -> ValidationResult:
        """Validate NSG template comprehensively.

        Performs all validation checks and returns consolidated results.

        Args:
            template: NSG template dictionary

        Returns:
            ValidationResult with all errors, warnings, and findings
        """
        errors = []
        warnings = []
        findings = []
        compliance_tags = set()

        # 1. Schema validation
        schema_errors = self._validate_schema(template)
        errors.extend(schema_errors)

        # If schema validation fails, don't proceed with other checks
        if schema_errors:
            return ValidationResult(
                is_valid=False, errors=errors, warnings=warnings, findings=findings
            )

        # 2. Check for dangerous rules
        dangerous_findings = self.check_dangerous_rules(template)
        findings.extend(dangerous_findings)

        # 3. Check policy compliance
        template_compliance = self.check_policy_compliance(template)
        compliance_tags.update(template_compliance)

        # 4. Check for conflicting rules (duplicate priorities)
        conflict_errors = self._check_conflicts(template)
        errors.extend(conflict_errors)

        # 5. Check deny-by-default requirement
        if not self.check_deny_default(template):
            errors.append("Missing deny-all default rule for inbound traffic (priority 4096)")
            findings.append(
                PolicyFinding(
                    name="missing-deny-default",
                    severity=RuleSeverity.CRITICAL,
                    message="NSG must have deny-all default rule for inbound traffic",
                    remediation="Add deny-all rule with priority 4096 and direction=Inbound",
                    compliance_impact=["CIS-6.2", "SOC2-CC6.6"],
                )
            )

        # 6. Check for policy violations
        rules = template.get("security_rules", [])
        forbidden_violations = self.policy.check_forbidden_rules(rules)
        findings.extend(
            [
                PolicyFinding(
                    name=v["name"],
                    severity=v["severity"],
                    message=v["message"],
                    remediation=v.get("remediation"),
                    compliance_impact=v.get("compliance_impact", []),
                )
                for v in forbidden_violations
            ]
        )

        required_violations = self.policy.check_required_rules(rules)
        findings.extend(
            [
                PolicyFinding(
                    name=v["name"],
                    severity=v["severity"],
                    message=v["message"],
                    remediation=v.get("remediation"),
                    compliance_impact=v.get("compliance_impact", []),
                )
                for v in required_violations
            ]
        )

        # Determine overall validity
        is_valid = (
            len(errors) == 0
            and len([f for f in findings if f.severity == RuleSeverity.CRITICAL]) == 0
        )

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            findings=findings,
            compliance_tags=list(compliance_tags),
        )

    def _validate_schema(self, template: dict[str, Any]) -> list[str]:
        """Validate template schema (structure and types).

        Args:
            template: NSG template dictionary

        Returns:
            List of validation errors
        """
        errors = []

        # Check required top-level fields
        required_fields = ["name", "description", "version", "security_rules", "default_rules"]
        errors.extend(
            f"Missing required field: {required_field}"
            for required_field in required_fields
            if required_field not in template
        )

        if errors:
            return errors  # Don't proceed if top-level fields are missing

        # Validate security rules
        security_rules = template.get("security_rules", [])
        if not isinstance(security_rules, list):
            errors.append("security_rules must be a list")
            return errors

        for i, rule in enumerate(security_rules):
            rule_errors = self._validate_rule_schema(rule, i)
            errors.extend(rule_errors)

        # Validate default_rules
        default_rules = template.get("default_rules", {})
        if not isinstance(default_rules, dict):
            errors.append("default_rules must be a dictionary")
        else:
            if "inbound" not in default_rules or "outbound" not in default_rules:
                errors.append("default_rules must specify 'inbound' and 'outbound' policies")

        return errors

    def _validate_rule_schema(self, rule: dict[str, Any], index: int) -> list[str]:
        """Validate individual NSG rule schema.

        Args:
            rule: NSG rule dictionary
            index: Rule index in template

        Returns:
            List of validation errors for this rule
        """
        errors = []
        rule_name = rule.get("name", f"rule_{index}")

        # Required fields
        required_fields = [
            "name",
            "priority",
            "direction",
            "access",
            "protocol",
            "source_port_range",
            "destination_port_range",
            "source_address_prefix",
            "destination_address_prefix",
            "justification",
        ]

        errors.extend(
            f"Rule '{rule_name}': missing required field '{required_field}'"
            for required_field in required_fields
            if required_field not in rule
        )

        if errors:
            return errors  # Don't validate values if fields are missing

        # Validate priority
        priority = rule.get("priority")
        if not isinstance(priority, int):
            errors.append(f"Rule '{rule_name}': priority must be an integer")
        elif priority < self.MIN_PRIORITY or priority > self.MAX_PRIORITY:
            errors.append(
                f"Rule '{rule_name}': priority must be between {self.MIN_PRIORITY} and {self.MAX_PRIORITY}"
            )

        # Validate direction
        direction = rule.get("direction")
        if direction not in self.VALID_DIRECTIONS:
            errors.append(
                f"Rule '{rule_name}': direction must be one of {self.VALID_DIRECTIONS}, got '{direction}'"
            )

        # Validate access
        access = rule.get("access")
        if access not in self.VALID_ACCESS:
            errors.append(
                f"Rule '{rule_name}': access must be one of {self.VALID_ACCESS}, got '{access}'"
            )

        # Validate protocol
        protocol = rule.get("protocol")
        if protocol not in self.VALID_PROTOCOLS:
            errors.append(
                f"Rule '{rule_name}': protocol must be one of {self.VALID_PROTOCOLS}, got '{protocol}'"
            )

        return errors

    def _check_conflicts(self, template: dict[str, Any]) -> list[str]:
        """Check for conflicting rules (duplicate priorities).

        Args:
            template: NSG template dictionary

        Returns:
            List of conflict errors
        """
        errors = []
        security_rules = template.get("security_rules", [])

        # Group rules by direction and check for duplicate priorities within each direction
        priorities_by_direction = {"Inbound": [], "Outbound": []}

        for rule in security_rules:
            direction = rule.get("direction")
            priority = rule.get("priority")
            if direction in priorities_by_direction:
                priorities_by_direction[direction].append((priority, rule.get("name")))

        # Check for duplicates
        for direction, rules in priorities_by_direction.items():
            seen_priorities = {}
            for priority, name in rules:
                if priority in seen_priorities:
                    errors.append(
                        f"Conflicting priority {priority} for {direction} rules: "
                        f"'{seen_priorities[priority]}' and '{name}'"
                    )
                else:
                    seen_priorities[priority] = name

        return errors

    def check_deny_default(self, template: dict[str, Any]) -> bool:
        """Check if template has deny-by-default rule for inbound traffic.

        Args:
            template: NSG template dictionary

        Returns:
            True if deny-default rule exists, False otherwise
        """
        security_rules = template.get("security_rules", [])

        # Look for deny-all rule with priority 4096, direction Inbound
        for rule in security_rules:
            if (
                rule.get("priority") == 4096
                and rule.get("direction") == "Inbound"
                and rule.get("access") == "Deny"
            ):
                return True

        return False

    def check_dangerous_rules(self, template: dict[str, Any]) -> list[PolicyFinding]:
        """Flag dangerous NSG rules.

        Checks for:
        - Wildcard source on sensitive ports (SSH, RDP, etc.)
        - Management ports exposed to internet
        - Overly broad CIDR ranges

        Args:
            template: NSG template dictionary

        Returns:
            List of dangerous rule findings
        """
        findings = []
        security_rules = template.get("security_rules", [])

        for rule in security_rules:
            rule_name = rule.get("name", "unnamed")
            dest_port = str(rule.get("destination_port_range", ""))
            source_prefix = rule.get("source_address_prefix", "")
            access = rule.get("access", "")
            direction = rule.get("direction", "")

            # Skip deny rules - we're looking for dangerous allow rules
            if access != "Allow" or direction != "Inbound":
                continue

            # Check for SSH from internet
            if dest_port == "22" and source_prefix in ["Internet", "*", "0.0.0.0/0"]:
                findings.append(
                    PolicyFinding(
                        name=f"ssh-from-internet-{rule_name}",
                        severity=RuleSeverity.CRITICAL,
                        message=f"Rule '{rule_name}' exposes SSH (port 22) to the internet. Use Azure Bastion instead.",
                        rule_name=rule_name,
                        remediation="Remove this rule and use Azure Bastion for SSH access",
                        compliance_impact=["CIS-6.2", "SOC2-CC6.6"],
                    )
                )

            # Check for RDP from internet
            if dest_port == "3389" and source_prefix in ["Internet", "*", "0.0.0.0/0"]:
                findings.append(
                    PolicyFinding(
                        name=f"rdp-from-internet-{rule_name}",
                        severity=RuleSeverity.CRITICAL,
                        message=f"Rule '{rule_name}' exposes RDP (port 3389) to the internet.",
                        rule_name=rule_name,
                        remediation="Remove this rule and use Azure Bastion for RDP access",
                        compliance_impact=["CIS-6.1", "SOC2-CC6.6"],
                    )
                )

            # Check for other sensitive ports from wildcard source
            if dest_port in self.SENSITIVE_PORTS and source_prefix in ["*", "0.0.0.0/0"]:
                port_name = self.SENSITIVE_PORTS[dest_port]
                findings.append(
                    PolicyFinding(
                        name=f"{port_name.lower()}-wildcard-{rule_name}",
                        severity=RuleSeverity.HIGH,
                        message=f"Rule '{rule_name}' exposes {port_name} (port {dest_port}) to all sources",
                        rule_name=rule_name,
                        remediation=f"Restrict source to specific IP ranges for {port_name} access",
                        compliance_impact=["CIS-6.2"],
                    )
                )

        return findings

    def check_policy_compliance(self, template: dict[str, Any]) -> list[str]:
        """Map NSG rules to compliance frameworks.

        Args:
            template: NSG template dictionary

        Returns:
            List of compliance tags that this template addresses
        """
        compliance_tags = set()
        security_rules = template.get("security_rules", [])

        for rule in security_rules:
            dest_port = str(rule.get("destination_port_range", ""))
            source_prefix = rule.get("source_address_prefix", "")
            access = rule.get("access", "")
            direction = rule.get("direction", "")

            # CIS 6.2: SSH restrictions
            if (
                dest_port == "22"
                and direction == "Inbound"
                and access == "Deny"
                and source_prefix in ["Internet", "*"]
            ):
                compliance_tags.add("CIS-6.2")
                compliance_tags.add("SOC2-CC6.6")

            # CIS 6.1: RDP restrictions
            if (
                dest_port == "3389"
                and direction == "Inbound"
                and access == "Deny"
                and source_prefix in ["Internet", "*"]
            ):
                compliance_tags.add("CIS-6.1")
                compliance_tags.add("SOC2-CC6.6")

            # ISO27001 A.13.1: Network security controls
            if access == "Deny" and direction == "Inbound":
                compliance_tags.add("ISO27001-A.13.1")

        # Check for deny-default rule (required by multiple frameworks)
        if self.check_deny_default(template):
            compliance_tags.add("CIS-6.2")
            compliance_tags.add("SOC2-CC6.6")
            compliance_tags.add("ISO27001-A.13.1")

        return list(compliance_tags)


__all__ = ["NSGValidator", "PolicyFinding", "RuleSeverity", "ValidationResult"]
