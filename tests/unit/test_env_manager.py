"""Unit tests for env_manager module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.env_manager import EnvManager, EnvManagerError
from azlin.modules.ssh_connector import SSHConfig


class TestEnvManager:
    """Tests for EnvManager class."""

    @pytest.fixture
    def ssh_config(self):
        """Create mock SSH config."""
        return SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/id_rsa"))

    @pytest.fixture
    def sample_bashrc_content(self):
        """Sample bashrc content without azlin env vars."""
        return """# ~/.bashrc

# User configuration
export PATH=$HOME/bin:$PATH
alias ll='ls -la'

# End of file
"""

    @pytest.fixture
    def sample_bashrc_with_env(self):
        """Sample bashrc with azlin env vars."""
        return """# ~/.bashrc

# User configuration
export PATH=$HOME/bin:$PATH
alias ll='ls -la'

# AZLIN_ENV_START - Do not edit this section manually
export DATABASE_URL="postgres://localhost/db"
export API_KEY="secret123"
# AZLIN_ENV_END

# End of file
"""

    def test_set_env_var_success(self, ssh_config, sample_bashrc_content):
        """Test setting a new environment variable."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            # Mock reading current bashrc
            mock_exec.side_effect = [
                sample_bashrc_content,  # cat ~/.bashrc
                "",  # echo to temp file
                "",  # mv temp to bashrc
            ]

            result = EnvManager.set_env_var(ssh_config, "DATABASE_URL", "postgres://localhost/db")

            assert result is True
            assert mock_exec.call_count == 3

    def test_set_env_var_updates_existing(self, ssh_config, sample_bashrc_with_env):
        """Test updating an existing environment variable."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            # Mock reading current bashrc with existing var
            mock_exec.side_effect = [
                sample_bashrc_with_env,  # cat ~/.bashrc
                "",  # echo to temp file
                "",  # mv temp to bashrc
            ]

            result = EnvManager.set_env_var(ssh_config, "DATABASE_URL", "postgres://newhost/db")

            assert result is True
            # Check that the update command was called
            assert mock_exec.call_count == 3

    def test_list_env_vars_empty(self, ssh_config, sample_bashrc_content):
        """Test listing when no environment variables are set."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.return_value = sample_bashrc_content

            env_vars = EnvManager.list_env_vars(ssh_config)

            assert env_vars == {}

    def test_list_env_vars_multiple(self, ssh_config, sample_bashrc_with_env):
        """Test listing multiple environment variables."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.return_value = sample_bashrc_with_env

            env_vars = EnvManager.list_env_vars(ssh_config)

            assert len(env_vars) == 2
            assert env_vars["DATABASE_URL"] == "postgres://localhost/db"
            assert env_vars["API_KEY"] == "secret123"

    def test_delete_env_var_success(self, ssh_config, sample_bashrc_with_env):
        """Test deleting an existing environment variable."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                sample_bashrc_with_env,  # cat ~/.bashrc
                "",  # echo to temp file
                "",  # mv temp to bashrc
            ]

            result = EnvManager.delete_env_var(ssh_config, "API_KEY")

            assert result is True

    def test_delete_env_var_not_found(self, ssh_config, sample_bashrc_with_env):
        """Test deleting a non-existent environment variable."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.return_value = sample_bashrc_with_env

            result = EnvManager.delete_env_var(ssh_config, "NONEXISTENT_VAR")

            assert result is False

    def test_export_env_vars_format(self, ssh_config, sample_bashrc_with_env):
        """Test exporting environment variables to .env format."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.return_value = sample_bashrc_with_env

            output = EnvManager.export_env_vars(ssh_config)

            assert 'DATABASE_URL="postgres://localhost/db"' in output
            assert 'API_KEY="secret123"' in output

    def test_export_env_vars_to_file(self, ssh_config, sample_bashrc_with_env, tmp_path):
        """Test exporting environment variables to a file."""
        output_file = tmp_path / "test.env"

        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.return_value = sample_bashrc_with_env

            result = EnvManager.export_env_vars(ssh_config, str(output_file))

            assert result == str(output_file)
            assert output_file.exists()
            content = output_file.read_text()
            assert 'DATABASE_URL="postgres://localhost/db"' in content

    def test_validate_env_key_valid(self):
        """Test validation of valid environment variable names."""
        valid_keys = [
            "DATABASE_URL",
            "API_KEY",
            "MY_VAR_123",
            "SIMPLE",
            "_LEADING_UNDERSCORE",
        ]

        for key in valid_keys:
            is_valid, _message = EnvManager.validate_env_key(key)
            assert is_valid is True, f"Expected {key} to be valid"

    def test_validate_env_key_invalid(self):
        """Test validation of invalid environment variable names."""
        invalid_keys = [
            "123_START_WITH_NUMBER",
            "has-dash",
            "has space",
            "has.dot",
            "",
            "special!char",
        ]

        for key in invalid_keys:
            is_valid, message = EnvManager.validate_env_key(key)
            assert is_valid is False, f"Expected {key} to be invalid"
            assert len(message) > 0

    def test_detect_secrets_warning(self):
        """Test detection of potential secrets in values."""
        secret_patterns = [
            ("my_api_key_secret123", ["API_KEY"]),
            ("postgres://user:pass@host/db", ["postgres://"]),
            ("Bearer token_abc123", ["token"]),
            ("password=secret", ["password"]),
            ("mongodb+srv://user:pass@cluster", ["mongodb+srv://"]),
        ]

        for value, expected_patterns in secret_patterns:
            warnings = EnvManager.detect_secrets(value)
            assert len(warnings) > 0, f"Expected warnings for {value}"
            for pattern in expected_patterns:
                assert any(pattern.lower() in w.lower() for w in warnings), (
                    f"Expected pattern '{pattern}' in warnings for {value}"
                )

    def test_detect_secrets_no_warning(self):
        """Test no warnings for non-secret values."""
        safe_values = [
            "production",
            "http://localhost:3000",
            "my-app-name",
            "true",
            "123",
        ]

        for value in safe_values:
            warnings = EnvManager.detect_secrets(value)
            assert len(warnings) == 0, f"Expected no warnings for {value}"

    def test_import_env_file(self, ssh_config, tmp_path):
        """Test importing environment variables from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """# Comment line
DATABASE_URL="postgres://localhost/db"
API_KEY="secret123"
# Another comment
EXPORT_VAR="value"
"""
        )

        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                "# bashrc content",  # cat ~/.bashrc for each set
                "",  # echo
                "",  # mv
            ] * 3  # 3 variables to set

            count = EnvManager.import_env_file(ssh_config, str(env_file))

            assert count == 3

    def test_import_env_file_invalid_format(self, ssh_config, tmp_path):
        """Test importing with invalid .env format."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """INVALID LINE WITHOUT EQUALS
DATABASE_URL="value"
"""
        )

        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                "# bashrc",
                "",
                "",
            ]

            # Should only import valid lines
            count = EnvManager.import_env_file(ssh_config, str(env_file))
            assert count == 1

    def test_bashrc_section_isolation(self, ssh_config, sample_bashrc_content):
        """Test that setting env vars doesn't affect other bashrc content."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                sample_bashrc_content,
                "",
                "",
            ]

            EnvManager.set_env_var(ssh_config, "TEST_VAR", "value")

            # Check that the write command (first printf) contains the right content
            # The actual content is in the first call, wrapped in printf command
            write_call = mock_exec.call_args_list[1]
            printf_command = write_call[0][1]

            # Extract the content from printf command (between the single quotes)
            # Format is: printf '%s' 'content' > file
            import re

            match = re.search(r"printf '%s' '(.+?)' >", printf_command, re.DOTALL)
            written_content = match.group(1).replace("'\\''", "'") if match else printf_command

            # Original content should be preserved
            assert "export PATH=$HOME/bin:$PATH" in written_content
            assert "alias ll=" in written_content
            # New content should be added in markers
            assert "# AZLIN_ENV_START" in written_content
            assert "# AZLIN_ENV_END" in written_content
            assert 'export TEST_VAR="value"' in written_content

    def test_set_env_var_with_special_chars(self, ssh_config, sample_bashrc_content):
        """Test setting env var with special characters that need escaping."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                sample_bashrc_content,
                "",
                "",
            ]

            # Value with quotes and special chars
            result = EnvManager.set_env_var(
                ssh_config, "COMPLEX_VAR", 'value with "quotes" and $pecial'
            )

            assert result is True

    def test_ssh_connection_error(self, ssh_config):
        """Test handling of SSH connection errors."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = Exception("SSH connection failed")

            with pytest.raises(EnvManagerError) as exc_info:
                EnvManager.list_env_vars(ssh_config)

            assert "SSH connection failed" in str(exc_info.value)

    def test_clear_all_env_vars(self, ssh_config, sample_bashrc_with_env):
        """Test clearing all environment variables."""
        with patch("azlin.env_manager.SSHConnector.execute_remote_command") as mock_exec:
            mock_exec.side_effect = [
                sample_bashrc_with_env,
                "",
                "",
            ]

            result = EnvManager.clear_all_env_vars(ssh_config)

            assert result is True
            # Check that the section was removed
            write_call = mock_exec.call_args_list[1]
            written_content = write_call[0][1]
            assert "# AZLIN_ENV_START" not in written_content
            assert "# AZLIN_ENV_END" not in written_content
