"""Tests for Azure CLI command sanitization.

This test suite validates that sensitive data is properly redacted from
Azure CLI commands before display or logging.

Test Coverage:
- Password parameters
- SSH keys
- Connection strings
- SAS tokens
- Secrets and tokens
- Custom data (cloud-init scripts)
- Thread safety
- Terminal escape sequence handling
"""

import concurrent.futures

import pytest

from azlin.security import AzureCommandSanitizer


class TestPasswordSanitization:
    """Test password parameter sanitization."""

    @pytest.mark.parametrize(
        ("command", "expected_redacted"),
        [
            # VM admin password
            (
                "az vm create --admin-password MySecretPass123",
                "az vm create --admin-password [REDACTED]",
            ),
            # SQL admin password
            (
                "az sql server create --administrator-login-password SuperSecret!",
                "az sql server create --administrator-login-password [REDACTED]",
            ),
            # Generic password
            (
                "az resource create --password Pass123",
                "az resource create --password [REDACTED]",
            ),
            # Quoted password
            (
                'az vm create --admin-password "My Pass 123"',
                'az vm create --admin-password "[REDACTED]"',
            ),
            # Single quoted password
            (
                "az vm create --admin-password 'My Pass 123'",
                "az vm create --admin-password '[REDACTED]'",
            ),
            # EQUALS SIGN SYNTAX - CRITICAL SECURITY FIX
            # Unquoted with equals
            (
                "az vm create --admin-password=Secret123",
                "az vm create --admin-password=[REDACTED]",
            ),
            # Double quoted with equals
            (
                'az vm create --admin-password="Secret123"',
                'az vm create --admin-password="[REDACTED]"',
            ),
            # Single quoted with equals
            (
                "az vm create --admin-password='Secret123'",
                "az vm create --admin-password='[REDACTED]'",
            ),
        ],
    )
    def test_password_parameters_redacted(self, command: str, expected_redacted: str) -> None:
        """Test that password parameters are redacted."""
        result = AzureCommandSanitizer.sanitize(command)
        assert result == expected_redacted

    def test_password_not_in_output(self) -> None:
        """Test that actual password value doesn't appear in output."""
        command = "az vm create --admin-password VerySecretPassword123"
        result = AzureCommandSanitizer.sanitize(command)

        # No part of the password should remain
        assert "VerySecretPassword123" not in result
        assert "VerySecret" not in result
        assert "Password123" not in result

    def test_multiple_passwords_redacted(self) -> None:
        """Test that multiple password parameters are all redacted."""
        command = (
            "az vm create --admin-password Pass1 "
            "--custom-data 'password=Pass2' "
            "--sql-password Pass3"
        )
        result = AzureCommandSanitizer.sanitize(command)

        assert "Pass1" not in result
        assert "Pass2" not in result
        assert "Pass3" not in result
        assert result.count("[REDACTED]") >= 2


class TestEqualsSignSyntax:
    """Test equals sign parameter syntax (CRITICAL SECURITY FIX).

    These tests verify the fix for the security vulnerability where credentials
    leaked when using --param=value syntax instead of --param value.
    """

    @pytest.mark.parametrize(
        ("command", "expected_redacted"),
        [
            # VM passwords
            (
                "az vm create --admin-password=Secret123",
                "az vm create --admin-password=[REDACTED]",
            ),
            (
                'az vm create --admin-password="Secret123"',
                'az vm create --admin-password="[REDACTED]"',
            ),
            (
                "az vm create --admin-password='Secret123'",
                "az vm create --admin-password='[REDACTED]'",
            ),
            # Key Vault secrets
            (
                "az keyvault secret set --secret=TopSecret",
                "az keyvault secret set --secret=[REDACTED]",
            ),
            (
                'az keyvault secret set --secret="TopSecret"',
                'az keyvault secret set --secret="[REDACTED]"',
            ),
            # Storage keys
            (
                "az storage account keys list --account-key=abc123XYZ",
                "az storage account keys list --account-key=[REDACTED]",
            ),
            # SAS tokens
            (
                "az storage blob url --sas-token=?sv=2021-01-01",
                "az storage blob url --sas-token=[REDACTED]",
            ),
            # SSH keys
            (
                "az vm create --ssh-key-value=ssh-rsa-AAAAB3...",
                "az vm create --ssh-key-value=[REDACTED]",
            ),
            # Client secrets
            (
                "az ad sp create-for-rbac --client-secret=MySecret",
                "az ad sp create-for-rbac --client-secret=[REDACTED]",
            ),
            # Connection strings
            (
                "az storage blob upload --connection-string=DefaultEndpoints...",
                "az storage blob upload --connection-string=[REDACTED]",
            ),
            # Tokens
            (
                "az login --access-token=eyJhbGc...",
                "az login --access-token=[REDACTED]",
            ),
            # Database passwords
            (
                "az sql server create --administrator-login-password=DbPass123",
                "az sql server create --administrator-login-password=[REDACTED]",
            ),
        ],
    )
    def test_equals_sign_syntax_redacted(self, command: str, expected_redacted: str) -> None:
        """Test that equals sign syntax is properly redacted."""
        result = AzureCommandSanitizer.sanitize(command)
        assert result == expected_redacted

    def test_equals_no_credential_leak(self) -> None:
        """Test that credentials never leak with equals syntax."""
        commands_with_secrets = [
            ("az vm create --admin-password=Secret123", "Secret123"),
            ('az vm create --admin-password="Secret123"', "Secret123"),
            ("az keyvault secret set --secret=TopSecret", "TopSecret"),
            ("az storage account keys list --account-key=abc123", "abc123"),
        ]

        for command, secret in commands_with_secrets:
            result = AzureCommandSanitizer.sanitize(command)
            assert secret not in result, f"Secret '{secret}' leaked in: {result}"
            assert "[REDACTED]" in result

    def test_mixed_space_and_equals_syntax(self) -> None:
        """Test command with both space and equals syntax."""
        command = (
            "az vm create --name myvm --admin-password=Secret123 --ssh-key-value 'ssh-rsa AAA...'"
        )
        result = AzureCommandSanitizer.sanitize(command)

        # Both should be redacted
        assert "Secret123" not in result
        assert "ssh-rsa AAA..." not in result
        assert result.count("[REDACTED]") == 2
        # Non-sensitive preserved
        assert "myvm" in result

    def test_equals_sign_with_complex_values(self) -> None:
        """Test equals syntax with complex credential values."""
        complex_values = [
            "P@ssw0rd!#$%",
            "Secret-With-Dashes-123",
            "Key_With_Underscores_456",
            "MixedCase123UPPER",
        ]

        for value in complex_values:
            command = f"az vm create --admin-password={value}"
            result = AzureCommandSanitizer.sanitize(command)
            assert value not in result
            assert "[REDACTED]" in result

    def test_equals_sign_preserves_non_sensitive(self) -> None:
        """Test that equals syntax preserves non-sensitive parameters."""
        command = (
            "az vm create --name=myvm --size=Standard_B2s "
            "--admin-password=Secret123 --location=eastus"
        )
        result = AzureCommandSanitizer.sanitize(command)

        # Sensitive redacted
        assert "Secret123" not in result
        assert "[REDACTED]" in result

        # Non-sensitive preserved with equals sign
        assert "--name=myvm" in result
        assert "--size=Standard_B2s" in result
        assert "--location=eastus" in result


class TestSSHKeySanitization:
    """Test SSH key parameter sanitization."""

    @pytest.mark.parametrize(
        ("command", "should_be_redacted"),
        [
            (
                "az vm create --ssh-key-value 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC...'",
                True,
            ),
            (
                "az vm create --ssh-key-values 'ssh-rsa AAA...' 'ssh-rsa BBB...'",
                True,
            ),
            ("az vm create --ssh-private-key-file /path/to/key", True),
            ("az vm create --generate-ssh-keys", False),  # Flag only, no value
        ],
    )
    def test_ssh_key_parameters(self, command: str, should_be_redacted: bool) -> None:
        """Test SSH key parameter handling."""
        result = AzureCommandSanitizer.sanitize(command)

        if should_be_redacted:
            # SSH key content should be redacted
            assert "AAAAB3NzaC1yc2EAAAADAQABAAABAQC" not in result
            assert "[REDACTED]" in result
        else:
            # Flag-only parameters preserved
            assert result == command


class TestConnectionStringSanitization:
    """Test connection string and storage key sanitization."""

    def test_storage_connection_string_redacted(self) -> None:
        """Test Azure Storage connection string redaction."""
        command = (
            "az storage account show-connection-string "
            "--connection-string 'DefaultEndpointsProtocol=https;"
            "AccountName=myaccount;"
            "AccountKey=abcd1234567890ABCDEFGHIJK==;'"
        )
        result = AzureCommandSanitizer.sanitize(command)

        # Connection string should be redacted
        assert "AccountKey=abcd1234567890ABCDEFGHIJK==" not in result
        assert "abcd1234567890ABCDEFGHIJK" not in result
        assert "[REDACTED]" in result

    def test_sas_token_redacted(self) -> None:
        """Test SAS token redaction."""
        command = (
            "az storage blob url --sas-token "
            "'?sv=2021-01-01&ss=b&srt=sco&sp=rwdlac&se=2024-12-31T23:59:59Z'"
        )
        result = AzureCommandSanitizer.sanitize(command)

        # SAS token should be redacted
        assert "sv=2021-01-01" not in result
        assert "rwdlac" not in result
        assert "[REDACTED]" in result

    def test_account_key_redacted(self) -> None:
        """Test storage account key redaction."""
        command = "az storage account keys list --account-key 'abc123XYZ789+/=='"
        result = AzureCommandSanitizer.sanitize(command)

        assert "abc123XYZ789+/==" not in result
        assert "[REDACTED]" in result


class TestSecretAndTokenSanitization:
    """Test secret and token parameter sanitization."""

    @pytest.mark.parametrize(
        "command",
        [
            "az keyvault secret set --secret SecretValue123",
            "az ad sp create-for-rbac --client-secret MyClientSecret",
            "az login --access-token eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "az account get-access-token --token Bearer_Token_12345",
        ],
    )
    def test_secret_and_token_redacted(self, command: str) -> None:
        """Test that secrets and tokens are redacted."""
        result = AzureCommandSanitizer.sanitize(command)

        # Check that REDACTED marker is present
        assert "[REDACTED]" in result

        # Verify original secret values are gone
        if "SecretValue123" in command:
            assert "SecretValue123" not in result
        if "MyClientSecret" in command:
            assert "MyClientSecret" not in result
        if "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" in command:
            assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in result


class TestCustomDataSanitization:
    """Test custom data and cloud-init sanitization."""

    def test_custom_data_with_secrets_redacted(self) -> None:
        """Test that custom-data containing secrets is redacted."""
        command = (
            "az vm create --custom-data '#!/bin/bash\\nexport PASSWORD=SecretPass\\necho Hello\\n'"
        )
        result = AzureCommandSanitizer.sanitize(command)

        # Custom data should be redacted
        assert "[REDACTED]" in result
        # Secret shouldn't leak
        assert "SecretPass" not in result

    def test_cloud_init_redacted(self) -> None:
        """Test that cloud-init data is redacted."""
        command = "az vm create --user-data /path/to/cloud-init.yaml"
        result = AzureCommandSanitizer.sanitize(command)

        # user-data parameter should be redacted
        assert "[REDACTED]" in result


class TestValueBasedDetection:
    """Test value-based secret detection (pattern matching)."""

    def test_base64_long_strings_redacted(self) -> None:
        """Test that long base64 strings (likely keys) are redacted."""
        # 50+ character base64 string (likely a key)
        long_base64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=="
        command = f"az storage account create --key {long_base64}"
        result = AzureCommandSanitizer.sanitize(command)

        assert long_base64 not in result
        assert "[REDACTED]" in result

    def test_jwt_token_redacted(self) -> None:
        """Test that JWT tokens are detected and redacted."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        command = f"az login --token {jwt}"
        result = AzureCommandSanitizer.sanitize(command)

        assert jwt not in result
        assert "[REDACTED]" in result


class TestNonSensitivePreservation:
    """Test that non-sensitive data is preserved."""

    @pytest.mark.parametrize(
        "command",
        [
            "az vm list --output table",
            "az vm show --name myvm --resource-group myrg",
            "az vm create --name myvm --image Ubuntu2204 --size Standard_B2s",
            "az group create --name myrg --location eastus",
            "az network vnet create --name myvnet --address-prefix 10.0.0.0/16",
        ],
    )
    def test_non_sensitive_commands_unchanged(self, command: str) -> None:
        """Test that commands without sensitive data are unchanged."""
        result = AzureCommandSanitizer.sanitize(command)
        assert result == command
        assert "[REDACTED]" not in result


class TestThreadSafety:
    """Test thread safety of sanitization."""

    def test_concurrent_sanitization(self) -> None:
        """Test that sanitization works correctly with concurrent calls."""
        commands = [f"az vm create --admin-password Secret{i} --name vm{i}" for i in range(100)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(AzureCommandSanitizer.sanitize, commands))

        # All results should be sanitized
        for i, result in enumerate(results):
            assert f"Secret{i}" not in result
            assert "[REDACTED]" in result
            assert f"vm{i}" in result  # Non-sensitive data preserved

    def test_no_state_leakage_between_calls(self) -> None:
        """Test that state doesn't leak between sanitization calls."""
        cmd1 = "az vm create --admin-password FirstSecret"
        cmd2 = "az vm create --admin-password SecondSecret"

        result1 = AzureCommandSanitizer.sanitize(cmd1)
        result2 = AzureCommandSanitizer.sanitize(cmd2)

        # Each result should only redact its own secret
        assert "FirstSecret" not in result1
        assert "SecondSecret" not in result2
        assert "FirstSecret" not in result2  # No cross-contamination
        assert "SecondSecret" not in result1


class TestTerminalEscapeSequences:
    """Test terminal escape sequence sanitization."""

    def test_ansi_color_codes_removed(self) -> None:
        """Test that ANSI color codes are removed."""
        command = "az vm create \x1b[31m--admin-password\x1b[0m Secret123"
        result = AzureCommandSanitizer.sanitize(command)

        # ANSI codes should be removed
        assert "\x1b[31m" not in result
        assert "\x1b[0m" not in result
        # Password should still be redacted
        assert "Secret123" not in result
        assert "[REDACTED]" in result

    def test_osc_sequences_removed(self) -> None:
        """Test that OSC sequences (terminal title, etc.) are removed."""
        command = "az vm create \x1b]0;Evil Title\x07 --admin-password Secret"
        result = AzureCommandSanitizer.sanitize(command)

        assert "\x1b]0;Evil Title\x07" not in result
        assert "Secret" not in result

    def test_control_characters_removed(self) -> None:
        """Test that control characters are removed (except tab/newline)."""
        command = "az vm create\x00\x01\x02--admin-password Secret"
        result = AzureCommandSanitizer.sanitize(command)

        # Control characters removed
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x02" not in result


class TestUtilityMethods:
    """Test utility methods."""

    def test_is_command_safe_true_for_safe_commands(self) -> None:
        """Test is_command_safe returns True for safe commands."""
        safe_commands = [
            "az vm list",
            "az group show --name myrg",
            "az network vnet list",
        ]

        for cmd in safe_commands:
            assert AzureCommandSanitizer.is_command_safe(cmd) is True

    def test_is_command_safe_false_for_sensitive_commands(self) -> None:
        """Test is_command_safe returns False for sensitive commands."""
        sensitive_commands = [
            "az vm create --admin-password Secret",
            "az storage account show-connection-string",
            "az keyvault secret set --secret SecretValue",
        ]

        for cmd in sensitive_commands:
            assert AzureCommandSanitizer.is_command_safe(cmd) is False

    def test_get_sensitive_parameters_in_command(self) -> None:
        """Test extraction of sensitive parameters."""
        command = "az vm create --name myvm --admin-password Secret --ssh-key-value 'key'"

        params = AzureCommandSanitizer.get_sensitive_parameters_in_command(command)

        assert "--admin-password" in params
        assert "--ssh-key-value" in params
        assert len(params) == 2

    def test_sanitize_for_display_with_truncation(self) -> None:
        """Test display sanitization with length limit."""
        long_command = "az vm create --name myvm " + "x" * 1000
        result = AzureCommandSanitizer.sanitize_for_display(long_command, max_length=50)

        assert len(result) <= 53  # 50 + "..."
        assert result.endswith("...")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string(self) -> None:
        """Test sanitization of empty string."""
        result = AzureCommandSanitizer.sanitize("")
        assert result == ""

    def test_non_string_input(self) -> None:
        """Test that non-string input is converted to string."""
        result = AzureCommandSanitizer.sanitize(None)  # type: ignore[arg-type]
        assert isinstance(result, str)

    def test_command_with_only_whitespace(self) -> None:
        """Test command with only whitespace."""
        result = AzureCommandSanitizer.sanitize("   \n\t   ")
        assert result.strip() == ""

    def test_malformed_parameter(self) -> None:
        """Test handling of malformed parameters."""
        command = "az vm create --admin-password="  # No value
        result = AzureCommandSanitizer.sanitize(command)
        # Should not crash
        assert isinstance(result, str)

    def test_very_long_command(self) -> None:
        """Test sanitization of very long commands."""
        long_value = "x" * 10000
        command = f"az vm create --admin-password {long_value}"
        result = AzureCommandSanitizer.sanitize(command)

        assert long_value not in result
        assert "[REDACTED]" in result


class TestRealWorldCommands:
    """Test with real-world Azure CLI command examples."""

    def test_vm_creation_with_all_options(self) -> None:
        """Test realistic VM creation command."""
        command = (
            "az vm create "
            "--resource-group myResourceGroup "
            "--name myVM "
            "--image Ubuntu2204 "
            "--admin-username azureuser "
            '--admin-password "MyP@ssw0rd123!" '
            "--size Standard_DS2_v2 "
            "--location eastus "
            '--ssh-key-value "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC..."'
        )
        result = AzureCommandSanitizer.sanitize(command)

        # Sensitive data redacted
        assert "MyP@ssw0rd123!" not in result
        assert "AAAAB3NzaC1yc2EAAAADAQABAAABAQC" not in result
        assert result.count("[REDACTED]") >= 2

        # Non-sensitive data preserved
        assert "myResourceGroup" in result
        assert "myVM" in result
        assert "Ubuntu2204" in result
        assert "Standard_DS2_v2" in result

    def test_sql_server_creation(self) -> None:
        """Test SQL server creation command."""
        command = (
            "az sql server create "
            "--name myserver "
            "--resource-group mygroup "
            "--location eastus "
            "--admin-user myadmin "
            '--admin-password "SuperSecretP@ss123"'
        )
        result = AzureCommandSanitizer.sanitize(command)

        assert "SuperSecretP@ss123" not in result
        assert "[REDACTED]" in result
        assert "myserver" in result

    def test_storage_account_with_connection_string(self) -> None:
        """Test storage account command with connection string."""
        command = (
            "az storage blob upload "
            "--account-name myaccount "
            "--container-name mycontainer "
            "--file /path/to/file "
            '--connection-string "'
            "DefaultEndpointsProtocol=https;"
            "AccountName=myaccount;"
            'AccountKey=abc123XYZ789+/==;EndpointSuffix=core.windows.net"'
        )
        result = AzureCommandSanitizer.sanitize(command)

        assert "abc123XYZ789+/==" not in result
        assert "[REDACTED]" in result
        assert "myaccount" in result
        assert "mycontainer" in result


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_convenience_function(self) -> None:
        """Test that convenience function works."""
        from azlin.security import sanitize_azure_command

        command = "az vm create --admin-password Secret123"
        result = sanitize_azure_command(command)

        assert "Secret123" not in result
        assert "[REDACTED]" in result
