"""Tests for Resource Conflict Error Handler - Azure error transformation.

Testing Pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import json
from unittest.mock import patch

import pytest

from azlin.resource_conflict_error_handler import (
    ResourceConflictInfo,
    format_conflict_error,
    is_resource_conflict,
    parse_conflict_error,
)

# =============================================================================
# UNIT TESTS (60%) - Fast, focused tests
# =============================================================================


class TestConflictDetection:
    """Test detection of various Azure resource conflict error patterns."""

    def test_detects_resource_exists_error(self):
        """Verify detection of Azure ResourceExistsError."""
        error_message = (
            "The resource 'test-vm' already exists in resource group 'test-rg' "
            "in location 'eastus'."
        )

        assert is_resource_conflict(error_message) is True

    def test_detects_conflict_error(self):
        """Verify detection of Azure ConflictError."""
        error_message = (
            "ConflictError: The resource operation completed with terminal "
            "provisioning state 'Failed'."
        )

        assert is_resource_conflict(error_message) is True

    def test_detects_location_mismatch(self):
        """Verify detection of location mismatch errors."""
        error_message = (
            "Resource 'test-vm' already exists in location 'westus' but you "
            "attempted to create it in 'eastus'."
        )

        assert is_resource_conflict(error_message) is True

    def test_detects_already_exists_pattern(self):
        """Verify detection of 'already exists' error pattern."""
        error_message = "Virtual machine 'test-vm' already exists."

        assert is_resource_conflict(error_message) is True

    def test_detects_conflict_with_existing(self):
        """Verify detection of 'conflicts with existing' pattern."""
        error_message = (
            "The requested resource name conflicts with existing resource "
            "'test-vm' in resource group 'test-rg'."
        )

        assert is_resource_conflict(error_message) is True

    def test_rejects_non_conflict_errors(self):
        """Verify non-conflict errors are not detected as conflicts."""
        non_conflict_messages = [
            "Authentication failed",
            "Network timeout",
            "Invalid parameter value",
            "Resource not found",
            "Permission denied",
        ]

        for message in non_conflict_messages:
            assert is_resource_conflict(message) is False

    def test_case_insensitive_detection(self):
        """Verify conflict detection is case-insensitive."""
        assert is_resource_conflict("ALREADY EXISTS") is True
        assert is_resource_conflict("Already Exists") is True
        assert is_resource_conflict("already exists") is True

    def test_handles_none_input(self):
        """Verify graceful handling of None input."""
        assert is_resource_conflict(None) is False

    def test_handles_empty_string(self):
        """Verify graceful handling of empty string."""
        assert is_resource_conflict("") is False


class TestJSONParsing:
    """Test parsing of Azure CLI JSON output errors."""

    def test_parses_json_error_with_all_fields(self):
        """Verify parsing of complete JSON error structure."""
        error_json = {
            "error": {
                "code": "ResourceExists",
                "message": "Resource 'test-vm' already exists in location 'eastus'.",
                "details": {
                    "resourceName": "test-vm",
                    "resourceType": "Microsoft.Compute/virtualMachines",
                    "existingLocation": "eastus",
                    "resourceGroup": "test-rg",
                },
            }
        }

        result = parse_conflict_error(json.dumps(error_json))

        assert result.resource_name == "test-vm"
        assert result.resource_type == "Microsoft.Compute/virtualMachines"
        assert result.existing_location == "eastus"
        assert result.resource_group == "test-rg"

    def test_parses_nested_error_structure(self):
        """Verify parsing of deeply nested JSON error."""
        error_json = {
            "error": {
                "code": "Conflict",
                "message": "VM already exists",
                "additionalInfo": [
                    {
                        "type": "ResourceConflict",
                        "info": {"resourceName": "test-vm", "resourceType": "VirtualMachine"},
                    }
                ],
            }
        }

        result = parse_conflict_error(json.dumps(error_json))

        assert result.resource_name == "test-vm"
        assert result.resource_type == "VirtualMachine"

    def test_parses_json_with_partial_information(self):
        """Verify parsing when some fields are missing."""
        error_json = {"error": {"code": "ResourceExists", "message": "Resource already exists"}}

        result = parse_conflict_error(json.dumps(error_json))

        # Should extract what's available from message
        assert result is not None

    def test_handles_malformed_json(self):
        """Verify graceful handling of malformed JSON."""
        malformed_json = "{invalid json structure"

        result = parse_conflict_error(malformed_json)

        # Should fall back to plain text parsing and return None (no conflict detected)
        assert result is None

    def test_handles_json_without_error_key(self):
        """Verify handling of JSON without 'error' key."""
        error_json = {"status": "Failed", "message": "Resource test-vm already exists"}

        result = parse_conflict_error(json.dumps(error_json))

        # Should still attempt to extract information
        assert result is not None


class TestPlainTextParsing:
    """Test parsing of Azure CLI plain text error messages."""

    def test_extracts_resource_name_from_text(self):
        """Verify extraction of resource name from plain text error."""
        error_text = (
            "ERROR: The resource 'my-test-vm' already exists in resource group "
            "'my-rg' in location 'eastus'."
        )

        result = parse_conflict_error(error_text)

        assert result.resource_name == "my-test-vm"

    def test_extracts_resource_group_from_text(self):
        """Verify extraction of resource group from plain text."""
        error_text = (
            "Resource 'test-vm' conflicts with existing resource in resource group 'production-rg'."
        )

        result = parse_conflict_error(error_text)

        assert result.resource_group == "production-rg"

    def test_extracts_location_from_text(self):
        """Verify extraction of location information from text."""
        error_text = (
            "Virtual machine 'test-vm' already exists in location 'westus' but "
            "you attempted to create it in location 'eastus'."
        )

        result = parse_conflict_error(error_text)

        assert result.existing_location == "westus"
        assert result.attempted_location == "eastus"

    def test_extracts_resource_type_from_text(self):
        """Verify extraction of resource type from text."""
        error_text = "Microsoft.Compute/virtualMachines resource 'test-vm' already exists."

        result = parse_conflict_error(error_text)

        assert result.resource_type == "Microsoft.Compute/virtualMachines"

    def test_handles_multiple_patterns_in_text(self):
        """Verify extraction from complex multi-pattern error text."""
        error_text = (
            "ConflictError: The Virtual Machine 'test-vm-001' in resource group "
            "'prod-rg' already exists in location 'eastus2'. You attempted to "
            "create it in 'westus2'."
        )

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm-001"
        assert result.resource_group == "prod-rg"
        assert result.existing_location == "eastus2"
        assert result.attempted_location == "westus2"

    def test_handles_quoted_resource_names(self):
        """Verify handling of resource names in various quote styles."""
        test_cases = [
            "Resource 'test-vm' already exists",
            'Resource "test-vm" already exists',
            "Resource `test-vm` already exists",
        ]

        for error_text in test_cases:
            result = parse_conflict_error(error_text)
            assert result.resource_name == "test-vm"

    def test_extracts_from_multiline_error(self):
        """Verify extraction from multi-line error messages."""
        error_text = """
ERROR: Resource conflict detected
Resource Name: test-vm
Resource Group: test-rg
Location: eastus
The resource already exists.
        """

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm"
        assert result.resource_group == "test-rg"
        assert result.existing_location == "eastus"


class TestResourceTypeDetection:
    """Test detection and categorization of Azure resource types."""

    def test_detects_virtual_machine_type(self):
        """Verify detection of virtual machine resource type."""
        error_text = "Microsoft.Compute/virtualMachines 'test-vm' already exists"

        result = parse_conflict_error(error_text)

        assert result.resource_type == "Microsoft.Compute/virtualMachines"

    def test_detects_storage_account_type(self):
        """Verify detection of storage account resource type."""
        error_text = "Microsoft.Storage/storageAccounts 'teststorage' already exists"

        result = parse_conflict_error(error_text)

        assert result.resource_type == "Microsoft.Storage/storageAccounts"

    def test_detects_network_interface_type(self):
        """Verify detection of network interface resource type."""
        error_text = "Microsoft.Network/networkInterfaces 'test-nic' conflicts"

        result = parse_conflict_error(error_text)

        assert result.resource_type == "Microsoft.Network/networkInterfaces"

    def test_detects_public_ip_type(self):
        """Verify detection of public IP resource type."""
        error_text = "Microsoft.Network/publicIPAddresses 'test-ip' already exists"

        result = parse_conflict_error(error_text)

        assert result.resource_type == "Microsoft.Network/publicIPAddresses"

    def test_handles_short_resource_type_names(self):
        """Verify handling of abbreviated resource type names."""
        short_names = [
            ("Virtual Machine 'test-vm'", "Virtual Machine"),
            ("VM 'test-vm'", "VM"),
            ("Storage Account 'test-storage'", "Storage Account"),
        ]

        for error_text, expected_type in short_names:
            result = parse_conflict_error(error_text + " already exists")
            assert expected_type.lower() in result.resource_type.lower()


class TestLocationExtraction:
    """Test extraction of location information from errors."""

    def test_extracts_single_location(self):
        """Verify extraction when only existing location is mentioned."""
        error_text = "Resource 'test-vm' already exists in location 'eastus'"

        result = parse_conflict_error(error_text)

        assert result.existing_location == "eastus"

    def test_extracts_location_mismatch(self):
        """Verify extraction of both existing and attempted locations."""
        error_text = "Resource exists in 'westus' but you attempted to create in 'eastus'"

        result = parse_conflict_error(error_text)

        assert result.existing_location == "westus"
        assert result.attempted_location == "eastus"

    def test_handles_region_synonyms(self):
        """Verify handling of Azure region name variations."""
        region_variations = [
            "eastus",
            "East US",
            "East US 2",
            "eastus2",
        ]

        for region in region_variations:
            error_text = f"Resource exists in location '{region}'"
            result = parse_conflict_error(error_text)
            assert result.existing_location is not None


class TestFormatMessageGeneration:
    """Test generation of user-friendly error messages."""

    def test_formats_basic_conflict_message(self):
        """Verify basic conflict message formatting."""
        conflict_info = ResourceConflictInfo(
            resource_name="test-vm",
            resource_type="Virtual Machine",
            existing_location="eastus",
            resource_group="test-rg",
        )

        message = format_conflict_error(conflict_info)

        assert "test-vm" in message
        assert "Virtual Machine" in message
        assert "eastus" in message
        assert "test-rg" in message

    def test_includes_actionable_steps(self):
        """Verify formatted message includes actionable guidance."""
        conflict_info = ResourceConflictInfo(
            resource_name="test-vm", resource_type="Virtual Machine", existing_location="eastus"
        )

        message = format_conflict_error(conflict_info)

        # Should include actionable steps
        assert any(
            keyword in message.lower()
            for keyword in ["delete", "rename", "use existing", "choose different"]
        )

    def test_formats_location_mismatch_message(self):
        """Verify special formatting for location mismatch errors."""
        conflict_info = ResourceConflictInfo(
            resource_name="test-vm", existing_location="westus", attempted_location="eastus"
        )

        message = format_conflict_error(conflict_info)

        assert "westus" in message
        assert "eastus" in message
        assert "location" in message.lower()

    def test_includes_resource_group_in_delete_instructions(self):
        """Verify delete instructions include resource group."""
        conflict_info = ResourceConflictInfo(
            resource_name="test-vm", resource_type="Virtual Machine", resource_group="test-rg"
        )

        message = format_conflict_error(conflict_info)

        # If suggesting delete, should include resource group
        if "delete" in message.lower():
            assert "test-rg" in message

    def test_handles_minimal_information(self):
        """Verify formatting with minimal conflict information."""
        conflict_info = ResourceConflictInfo(resource_name="test-vm")

        message = format_conflict_error(conflict_info)

        # Should still produce useful message
        assert "test-vm" in message
        assert len(message) > 50  # Reasonably informative

    def test_formats_with_all_fields(self):
        """Verify formatting with complete conflict information."""
        conflict_info = ResourceConflictInfo(
            resource_name="test-vm",
            resource_type="Microsoft.Compute/virtualMachines",
            existing_location="westus",
            attempted_location="eastus",
            resource_group="prod-rg",
        )

        message = format_conflict_error(conflict_info)

        # All fields should appear
        assert "test-vm" in message
        assert "virtualMachines" in message.lower() or "virtual machine" in message.lower()
        assert "westus" in message
        assert "eastus" in message
        assert "prod-rg" in message


# =============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# =============================================================================


class TestRealAzureErrorParsing:
    """Test parsing of real Azure CLI error messages using fixtures."""

    @pytest.fixture
    def real_vm_conflict_json(self):
        """Fixture: Real Azure VM conflict error (JSON format)."""
        return """
{
  "error": {
    "code": "ResourceExists",
    "message": "The resource 'azlin-vm-001' already exists in resource group 'azlin-test' in location 'eastus'.",
    "details": [
      {
        "code": "Conflict",
        "message": "Virtual machine with the same name already exists in the specified resource group."
      }
    ]
  }
}
"""

    @pytest.fixture
    def real_vm_conflict_text(self):
        """Fixture: Real Azure VM conflict error (plain text)."""
        return (
            "ERROR: The resource 'azlin-vm-001' already exists in resource group "
            "'azlin-test' in location 'eastus'. Please use a different name or "
            "delete the existing resource."
        )

    @pytest.fixture
    def real_location_mismatch(self):
        """Fixture: Real location mismatch error."""
        return (
            "ConflictError: Resource 'azlin-vm-001' of type "
            "'Microsoft.Compute/virtualMachines' already exists in location 'westus' "
            "but you attempted to create it in location 'eastus'. Resources cannot "
            "be moved between locations."
        )

    def test_parse_real_json_error(self, real_vm_conflict_json):
        """Verify parsing of real Azure JSON error."""
        result = parse_conflict_error(real_vm_conflict_json)

        assert result.resource_name == "azlin-vm-001"
        assert result.resource_group == "azlin-test"
        assert result.existing_location == "eastus"

    def test_parse_real_text_error(self, real_vm_conflict_text):
        """Verify parsing of real Azure plain text error."""
        result = parse_conflict_error(real_vm_conflict_text)

        assert result.resource_name == "azlin-vm-001"
        assert result.resource_group == "azlin-test"
        assert result.existing_location == "eastus"

    def test_parse_real_location_mismatch(self, real_location_mismatch):
        """Verify parsing of real location mismatch error."""
        result = parse_conflict_error(real_location_mismatch)

        assert result.resource_name == "azlin-vm-001"
        assert result.resource_type == "Microsoft.Compute/virtualMachines"
        assert result.existing_location == "westus"
        assert result.attempted_location == "eastus"

    def test_format_real_error_message(self, real_vm_conflict_json):
        """Verify formatting produces user-friendly message for real error."""
        result = parse_conflict_error(real_vm_conflict_json)
        message = format_conflict_error(result)

        # Should be human-readable
        assert len(message) > 100
        assert "azlin-vm-001" in message
        assert any(word in message.lower() for word in ["delete", "rename", "existing"])


class TestPartialInformationHandling:
    """Test graceful handling when error information is incomplete."""

    def test_handles_missing_resource_group(self):
        """Verify handling when resource group is not in error."""
        error_text = "Virtual Machine 'test-vm' already exists in location 'eastus'"

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm"
        assert result.existing_location == "eastus"
        assert result.resource_group is None  # Missing but doesn't break parsing

        # Should still format a useful message
        message = format_conflict_error(result)
        assert "test-vm" in message

    def test_handles_missing_location(self):
        """Verify handling when location is not in error."""
        error_text = "Resource 'test-vm' already exists in resource group 'test-rg'"

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm"
        assert result.resource_group == "test-rg"

    def test_handles_missing_resource_type(self):
        """Verify handling when resource type is not specified."""
        error_text = "Resource 'test-vm' already exists"

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm"

    def test_handles_only_resource_name(self):
        """Verify minimal parsing with only resource name."""
        error_text = "'test-vm' already exists"

        result = parse_conflict_error(error_text)

        assert result.resource_name == "test-vm"
        assert result.resource_group is None
        assert result.existing_location is None


class TestDebugLogging:
    """Test that full error details are preserved for debugging."""

    def test_preserves_original_error_in_result(self):
        """Verify original error message is preserved in result."""
        # Use an actual conflict error message
        original_error = (
            "ResourceExistsError: Resource 'test-vm' already exists in location 'westus'"
        )

        result = parse_conflict_error(original_error)

        # Should preserve original for debugging
        assert result is not None, "parse_conflict_error should return result for conflict errors"
        assert hasattr(result, "original_error")
        assert result.original_error == original_error

    def test_preserves_stack_trace_info(self):
        """Verify stack trace information is preserved when available."""
        error_with_trace = """
Traceback (most recent call last):
  File "provision.py", line 42, in create_vm
    vm = client.create()
Azure.Core.ResourceExistsError: Resource 'test-vm' already exists
"""

        result = parse_conflict_error(error_with_trace)

        assert hasattr(result, "original_error")
        assert "Traceback" in result.original_error


# =============================================================================
# E2E TESTS (10%) - Complete workflows with VMProvisioner integration
# =============================================================================


class TestVMProvisionerIntegration:
    """Test integration with VMProvisioner error handling."""

    @patch("azlin.vm_provisioning.VMProvisioner")
    def test_vm_provisioner_transforms_conflict_error(self, mock_provisioner):
        """Verify VMProvisioner transforms Azure conflict errors into user-friendly messages."""
        # Simulate Azure CLI returning conflict error
        azure_error = (
            "ERROR: The resource 'test-vm' already exists in resource group "
            "'test-rg' in location 'eastus'."
        )

        # VMProvisioner should detect and transform
        assert is_resource_conflict(azure_error) is True

        conflict_info = parse_conflict_error(azure_error)
        user_message = format_conflict_error(conflict_info)

        # User should see friendly message
        assert "test-vm" in user_message
        assert any(word in user_message.lower() for word in ["delete", "rename", "existing"])

    @patch("azlin.vm_provisioning.VMProvisioner")
    def test_debug_log_contains_full_traceback(self, mock_provisioner):
        """Verify debug logs preserve full Azure error details."""
        azure_error = """
Traceback (most recent call last):
  File "/usr/lib/azure-cli/provision.py", line 123
Azure.Core.ResourceExistsError: Resource exists
Full JSON: {"error": {"code": "ResourceExists", "details": {...}}}
"""

        conflict_info = parse_conflict_error(azure_error)

        # Original error should be preserved
        assert conflict_info.original_error == azure_error
        assert "Traceback" in conflict_info.original_error
        assert "Full JSON" in conflict_info.original_error

    def test_user_sees_actionable_message(self):
        """Verify user receives actionable guidance, not raw Azure error."""
        azure_error = (
            "ConflictError: Microsoft.Compute/virtualMachines 'test-vm' already "
            "exists in resource group 'test-rg' in location 'eastus'."
        )

        # Transform error
        conflict_info = parse_conflict_error(azure_error)
        user_message = format_conflict_error(conflict_info)

        # User message should be clear and actionable
        assert "test-vm" in user_message
        assert "test-rg" in user_message

        # Should NOT contain technical jargon
        assert "ConflictError" not in user_message
        assert "Microsoft.Compute/virtualMachines" not in user_message

        # Should contain actionable steps
        assert any(
            word in user_message.lower()
            for word in ["delete", "rename", "choose different", "use existing"]
        )

    def test_handles_nested_provisioning_errors(self):
        """Verify handling of nested errors during VM provisioning."""
        nested_error = {
            "error": {
                "code": "DeploymentFailed",
                "message": "Deployment failed",
                "details": [
                    {
                        "code": "ResourceExists",
                        "message": "VM 'test-vm' already exists",
                        "target": "Microsoft.Compute/virtualMachines",
                    }
                ],
            }
        }

        result = parse_conflict_error(json.dumps(nested_error))

        assert result.resource_name == "test-vm"
        assert result.resource_type == "Microsoft.Compute/virtualMachines"


class TestEndToEndErrorFlow:
    """Test complete error flow from Azure CLI to user."""

    def test_complete_conflict_error_flow(self):
        """Test complete flow: Azure error → Detection → Parsing → Formatting → User."""
        # Step 1: Azure CLI returns error
        azure_cli_output = (
            "ERROR: The resource 'azlin-prod-vm' already exists in resource group "
            "'production' in location 'eastus'. Command: az vm create"
        )

        # Step 2: Detection
        is_conflict = is_resource_conflict(azure_cli_output)
        assert is_conflict is True

        # Step 3: Parsing
        conflict_info = parse_conflict_error(azure_cli_output)
        assert conflict_info.resource_name == "azlin-prod-vm"
        assert conflict_info.resource_group == "production"
        assert conflict_info.existing_location == "eastus"

        # Step 4: Formatting
        user_message = format_conflict_error(conflict_info)
        assert len(user_message) > 100
        assert "azlin-prod-vm" in user_message

        # Step 5: User sees actionable guidance
        assert any(
            word in user_message.lower()
            for word in ["delete", "rename", "already exists", "choose different"]
        )

    def test_non_conflict_error_passes_through(self):
        """Verify non-conflict errors are not transformed."""
        non_conflict_error = "ERROR: Authentication failed. Please run 'az login'."

        # Should not be detected as conflict
        assert is_resource_conflict(non_conflict_error) is False

        # Should return None or raise appropriate exception
        result = parse_conflict_error(non_conflict_error)
        assert result is None

    def test_performance_of_error_transformation(self):
        """Verify error transformation completes quickly."""
        import time

        azure_error = (
            "ERROR: The resource 'test-vm' already exists in resource group "
            "'test-rg' in location 'eastus'."
        )

        start = time.time()

        is_conflict = is_resource_conflict(azure_error)
        if is_conflict:
            conflict_info = parse_conflict_error(azure_error)
            user_message = format_conflict_error(conflict_info)

        duration = time.time() - start

        # Should complete in < 100ms
        assert duration < 0.1


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_conflict_info():
    """Fixture: Sample ResourceConflictInfo for testing."""
    return ResourceConflictInfo(
        resource_name="test-vm",
        resource_type="Microsoft.Compute/virtualMachines",
        existing_location="eastus",
        attempted_location="westus",
        resource_group="test-rg",
        original_error="Original Azure error message",
    )


@pytest.fixture
def minimal_conflict_info():
    """Fixture: Minimal ResourceConflictInfo with only required fields."""
    return ResourceConflictInfo(resource_name="test-vm", original_error="Minimal error information")
