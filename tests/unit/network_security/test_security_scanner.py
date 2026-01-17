"""Unit tests for vulnerability scanning integration.

Tests the SecurityScanner class that integrates with Azure Security Center.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Finding detection and classification
- Severity mapping
- Local NSG validation
- Pre-deployment scanning
- Azure Security Center integration (mocked)
"""

import json
from unittest.mock import Mock, patch

import pytest

# Mark all tests as TDD RED phase (expected to fail)
pytestmark = [pytest.mark.unit, pytest.mark.tdd_red]


class TestSecurityFindingDataclass:
    """Test SecurityFinding dataclass."""

    def test_security_finding_creation(self):
        """SecurityFinding should be created with all required fields."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityFinding,
        )

        finding = SecurityFinding(
            finding_id="test-123",
            severity=ScanSeverity.CRITICAL,
            category="network",
            resource="/subscriptions/test/nsg1",
            title="SSH exposed to internet",
            description="Port 22 is open to 0.0.0.0/0",
            remediation="Restrict SSH to specific IP ranges or use Bastion",
            compliance_impact=["CIS-6.2", "SOC2-CC6.6"],
        )

        assert finding.finding_id == "test-123"
        assert finding.severity == ScanSeverity.CRITICAL
        assert finding.category == "network"

    def test_is_blocking_returns_true_for_critical(self):
        """Critical findings should be blocking."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityFinding,
        )

        finding = SecurityFinding(
            finding_id="crit-1",
            severity=ScanSeverity.CRITICAL,
            category="network",
            resource="/test",
            title="Critical issue",
            description="Test",
            remediation="Fix it",
            compliance_impact=[],
        )

        assert finding.is_blocking() is True

    def test_is_blocking_returns_true_for_high(self):
        """High severity findings should be blocking."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityFinding,
        )

        finding = SecurityFinding(
            finding_id="high-1",
            severity=ScanSeverity.HIGH,
            category="network",
            resource="/test",
            title="High severity issue",
            description="Test",
            remediation="Fix it",
            compliance_impact=[],
        )

        assert finding.is_blocking() is True

    def test_is_blocking_returns_false_for_medium_and_lower(self):
        """Medium and lower severity findings should not be blocking."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityFinding,
        )

        for severity in [ScanSeverity.MEDIUM, ScanSeverity.LOW, ScanSeverity.INFO]:
            finding = SecurityFinding(
                finding_id="low-1",
                severity=severity,
                category="network",
                resource="/test",
                title="Non-blocking issue",
                description="Test",
                remediation="Optional fix",
                compliance_impact=[],
            )

            assert finding.is_blocking() is False


class TestSecurityScannerInitialization:
    """Test SecurityScanner initialization."""

    def test_scanner_initialization(self):
        """Scanner should be initialized with subscription ID."""
        from azlin.network_security.security_scanner import SecurityScanner

        scanner = SecurityScanner(subscription_id="test-sub-123")

        assert scanner.subscription_id == "test-sub-123"


class TestSecurityScannerNSGScanning:
    """Test NSG security scanning."""

    @patch("subprocess.run")
    def test_scan_nsg_retrieves_nsg_configuration(self, mock_run):
        """scan_nsg should retrieve NSG configuration via Azure CLI."""
        from azlin.network_security.security_scanner import SecurityScanner

        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "/subscriptions/test/nsg1",
                    "name": "test-nsg",
                    "securityRules": [],
                }
            ),
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        with patch.object(scanner, "_query_security_center", return_value=[]):
            with patch.object(scanner, "_local_nsg_validation", return_value=[]):
                findings = scanner.scan_nsg(nsg_name="test-nsg", resource_group="test-rg")

        # Verify Azure CLI was called
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "network" in call_args
        assert "nsg" in call_args
        assert "show" in call_args

    @patch("subprocess.run")
    def test_scan_nsg_raises_error_on_cli_failure(self, mock_run):
        """scan_nsg should raise error when Azure CLI fails."""
        from azlin.network_security.security_scanner import (
            SecurityScanner,
            SecurityScannerError,
        )

        mock_run.return_value = Mock(returncode=1, stderr="NSG not found")

        scanner = SecurityScanner(subscription_id="test-sub")

        with pytest.raises(SecurityScannerError, match="Failed to retrieve NSG"):
            scanner.scan_nsg(nsg_name="missing-nsg", resource_group="test-rg")


class TestSecurityScannerLocalNSGValidation:
    """Test local NSG validation (without Azure Security Center)."""

    def test_local_validation_detects_ssh_from_internet(self):
        """Local validation should detect SSH exposed to internet."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        nsg_config = {
            "id": "/subscriptions/test/nsg1",
            "securityRules": [
                {
                    "name": "allow-ssh",
                    "destinationPortRange": "22",
                    "sourceAddressPrefix": "*",
                    "access": "Allow",
                    "direction": "Inbound",
                }
            ],
        }

        findings = scanner._local_nsg_validation(nsg_config)

        assert len(findings) > 0
        assert any(f.severity == ScanSeverity.CRITICAL for f in findings)
        assert any("ssh" in f.title.lower() or "22" in f.title for f in findings)

    def test_local_validation_detects_rdp_from_internet(self):
        """Local validation should detect RDP exposed to internet."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        nsg_config = {
            "id": "/subscriptions/test/nsg1",
            "securityRules": [
                {
                    "name": "allow-rdp",
                    "destinationPortRange": "3389",
                    "sourceAddressPrefix": "*",
                    "access": "Allow",
                    "direction": "Inbound",
                }
            ],
        }

        findings = scanner._local_nsg_validation(nsg_config)

        assert len(findings) > 0
        assert any(f.severity == ScanSeverity.CRITICAL for f in findings)
        assert any("rdp" in f.title.lower() or "3389" in f.title for f in findings)

    def test_local_validation_detects_missing_deny_default(self):
        """Local validation should detect missing deny-all default rule."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        nsg_config = {
            "id": "/subscriptions/test/nsg1",
            "securityRules": [
                # No deny-all rule with priority 4096
                {
                    "name": "allow-https",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "destinationPortRange": "443",
                    "sourceAddressPrefix": "*",
                }
            ],
        }

        findings = scanner._local_nsg_validation(nsg_config)

        assert any("deny" in f.title.lower() for f in findings)
        assert any(f.severity == ScanSeverity.HIGH for f in findings)

    def test_local_validation_passes_secure_nsg(self):
        """Secure NSG with deny-default should pass local validation."""
        from azlin.network_security.security_scanner import SecurityScanner

        scanner = SecurityScanner(subscription_id="test-sub")

        nsg_config = {
            "id": "/subscriptions/test/nsg1",
            "securityRules": [
                {
                    "name": "allow-https",
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "destinationPortRange": "443",
                    "sourceAddressPrefix": "Internet",
                },
                {
                    "name": "deny-all",
                    "priority": 4096,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "*",
                },
            ],
        }

        findings = scanner._local_nsg_validation(nsg_config)

        # Should have no critical findings
        assert all(f.severity != "CRITICAL" for f in findings)


class TestSecurityScannerAzureSecurityCenter:
    """Test Azure Security Center integration (mocked)."""

    @patch("subprocess.run")
    def test_query_security_center_calls_az_cli(self, mock_run):
        """_query_security_center should call Azure CLI."""
        from azlin.network_security.security_scanner import SecurityScanner

        mock_run.return_value = Mock(returncode=0, stdout="[]")

        scanner = SecurityScanner(subscription_id="test-sub")
        findings = scanner._query_security_center(resource_id="/subscriptions/test/nsg1")

        # Verify az security assessment list was called
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "security" in call_args
        assert "assessment" in call_args

    @patch("subprocess.run")
    def test_query_security_center_maps_assessments_to_findings(self, mock_run):
        """_query_security_center should map assessments to SecurityFindings."""
        from azlin.network_security.security_scanner import SecurityScanner

        assessments = [
            {
                "id": "/assessment-1",
                "displayName": "NSG rule too permissive",
                "description": "Test description",
                "status": {"severity": "High"},
                "resourceDetails": {"resourceType": "network"},
                "remediation": "Restrict access",
                "complianceRelevance": ["CIS-6.2"],
            }
        ]

        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(assessments))

        scanner = SecurityScanner(subscription_id="test-sub")
        findings = scanner._query_security_center(resource_id="/subscriptions/test/nsg1")

        assert len(findings) == 1
        assert findings[0].title == "NSG rule too permissive"

    def test_map_severity_converts_azure_severity_to_scan_severity(self):
        """_map_severity should convert Azure severity to ScanSeverity enum."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        # Test all severity mappings
        assert scanner._map_severity("Critical") == ScanSeverity.CRITICAL
        assert scanner._map_severity("High") == ScanSeverity.HIGH
        assert scanner._map_severity("Medium") == ScanSeverity.MEDIUM
        assert scanner._map_severity("Low") == ScanSeverity.LOW


class TestSecurityScannerVMScanning:
    """Test VM security scanning."""

    @patch("subprocess.run")
    def test_scan_vm_detects_public_ip(self, mock_run):
        """scan_vm should flag VMs with public IPs."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        vm_config = {
            "id": "/subscriptions/test/vm1",
            "name": "test-vm",
            "publicIpAddress": "1.2.3.4",  # Has public IP
        }

        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(vm_config))

        scanner = SecurityScanner(subscription_id="test-sub")

        with patch.object(scanner, "_query_security_center", return_value=[]):
            findings = scanner.scan_vm(vm_name="test-vm", resource_group="test-rg")

        assert len(findings) > 0
        assert any("public ip" in f.title.lower() for f in findings)
        assert any(f.severity == ScanSeverity.HIGH for f in findings)

    @patch("subprocess.run")
    def test_scan_vm_passes_for_private_vm(self, mock_run):
        """scan_vm should pass for VMs without public IPs."""
        from azlin.network_security.security_scanner import SecurityScanner

        vm_config = {
            "id": "/subscriptions/test/vm1",
            "name": "test-vm",
            # No publicIpAddress field
        }

        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(vm_config))

        scanner = SecurityScanner(subscription_id="test-sub")

        with patch.object(scanner, "_query_security_center", return_value=[]):
            findings = scanner.scan_vm(vm_name="test-vm", resource_group="test-rg")

        # Should not have public IP finding
        assert not any("public ip" in f.title.lower() for f in findings)


class TestSecurityScannerPreDeploymentScanning:
    """Test pre-deployment security scanning."""

    def test_pre_deployment_scan_validates_nsg_templates(self):
        """Pre-deployment scan should validate NSG templates."""
        from azlin.network_security.security_scanner import SecurityScanner

        scanner = SecurityScanner(subscription_id="test-sub")

        template = {
            "resources": [
                {
                    "type": "Microsoft.Network/networkSecurityGroups",
                    "name": "test-nsg",
                    "properties": {"securityRules": []},
                }
            ]
        }

        with patch("azlin.network_security.nsg_validator.NSGValidator") as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate_template.return_value = Mock(critical_issues=[])
            mock_validator_class.return_value = mock_validator

            can_deploy, findings = scanner.pre_deployment_scan(
                resource_group="test-rg", template=template
            )

        assert mock_validator.validate_template.called

    def test_pre_deployment_scan_blocks_on_critical_findings(self):
        """Pre-deployment scan should block deployment on critical findings."""
        from azlin.network_security.security_scanner import (
            ScanSeverity,
            SecurityScanner,
        )

        scanner = SecurityScanner(subscription_id="test-sub")

        template = {
            "resources": [
                {
                    "type": "Microsoft.Network/networkSecurityGroups",
                    "name": "bad-nsg",
                    "properties": {"securityRules": []},
                }
            ]
        }

        with patch("azlin.network_security.nsg_validator.NSGValidator") as mock_validator_class:
            from azlin.network_security.nsg_validator import PolicyFinding

            mock_validator = Mock()
            mock_validator.validate_template.return_value = Mock(
                critical_issues=[
                    PolicyFinding(
                        name="ssh-exposed",
                        severity="CRITICAL",
                        message="SSH exposed to internet",
                        remediation="Close port 22",
                        compliance_impact=["CIS-6.2"],
                    )
                ]
            )
            mock_validator_class.return_value = mock_validator

            can_deploy, findings = scanner.pre_deployment_scan(
                resource_group="test-rg", template=template
            )

        assert can_deploy is False
        assert len(findings) > 0
        assert any(f.severity == ScanSeverity.CRITICAL for f in findings)

    def test_pre_deployment_scan_allows_deployment_with_no_critical_findings(self):
        """Pre-deployment scan should allow deployment with no critical findings."""
        from azlin.network_security.security_scanner import SecurityScanner

        scanner = SecurityScanner(subscription_id="test-sub")

        template = {
            "resources": [
                {
                    "type": "Microsoft.Network/networkSecurityGroups",
                    "name": "good-nsg",
                    "properties": {"securityRules": []},
                }
            ]
        }

        with patch("azlin.network_security.nsg_validator.NSGValidator") as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate_template.return_value = Mock(critical_issues=[])
            mock_validator_class.return_value = mock_validator

            can_deploy, findings = scanner.pre_deployment_scan(
                resource_group="test-rg", template=template
            )

        assert can_deploy is True
