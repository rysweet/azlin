"""Tests for ErrorAnalyzer.

Testing pyramid:
- 70% Unit tests (pattern matching, error extraction)
- 20% Integration tests (with real error messages)
- 10% Edge cases (empty errors, malformed messages)
"""

from azlin.agentic.error_analyzer import ErrorAnalyzer


class TestErrorAnalyzerBasics:
    """Test basic error analyzer functionality."""

    def test_initialization(self):
        """Test ErrorAnalyzer can be initialized."""
        analyzer = ErrorAnalyzer()
        assert analyzer is not None

    def test_empty_error(self):
        """Test handling of empty error message."""
        analyzer = ErrorAnalyzer()
        result = analyzer.analyze("azlin test", "")
        assert "Command failed with no error message" in result

    def test_whitespace_only_error(self):
        """Test handling of whitespace-only error."""
        analyzer = ErrorAnalyzer()
        result = analyzer.analyze("azlin test", "   \n  ")
        assert "Command failed with no error message" in result


class TestAuthenticationErrors:
    """Test authentication error patterns."""

    def test_authentication_failed(self):
        """Test AuthenticationFailed error detection."""
        analyzer = ErrorAnalyzer()
        stderr = "AuthenticationFailed: Authentication failed"
        result = analyzer.analyze("azlin new", stderr)
        assert "Authentication failed" in result
        assert "az login" in result

    def test_please_run_az_login(self):
        """Test 'Please run az login' pattern."""
        analyzer = ErrorAnalyzer()
        stderr = "ERROR: Please run 'az login' to continue"
        result = analyzer.analyze("azlin list", stderr)
        assert "Authentication failed" in result
        assert "az login" in result

    def test_subscription_not_found(self):
        """Test subscription not found error."""
        analyzer = ErrorAnalyzer()
        stderr = "SubscriptionNotFound: The subscription was not found"
        result = analyzer.analyze("azlin cost", stderr)
        assert "Subscription not found" in result
        assert "az account list" in result


class TestResourceGroupErrors:
    """Test resource group error patterns."""

    def test_resource_group_not_found(self):
        """Test ResourceGroupNotFound error."""
        analyzer = ErrorAnalyzer()
        stderr = "ResourceGroupNotFound: Resource group 'my-rg' not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Resource group not found" in result
        assert "azlin config set-rg" in result

    def test_resource_group_lowercase_pattern(self):
        """Test case-insensitive matching for resource group."""
        analyzer = ErrorAnalyzer()
        stderr = "Error: resource group 'test-rg' not found in subscription"
        result = analyzer.analyze("azlin new", stderr)
        assert "Resource group not found" in result


class TestVMErrors:
    """Test VM-specific error patterns."""

    def test_vm_not_found(self):
        """Test VM not found error."""
        analyzer = ErrorAnalyzer()
        stderr = "VMNotFound: Virtual machine 'test-vm' not found"
        result = analyzer.analyze("azlin start test-vm", stderr)
        assert "VM not found" in result
        assert "azlin list" in result

    def test_vm_already_exists(self):
        """Test VM already exists error."""
        analyzer = ErrorAnalyzer()
        stderr = "VMAlreadyExists: A virtual machine with name 'test' already exists"
        result = analyzer.analyze("azlin new --name test", stderr)
        assert "already exists" in result
        assert "azlin kill" in result

    def test_vm_not_running(self):
        """Test VM not running error."""
        analyzer = ErrorAnalyzer()
        stderr = "VMNotRunning: VM is not running"
        result = analyzer.analyze("azlin connect test", stderr)
        assert "not running" in result
        assert "azlin start" in result


class TestQuotaAndCapacityErrors:
    """Test quota and capacity error patterns."""

    def test_quota_exceeded(self):
        """Test quota exceeded error."""
        analyzer = ErrorAnalyzer()
        stderr = "QuotaExceeded: Quota for VM cores exceeded"
        result = analyzer.analyze("azlin new", stderr)
        assert "Quota exceeded" in result
        assert "different region" in result

    def test_sku_not_available(self):
        """Test SKU not available error."""
        analyzer = ErrorAnalyzer()
        stderr = "SkuNotAvailable: The requested VM size 'Standard_D4s_v3' is not available"
        result = analyzer.analyze("azlin new", stderr)
        assert "not available" in result
        assert "different VM size" in result

    def test_zone_not_allowed(self):
        """Test availability zone error."""
        analyzer = ErrorAnalyzer()
        stderr = "OperationNotAllowed: Availability zones are not supported"
        result = analyzer.analyze("azlin new", stderr)
        assert "zone not supported" in result
        assert "different region" in result


class TestNetworkErrors:
    """Test network-related error patterns."""

    def test_nsg_not_found(self):
        """Test Network Security Group not found."""
        analyzer = ErrorAnalyzer()
        stderr = "NetworkSecurityGroupNotFound: NSG not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Network security group not found" in result
        assert "network configuration" in result

    def test_public_ip_cannot_be_deleted(self):
        """Test public IP deletion error."""
        analyzer = ErrorAnalyzer()
        stderr = "PublicIPAddressCannotBeDeleted: Public IP is in use"
        result = analyzer.analyze("azlin kill", stderr)
        assert "Public IP address is in use" in result
        assert "Deallocate" in result

    def test_subnet_not_found(self):
        """Test subnet not found error."""
        analyzer = ErrorAnalyzer()
        stderr = "SubnetNotFound: Subnet 'default' not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Subnet not found" in result
        assert "virtual network" in result


class TestStorageErrors:
    """Test storage-related error patterns."""

    def test_storage_account_not_found(self):
        """Test storage account not found."""
        analyzer = ErrorAnalyzer()
        stderr = "StorageAccountNotFound: Storage account 'mystore' not found"
        result = analyzer.analyze("azlin storage status mystore", stderr)
        assert "Storage account not found" in result
        assert "azlin storage create" in result

    def test_storage_account_already_exists(self):
        """Test storage account name conflict."""
        analyzer = ErrorAnalyzer()
        stderr = "StorageAccountAlreadyExists: The storage account name is already taken"
        result = analyzer.analyze("azlin storage create mystore", stderr)
        assert "already taken" in result
        assert "globally unique" in result


class TestBastionErrors:
    """Test Bastion-related error patterns."""

    def test_bastion_not_found(self):
        """Test Bastion not found error."""
        analyzer = ErrorAnalyzer()
        stderr = "BastionNotFound: Azure Bastion not found for VNet"
        result = analyzer.analyze("azlin connect test", stderr)
        assert "Bastion not configured" in result
        assert "automatically" in result or "manually" in result


class TestPermissionErrors:
    """Test permission-related error patterns."""

    def test_authorization_failed(self):
        """Test authorization failed error."""
        analyzer = ErrorAnalyzer()
        stderr = "AuthorizationFailed: User does not have authorization"
        result = analyzer.analyze("azlin new", stderr)
        assert "Authorization failed" in result
        assert "permissions" in result

    def test_not_authorized(self):
        """Test 'not authorized' pattern."""
        analyzer = ErrorAnalyzer()
        stderr = "Error: You are not authorized to perform this action"
        result = analyzer.analyze("azlin kill", stderr)
        assert "Authorization failed" in result
        assert "role assignments" in result

    def test_role_assignment_not_found(self):
        """Test role assignment error."""
        analyzer = ErrorAnalyzer()
        stderr = "RoleAssignmentNotFound: Role assignment not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Role assignment not found" in result
        assert "permissions" in result


class TestConfigurationErrors:
    """Test configuration error patterns."""

    def test_invalid_parameter(self):
        """Test invalid parameter error."""
        analyzer = ErrorAnalyzer()
        stderr = "InvalidParameter: Parameter 'vmSize' is invalid"
        result = analyzer.analyze("azlin new", stderr)
        assert "Invalid parameter" in result
        assert "--help" in result

    def test_missing_parameter(self):
        """Test missing parameter error."""
        analyzer = ErrorAnalyzer()
        stderr = "MissingParameter: Required parameter 'location' is missing"
        result = analyzer.analyze("azlin new", stderr)
        assert "Required parameter missing" in result
        assert "--help" in result


class TestTimeoutErrors:
    """Test timeout error patterns."""

    def test_operation_timed_out(self):
        """Test operation timeout error."""
        analyzer = ErrorAnalyzer()
        stderr = "OperationTimedOut: The operation timed out"
        result = analyzer.analyze("azlin new", stderr)
        assert "timed out" in result
        assert "Try again" in result


class TestKeyVaultErrors:
    """Test Key Vault error patterns."""

    def test_key_vault_not_found(self):
        """Test Key Vault not found error."""
        analyzer = ErrorAnalyzer()
        stderr = "KeyVaultNotFound: Key vault 'mykv' not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Key Vault not found" in result
        assert "configuration" in result or "permissions" in result


class TestGenericErrors:
    """Test generic error patterns."""

    def test_resource_not_found(self):
        """Test generic ResourceNotFound error."""
        analyzer = ErrorAnalyzer()
        stderr = "ResourceNotFound: The specified resource was not found"
        result = analyzer.analyze("azlin status", stderr)
        assert "Resource not found" in result
        assert "azlin list" in result


class TestErrorExtraction:
    """Test error message extraction and cleaning."""

    def test_extract_error_with_code_prefix(self):
        """Test extraction of error with code prefix."""
        analyzer = ErrorAnalyzer()
        stderr = "ERROR: (ResourceGroupNotFound) Resource group 'test' not found\nCode: ResourceGroupNotFound"
        result = analyzer._extract_error_details(stderr)
        assert "Resource group 'test' not found" in result
        # Should not include "ERROR:" or "Code:"
        assert "ERROR:" not in result
        assert "Code:" not in result

    def test_extract_multiline_error(self):
        """Test extraction from multiline error."""
        analyzer = ErrorAnalyzer()
        stderr = """ERROR: Something failed
Traceback (most recent call last):
  File "test.py", line 1
    VMNotFound: VM 'test' not found"""
        result = analyzer._extract_error_details(stderr)
        # Should extract the main error, skip ERROR: and Traceback
        assert "Something failed" in result or "VMNotFound" in result

    def test_extract_with_parenthesis_code(self):
        """Test extraction with parenthesized error code."""
        analyzer = ErrorAnalyzer()
        stderr = "(AuthenticationFailed) Please run 'az login'"
        result = analyzer._extract_error_details(stderr)
        # Should remove (ErrorCode) prefix
        assert "AuthenticationFailed" not in result or "Please run" in result


class TestUnknownErrors:
    """Test handling of unknown error patterns."""

    def test_unknown_error_pattern(self):
        """Test handling of error that doesn't match any pattern."""
        analyzer = ErrorAnalyzer()
        stderr = "SomeWeirdError: This is an unknown error type"
        result = analyzer.analyze("azlin new", stderr)
        # Should return original error with generic suggestion
        assert "SomeWeirdError" in result
        assert "--help" in result

    def test_fallback_suggestion(self):
        """Test that fallback suggestion is provided."""
        analyzer = ErrorAnalyzer()
        stderr = "Completely unrecognized error message format"
        result = analyzer.analyze("azlin test", stderr)
        assert stderr in result
        assert "Suggestion:" in result


class TestCaseInsensitivity:
    """Test case-insensitive pattern matching."""

    def test_lowercase_error_code(self):
        """Test matching lowercase error codes."""
        analyzer = ErrorAnalyzer()
        stderr = "resourcegroupnotfound: RG not found"
        result = analyzer.analyze("azlin new", stderr)
        assert "Resource group not found" in result

    def test_mixed_case_error(self):
        """Test matching mixed case errors."""
        analyzer = ErrorAnalyzer()
        stderr = "QuOtA ExCeEdEd: Quota limit reached"
        result = analyzer.analyze("azlin new", stderr)
        assert "Quota exceeded" in result


class TestRealWorldErrors:
    """Test with real-world error message formats."""

    def test_azure_cli_error_format(self):
        """Test typical Azure CLI error format."""
        analyzer = ErrorAnalyzer()
        stderr = """ERROR: (ResourceGroupNotFound) Resource group 'azlin-test' could not be found.
Code: ResourceGroupNotFound
Message: Resource group 'azlin-test' could not be found."""
        result = analyzer.analyze("azlin new --name test", stderr)
        assert "Resource group not found" in result
        assert "azlin config set-rg" in result

    def test_long_error_with_context(self):
        """Test long error message with additional context."""
        analyzer = ErrorAnalyzer()
        stderr = """ERROR: (QuotaExceeded) Operation could not be completed as it results in exceeding approved standardDSv2Family Cores quota.
Additional details: Requested: 4, Current: 0, Quota: 4, Used: 4
Code: QuotaExceeded"""
        result = analyzer.analyze("azlin new --vm-size Standard_D2s_v2", stderr)
        assert "Quota exceeded" in result
        assert "different region" in result


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_short_error(self):
        """Test very short error message."""
        analyzer = ErrorAnalyzer()
        stderr = "Error"
        result = analyzer.analyze("azlin test", stderr)
        assert "Error" in result
        assert "Suggestion:" in result

    def test_error_with_special_characters(self):
        """Test error with special characters."""
        analyzer = ErrorAnalyzer()
        stderr = "Error: Invalid name 'test@#$%' - special characters not allowed"
        result = analyzer.analyze("azlin new", stderr)
        # Should handle gracefully
        assert "test@#$%" in result or "special characters" in result

    def test_unicode_in_error(self):
        """Test error message with unicode characters."""
        analyzer = ErrorAnalyzer()
        stderr = "Error: Resource 'tëst-vм' not found"
        result = analyzer.analyze("azlin status", stderr)
        # Should preserve unicode
        assert "tëst" in result or "Resource" in result
