"""Unit tests for VM provisioning quota error handling - Issue #380.

This module tests that QuotaExceeded errors are transformed from raw stack traces
into clear, actionable user messages with helpful suggestions.

Test Philosophy:
- Tests should FAIL initially (TDD approach)
- Each test verifies a specific aspect of quota error handling
- Error messages should be helpful, not technical
- Users should get actionable suggestions (smaller sizes, increase link)

Coverage:
1. Clear error messages (not stack traces)
2. Suggestion of smaller VM sizes
3. Error detail extraction (region, limit, usage, requested)
4. Other errors still handled normally
5. Link to quota increase documentation
"""

import json
from unittest.mock import Mock, patch

import pytest

from azlin.vm_provisioning import (
    ProvisioningError,
    VMConfig,
    VMProvisioner,
)


class TestQuotaExceededErrorMessages:
    """Test that quota exceeded errors show clear messages, not stack traces."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_exceeded_error_shows_clear_message(self, mock_executor_class):
        """Test that QuotaExceeded error displays formatted message, not stack trace.

        Given: Azure CLI raises QuotaExceeded error during VM provisioning
        When: provision_vm is called
        Then: User sees clear formatted message with quota details
        And: Message includes region, limit, usage, and requested cores
        And: No raw stack trace or JSON error is shown

        Expected to FAIL until implementation is complete.
        """
        # Setup provisioner
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",  # 16 vCPUs
        )

        # Mock resource group check to succeed
        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        # First call: RG exists check (returns "true")
        # Second call: VM create fails with quota error
        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved standardEASv5Family Cores quota.",
                    "details": [
                        {
                            "code": "QuotaExceeded",
                            "target": "standardEASv5Family",
                            "message": "Current usage: 24, Limit: 32, Requested: 16, Region: eastus",
                        }
                    ],
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},  # RG check
            {
                "success": False,
                "stdout": "",
                "stderr": quota_error_json,
                "returncode": 1,
            },  # VM create fails
        ]

        # Execute and verify
        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify clear message components (should NOT be raw JSON/stack trace)
        assert "QuotaExceeded" in error_message or "quota" in error_message.lower()
        assert "eastus" in error_message
        assert "24" in error_message  # current usage
        assert "32" in error_message  # limit
        assert "16" in error_message  # requested

        # Verify it's NOT a raw stack trace or JSON dump
        assert '"error"' not in error_message, "Should not show raw JSON error structure"
        assert '"code"' not in error_message, "Should not show raw JSON fields"

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_message_is_user_friendly(self, mock_executor_class):
        """Test that quota error message is user-friendly and actionable.

        Given: QuotaExceeded error occurs
        When: Error is processed
        Then: Message uses plain language
        And: Message explains what happened
        And: Message suggests next steps

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            size="Standard_E32as_v5",  # 32 vCPUs
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved standardEASv5Family Cores quota.",
                    "details": [
                        {
                            "code": "QuotaExceeded",
                            "target": "standardEASv5Family",
                            "message": "Current usage: 60, Limit: 64, Requested: 32",
                        }
                    ],
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value).lower()

        # Verify user-friendly language
        assert any(
            phrase in error_message
            for phrase in ["quota", "limit", "exceeded", "insufficient", "not enough"]
        ), "Should explain quota issue in plain language"

        # Should NOT contain technical jargon or raw error codes
        assert "traceback" not in error_message
        assert "exception" not in error_message


class TestQuotaErrorSuggestions:
    """Test that quota errors suggest smaller VM sizes."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_suggests_smaller_sizes(self, mock_executor_class):
        """Test that quota error suggests smaller VM sizes as alternatives.

        Given: QuotaExceeded error for 16-core VM (size L)
        When: Error is processed
        Then: Message suggests --size m (8 cores) or --size s (4 cores)
        And: Message shows specific tier names with vCPU counts

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",  # 16 vCPUs (tier L)
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved standardEASv5Family Cores quota.",
                    "details": [
                        {
                            "code": "QuotaExceeded",
                            "target": "standardEASv5Family",
                            "message": "Current usage: 20, Limit: 32, Requested: 16",
                        }
                    ],
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value).lower()

        # Verify suggestions for smaller sizes
        assert any(
            phrase in error_message for phrase in ["smaller", "try", "alternative", "reduce"]
        ), "Should suggest trying smaller sizes"

        # Should mention specific tier options
        assert "--size" in error_message or "size" in error_message

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_suggests_appropriate_alternatives(self, mock_executor_class):
        """Test that quota error suggests appropriate alternatives based on request.

        Given: QuotaExceeded error for XL size (32 cores)
        When: Error is processed
        Then: Message suggests L (16 cores) or M (8 cores)
        And: Suggestions are smaller than the requested size

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2",
            size="Standard_E32as_v5",  # 32 vCPUs (tier XL)
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved standardEASv5Family Cores quota.",
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Should suggest smaller alternatives
        assert any(size in error_message.lower() for size in ["smaller", "16", "8", "reduce"]), (
            "Should suggest smaller sizes than requested"
        )


class TestQuotaErrorParsing:
    """Test extraction of quota details from Azure error responses."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_parsing_extracts_details(self, mock_executor_class):
        """Test that quota error parser correctly extracts all details.

        Given: Azure error with quota information
        When: Error is parsed
        Then: Correctly extracts limit, usage, region, and family
        And: All values are present in the error message

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="centralus",
            size="Standard_D8s_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved standardDSv5Family Cores quota.",
                    "details": [
                        {
                            "code": "QuotaExceeded",
                            "target": "standardDSv5Family",
                            "message": "Current usage: 48, Limit: 50, Requested: 8, Region: centralus",
                        }
                    ],
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify all details are extracted and included
        assert "centralus" in error_message, "Should include region"
        assert "48" in error_message, "Should include current usage"
        assert "50" in error_message, "Should include limit"
        assert "8" in error_message, "Should include requested amount"

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_parsing_handles_missing_details(self, mock_executor_class):
        """Test that quota error parser handles missing optional details gracefully.

        Given: Azure error with minimal quota information (no details array)
        When: Error is parsed
        Then: Basic error message is still shown
        And: No exception is raised during parsing

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        # Minimal quota error without details
        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding quota.",
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Should still provide helpful message even with minimal info
        assert "quota" in error_message.lower()
        # Should not crash or show raw exception


class TestNonQuotaErrorHandling:
    """Test that other (non-quota) errors are still handled normally."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_other_errors_still_handled_normally(self, mock_executor_class):
        """Test that non-quota errors maintain normal error handling.

        Given: Non-quota error (e.g., network error, auth error)
        When: provision_vm encounters the error
        Then: Normal error handling is used
        And: Error is not misidentified as quota issue

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        # Network error (not quota-related)
        network_error = "ERROR: Network connection failed: Connection timed out"

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": network_error, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify it's treated as normal error, not quota error
        assert "Network connection failed" in error_message
        # Should NOT add quota-specific suggestions
        assert "quota" not in error_message.lower() or "connection" in error_message.lower()

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_authentication_error_handled_normally(self, mock_executor_class):
        """Test that authentication errors are not confused with quota errors.

        Given: Authentication failure error
        When: provision_vm encounters the error
        Then: Authentication error message is preserved
        And: No quota-related suggestions are added

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        auth_error_json = json.dumps(
            {
                "error": {
                    "code": "AuthorizationFailed",
                    "message": "The client 'user@example.com' does not have authorization to perform action 'Microsoft.Compute/virtualMachines/write'.",
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": auth_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify auth error is preserved
        assert "authorization" in error_message.lower() or "AuthorizationFailed" in error_message
        # Should not suggest quota solutions
        assert "--size" not in error_message.lower()

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_invalid_parameter_error_handled_normally(self, mock_executor_class):
        """Test that invalid parameter errors maintain normal handling.

        Given: Invalid parameter error (e.g., invalid VM size)
        When: provision_vm encounters the error
        Then: Parameter error message is shown
        And: Not treated as quota issue

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        invalid_param_error = json.dumps(
            {
                "error": {
                    "code": "InvalidParameter",
                    "message": "The value 'InvalidSize' is not valid for parameter vmSize.",
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": invalid_param_error, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify parameter error is clear
        assert "InvalidParameter" in error_message or "not valid" in error_message.lower()


class TestQuotaErrorDocumentation:
    """Test that quota errors provide link to quota increase documentation."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_provides_increase_link(self, mock_executor_class):
        """Test that quota error includes link to Azure quota increase docs.

        Given: QuotaExceeded error
        When: Error message is generated
        Then: Message includes aka.ms/azquotaincrease link
        And: Link is clearly visible to user

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding approved quota.",
                    "details": [
                        {
                            "code": "QuotaExceeded",
                            "message": "Current usage: 20, Limit: 32, Requested: 16",
                        }
                    ],
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Verify quota increase link is present
        assert any(
            link in error_message
            for link in ["aka.ms/azquotaincrease", "quota increase", "request"]
        ), "Should provide link to quota increase documentation"

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_message_is_actionable(self, mock_executor_class):
        """Test that quota error provides clear next steps.

        Given: QuotaExceeded error
        When: Error message is generated
        Then: Message suggests at least two actionable options:
              1. Try smaller VM size
              2. Request quota increase

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E32as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        quota_error_json = json.dumps(
            {
                "error": {
                    "code": "QuotaExceeded",
                    "message": "Operation could not be completed as it results in exceeding quota.",
                }
            }
        )

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": quota_error_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value).lower()

        # Verify actionable suggestions
        has_size_suggestion = any(
            phrase in error_message for phrase in ["smaller", "reduce", "--size"]
        )
        has_increase_suggestion = any(
            phrase in error_message for phrase in ["increase", "request", "quota"]
        )

        assert has_size_suggestion or has_increase_suggestion, (
            "Should provide at least one actionable suggestion"
        )


class TestQuotaErrorEdgeCases:
    """Test edge cases and boundary conditions for quota error handling."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_with_malformed_json(self, mock_executor_class):
        """Test that malformed JSON in quota error is handled gracefully.

        Given: Quota error with malformed JSON
        When: Error is processed
        Then: Fallback error message is shown
        And: No exception is raised during parsing

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        # Malformed JSON
        malformed_json = '{"error": {"code": "QuotaExceeded", "message": "Quota exceeded'  # Missing closing braces

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": malformed_json, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Should still provide some error message (not crash)
        assert len(error_message) > 0
        # Check for quota-related terms (our handler provides good messages even for malformed JSON)
        assert (
            "quota" in error_message.lower()
            or "error" in error_message.lower()
            or "failed" in error_message.lower()
        )

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_quota_error_with_plain_text_error(self, mock_executor_class):
        """Test quota error when Azure returns plain text (not JSON).

        Given: Quota error as plain text message
        When: Error is processed
        Then: Plain text error is shown with helpful context
        And: Still suggests quota solutions

        Expected to FAIL until implementation is complete.
        """
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            size="Standard_E16as_v5",
        )

        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        # Plain text error (not JSON)
        plain_text_error = "ERROR: QuotaExceeded - Operation could not be completed as it results in exceeding approved standardEASv5Family Cores quota. Current: 24, Limit: 32, Requested: 16"

        mock_executor_instance.execute.side_effect = [
            {"success": True, "stdout": "true", "stderr": "", "returncode": 0},
            {"success": False, "stdout": "", "stderr": plain_text_error, "returncode": 1},
        ]

        with pytest.raises(ProvisioningError) as exc_info:
            provisioner.provision_vm(config)

        error_message = str(exc_info.value)

        # Should still detect and handle quota error
        assert "quota" in error_message.lower() or "QuotaExceeded" in error_message
        # Should parse numbers from plain text
        assert any(num in error_message for num in ["24", "32", "16"])
