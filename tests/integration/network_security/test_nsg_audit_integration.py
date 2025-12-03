"""Integration tests for NSG + audit logging integration.

Tests the integration between NSGManager and SecurityAuditLogger.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- NSG template application workflow
- Audit logging of NSG operations
- Validation failures logged correctly
- Compliance event tracking
"""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# Mark all tests as integration and TDD RED phase
pytestmark = [pytest.mark.integration, pytest.mark.tdd_red]


class TestNSGTemplateApplicationWithAudit:
    """Test NSG template application with audit logging."""

    @patch("subprocess.run")
    def test_successful_template_application_logs_audit_event(self, mock_run, tmp_path):
        """Successful NSG template application should log audit event."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import (
            AuditEventType,
            SecurityAuditLogger,
        )

        mock_run.return_value = Mock(returncode=0, stdout="{}")

        # Create test template
        template_path = tmp_path / "test-nsg.yaml"
        template_path.write_text(
            """
name: test-nsg
description: Test NSG
version: 1.0
security_rules:
  - name: allow-https
    priority: 100
    direction: Inbound
    access: Allow
    protocol: Tcp
    source_port_range: "*"
    destination_port_range: "443"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: HTTPS traffic
  - name: deny-all
    priority: 4096
    direction: Inbound
    access: Deny
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: Default deny
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Apply template
        result = manager.apply_template(
            template_path=str(template_path),
            nsg_name="test-nsg",
            resource_group="test-rg",
            dry_run=False,
        )

        # Verify audit event was logged
        events = logger.query_events(event_type=AuditEventType.NSG_RULE_APPLY)
        assert len(events) > 0
        assert events[0].resource == "test-nsg"
        assert events[0].outcome == "success"

    @patch("subprocess.run")
    def test_validation_failure_logs_critical_audit_event(self, mock_run, tmp_path):
        """Failed NSG validation should log CRITICAL audit event."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import (
            AuditEventType,
            SecurityAuditLogger,
        )

        # Create template with dangerous rule
        template_path = tmp_path / "dangerous-nsg.yaml"
        template_path.write_text(
            """
name: dangerous-nsg
description: SSH exposed
version: 1.0
security_rules:
  - name: allow-ssh-internet
    priority: 100
    direction: Inbound
    access: Allow
    protocol: Tcp
    source_port_range: "*"
    destination_port_range: "22"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: SSH access
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Apply template (should fail validation)
        with pytest.raises(Exception, match="validation"):  # Should raise validation error
            manager.apply_template(
                template_path=str(template_path),
                nsg_name="dangerous-nsg",
                resource_group="test-rg",
                dry_run=False,
            )

        # Verify critical audit event was logged
        events = logger.query_events(
            event_type=AuditEventType.NSG_VALIDATION_FAIL, severity="critical"
        )
        assert len(events) > 0
        assert events[0].resource == "dangerous-nsg"

    @patch("subprocess.run")
    def test_dry_run_does_not_apply_but_logs(self, mock_run, tmp_path):
        """Dry-run should not apply changes but should log validation."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import SecurityAuditLogger

        template_path = tmp_path / "test-nsg.yaml"
        template_path.write_text(
            """
name: test-nsg
description: Test
version: 1.0
security_rules:
  - name: deny-all
    priority: 4096
    direction: Inbound
    access: Deny
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: Default deny
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Apply in dry-run mode
        result = manager.apply_template(
            template_path=str(template_path),
            nsg_name="test-nsg",
            resource_group="test-rg",
            dry_run=True,
        )

        # Verify no Azure CLI commands were executed
        mock_run.assert_not_called()

        # Verify validation was logged
        assert result.validated is True


class TestNSGComplianceTracking:
    """Test NSG compliance event tracking in audit logs."""

    @patch("subprocess.run")
    def test_nsg_application_includes_compliance_tags(self, mock_run, tmp_path):
        """NSG application audit events should include compliance tags."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import SecurityAuditLogger

        mock_run.return_value = Mock(returncode=0, stdout="{}")

        template_path = tmp_path / "compliant-nsg.yaml"
        template_path.write_text(
            """
name: compliant-nsg
description: CIS compliant NSG
version: 1.0
metadata:
  compliance:
    - CIS-6.2
    - SOC2-CC6.6
security_rules:
  - name: deny-ssh-internet
    priority: 200
    direction: Inbound
    access: Deny
    protocol: Tcp
    source_port_range: "*"
    destination_port_range: "22"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: Block SSH
  - name: deny-all
    priority: 4096
    direction: Inbound
    access: Deny
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: Default deny
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Apply template
        manager.apply_template(
            template_path=str(template_path),
            nsg_name="compliant-nsg",
            resource_group="test-rg",
            dry_run=False,
        )

        # Verify compliance tags in audit event
        events = logger.query_events(resource="compliant-nsg")
        assert len(events) > 0
        assert "CIS-6.2" in events[0].compliance_tags
        assert "SOC2-CC6.6" in events[0].compliance_tags

    def test_compliance_report_includes_nsg_events(self, tmp_path):
        """Compliance reports should include NSG application events."""
        from azlin.network_security.security_audit import (
            AuditEvent,
            AuditEventType,
            SecurityAuditLogger,
        )

        logger = SecurityAuditLogger()

        # Log some NSG events with compliance tags
        for i in range(3):
            event = AuditEvent(
                event_id=f"nsg-event-{i}",
                timestamp=datetime.now(),
                event_type=AuditEventType.NSG_RULE_APPLY,
                user="test-user",
                resource=f"nsg-{i}",
                action="apply_template",
                outcome="success",
                details={},
                severity="info",
                compliance_tags=["CIS-6.2", "SOC2-CC6.6"],
            )
            logger.log_event(event)

        # Generate compliance report
        report = logger.generate_compliance_report(
            framework="CIS",
            start_date=datetime.now(),
            end_date=datetime.now(),
        )

        assert report["total_events"] == 3
        assert "nsg" in str(report).lower()


class TestNSGDriftDetection:
    """Test detection of configuration drift between template and applied NSG."""

    @patch("subprocess.run")
    def test_compare_nsg_detects_drift(self, mock_run, tmp_path):
        """compare_nsg should detect differences between template and actual."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import SecurityAuditLogger

        # Mock Azure CLI to return different NSG config
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "/subscriptions/test/nsg1",
                    "securityRules": [
                        {
                            "name": "unexpected-rule",
                            "priority": 150,
                            "direction": "Inbound",
                            "access": "Allow",
                            "destinationPortRange": "80",
                        }
                    ],
                }
            ),
        )

        template_path = tmp_path / "expected-nsg.yaml"
        template_path.write_text(
            """
name: test-nsg
description: Expected config
version: 1.0
security_rules:
  - name: deny-all
    priority: 4096
    direction: Inbound
    access: Deny
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: Default deny
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Compare NSG
        comparison = manager.compare_nsg(template_path=str(template_path), nsg_name="test-nsg")

        # Verify drift detected
        assert comparison.has_drift is True
        assert len(comparison.differences) > 0

    @patch("subprocess.run")
    def test_drift_detection_logs_configuration_drift_event(self, mock_run, tmp_path):
        """Configuration drift should be logged as audit event."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.security_audit import (
            AuditEventType,
            SecurityAuditLogger,
        )

        # Mock drifted config
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "/subscriptions/test/nsg1",
                    "securityRules": [{"name": "manual-rule", "priority": 100}],
                }
            ),
        )

        template_path = tmp_path / "expected-nsg.yaml"
        template_path.write_text(
            """
name: test-nsg
version: 1.0
security_rules: []
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        validator = NSGValidator()
        logger = SecurityAuditLogger()
        manager = NSGManager(validator, logger)

        # Detect drift
        manager.compare_nsg(template_path=str(template_path), nsg_name="test-nsg")

        # Verify drift audit event
        events = logger.query_events(event_type=AuditEventType.CONFIGURATION_DRIFT)
        assert len(events) > 0
        assert events[0].severity == "warning"
