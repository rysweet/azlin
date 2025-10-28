"""Unit tests for IP diagnostics - Issue #186: IP classification and connectivity checks.

These tests verify IP classification (especially Azure public IPs in 172.171.x.x range),
connectivity testing, NSG rule checking, and diagnostic output formatting.

TDD approach: These tests will FAIL until the implementation is created.
"""

import json
from unittest.mock import Mock, patch, MagicMock

import pytest


class TestIPClassification:
    """Test IP address classification - Critical for Issue #186."""

    # =========================================================================
    # Test 1: Azure Public IP Detection (172.171.x.x) - THE CRITICAL TEST
    # =========================================================================

    def test_classify_azure_public_ip_172_171_range(self):
        """Test that 172.171.118.91 is correctly classified as Public-Azure.

        This is the CORE problem we're solving: IPs in 172.171.x.x range
        look private but are actually Azure public IPs.

        Expected to FAIL until implementation is created.
        """
        from azlin.ip_diagnostics import classify_ip_address

        ip = "172.171.118.91"
        result = classify_ip_address(ip)

        assert result == "Public-Azure", (
            f"IP {ip} should be classified as Public-Azure, "
            f"not {result}. This is Azure's public IP range!"
        )

    def test_classify_azure_public_ip_lower_bound(self):
        """Test 172.171.0.0 is classified as Public-Azure (lower boundary)."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "172.171.0.0"
        result = classify_ip_address(ip)

        assert result == "Public-Azure"

    def test_classify_azure_public_ip_upper_bound(self):
        """Test 172.171.255.255 is classified as Public-Azure (upper boundary)."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "172.171.255.255"
        result = classify_ip_address(ip)

        assert result == "Public-Azure"

    # =========================================================================
    # Test 2: Standard Public IP Detection
    # =========================================================================

    def test_classify_standard_public_ip(self):
        """Test that 4.155.169.201 is classified as Public."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "4.155.169.201"
        result = classify_ip_address(ip)

        assert result == "Public"

    def test_classify_public_ip_8_8_8_8(self):
        """Test that 8.8.8.8 (Google DNS) is classified as Public."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "8.8.8.8"
        result = classify_ip_address(ip)

        assert result == "Public"

    # =========================================================================
    # Test 3: Private IP Detection
    # =========================================================================

    def test_classify_private_ip_10_network(self):
        """Test that 10.0.0.24 is classified as Private."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "10.0.0.24"
        result = classify_ip_address(ip)

        assert result == "Private"

    def test_classify_private_ip_192_168_network(self):
        """Test that 192.168.1.1 is classified as Private."""
        from azlin.ip_diagnostics import classify_ip_address

        ip = "192.168.1.1"
        result = classify_ip_address(ip)

        assert result == "Private"

    def test_classify_private_ip_172_16_to_31_range(self):
        """Test that 172.16.0.0-172.31.255.255 is classified as Private.

        Important: This should NOT include 172.171.x.x!
        """
        from azlin.ip_diagnostics import classify_ip_address

        # Test standard RFC1918 172.16-31 range
        assert classify_ip_address("172.16.0.0") == "Private"
        assert classify_ip_address("172.31.255.255") == "Private"
        assert classify_ip_address("172.20.10.5") == "Private"

    # =========================================================================
    # Test 4: Edge Cases and Boundaries
    # =========================================================================

    def test_classify_none_ip(self):
        """Test that None returns None classification."""
        from azlin.ip_diagnostics import classify_ip_address

        result = classify_ip_address(None)
        assert result is None

    def test_classify_empty_string(self):
        """Test that empty string returns None classification."""
        from azlin.ip_diagnostics import classify_ip_address

        result = classify_ip_address("")
        assert result is None

    def test_classify_invalid_ip_format(self):
        """Test that invalid IP format raises ValueError."""
        from azlin.ip_diagnostics import classify_ip_address

        with pytest.raises(ValueError, match="Invalid IP address"):
            classify_ip_address("not.an.ip.address")

    def test_classify_localhost(self):
        """Test that 127.0.0.1 is classified as Private."""
        from azlin.ip_diagnostics import classify_ip_address

        result = classify_ip_address("127.0.0.1")
        assert result == "Private"


class TestConnectivityTesting:
    """Test connectivity testing functionality."""

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_connectivity_success(self, mock_run):
        """Test successful connectivity check returns True."""
        from azlin.ip_diagnostics import check_connectivity

        # Mock successful ping
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = check_connectivity("8.8.8.8")
        assert result is True

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_connectivity_failure(self, mock_run):
        """Test failed connectivity check returns False."""
        from azlin.ip_diagnostics import check_connectivity

        # Mock failed ping
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="timeout")

        result = check_connectivity("192.168.1.1")
        assert result is False

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_connectivity_with_timeout(self, mock_run):
        """Test connectivity check with custom timeout."""
        from azlin.ip_diagnostics import check_connectivity

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = check_connectivity("8.8.8.8", timeout=5)
        assert result is True

        # Verify timeout was passed correctly
        mock_run.assert_called_once()
        assert mock_run.call_args[1]["timeout"] == 5

    def test_check_connectivity_none_ip(self):
        """Test that checking connectivity of None IP raises ValueError."""
        from azlin.ip_diagnostics import check_connectivity

        with pytest.raises(ValueError, match="IP address cannot be None"):
            check_connectivity(None)


class TestNSGRuleChecking:
    """Test NSG rule checking functionality."""

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_nsg_rules_finds_allow_rule(self, mock_run):
        """Test that NSG check finds allow rule for SSH."""
        from azlin.ip_diagnostics import check_nsg_rules

        nsg_data = {
            "securityRules": [
                {
                    "name": "AllowSSH",
                    "access": "Allow",
                    "destinationPortRange": "22",
                    "direction": "Inbound",
                    "priority": 100,
                    "sourceAddressPrefix": "*",
                }
            ]
        }

        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps(nsg_data), stderr=""
        )

        result = check_nsg_rules("test-rg", "test-nsg", port=22)

        assert result["allowed"] is True
        assert result["rule_name"] == "AllowSSH"

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_nsg_rules_finds_deny_rule(self, mock_run):
        """Test that NSG check identifies deny rule."""
        from azlin.ip_diagnostics import check_nsg_rules

        nsg_data = {
            "securityRules": [
                {
                    "name": "DenySSH",
                    "access": "Deny",
                    "destinationPortRange": "22",
                    "direction": "Inbound",
                    "priority": 100,
                    "sourceAddressPrefix": "*",
                }
            ]
        }

        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps(nsg_data), stderr=""
        )

        result = check_nsg_rules("test-rg", "test-nsg", port=22)

        assert result["allowed"] is False
        assert result["rule_name"] == "DenySSH"

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_nsg_rules_no_matching_rule(self, mock_run):
        """Test NSG check when no rule matches the port."""
        from azlin.ip_diagnostics import check_nsg_rules

        nsg_data = {
            "securityRules": [
                {
                    "name": "AllowHTTP",
                    "access": "Allow",
                    "destinationPortRange": "80",
                    "direction": "Inbound",
                    "priority": 100,
                }
            ]
        }

        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps(nsg_data), stderr=""
        )

        result = check_nsg_rules("test-rg", "test-nsg", port=22)

        assert result["allowed"] is False
        assert result["rule_name"] is None

    @patch("azlin.ip_diagnostics.subprocess.run")
    def test_check_nsg_rules_azure_cli_error(self, mock_run):
        """Test NSG check handles Azure CLI errors."""
        from azlin.ip_diagnostics import check_nsg_rules

        mock_run.return_value = Mock(returncode=1, stdout="", stderr="NSG not found")

        with pytest.raises(RuntimeError, match="Failed to query NSG"):
            check_nsg_rules("test-rg", "nonexistent-nsg", port=22)


class TestDiagnosticOutput:
    """Test diagnostic output formatting."""

    def test_format_diagnostic_report_public_azure_ip(self):
        """Test formatting report for Azure public IP."""
        from azlin.ip_diagnostics import format_diagnostic_report

        diagnostic_data = {
            "ip": "172.171.118.91",
            "classification": "Public-Azure",
            "connectivity": True,
            "nsg_check": {"allowed": True, "rule_name": "AllowSSH"},
        }

        report = format_diagnostic_report(diagnostic_data)

        assert "172.171.118.91" in report
        assert "Public-Azure" in report
        assert "Connectivity: Success" in report
        assert "AllowSSH" in report

    def test_format_diagnostic_report_private_ip(self):
        """Test formatting report for private IP."""
        from azlin.ip_diagnostics import format_diagnostic_report

        diagnostic_data = {
            "ip": "10.0.0.24",
            "classification": "Private",
            "connectivity": False,
            "nsg_check": None,
        }

        report = format_diagnostic_report(diagnostic_data)

        assert "10.0.0.24" in report
        assert "Private" in report
        assert "Connectivity: Failed" in report

    def test_format_diagnostic_report_none_ip(self):
        """Test formatting report for None IP."""
        from azlin.ip_diagnostics import format_diagnostic_report

        diagnostic_data = {
            "ip": None,
            "classification": None,
            "connectivity": None,
            "nsg_check": None,
        }

        report = format_diagnostic_report(diagnostic_data)

        assert "No IP" in report or "None" in report


class TestIPDiagnosticsIntegration:
    """Integration tests for complete diagnostic flow."""

    @patch("azlin.ip_diagnostics.subprocess.run")
    @patch("azlin.ip_diagnostics.check_connectivity")
    def test_run_full_diagnostic_azure_public_ip(self, mock_connectivity, mock_run):
        """Test complete diagnostic flow for Azure public IP 172.171.118.91."""
        from azlin.ip_diagnostics import run_ip_diagnostic

        # Mock NSG query
        nsg_data = {
            "securityRules": [
                {
                    "name": "AllowSSH",
                    "access": "Allow",
                    "destinationPortRange": "22",
                    "direction": "Inbound",
                    "priority": 100,
                }
            ]
        }
        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps(nsg_data), stderr=""
        )

        # Mock connectivity
        mock_connectivity.return_value = True

        result = run_ip_diagnostic(
            ip="172.171.118.91",
            resource_group="test-rg",
            nsg_name="test-nsg",
            check_port=22,
        )

        # Verify classification
        assert result["classification"] == "Public-Azure"
        assert result["connectivity"] is True
        assert result["nsg_check"]["allowed"] is True

    @patch("azlin.ip_diagnostics.check_connectivity")
    def test_run_diagnostic_skip_nsg_when_no_rg(self, mock_connectivity):
        """Test diagnostic skips NSG check when resource group not provided."""
        from azlin.ip_diagnostics import run_ip_diagnostic

        mock_connectivity.return_value = True

        result = run_ip_diagnostic(ip="8.8.8.8")

        assert result["classification"] == "Public"
        assert result["nsg_check"] is None


# =========================================================================
# Parametrized tests for comprehensive IP coverage
# =========================================================================


@pytest.mark.parametrize(
    ("ip", "expected_classification"),
    [
        # Azure public IPs
        ("172.171.0.0", "Public-Azure"),
        ("172.171.118.91", "Public-Azure"),
        ("172.171.255.255", "Public-Azure"),
        # Standard public IPs
        ("4.155.169.201", "Public"),
        ("8.8.8.8", "Public"),
        ("1.1.1.1", "Public"),
        # Private IPs
        ("10.0.0.24", "Private"),
        ("192.168.1.1", "Private"),
        ("172.16.0.0", "Private"),
        ("172.31.255.255", "Private"),
        # Edge cases
        (None, None),
        ("", None),
    ],
)
def test_ip_classification_parametrized(ip, expected_classification):
    """Parametrized test for IP classification across all categories."""
    from azlin.ip_diagnostics import classify_ip_address

    result = classify_ip_address(ip)
    assert result == expected_classification, (
        f"IP {ip} should be {expected_classification}, got {result}"
    )
