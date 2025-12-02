"""Security Policy Engine for NSG validation.

Defines forbidden and required rules that NSG templates must comply with.
These policies are derived from security best practices and compliance frameworks.

Philosophy:
- Explicit policy definitions
- Framework-agnostic policy checks
- Clear violation messages with remediation
- Fail-secure defaults

Public API:
    SecurityPolicy: Policy engine for checking rules

Example:
    >>> policy = SecurityPolicy()
    >>> violations = policy.check_forbidden_rules(rules)
    >>> if violations:
    ...     print(f"Found {len(violations)} policy violations")
"""

from typing import Any, Callable, Dict, List


class SecurityPolicy:
    """Security policy rules for NSG validation.

    Defines forbidden rules (things you must NOT do) and required rules
    (things you MUST do) for secure NSG configuration.
    """

    def __init__(self):
        """Initialize security policy with forbidden and required rules."""
        self.forbidden_rules = self._define_forbidden_rules()
        self.required_rules = self._define_required_rules()

    def _define_forbidden_rules(self) -> List[Dict[str, Any]]:
        """Define forbidden rules that must not exist in NSG templates.

        Returns:
            List of forbidden rule definitions
        """
        return [
            {
                "name": "no-ssh-from-internet",
                "condition": lambda rule: (
                    str(rule.get("destination_port_range")) == "22"
                    and rule.get("source_address_prefix") in ["Internet", "*", "0.0.0.0/0"]
                    and rule.get("access") == "Allow"
                    and rule.get("direction", "Inbound") == "Inbound"  # Default to Inbound if missing
                ),
                "severity": "CRITICAL",
                "message": "SSH must not be exposed to internet. Use Bastion instead.",
                "remediation": "Remove SSH allow rule from internet and use Azure Bastion for SSH access",
                "compliance_impact": ["CIS-6.2", "SOC2-CC6.6"],
            },
            {
                "name": "no-rdp-from-internet",
                "condition": lambda rule: (
                    str(rule.get("destination_port_range")) == "3389"
                    and rule.get("source_address_prefix") in ["Internet", "*", "0.0.0.0/0"]
                    and rule.get("access") == "Allow"
                    and rule.get("direction", "Inbound") == "Inbound"  # Default to Inbound if missing
                ),
                "severity": "CRITICAL",
                "message": "RDP must not be exposed to internet.",
                "remediation": "Remove RDP allow rule from internet and use Azure Bastion for RDP access",
                "compliance_impact": ["CIS-6.1", "SOC2-CC6.6"],
            },
            {
                "name": "no-wildcard-management-ports",
                "condition": lambda rule: (
                    str(rule.get("destination_port_range")) in ["22", "3389", "23", "21"]
                    and rule.get("source_address_prefix") == "*"
                    and rule.get("access") == "Allow"
                    and rule.get("direction", "Inbound") == "Inbound"  # Default to Inbound if missing
                ),
                "severity": "CRITICAL",
                "message": "Management ports must not accept connections from any source (*)",
                "remediation": "Restrict source to specific IP ranges or use Azure Bastion",
                "compliance_impact": ["CIS-6.2", "SOC2-CC6.6"],
            },
        ]

    def _define_required_rules(self) -> List[Dict[str, Any]]:
        """Define required rules that must exist in NSG templates.

        Returns:
            List of required rule definitions
        """
        return [
            {
                "name": "deny-default-inbound",
                "condition": lambda rules: any(
                    rule.get("priority") == 4096
                    and rule.get("direction") == "Inbound"
                    and rule.get("access") == "Deny"
                    and rule.get("source_address_prefix") == "*"
                    and rule.get("destination_address_prefix") == "*"
                    for rule in rules
                ),
                "severity": "CRITICAL",
                "message": "NSG must have deny-all default rule for inbound traffic (priority 4096)",
                "remediation": "Add deny-all rule with priority=4096, direction=Inbound, access=Deny, source=*, dest=*",
                "compliance_impact": ["CIS-6.2", "SOC2-CC6.6", "ISO27001-A.13.1"],
            }
        ]

    def check_forbidden_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check if any forbidden rules exist.

        Args:
            rules: List of NSG rules to check

        Returns:
            List of violations found (empty if none)
        """
        violations = []

        for rule in rules:
            for forbidden in self.forbidden_rules:
                if forbidden["condition"](rule):
                    violations.append(
                        {
                            "name": forbidden["name"],
                            "severity": forbidden["severity"],
                            "message": forbidden["message"],
                            "remediation": forbidden.get("remediation"),
                            "compliance_impact": forbidden.get("compliance_impact", []),
                            "violating_rule": rule.get("name", "unnamed"),
                        }
                    )

        return violations

    def check_required_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check if all required rules exist.

        Args:
            rules: List of NSG rules to check

        Returns:
            List of violations (missing required rules)
        """
        violations = []

        for required in self.required_rules:
            # Required rules check entire rule set, not individual rules
            if not required["condition"](rules):
                violations.append(
                    {
                        "name": required["name"],
                        "severity": required["severity"],
                        "message": required["message"],
                        "remediation": required.get("remediation"),
                        "compliance_impact": required.get("compliance_impact", []),
                    }
                )

        return violations


__all__ = ["SecurityPolicy"]
