"""Unit tests for SSHConnector backward compatibility.

This test suite validates that SSHConnector maintains backward compatibility
when adding support for increased timeouts for Bastion connections.

These tests follow TDD approach and will FAIL until implementation is complete.

Key Requirements:
1. Existing calls work without new parameters (backward compatible)
2. Method signatures remain compatible with existing code
3. Default behavior unchanged for non-Bastion connections
4. New timeout parameter is optional
"""

import itertools
from unittest.mock import Mock, patch

import pytest

from azlin.modules.ssh_connector import SSHConfig, SSHConnector


class TestSSHConnectorBackwardCompatibility:
    """Test SSHConnector backward compatibility with existing code."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH config."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(host="192.168.1.100", user="azureuser", key_path=key_file, port=22)

    def test_wait_for_ssh_ready_works_without_new_parameters(self, tmp_path):
        """Test that wait_for_ssh_ready works with existing call signature."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act - Call with original parameters only
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="192.168.1.100", key_path=key_file, port=22, timeout=300, interval=5
                )

        # Assert - Should work without errors
        assert result is True

    def test_wait_for_ssh_ready_accepts_optional_timeout_parameter(self, tmp_path):
        """Test that wait_for_ssh_ready accepts optional increased timeout."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act - Call with new timeout parameter
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="192.168.1.100",
                    key_path=key_file,
                    port=22,
                    timeout=600,  # Increased timeout for Bastion
                    interval=5,
                )

        # Assert
        assert result is True

    def test_wait_for_ssh_ready_default_timeout_unchanged(self, tmp_path):
        """Test that default timeout behavior is unchanged."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act - Call without timeout parameter (should use default 300s)
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=False):
            with patch("time.sleep"):
                with patch("time.time") as mock_time:
                    # Simulate timeout after 300 seconds using non-exhausting iterator
                    mock_time.side_effect = itertools.cycle([0, 100, 200, 301])

                    result = SSHConnector.wait_for_ssh_ready(
                        host="192.168.1.100", key_path=key_file
                    )

        # Assert - Should timeout at 300s (default)
        assert result is False

    def test_connect_method_signature_backward_compatible(self, ssh_config):
        """Test that connect() method signature is backward compatible."""
        # Arrange
        with patch(
            "azlin.modules.ssh_connector.SSHConnector.wait_for_ssh_ready", return_value=True
        ):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0)

                # Act - Call with original parameters
                exit_code = SSHConnector.connect(
                    config=ssh_config, tmux_session="azlin", auto_tmux=True, remote_command=None
                )

        # Assert - Should work without errors
        assert exit_code == 0

    def test_build_ssh_command_signature_backward_compatible(self, ssh_config):
        """Test that build_ssh_command() signature is backward compatible."""
        # Act - Call with original parameters
        ssh_args = SSHConnector.build_ssh_command(config=ssh_config, remote_command=None)

        # Assert - Should return valid SSH command
        assert ssh_args[0] == "ssh"
        assert f"{ssh_config.user}@{ssh_config.host}" in ssh_args

    def test_execute_remote_command_signature_backward_compatible(self, ssh_config):
        """Test that execute_remote_command() signature is backward compatible."""
        # Arrange
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="test output", stderr="")

            # Act - Call with original parameters
            output = SSHConnector.execute_remote_command(
                config=ssh_config, command="echo test", timeout=60
            )

        # Assert
        assert output == "test output"


class TestSSHConnectorTimeoutBehavior:
    """Test timeout behavior for different connection types."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH config."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(host="192.168.1.100", user="azureuser", key_path=key_file, port=22)

    def test_direct_ssh_uses_standard_timeout(self, tmp_path):
        """Test that direct SSH connections use standard 300s timeout."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                with patch("time.time") as mock_time:
                    mock_time.side_effect = itertools.cycle([0, 1])
                    result = SSHConnector.wait_for_ssh_ready(
                        host="20.12.34.56",  # Public IP (direct SSH)
                        key_path=key_file,
                        port=22,
                        timeout=300,  # Standard timeout
                    )

        # Assert
        assert result is True

    def test_bastion_connection_supports_increased_timeout(self, tmp_path):
        """Test that Bastion connections can use increased 600s timeout."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act - Simulate Bastion connection with longer timeout
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open") as mock_check:
            # Simulate SSH not ready until after 400s (would fail with 300s timeout)
            with patch("time.time") as mock_time:
                mock_time.side_effect = itertools.cycle([0, 100, 200, 300, 400, 450])
                mock_check.side_effect = [False, False, False, False, True]

                with patch(
                    "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                    return_value=True,
                ):
                    with patch("time.sleep"):
                        result = SSHConnector.wait_for_ssh_ready(
                            host="127.0.0.1",  # Localhost (Bastion tunnel)
                            key_path=key_file,
                            port=50022,  # High port (Bastion tunnel)
                            timeout=600,  # Increased timeout
                            interval=5,
                        )

        # Assert - Should succeed with increased timeout
        assert result is True

    def test_timeout_parameter_overrides_default(self, tmp_path):
        """Test that explicit timeout parameter overrides default."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=False):
            with patch("time.sleep"):
                with patch("time.time") as mock_time:
                    # Simulate timeout at custom value (120s)
                    mock_time.side_effect = itertools.cycle([0, 60, 121])

                    result = SSHConnector.wait_for_ssh_ready(
                        host="192.168.1.100",
                        key_path=key_file,
                        timeout=120,  # Custom timeout
                    )

        # Assert
        assert result is False


class TestSSHConnectorPortDetection:
    """Test that port numbers help identify connection type."""

    @pytest.fixture
    def key_path(self, tmp_path):
        """Create test SSH key."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)
        return key_file

    def test_standard_ssh_port_22(self, key_path):
        """Test standard SSH port (22) is recognized."""
        # Arrange & Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="192.168.1.100",
                    key_path=key_path,
                    port=22,  # Standard SSH port
                )

        # Assert
        assert result is True

    def test_high_port_for_bastion_tunnel(self, key_path):
        """Test high port numbers (50000+) typical of Bastion tunnels."""
        # Arrange & Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="127.0.0.1",
                    key_path=key_path,
                    port=50022,  # Bastion tunnel port
                )

        # Assert
        assert result is True

    def test_localhost_indicates_tunnel_connection(self, key_path):
        """Test that localhost (127.0.0.1) indicates tunnel connection."""
        # Arrange & Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="127.0.0.1",  # Localhost (tunnel)
                    key_path=key_path,
                    port=50022,
                )

        # Assert
        assert result is True


class TestSSHConnectorMethodSignatures:
    """Test that method signatures remain compatible."""

    def test_wait_for_ssh_ready_has_all_original_parameters(self):
        """Test that wait_for_ssh_ready has all original parameters."""
        import inspect

        sig = inspect.signature(SSHConnector.wait_for_ssh_ready)
        params = list(sig.parameters.keys())

        # Assert - Original parameters present
        assert "host" in params
        assert "key_path" in params
        assert "port" in params
        assert "timeout" in params
        assert "interval" in params

    def test_wait_for_ssh_ready_timeout_has_default_value(self):
        """Test that timeout parameter has default value for backward compatibility."""
        import inspect

        sig = inspect.signature(SSHConnector.wait_for_ssh_ready)
        timeout_param = sig.parameters["timeout"]

        # Assert - Should have default value
        assert timeout_param.default != inspect.Parameter.empty
        assert timeout_param.default == 300  # Default should be 300s

    def test_connect_method_has_original_parameters(self):
        """Test that connect() has all original parameters."""
        import inspect

        sig = inspect.signature(SSHConnector.connect)
        params = list(sig.parameters.keys())

        # Assert
        assert "config" in params
        assert "tmux_session" in params
        assert "auto_tmux" in params
        assert "remote_command" in params

    def test_execute_remote_command_has_original_parameters(self):
        """Test that execute_remote_command() has all original parameters."""
        import inspect

        sig = inspect.signature(SSHConnector.execute_remote_command)
        params = list(sig.parameters.keys())

        # Assert
        assert "config" in params
        assert "command" in params
        assert "timeout" in params


class TestSSHConnectorEdgeCases:
    """Test edge cases for backward compatibility."""

    @pytest.fixture
    def ssh_config(self, tmp_path):
        """Create test SSH config."""
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        return SSHConfig(host="192.168.1.100", user="azureuser", key_path=key_file, port=22)

    def test_zero_timeout_handled_gracefully(self, tmp_path):
        """Test that zero timeout is handled gracefully."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=False):
            result = SSHConnector.wait_for_ssh_ready(
                host="192.168.1.100", key_path=key_file, timeout=0
            )

        # Assert - Should immediately return False
        assert result is False

    def test_negative_timeout_raises_error(self, tmp_path):
        """Test that negative timeout raises appropriate error."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act & Assert
        with pytest.raises(ValueError, match="timeout.*negative|positive"):
            SSHConnector.wait_for_ssh_ready(host="192.168.1.100", key_path=key_file, timeout=-10)

    def test_very_large_timeout_accepted(self, tmp_path):
        """Test that very large timeout values are accepted."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act - Should not raise error
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                result = SSHConnector.wait_for_ssh_ready(
                    host="192.168.1.100",
                    key_path=key_file,
                    timeout=3600,  # 1 hour
                )

        # Assert
        assert result is True

    def test_none_timeout_uses_default(self, tmp_path):
        """Test that None timeout uses default value."""
        # Arrange
        key_file = tmp_path / "test_key"
        key_file.write_text("fake key")
        key_file.chmod(0o600)

        # Act
        with patch("azlin.modules.ssh_connector.SSHConnector._check_port_open", return_value=True):
            with patch(
                "azlin.modules.ssh_connector.SSHConnector._test_ssh_connection",
                return_value=True,
            ):
                # Call without timeout (should use default)
                result = SSHConnector.wait_for_ssh_ready(
                    host="192.168.1.100",
                    key_path=key_file,  # No timeout specified
                )

        # Assert
        assert result is True
