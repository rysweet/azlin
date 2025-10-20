"""Security tests for config_manager module.

These tests specifically verify protection against path traversal attacks
and other security vulnerabilities in configuration file handling.
"""

from pathlib import Path

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestConfigPathSecurity:
    """Test configuration path security validation."""

    def test_path_traversal_attack(self, tmp_path):
        """Test that path traversal attempts are rejected."""
        # Attempt to access /etc/passwd via path traversal
        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path("../../../../../../etc/passwd")

    def test_absolute_path_attack(self, tmp_path):
        """Test that absolute paths to sensitive locations are rejected."""
        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path("/etc/passwd")

    def test_symlink_attack_to_sensitive_file(self, tmp_path):
        """Test that symlinks to sensitive files are rejected."""
        # Create a symlink to /etc/passwd
        symlink_path = tmp_path / "malicious_config.toml"
        symlink_path.symlink_to("/etc/passwd")

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.get_config_path(str(symlink_path))

    def test_valid_path_in_azlin_dir(self, tmp_path):
        """Test that valid paths in ~/.azlin/ are accepted."""
        # Create a config file in ~/.azlin/
        azlin_dir = Path.home() / ".azlin"
        azlin_dir.mkdir(parents=True, exist_ok=True)

        config_file = azlin_dir / "test_config.toml"
        config_file.write_text("")

        try:
            # Should succeed
            path = ConfigManager.get_config_path(str(config_file))
            assert path == config_file.resolve()
        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()

    def test_valid_path_in_current_directory(self, tmp_path):
        """Test that valid paths in current working directory are accepted."""
        # Create a config file in current directory
        config_file = Path.cwd() / "test_config.toml"
        config_file.write_text("")

        try:
            # Should succeed
            path = ConfigManager.get_config_path(str(config_file))
            assert path == config_file.resolve()
        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()

    def test_path_traversal_within_allowed_dir(self, tmp_path):
        """Test that path traversal within allowed directory is accepted."""
        # Create nested directory structure in ~/.azlin/
        azlin_dir = Path.home() / ".azlin"
        azlin_dir.mkdir(parents=True, exist_ok=True)
        nested_dir = azlin_dir / "subdir"
        nested_dir.mkdir(exist_ok=True)

        config_file = nested_dir / "config.toml"
        config_file.write_text("")

        try:
            # Use path traversal within allowed directory
            path_with_traversal = azlin_dir / "subdir" / ".." / "subdir" / "config.toml"

            # Should succeed because resolved path is within ~/.azlin/
            path = ConfigManager.get_config_path(str(path_with_traversal))
            assert path.resolve() == config_file.resolve()
        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()
            if nested_dir.exists():
                nested_dir.rmdir()

    def test_save_config_with_path_traversal(self, tmp_path):
        """Test that saving config with path traversal is rejected."""
        config = AzlinConfig()

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.save_config(config, "../../../tmp/evil_config.toml")

    def test_save_config_with_absolute_path(self, tmp_path):
        """Test that saving config to absolute path outside allowed dirs is rejected."""
        config = AzlinConfig()

        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.save_config(config, "/tmp/evil_config.toml")

    def test_save_config_in_allowed_directory(self, tmp_path):
        """Test that saving config in allowed directory succeeds."""
        config = AzlinConfig(default_resource_group="test-rg")

        # Save to current directory (allowed)
        config_file = Path.cwd() / "test_config.toml"

        try:
            ConfigManager.save_config(config, str(config_file))

            # Verify file exists and has secure permissions
            assert config_file.exists()
            mode = config_file.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()

    def test_empty_path(self):
        """Test that empty path falls back to default."""
        # Should use default path (no error)
        path = ConfigManager.get_config_path("")
        assert path == ConfigManager.DEFAULT_CONFIG_FILE

    def test_mixed_traversal_attempts(self):
        """Test various mixed path traversal attempts."""
        malicious_paths = [
            "~/../../../etc/passwd",  # Home expansion + traversal
            "./../../../etc/passwd",  # Relative traversal
            "/etc/../etc/passwd",  # Absolute with traversal
            "//etc/passwd",  # Double slash
        ]

        for malicious_path in malicious_paths:
            with pytest.raises(ConfigError, match="outside allowed directories"):
                ConfigManager.get_config_path(malicious_path)

    def test_symlink_within_allowed_directory(self, tmp_path):
        """Test that symlinks within allowed directory are accepted."""
        azlin_dir = Path.home() / ".azlin"
        azlin_dir.mkdir(parents=True, exist_ok=True)

        # Create a real file
        real_file = azlin_dir / "real_config.toml"
        real_file.write_text("")

        # Create symlink to it (within same directory)
        symlink_file = azlin_dir / "symlink_config.toml"
        symlink_file.symlink_to(real_file)

        try:
            # Should succeed because symlink resolves to path within ~/.azlin/
            path = ConfigManager.get_config_path(str(symlink_file))
            assert path.resolve() == real_file.resolve()
        finally:
            # Cleanup
            if symlink_file.exists():
                symlink_file.unlink()
            if real_file.exists():
                real_file.unlink()


class TestConfigManagerIntegration:
    """Integration tests for ConfigManager with security validation."""

    def test_load_and_save_config_in_allowed_dir(self, tmp_path):
        """Test full load/save cycle in allowed directory."""
        config_file = Path.cwd() / "integration_test_config.toml"

        try:
            # Create config
            config = AzlinConfig(
                default_resource_group="integration-test-rg", default_region="westus2"
            )

            # Save
            ConfigManager.save_config(config, str(config_file))

            # Load
            loaded_config = ConfigManager.load_config(str(config_file))

            # Verify
            assert loaded_config.default_resource_group == "integration-test-rg"
            assert loaded_config.default_region == "westus2"
        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()

    def test_update_config_with_security_validation(self, tmp_path):
        """Test that update_config also validates paths."""
        # Attempting to update config at malicious path should fail
        with pytest.raises(ConfigError, match="outside allowed directories"):
            ConfigManager.update_config(custom_path="/etc/passwd", default_resource_group="evil-rg")
