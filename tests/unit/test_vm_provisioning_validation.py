"""Unit tests for VM provisioning validation methods.

This module tests the static validation methods added to VMProvisioner:
1. validate_azure_vm_name() - Validates VM names against Azure naming rules
2. check_vm_exists() - Checks if a VM exists in a resource group

Test Philosophy:
- Comprehensive coverage of all validation rules
- Test valid cases, invalid cases, and edge cases
- Use mocks to avoid actual Azure API calls
- Clear test names that describe expected behavior

Coverage:
1. Valid VM names (various formats)
2. Invalid VM names (all rejection cases)
3. Edge cases (empty, too long, special chars)
4. VM existence checking with mocks
"""

from unittest.mock import Mock, patch

import pytest

from azlin.vm_provisioning import VMProvisioner


class TestValidateAzureVMName:
    """Test validate_azure_vm_name() static method."""

    def test_valid_simple_alphanumeric_name(self):
        """Test that simple alphanumeric names are valid.

        Given: A simple alphanumeric VM name
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("myvm")
        assert is_valid is True
        assert error == ""

    def test_valid_name_with_numbers(self):
        """Test that names with numbers are valid.

        Given: A VM name with numbers
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("vm123")
        assert is_valid is True
        assert error == ""

    def test_valid_name_with_hyphens(self):
        """Test that names with hyphens are valid.

        Given: A VM name with hyphens
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("my-test-vm")
        assert is_valid is True
        assert error == ""

    def test_valid_name_with_periods(self):
        """Test that names with periods are valid.

        Given: A VM name with periods
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("my.test.vm")
        assert is_valid is True
        assert error == ""

    def test_valid_name_with_mixed_characters(self):
        """Test that names with alphanumeric, hyphens, and periods are valid.

        Given: A VM name with mixed valid characters
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("My-Test.VM-123")
        assert is_valid is True
        assert error == ""

    def test_valid_name_starting_with_uppercase(self):
        """Test that names starting with uppercase are valid.

        Given: A VM name starting with uppercase letter
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("TestVM")
        assert is_valid is True
        assert error == ""

    def test_valid_name_starting_with_number(self):
        """Test that names starting with numbers are valid.

        Given: A VM name starting with a number
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("1testvm")
        assert is_valid is True
        assert error == ""

    def test_valid_max_length_name(self):
        """Test that 64-character names are valid (max length).

        Given: A VM name with exactly 64 characters
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        # 64 characters exactly
        name = "a" * 64
        is_valid, error = VMProvisioner.validate_azure_vm_name(name)
        assert is_valid is True
        assert error == ""

    def test_valid_single_character_name(self):
        """Test that single-character names are valid (min length).

        Given: A VM name with 1 character
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("a")
        assert is_valid is True
        assert error == ""

    def test_invalid_empty_name(self):
        """Test that empty names are rejected.

        Given: An empty VM name
        When: validate_azure_vm_name is called
        Then: Returns (False, "VM name cannot be empty")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("")
        assert is_valid is False
        assert "cannot be empty" in error

    def test_invalid_too_long_name(self):
        """Test that names over 64 characters are rejected.

        Given: A VM name with 65 characters
        When: validate_azure_vm_name is called
        Then: Returns (False, error with length info)
        """
        # 65 characters (one over limit)
        name = "a" * 65
        is_valid, error = VMProvisioner.validate_azure_vm_name(name)
        assert is_valid is False
        assert "too long" in error.lower()
        assert "65" in error
        assert "64" in error

    def test_invalid_name_starting_with_hyphen(self):
        """Test that names starting with hyphen are rejected.

        Given: A VM name starting with hyphen
        When: validate_azure_vm_name is called
        Then: Returns (False, error about start character)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("-myvm")
        assert is_valid is False
        assert "must start with alphanumeric" in error.lower()
        assert "'-'" in error

    def test_invalid_name_starting_with_period(self):
        """Test that names starting with period are rejected.

        Given: A VM name starting with period
        When: validate_azure_vm_name is called
        Then: Returns (False, error about start character)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name(".myvm")
        assert is_valid is False
        assert "must start with alphanumeric" in error.lower()
        assert "'.'" in error

    def test_invalid_name_ending_with_hyphen(self):
        """Test that names ending with hyphen are rejected.

        Given: A VM name ending with hyphen
        When: validate_azure_vm_name is called
        Then: Returns (False, error about end character)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("myvm-")
        assert is_valid is False
        assert "cannot end with" in error.lower()
        assert "'-'" in error

    def test_invalid_name_ending_with_period(self):
        """Test that names ending with period are rejected.

        Given: A VM name ending with period
        When: validate_azure_vm_name is called
        Then: Returns (False, error about end character)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("myvm.")
        assert is_valid is False
        assert "cannot end with" in error.lower()
        assert "'.'" in error

    def test_invalid_name_with_underscore(self):
        """Test that names with underscores are rejected.

        Given: A VM name containing underscore
        When: validate_azure_vm_name is called
        Then: Returns (False, error about invalid characters)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("my_vm")
        assert is_valid is False
        assert "can only contain" in error.lower()

    def test_invalid_name_with_space(self):
        """Test that names with spaces are rejected.

        Given: A VM name containing space
        When: validate_azure_vm_name is called
        Then: Returns (False, error about invalid characters)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("my vm")
        assert is_valid is False
        assert "can only contain" in error.lower()

    def test_invalid_name_with_special_chars(self):
        """Test that names with special characters are rejected.

        Given: A VM name containing special characters
        When: validate_azure_vm_name is called
        Then: Returns (False, error about invalid characters)
        """
        special_chars = ["@", "#", "$", "%", "^", "&", "*", "(", ")", "+", "=", "[", "]", "{", "}"]
        for char in special_chars:
            name = f"myvm{char}test"
            is_valid, error = VMProvisioner.validate_azure_vm_name(name)
            assert is_valid is False, f"Expected {name} to be invalid"
            assert "can only contain" in error.lower()

    def test_invalid_name_with_emoji(self):
        """Test that names with emoji are rejected.

        Given: A VM name containing emoji
        When: validate_azure_vm_name is called
        Then: Returns (False, error about invalid characters)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("myvm😀")
        assert is_valid is False
        assert "can only contain" in error.lower()

    def test_edge_case_only_hyphens_and_periods(self):
        """Test that names with only hyphens/periods are rejected.

        Given: A VM name containing only hyphens and periods
        When: validate_azure_vm_name is called
        Then: Returns (False, error about start character)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name(".-.-")
        assert is_valid is False
        assert "must start with alphanumeric" in error.lower()

    def test_valid_hostname_like_name(self):
        """Test that hostname-like names are valid.

        Given: A VM name resembling a hostname
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        # This is the use case from the issue - session names as hostnames
        is_valid, error = VMProvisioner.validate_azure_vm_name("azlin-session-main")
        assert is_valid is True
        assert error == ""


class TestCheckVMExists:
    """Test check_vm_exists() static method."""

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_vm_exists_returns_true(self, mock_executor_class):
        """Test that check_vm_exists returns True when VM exists.

        Given: A VM exists in the resource group
        When: check_vm_exists is called
        Then: Returns True
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor

        # Mock successful VM show command
        mock_executor.execute.return_value = {
            "success": True,
            "stdout": "test-vm",
            "stderr": "",
            "returncode": 0,
        }

        # Test
        result = VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify
        assert result is True
        mock_executor_class.assert_called_once_with(show_progress=False, timeout=10)
        mock_executor.execute.assert_called_once()

        # Verify command structure
        call_args = mock_executor.execute.call_args[0][0]
        assert call_args[0] == "az"
        assert call_args[1] == "vm"
        assert call_args[2] == "show"
        assert "--name" in call_args
        assert "test-vm" in call_args
        assert "--resource-group" in call_args
        assert "test-rg" in call_args

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_vm_does_not_exist_returns_false(self, mock_executor_class):
        """Test that check_vm_exists returns False when VM doesn't exist.

        Given: A VM does not exist in the resource group
        When: check_vm_exists is called
        Then: Returns False
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor

        # Mock failed VM show command (VM not found)
        mock_executor.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "ResourceNotFound: The Resource 'test-vm' was not found.",
            "returncode": 3,
        }

        # Test
        result = VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify
        assert result is False

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_resource_group_does_not_exist_returns_false(self, mock_executor_class):
        """Test that check_vm_exists returns False when RG doesn't exist.

        Given: A resource group does not exist
        When: check_vm_exists is called
        Then: Returns False (not an error)
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor

        # Mock failed VM show command (RG not found)
        mock_executor.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "ResourceGroupNotFound: Resource group 'test-rg' could not be found.",
            "returncode": 3,
        }

        # Test
        result = VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify - should return False, not raise
        assert result is False

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_executor_raises_exception_returns_false(self, mock_executor_class):
        """Test that check_vm_exists returns False when executor raises exception.

        Given: AzureCLIExecutor raises an exception
        When: check_vm_exists is called
        Then: Returns False (exception is caught)
        """
        # Setup mock executor to raise exception
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute.side_effect = Exception("Network error")

        # Test
        result = VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify - should return False, not raise
        assert result is False

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_check_vm_exists_uses_minimal_output(self, mock_executor_class):
        """Test that check_vm_exists uses minimal output for speed.

        Given: A VM exists
        When: check_vm_exists is called
        Then: Command uses --query and --output tsv for minimal output
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute.return_value = {
            "success": True,
            "stdout": "test-vm",
            "stderr": "",
            "returncode": 0,
        }

        # Test
        VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify command includes query and output flags
        call_args = mock_executor.execute.call_args[0][0]
        assert "--query" in call_args
        assert "name" in call_args
        assert "--output" in call_args
        assert "tsv" in call_args

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_check_vm_exists_uses_short_timeout(self, mock_executor_class):
        """Test that check_vm_exists uses short timeout for fast checks.

        Given: A VM existence check
        When: check_vm_exists is called
        Then: Executor is initialized with timeout=10
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute.return_value = {
            "success": True,
            "stdout": "test-vm",
            "stderr": "",
            "returncode": 0,
        }

        # Test
        VMProvisioner.check_vm_exists("test-vm", "test-rg")

        # Verify timeout
        mock_executor_class.assert_called_once_with(show_progress=False, timeout=10)

    @patch("azlin.vm_provisioning.AzureCLIExecutor")
    def test_check_vm_exists_with_special_characters_in_name(self, mock_executor_class):
        """Test that check_vm_exists handles VM names with special characters.

        Given: A VM name with hyphens and periods
        When: check_vm_exists is called
        Then: Command passes name correctly to Azure CLI
        """
        # Setup mock executor
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute.return_value = {
            "success": True,
            "stdout": "my-test.vm-123",
            "stderr": "",
            "returncode": 0,
        }

        # Test with complex name
        result = VMProvisioner.check_vm_exists("my-test.vm-123", "test-rg")

        # Verify
        assert result is True
        call_args = mock_executor.execute.call_args[0][0]
        assert "my-test.vm-123" in call_args


class TestValidationIntegration:
    """Integration tests combining validation methods."""

    def test_validate_then_check_flow(self):
        """Test typical flow: validate name before checking existence.

        Given: A valid VM name
        When: Name is validated and then checked for existence
        Then: Validation passes and existence check can proceed
        """
        # Validate name
        is_valid, error = VMProvisioner.validate_azure_vm_name("test-vm-123")
        assert is_valid is True
        assert error == ""

        # Check existence would happen next (mocked separately in other tests)

    def test_invalid_name_caught_before_existence_check(self):
        """Test that invalid names are caught by validation.

        Given: An invalid VM name
        When: Name is validated
        Then: Validation fails and existence check is not needed
        """
        # Validate invalid name
        is_valid, error = VMProvisioner.validate_azure_vm_name("_invalid_name")
        assert is_valid is False
        assert error != ""

        # No need to check existence for invalid names


class TestValidationEdgeCases:
    """Edge cases and boundary conditions for validation."""

    def test_validate_name_with_unicode_characters(self):
        """Test that names with unicode characters are rejected.

        Given: A VM name with unicode characters
        When: validate_azure_vm_name is called
        Then: Returns (False, error)
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("vm-café")
        assert is_valid is False
        assert "can only contain" in error.lower()

    def test_validate_name_boundary_63_chars(self):
        """Test that 63-character names are valid (one under limit).

        Given: A VM name with exactly 63 characters
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        name = "a" * 63
        is_valid, error = VMProvisioner.validate_azure_vm_name(name)
        assert is_valid is True
        assert error == ""

    def test_validate_name_boundary_66_chars(self):
        """Test that 66-character names are rejected (two over limit).

        Given: A VM name with 66 characters
        When: validate_azure_vm_name is called
        Then: Returns (False, error with length info)
        """
        name = "a" * 66
        is_valid, error = VMProvisioner.validate_azure_vm_name(name)
        assert is_valid is False
        assert "too long" in error.lower()
        assert "66" in error

    def test_validate_name_with_consecutive_hyphens(self):
        """Test that names with consecutive hyphens are valid.

        Given: A VM name with consecutive hyphens
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("vm--test")
        assert is_valid is True
        assert error == ""

    def test_validate_name_with_consecutive_periods(self):
        """Test that names with consecutive periods are valid.

        Given: A VM name with consecutive periods
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("vm..test")
        assert is_valid is True
        assert error == ""

    def test_validate_name_mixed_case_complex(self):
        """Test that complex mixed-case names are valid.

        Given: A VM name with mixed case, hyphens, periods, and numbers
        When: validate_azure_vm_name is called
        Then: Returns (True, "")
        """
        is_valid, error = VMProvisioner.validate_azure_vm_name("MyTest-VM.123-prod")
        assert is_valid is True
        assert error == ""
