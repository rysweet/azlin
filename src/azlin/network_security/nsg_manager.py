"""NSG Manager for applying and managing Network Security Group configurations.

This module provides NSGManager class for applying NSG templates to Azure
with validation, audit logging, and compliance tracking.
"""

import os
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any

import yaml

from azlin.network_security.nsg_validator import NSGValidator
from azlin.network_security.security_audit import (
    AuditEvent,
    AuditEventType,
    SecurityAuditLogger,
)


class NSGManager:
    """Manages Network Security Group template application and configuration."""

    def __init__(
        self,
        validator: NSGValidator | None = None,
        audit_logger: SecurityAuditLogger | None = None,
    ):
        """Initialize NSG Manager.

        Args:
            validator: NSG validator instance (creates new if None)
            audit_logger: Audit logger instance (creates new if None)
        """
        self.validator = validator or NSGValidator()
        self.audit_logger = audit_logger or SecurityAuditLogger()

    def apply_template(
        self,
        template_path: str,
        nsg_name: str,
        resource_group: str,
        dry_run: bool = False,
        compliance_framework: str | None = None,
    ) -> dict[str, Any]:
        """Apply NSG template to Azure with validation and audit logging.

        Args:
            template_path: Path to YAML template file
            nsg_name: Name of NSG to create/update
            resource_group: Azure resource group name
            dry_run: If True, validate only without applying
            compliance_framework: Optional compliance framework (CIS, SOC2, etc.)

        Returns:
            Dict with status and details

        Raises:
            Exception: If validation fails or Azure CLI command fails
        """
        # Load template
        template = self._load_template(template_path)

        # Validate template
        validation_result = self.validator.validate_template(template)

        if not validation_result.is_valid:
            # Log validation failure
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                event_type=AuditEventType.NSG_VALIDATION_FAIL,
                user=os.environ.get("USER", "unknown"),
                resource=nsg_name,
                action="validate_nsg_template",
                outcome="failure",
                details={
                    "template_path": template_path,
                    "resource_group": resource_group,
                    "findings": [
                        {
                            "name": f.name,
                            "severity": f.severity,
                            "description": f.message,
                        }
                        for f in validation_result.findings
                    ],
                },
                severity="critical",
            )
            self.audit_logger.log_event(event)
            raise Exception(
                f"NSG template validation failed with {len(validation_result.findings)} findings"
            )

        # Dry run - validation only
        if dry_run:
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                event_type=AuditEventType.NSG_VALIDATION_PASS,
                user=os.environ.get("USER", "unknown"),
                resource=nsg_name,
                action="validate_nsg_template_dry_run",
                outcome="success",
                details={
                    "template_path": template_path,
                    "resource_group": resource_group,
                    "dry_run": True,
                },
                severity="info",
            )
            self.audit_logger.log_event(event)
            return {
                "status": "dry_run_success",
                "nsg_name": nsg_name,
                "validation": "passed",
            }

        # Apply NSG to Azure
        try:
            self._apply_to_azure(nsg_name, resource_group, template)

            # Log successful application
            event_details: dict[str, Any] = {
                "template_path": template_path,
                "resource_group": resource_group,
                "rules_count": len(template.get("security_rules", [])),
            }

            if compliance_framework:
                event_details["compliance_framework"] = compliance_framework

            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                event_type=AuditEventType.NSG_RULE_APPLY,
                user=os.environ.get("USER", "unknown"),
                resource=nsg_name,
                action="apply_nsg_template",
                outcome="success",
                details=event_details,
                severity="info",
            )
            self.audit_logger.log_event(event)

            return {
                "status": "success",
                "nsg_name": nsg_name,
                "resource_group": resource_group,
            }

        except subprocess.CalledProcessError as e:
            # Log application failure
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                event_type=AuditEventType.NSG_RULE_APPLY,
                user=os.environ.get("USER", "unknown"),
                resource=nsg_name,
                action="apply_nsg_template",
                outcome="failure",
                details={
                    "template_path": template_path,
                    "resource_group": resource_group,
                    "error": str(e),
                },
                severity="critical",
            )
            self.audit_logger.log_event(event)
            raise

    def compare_nsg(self, nsg_name: str, resource_group: str, template_path: str) -> dict[str, Any]:
        """Compare deployed NSG with template to detect drift.

        Args:
            nsg_name: Name of deployed NSG
            resource_group: Resource group name
            template_path: Path to expected template

        Returns:
            Dict with drift detection results
        """
        # Load expected template
        expected = self._load_template(template_path)

        # Get actual NSG configuration from Azure
        actual = self._get_deployed_nsg(nsg_name, resource_group)

        # Compare configurations
        drift_detected = self._detect_drift(expected, actual)

        if drift_detected:
            # Log configuration drift
            event = AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC),
                event_type=AuditEventType.CONFIGURATION_DRIFT,
                user=os.environ.get("USER", "unknown"),
                resource=nsg_name,
                action="compare_nsg_configuration",
                outcome="drift_detected",
                details={
                    "resource_group": resource_group,
                    "template_path": template_path,
                    "drift_details": drift_detected,
                },
                severity="warning",
            )
            self.audit_logger.log_event(event)

        return {
            "drift_detected": bool(drift_detected),
            "differences": drift_detected if drift_detected else {},
        }

    def _load_template(self, template_path: str) -> dict[str, Any]:
        """Load YAML template from file.

        Args:
            template_path: Path to template file

        Returns:
            Parsed template as dict
        """
        with open(template_path) as f:
            return yaml.safe_load(f)

    def _apply_to_azure(self, nsg_name: str, resource_group: str, template: dict[str, Any]) -> None:
        """Apply NSG configuration to Azure using Azure CLI.

        Args:
            nsg_name: NSG name
            resource_group: Resource group
            template: NSG template dict

        Raises:
            subprocess.CalledProcessError: If Azure CLI command fails
        """
        # Create or update NSG
        cmd = [
            "az",
            "network",
            "nsg",
            "create",
            "--name",
            nsg_name,
            "--resource-group",
            resource_group,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # Apply security rules
        for rule in template.get("security_rules", []):
            self._apply_rule(nsg_name, resource_group, rule)

    def _apply_rule(self, nsg_name: str, resource_group: str, rule: dict[str, Any]) -> None:
        """Apply single security rule to NSG.

        Args:
            nsg_name: NSG name
            resource_group: Resource group
            rule: Rule configuration dict
        """
        cmd = [
            "az",
            "network",
            "nsg",
            "rule",
            "create",
            "--nsg-name",
            nsg_name,
            "--resource-group",
            resource_group,
            "--name",
            rule["name"],
            "--priority",
            str(rule["priority"]),
            "--direction",
            rule["direction"],
            "--access",
            rule["access"],
            "--protocol",
            rule["protocol"],
            "--source-port-ranges",
            rule["source_port_range"],
            "--destination-port-ranges",
            rule["destination_port_range"],
            "--source-address-prefixes",
            rule["source_address_prefix"],
            "--destination-address-prefixes",
            rule["destination_address_prefix"],
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _get_deployed_nsg(self, nsg_name: str, resource_group: str) -> dict[str, Any]:
        """Get deployed NSG configuration from Azure.

        Args:
            nsg_name: NSG name
            resource_group: Resource group

        Returns:
            NSG configuration dict
        """
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        import json

        return json.loads(result.stdout)

    def _detect_drift(
        self, expected: dict[str, Any], actual: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Detect configuration drift between expected and actual NSG.

        Args:
            expected: Expected NSG configuration
            actual: Actual deployed configuration

        Returns:
            Dict describing drift, or None if no drift
        """
        drift: dict[str, Any] = {}

        # Compare security rules
        expected_rules = {r["name"]: r for r in expected.get("security_rules", [])}
        actual_rules = {r["name"]: r for r in actual.get("securityRules", [])}

        # Check for missing rules
        missing = set(expected_rules.keys()) - set(actual_rules.keys())
        if missing:
            drift["missing_rules"] = list(missing)

        # Check for extra rules
        extra = set(actual_rules.keys()) - set(expected_rules.keys())
        if extra:
            drift["extra_rules"] = list(extra)

        # Check for modified rules
        modified = []
        for name in set(expected_rules.keys()) & set(actual_rules.keys()):
            exp_rule = expected_rules[name]
            act_rule = actual_rules[name]

            # Compare key fields
            if exp_rule.get("priority") != act_rule.get("priority"):
                modified.append({"rule": name, "field": "priority"})
            if exp_rule.get("access") != act_rule.get("access"):
                modified.append({"rule": name, "field": "access"})

        if modified:
            drift["modified_rules"] = modified

        return drift if drift else None


__all__ = ["NSGManager"]
