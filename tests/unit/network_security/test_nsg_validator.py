"""Unit tests for NSG validator and policy engine.

Tests the NSGValidator class that validates NSG templates against security policies.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Template schema validation
- Policy compliance checking
- Dangerous rule detection
- Deny-by-default enforcement
- Conflict detection
"""

import pytest
from typing import Any, Dict, List

# Mark all tests as TDD RED phase (expected to fail)
pytestmark = [pytest.mark.unit, pytest.mark.tdd_red]


class TestNSGValidatorSchemaValidation:
    """Test NSG template schema validation (Structure and types)."""

    def test_validate_valid_template_passes(self):
        """Valid NSG template should pass validation."""
        from azlin.network_security.nsg_validator import NSGValidator, ValidationResult

        validator = NSGValidator()
        template = {
            "name": "test-nsg",
            "description": "Test NSG",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "allow-https",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "443",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "HTTPS traffic",
                },
                {
                    "name": "deny-all",
                    "priority": 4096,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "*",
                    "source_port_range": "*",
                    "destination_port_range": "*",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "Default deny all inbound",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result: ValidationResult = validator.validate_template(template)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_missing_required_fields_fails(self):
        """Template missing required fields should fail validation."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {"name": "incomplete-nsg"}  # Missing required fields

        result = validator.validate_template(template)
        assert not result.is_valid
        assert any("required" in err.lower() for err in result.errors)

    def test_validate_invalid_priority_fails(self):
        """Template with invalid priority (out of range 100-4096) should fail."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "test-nsg",
            "description": "Test",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "invalid-priority",
                    "priority": 50,  # Invalid: below 100
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "80",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "Test",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result = validator.validate_template(template)
        assert not result.is_valid
        assert any("priority" in err.lower() for err in result.errors)

    def test_validate_invalid_direction_fails(self):
        """Template with invalid direction should fail."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "test-nsg",
            "description": "Test",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "invalid-direction",
                    "priority": 100,
                    "direction": "Sideways",  # Invalid direction
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "80",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "Test",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result = validator.validate_template(template)
        assert not result.is_valid
        assert any("direction" in err.lower() for err in result.errors)


class TestNSGValidatorPolicyCompliance:
    """Test NSG policy compliance checking (CIS, SOC2, ISO27001)."""

    def test_check_deny_default_exists(self):
        """Template with deny-all default rule should pass."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "secure-nsg",
            "description": "Secure NSG",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "deny-all-inbound",
                    "priority": 4096,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "*",
                    "source_port_range": "*",
                    "destination_port_range": "*",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "Default deny",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result = validator.check_deny_default(template)
        assert result is True

    def test_check_deny_default_missing_fails(self):
        """Template without deny-all default rule should fail."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "insecure-nsg",
            "description": "Missing deny default",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "allow-https",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "443",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "HTTPS",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result = validator.check_deny_default(template)
        assert result is False


class TestNSGValidatorDangerousRules:
    """Test detection of dangerous NSG rules."""

    def test_detect_ssh_from_internet_is_critical(self):
        """SSH exposed to internet should be flagged as CRITICAL."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "dangerous-nsg",
            "description": "SSH exposed",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "allow-ssh-internet",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "22",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "SSH access",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        findings = validator.check_dangerous_rules(template)
        assert len(findings) > 0
        assert any(f.severity == "CRITICAL" for f in findings)
        assert any("ssh" in f.message.lower() for f in findings)

    def test_detect_rdp_from_internet_is_critical(self):
        """RDP exposed to internet should be flagged as CRITICAL."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "dangerous-nsg",
            "description": "RDP exposed",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "allow-rdp-internet",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "3389",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "RDP access",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        findings = validator.check_dangerous_rules(template)
        assert len(findings) > 0
        assert any(f.severity == "CRITICAL" for f in findings)
        assert any("rdp" in f.message.lower() for f in findings)

    def test_detect_wildcard_source_on_sensitive_port(self):
        """Wildcard source on sensitive ports should be flagged."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "overly-permissive",
            "description": "Wildcard source",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "allow-all-ssh",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "22",
                    "source_address_prefix": "*",  # Wildcard source
                    "destination_address_prefix": "*",
                    "justification": "SSH",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        findings = validator.check_dangerous_rules(template)
        assert len(findings) > 0


class TestNSGValidatorConflictDetection:
    """Test detection of conflicting NSG rules."""

    def test_detect_conflicting_priorities(self):
        """Rules with same priority should be flagged as conflicts."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "conflict-nsg",
            "description": "Conflicting priorities",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "rule-1",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "80",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "HTTP",
                },
                {
                    "name": "rule-2",
                    "priority": 100,  # Same priority!
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "443",
                    "source_address_prefix": "*",
                    "destination_address_prefix": "*",
                    "justification": "HTTPS",
                },
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        result = validator.validate_template(template)
        assert not result.is_valid
        assert any("priority" in err.lower() for err in result.errors)


class TestSecurityPolicyEngine:
    """Test security policy engine for forbidden and required rules."""

    def test_forbidden_rule_ssh_from_internet(self):
        """Policy engine should flag SSH from internet as forbidden."""
        from azlin.network_security.security_policy import SecurityPolicy

        policy = SecurityPolicy()
        rule = {
            "destination_port_range": "22",
            "source_address_prefix": "Internet",
            "access": "Allow",
        }

        violations = policy.check_forbidden_rules([rule])
        assert len(violations) > 0
        assert violations[0]["severity"] == "CRITICAL"

    def test_required_rule_deny_default_inbound(self):
        """Policy engine should require deny-all default inbound rule."""
        from azlin.network_security.security_policy import SecurityPolicy

        policy = SecurityPolicy()
        rules = [
            {
                "priority": 4096,
                "direction": "Inbound",
                "access": "Deny",
                "protocol": "*",
                "source_port_range": "*",
                "destination_port_range": "*",
                "source_address_prefix": "*",
                "destination_address_prefix": "*",
            }
        ]

        violations = policy.check_required_rules(rules)
        assert len(violations) == 0  # No violations if deny-default exists

    def test_required_rule_deny_default_missing(self):
        """Policy engine should flag missing deny-default as violation."""
        from azlin.network_security.security_policy import SecurityPolicy

        policy = SecurityPolicy()
        rules = []  # No deny-default rule

        violations = policy.check_required_rules(rules)
        assert len(violations) > 0
        assert violations[0]["severity"] == "CRITICAL"


class TestNSGValidatorComplianceMappings:
    """Test compliance framework mappings (CIS, SOC2, ISO27001)."""

    def test_check_policy_compliance_cis(self):
        """Template should map rules to CIS controls."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "compliant-nsg",
            "description": "CIS compliant",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "deny-ssh-internet",
                    "priority": 200,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "22",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "Block SSH from internet",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        compliance_tags = validator.check_policy_compliance(template)
        assert any("CIS" in tag for tag in compliance_tags)

    def test_check_policy_compliance_soc2(self):
        """Template should map rules to SOC2 criteria."""
        from azlin.network_security.nsg_validator import NSGValidator

        validator = NSGValidator()
        template = {
            "name": "compliant-nsg",
            "description": "SOC2 compliant",
            "version": "1.0",
            "security_rules": [
                {
                    "name": "deny-rdp-internet",
                    "priority": 200,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "Tcp",
                    "source_port_range": "*",
                    "destination_port_range": "3389",
                    "source_address_prefix": "Internet",
                    "destination_address_prefix": "*",
                    "justification": "Block RDP from internet",
                }
            ],
            "default_rules": {"outbound": "Allow", "inbound": "Deny"},
        }

        compliance_tags = validator.check_policy_compliance(template)
        assert any("SOC2" in tag for tag in compliance_tags)
