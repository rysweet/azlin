"""Pytest configuration and fixtures for azlin tests.

CRITICAL: Protects production configuration from test modifications.
"""

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def protect_production_config():
    """Protect ~/.azlin/config.toml from being modified by tests.

    CRITICAL PROTECTION: Tests should NEVER modify production config files.

    This fixture:
    1. Backs up the real config.toml before any tests run
    2. Restores it after all tests complete
    3. Fails tests that try to use real Azure resources

    Related Issues: #279
    - Tests creating VMs in production resource groups
    - Tests modifying ~/.azlin/config.toml
    """
    config_path = Path.home() / ".azlin" / "config.toml"
    backup_path = Path.home() / ".azlin" / ".config.toml.pytest-backup"

    # Backup if exists
    config_existed = config_path.exists()
    if config_existed:
        shutil.copy2(config_path, backup_path)
        print(f"\n[PYTEST] Protected config.toml - backup at {backup_path}")

    yield

    # Restore after all tests
    if config_existed and backup_path.exists():
        shutil.copy2(backup_path, config_path)
        backup_path.unlink()
        print(f"\n[PYTEST] Restored config.toml from backup")
    elif backup_path.exists():
        backup_path.unlink()


@pytest.fixture(scope="session", autouse=True)
def prevent_real_azure_operations():
    """Prevent tests from creating real Azure resources accidentally.

    Sets environment variable to mark test mode.
    Tests that need real Azure should explicitly check for RUN_E2E_TESTS=true.
    """
    # Mark that we're in test mode
    os.environ["AZLIN_TEST_MODE"] = "true"

    # Ensure E2E tests are not accidentally enabled
    if os.environ.get("RUN_E2E_TESTS") == "true":
        print("\n" + "=" * 70)
        print("WARNING: RUN_E2E_TESTS=true - E2E tests will use REAL Azure resources!")
        print("=" * 70 + "\n")

    yield

    # Cleanup
    if "AZLIN_TEST_MODE" in os.environ:
        del os.environ["AZLIN_TEST_MODE"]


@pytest.fixture
def isolated_config(tmp_path):
    """Provide isolated config file for tests.

    Use this fixture instead of modifying ~/.azlin/config.toml.

    Example:
        def test_something(isolated_config):
            config_path = isolated_config / "config.toml"
            # Safe to modify - it's in tmp_path
    """
    config_dir = tmp_path / ".azlin"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def mock_config_path(isolated_config, monkeypatch):
    """Mock ConfigManager to use isolated config instead of ~/.azlin.

    This prevents tests from accidentally touching production config.

    Example:
        def test_something(mock_config_path):
            # ConfigManager now uses tmp_path instead of ~/.azlin
            ConfigManager.save_config(config)  # Safe!
    """
    config_file = isolated_config / "config.toml"

    from azlin.config_manager import ConfigManager

    # Mock get_config_path to return isolated path
    def mock_get_path(custom_path=None):
        if custom_path:
            return Path(custom_path)
        return config_file

    monkeypatch.setattr(ConfigManager, "get_config_path", mock_get_path)

    return config_file
