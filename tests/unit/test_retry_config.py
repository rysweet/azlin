"""Tests for retry configuration."""

import os
from unittest.mock import patch

from azlin.retry_config import RetryConfig, get_retry_config, reset_retry_config


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self):
        """Should have sensible default values."""
        config = RetryConfig()

        # Azure CLI defaults
        assert config.azure_cli_max_attempts == 3
        assert config.azure_cli_initial_delay == 1.0
        assert config.azure_cli_max_delay == 30.0

        # SSH defaults
        assert config.ssh_max_attempts == 3
        assert config.ssh_initial_delay == 2.0
        assert config.ssh_max_delay == 10.0

        # Remote command defaults
        assert config.remote_command_max_attempts == 3
        assert config.remote_command_initial_delay == 1.0
        assert config.remote_command_max_delay == 30.0

        # Rate limiting defaults
        assert config.rate_limit_max_wait == 300.0
        assert config.rate_limit_default_backoff == 10.0

        # Global settings
        assert config.jitter_enabled is True

    def test_custom_values(self):
        """Should accept custom values."""
        config = RetryConfig(
            azure_cli_max_attempts=5,
            azure_cli_initial_delay=2.0,
            ssh_max_attempts=4,
            rate_limit_max_wait=600.0,
            jitter_enabled=False,
        )

        assert config.azure_cli_max_attempts == 5
        assert config.azure_cli_initial_delay == 2.0
        assert config.ssh_max_attempts == 4
        assert config.rate_limit_max_wait == 600.0
        assert config.jitter_enabled is False


class TestFromEnvironment:
    """Tests for RetryConfig.from_environment()."""

    def test_loads_from_environment_variables(self):
        """Should load configuration from environment variables."""
        env_vars = {
            "AZLIN_RETRY_MAX_ATTEMPTS": "5",
            "AZLIN_RETRY_INITIAL_DELAY": "2.0",
            "AZLIN_RETRY_MAX_DELAY": "60.0",
            "AZLIN_RETRY_JITTER_ENABLED": "false",
            "AZLIN_RATE_LIMIT_MAX_WAIT": "600.0",
            "AZLIN_RATE_LIMIT_DEFAULT_BACKOFF": "15.0",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = RetryConfig.from_environment()

        assert config.azure_cli_max_attempts == 5
        assert config.azure_cli_initial_delay == 2.0
        assert config.azure_cli_max_delay == 60.0
        assert config.ssh_max_attempts == 5  # Uses default
        assert config.rate_limit_max_wait == 600.0
        assert config.rate_limit_default_backoff == 15.0
        assert config.jitter_enabled is False

    def test_loads_specific_azure_cli_settings(self):
        """Should load Azure CLI specific settings."""
        env_vars = {
            "AZLIN_RETRY_AZURE_CLI_MAX_ATTEMPTS": "7",
            "AZLIN_RETRY_AZURE_CLI_INITIAL_DELAY": "3.0",
            "AZLIN_RETRY_AZURE_CLI_MAX_DELAY": "90.0",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = RetryConfig.from_environment()

        assert config.azure_cli_max_attempts == 7
        assert config.azure_cli_initial_delay == 3.0
        assert config.azure_cli_max_delay == 90.0

    def test_loads_specific_ssh_settings(self):
        """Should load SSH specific settings."""
        env_vars = {
            "AZLIN_RETRY_SSH_MAX_ATTEMPTS": "6",
            "AZLIN_RETRY_SSH_INITIAL_DELAY": "4.0",
            "AZLIN_RETRY_SSH_MAX_DELAY": "20.0",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = RetryConfig.from_environment()

        assert config.ssh_max_attempts == 6
        assert config.ssh_initial_delay == 4.0
        assert config.ssh_max_delay == 20.0

    def test_uses_defaults_when_env_vars_not_set(self):
        """Should use defaults when environment variables not set."""
        # Clear relevant env vars
        env_vars = {k: v for k, v in os.environ.items() if not k.startswith("AZLIN_RETRY")}

        with patch.dict(os.environ, env_vars, clear=True):
            config = RetryConfig.from_environment()

        assert config.azure_cli_max_attempts == 3
        assert config.ssh_max_attempts == 3
        assert config.jitter_enabled is True
        assert config.rate_limit_max_wait == 300.0

    def test_jitter_enabled_parsing(self):
        """Should correctly parse jitter enabled flag."""
        # Test 'true'
        with patch.dict(os.environ, {"AZLIN_RETRY_JITTER_ENABLED": "true"}):
            config = RetryConfig.from_environment()
            assert config.jitter_enabled is True

        # Test 'false'
        with patch.dict(os.environ, {"AZLIN_RETRY_JITTER_ENABLED": "false"}):
            config = RetryConfig.from_environment()
            assert config.jitter_enabled is False

        # Test 'True' (mixed case)
        with patch.dict(os.environ, {"AZLIN_RETRY_JITTER_ENABLED": "True"}):
            config = RetryConfig.from_environment()
            assert config.jitter_enabled is True

        # Test invalid value (defaults to false)
        with patch.dict(os.environ, {"AZLIN_RETRY_JITTER_ENABLED": "invalid"}):
            config = RetryConfig.from_environment()
            assert config.jitter_enabled is False


class TestGetRetryConfig:
    """Tests for get_retry_config()."""

    def test_returns_singleton_instance(self):
        """Should return same instance on multiple calls."""
        reset_retry_config()  # Clear any cached config

        config1 = get_retry_config()
        config2 = get_retry_config()

        assert config1 is config2

    def test_loads_from_environment_on_first_access(self):
        """Should load from environment on first access."""
        reset_retry_config()

        env_vars = {
            "AZLIN_RETRY_MAX_ATTEMPTS": "8",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = get_retry_config()

        assert config.azure_cli_max_attempts == 8

    def test_caches_configuration(self):
        """Should cache configuration after first load."""
        reset_retry_config()

        # First load with one value
        with patch.dict(os.environ, {"AZLIN_RETRY_MAX_ATTEMPTS": "4"}):
            config1 = get_retry_config()

        # Change environment (should not affect cached config)
        with patch.dict(os.environ, {"AZLIN_RETRY_MAX_ATTEMPTS": "9"}):
            config2 = get_retry_config()

        assert config1 is config2
        assert config1.azure_cli_max_attempts == 4  # Original value


class TestResetRetryConfig:
    """Tests for reset_retry_config()."""

    def test_clears_cached_configuration(self):
        """Should clear cached configuration."""
        reset_retry_config()

        # Load config with first value
        with patch.dict(os.environ, {"AZLIN_RETRY_MAX_ATTEMPTS": "3"}):
            config1 = get_retry_config()
            assert config1.azure_cli_max_attempts == 3

        # Reset and reload with new value
        reset_retry_config()

        with patch.dict(os.environ, {"AZLIN_RETRY_MAX_ATTEMPTS": "7"}):
            config2 = get_retry_config()
            assert config2.azure_cli_max_attempts == 7

        # Should be different instances
        assert config1 is not config2

    def test_allows_runtime_config_changes(self):
        """Should allow runtime configuration changes."""
        reset_retry_config()

        # Initial config
        config1 = get_retry_config()
        initial_attempts = config1.azure_cli_max_attempts

        # Simulate runtime change
        reset_retry_config()

        with patch.dict(os.environ, {"AZLIN_RETRY_MAX_ATTEMPTS": "10"}):
            config2 = get_retry_config()

        assert config2.azure_cli_max_attempts == 10
        assert config2.azure_cli_max_attempts != initial_attempts


class TestIntegrationScenarios:
    """Integration tests for configuration usage."""

    def test_production_like_configuration(self):
        """Should support production-like configuration."""
        env_vars = {
            "AZLIN_RETRY_MAX_ATTEMPTS": "5",
            "AZLIN_RETRY_INITIAL_DELAY": "2.0",
            "AZLIN_RETRY_MAX_DELAY": "60.0",
            "AZLIN_RATE_LIMIT_MAX_WAIT": "600.0",
            "AZLIN_RATE_LIMIT_DEFAULT_BACKOFF": "20.0",
            "AZLIN_RETRY_JITTER_ENABLED": "true",
        }

        reset_retry_config()

        with patch.dict(os.environ, env_vars, clear=False):
            config = get_retry_config()

        # Verify production settings
        assert config.azure_cli_max_attempts == 5
        assert config.azure_cli_initial_delay == 2.0
        assert config.rate_limit_max_wait == 600.0
        assert config.jitter_enabled is True

    def test_aggressive_retry_configuration(self):
        """Should support aggressive retry configuration."""
        env_vars = {
            "AZLIN_RETRY_MAX_ATTEMPTS": "10",
            "AZLIN_RETRY_INITIAL_DELAY": "0.5",
            "AZLIN_RETRY_MAX_DELAY": "120.0",
        }

        reset_retry_config()

        with patch.dict(os.environ, env_vars, clear=False):
            config = get_retry_config()

        assert config.azure_cli_max_attempts == 10
        assert config.azure_cli_initial_delay == 0.5
        assert config.azure_cli_max_delay == 120.0

    def test_conservative_retry_configuration(self):
        """Should support conservative retry configuration."""
        env_vars = {
            "AZLIN_RETRY_MAX_ATTEMPTS": "2",
            "AZLIN_RETRY_INITIAL_DELAY": "5.0",
            "AZLIN_RETRY_JITTER_ENABLED": "false",
        }

        reset_retry_config()

        with patch.dict(os.environ, env_vars, clear=False):
            config = get_retry_config()

        assert config.azure_cli_max_attempts == 2
        assert config.azure_cli_initial_delay == 5.0
        assert config.jitter_enabled is False
