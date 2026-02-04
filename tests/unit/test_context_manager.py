"""Unit tests for context_manager module."""

import os
import subprocess as real_subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.context_manager import (
    Context,
    ContextConfig,
    ContextError,
    ContextManager,
    validate_context_name,
    validate_uuid,
)


class TestValidateUUID:
    """Tests for UUID validation."""

    def test_valid_uuid(self):
        """Test valid UUID format."""
        valid_uuid = "12345678-1234-1234-1234-123456789abc"
        validate_uuid(valid_uuid, "test_field")  # Should not raise

    def test_valid_uuid_uppercase(self):
        """Test valid UUID with uppercase."""
        valid_uuid = "12345678-1234-1234-1234-123456789ABC"
        validate_uuid(valid_uuid, "test_field")  # Should not raise

    def test_invalid_uuid_format(self):
        """Test invalid UUID format."""
        with pytest.raises(ContextError, match="Invalid test_field format"):
            validate_uuid("not-a-uuid", "test_field")

    def test_invalid_uuid_missing_hyphens(self):
        """Test UUID without hyphens."""
        with pytest.raises(ContextError, match="Invalid test_field format"):
            validate_uuid("12345678123412341234123456789abc", "test_field")

    def test_empty_uuid(self):
        """Test empty UUID."""
        with pytest.raises(ContextError, match="test_field cannot be empty"):
            validate_uuid("", "test_field")


class TestValidateContextName:
    """Tests for context name validation."""

    def test_valid_name(self):
        """Test valid context name."""
        validate_context_name("production")  # Should not raise
        validate_context_name("dev-environment")  # Should not raise
        validate_context_name("staging_01")  # Should not raise

    def test_invalid_name_special_chars(self):
        """Test name with invalid special characters."""
        with pytest.raises(ContextError, match="Invalid context name"):
            validate_context_name("prod@env")

    def test_invalid_name_spaces(self):
        """Test name with spaces."""
        with pytest.raises(ContextError, match="Invalid context name"):
            validate_context_name("prod env")

    def test_invalid_name_too_long(self):
        """Test name exceeding length limit."""
        long_name = "a" * 65
        with pytest.raises(ContextError, match="Context name too long"):
            validate_context_name(long_name)

    def test_invalid_name_empty(self):
        """Test empty context name."""
        with pytest.raises(ContextError, match="Context name cannot be empty"):
            validate_context_name("")

    def test_reserved_name_current(self):
        """Test reserved name 'current'."""
        with pytest.raises(ContextError, match="reserved"):
            validate_context_name("current")

    def test_reserved_name_definitions(self):
        """Test reserved name 'definitions'."""
        with pytest.raises(ContextError, match="reserved"):
            validate_context_name("definitions")


class TestContext:
    """Tests for Context dataclass."""

    def test_create_valid_context(self):
        """Test creating valid context."""
        ctx = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        assert ctx.name == "production"
        assert ctx.subscription_id == "12345678-1234-1234-1234-123456789abc"
        assert ctx.tenant_id == "87654321-4321-4321-4321-cba987654321"
        assert ctx.auth_profile is None
        assert ctx.description is None

    def test_create_context_with_auth_profile(self):
        """Test creating context with auth profile."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
            auth_profile="prod-sp",
            description="Production environment",
        )
        assert ctx.auth_profile == "prod-sp"
        assert ctx.description == "Production environment"

    def test_invalid_subscription_id(self):
        """Test context with invalid subscription ID."""
        with pytest.raises(ContextError, match="Invalid subscription_id format"):
            Context(
                name="prod",
                subscription_id="invalid-uuid",
                tenant_id="87654321-4321-4321-4321-cba987654321",
            )

    def test_invalid_tenant_id(self):
        """Test context with invalid tenant ID."""
        with pytest.raises(ContextError, match="Invalid tenant_id format"):
            Context(
                name="prod",
                subscription_id="12345678-1234-1234-1234-123456789abc",
                tenant_id="invalid-uuid",
            )

    def test_invalid_auth_profile(self):
        """Test context with invalid auth profile name."""
        with pytest.raises(ContextError, match="Invalid auth_profile format"):
            Context(
                name="prod",
                subscription_id="12345678-1234-1234-1234-123456789abc",
                tenant_id="87654321-4321-4321-4321-cba987654321",
                auth_profile="invalid@profile",
            )

    def test_to_dict(self):
        """Test converting context to dictionary."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
            auth_profile="prod-sp",
        )
        data = ctx.to_dict()
        assert data["subscription_id"] == "12345678-1234-1234-1234-123456789abc"
        assert data["tenant_id"] == "87654321-4321-4321-4321-cba987654321"
        assert data["auth_profile"] == "prod-sp"
        assert "name" not in data  # Name is the key in TOML

    def test_to_dict_minimal(self):
        """Test to_dict with only required fields."""
        ctx = Context(
            name="dev",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        data = ctx.to_dict()
        assert "subscription_id" in data
        assert "tenant_id" in data
        assert "auth_profile" not in data
        assert "description" not in data

    def test_from_dict(self):
        """Test creating context from dictionary."""
        data = {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "tenant_id": "87654321-4321-4321-4321-cba987654321",
            "auth_profile": "prod-sp",
            "description": "Production",
        }
        ctx = Context.from_dict("production", data)
        assert ctx.name == "production"
        assert ctx.subscription_id == "12345678-1234-1234-1234-123456789abc"
        assert ctx.tenant_id == "87654321-4321-4321-4321-cba987654321"
        assert ctx.auth_profile == "prod-sp"
        assert ctx.description == "Production"

    def test_from_dict_missing_subscription(self):
        """Test from_dict with missing subscription_id."""
        data = {"tenant_id": "87654321-4321-4321-4321-cba987654321"}
        with pytest.raises(ContextError, match="missing required field: subscription_id"):
            Context.from_dict("prod", data)

    def test_from_dict_missing_tenant(self):
        """Test from_dict with missing tenant_id."""
        data = {"subscription_id": "12345678-1234-1234-1234-123456789abc"}
        with pytest.raises(ContextError, match="missing required field: tenant_id"):
            Context.from_dict("prod", data)


class TestContextConfig:
    """Tests for ContextConfig dataclass."""

    def test_empty_config(self):
        """Test creating empty context config."""
        config = ContextConfig()
        assert config.current is None
        assert config.contexts == {}

    def test_config_with_contexts(self):
        """Test creating config with contexts."""
        ctx1 = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        ctx2 = Context(
            name="dev",
            subscription_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
        )
        config = ContextConfig(current="prod", contexts={"prod": ctx1, "dev": ctx2})
        assert config.current == "prod"
        assert len(config.contexts) == 2

    def test_invalid_current_context(self):
        """Test config with invalid current context."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        with pytest.raises(ContextError, match="Current context 'missing' not found"):
            ContextConfig(current="missing", contexts={"prod": ctx})

    def test_get_current_context(self):
        """Test getting current context."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="prod", contexts={"prod": ctx})
        current = config.get_current_context()
        assert current is not None
        assert current.name == "prod"

    def test_get_current_context_none(self):
        """Test getting current context when none set."""
        config = ContextConfig()
        assert config.get_current_context() is None

    def test_set_current_context(self):
        """Test setting current context."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"prod": ctx})
        config.set_current_context("prod")
        assert config.current == "prod"

    def test_set_current_context_not_found(self):
        """Test setting non-existent current context."""
        config = ContextConfig()
        with pytest.raises(ContextError, match="Context 'missing' not found"):
            config.set_current_context("missing")

    def test_add_context(self):
        """Test adding context."""
        config = ContextConfig()
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config.add_context(ctx)
        assert "prod" in config.contexts
        assert config.contexts["prod"].name == "prod"

    def test_delete_context(self):
        """Test deleting context."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"prod": ctx})
        result = config.delete_context("prod")
        assert result is True
        assert "prod" not in config.contexts

    def test_delete_context_not_found(self):
        """Test deleting non-existent context."""
        config = ContextConfig()
        result = config.delete_context("missing")
        assert result is False

    def test_delete_current_context(self):
        """Test deleting current context clears current."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="prod", contexts={"prod": ctx})
        config.delete_context("prod")
        assert config.current is None

    def test_rename_context(self):
        """Test renaming context."""
        ctx = Context(
            name="old",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"old": ctx})
        config.rename_context("old", "new")
        assert "old" not in config.contexts
        assert "new" in config.contexts
        assert config.contexts["new"].name == "new"

    def test_rename_context_updates_current(self):
        """Test renaming current context updates current pointer."""
        ctx = Context(
            name="old",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="old", contexts={"old": ctx})
        config.rename_context("old", "new")
        assert config.current == "new"

    def test_rename_context_not_found(self):
        """Test renaming non-existent context."""
        config = ContextConfig()
        with pytest.raises(ContextError, match="Context 'missing' not found"):
            config.rename_context("missing", "new")

    def test_rename_context_target_exists(self):
        """Test renaming to existing context name."""
        ctx1 = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        ctx2 = Context(
            name="dev",
            subscription_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
        )
        config = ContextConfig(contexts={"prod": ctx1, "dev": ctx2})
        with pytest.raises(ContextError, match="Context 'dev' already exists"):
            config.rename_context("prod", "dev")

    def test_to_dict(self):
        """Test converting config to dictionary."""
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="prod", contexts={"prod": ctx})
        data = config.to_dict()
        assert data["current"] == "prod"
        assert "definitions" in data
        assert "prod" in data["definitions"]

    def test_to_dict_empty(self):
        """Test to_dict with empty config."""
        config = ContextConfig()
        data = config.to_dict()
        assert data == {}

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "current": "prod",
            "definitions": {
                "prod": {
                    "subscription_id": "12345678-1234-1234-1234-123456789abc",
                    "tenant_id": "87654321-4321-4321-4321-cba987654321",
                }
            },
        }
        config = ContextConfig.from_dict(data)
        assert config.current == "prod"
        assert "prod" in config.contexts
        assert config.contexts["prod"].subscription_id == "12345678-1234-1234-1234-123456789abc"

    def test_from_dict_empty(self):
        """Test from_dict with empty data."""
        config = ContextConfig.from_dict({})
        assert config.current is None
        assert config.contexts == {}


class TestContextManager:
    """Tests for ContextManager class."""

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading from non-existent file returns empty config."""
        config_path = tmp_path / "nonexistent.toml"
        config = ContextManager.load(str(config_path))
        assert isinstance(config, ContextConfig)
        assert config.current is None
        assert config.contexts == {}

    def test_save_and_load(self, tmp_path):
        """Test saving and loading config."""
        # Set test mode
        os.environ["AZLIN_TEST_MODE"] = "true"

        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="prod", contexts={"prod": ctx})

        # Save
        ContextManager.save(config, str(config_path))

        # Load
        loaded = ContextManager.load(str(config_path))
        assert loaded.current == "prod"
        assert "prod" in loaded.contexts
        assert loaded.contexts["prod"].subscription_id == "12345678-1234-1234-1234-123456789abc"

        # Clean up
        del os.environ["AZLIN_TEST_MODE"]

    def test_save_creates_directory(self, tmp_path):
        """Test save creates parent directory if needed."""
        os.environ["AZLIN_TEST_MODE"] = "true"

        config_path = tmp_path / "subdir" / "config.toml"
        ctx = Context(
            name="dev",
            subscription_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
        )
        config = ContextConfig(contexts={"dev": ctx})

        ContextManager.save(config, str(config_path))
        assert config_path.exists()

        del os.environ["AZLIN_TEST_MODE"]

    def test_save_sets_permissions(self, tmp_path):
        """Test save sets secure file permissions."""
        os.environ["AZLIN_TEST_MODE"] = "true"

        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"prod": ctx})

        ContextManager.save(config, str(config_path))

        # Check permissions (owner read/write only)
        stat = config_path.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600

        del os.environ["AZLIN_TEST_MODE"]

    def test_save_preserves_existing_config(self, tmp_path):
        """Test save preserves other config sections."""
        os.environ["AZLIN_TEST_MODE"] = "true"

        config_path = tmp_path / "config.toml"

        # Create config with other sections
        with open(config_path, "w") as f:
            f.write(
                """
default_resource_group = "my-rg"
default_region = "westus2"

[auth.profiles.default]
tenant_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
client_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
"""
            )

        # Add contexts
        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"prod": ctx})
        ContextManager.save(config, str(config_path))

        # Verify other sections preserved
        with open(config_path) as f:
            content = f.read()
            assert "default_resource_group" in content
            assert "auth.profiles" in content
            assert "contexts" in content

        del os.environ["AZLIN_TEST_MODE"]

    def test_migrate_from_legacy(self, tmp_path):
        """Test migration from legacy config format."""
        config_path = tmp_path / "config.toml"

        # Create legacy config
        with open(config_path, "w") as f:
            f.write(
                """
subscription_id = "12345678-1234-1234-1234-123456789abc"
tenant_id = "87654321-4321-4321-4321-cba987654321"
default_resource_group = "my-rg"
"""
            )

        # Migrate
        result = ContextManager.migrate_from_legacy(str(config_path))
        assert result is True

        # Verify migration
        config = ContextManager.load(str(config_path))
        assert config.current == "default"
        assert "default" in config.contexts
        assert config.contexts["default"].subscription_id == "12345678-1234-1234-1234-123456789abc"
        assert config.contexts["default"].description == "Migrated from legacy config"

    def test_migrate_no_legacy_config(self, tmp_path):
        """Test migration when no legacy config exists."""
        config_path = tmp_path / "config.toml"

        # Create config without legacy fields
        with open(config_path, "w") as f:
            f.write('default_resource_group = "my-rg"\n')

        result = ContextManager.migrate_from_legacy(str(config_path))
        assert result is False

    def test_migrate_already_has_contexts(self, tmp_path):
        """Test migration when contexts already exist."""
        config_path = tmp_path / "config.toml"

        # Create config with contexts
        with open(config_path, "w") as f:
            f.write(
                """
subscription_id = "12345678-1234-1234-1234-123456789abc"
tenant_id = "87654321-4321-4321-4321-cba987654321"

[contexts]
current = "prod"

[contexts.definitions.prod]
subscription_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
tenant_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
"""
            )

        result = ContextManager.migrate_from_legacy(str(config_path))
        assert result is False

    def test_validate_config_path_security(self, tmp_path):
        """Test config path validation prevents path traversal."""
        # Try to access file outside allowed directories
        with pytest.raises(ContextError, match="outside allowed directories"):
            ContextManager._validate_config_path(Path("/etc/passwd"))

    def test_save_prevents_production_access_in_tests(self):
        """Test save prevents modifying production config during tests."""
        os.environ["AZLIN_TEST_MODE"] = "true"

        ctx = Context(
            name="prod",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(contexts={"prod": ctx})

        # Should fail without custom_path
        with pytest.raises(ContextError, match="Cannot save to production config during tests"):
            ContextManager.save(config, custom_path=None)

        del os.environ["AZLIN_TEST_MODE"]


class TestEnsureSubscriptionActive:
    """Tests for ensure_subscription_active method."""

    def test_successful_subscription_switch(self, tmp_path):
        """Test successful subscription switching when context is set."""
        # Create config with context
        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="production", contexts={"production": ctx})

        # Save config
        os.environ["AZLIN_TEST_MODE"] = "true"
        ContextManager.save(config, str(config_path))

        # Mock subprocess.run to simulate successful Azure CLI command
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Call ensure_subscription_active
            result = ContextManager.ensure_subscription_active(str(config_path))

            # Verify subscription ID returned
            assert result == "12345678-1234-1234-1234-123456789abc"

            # Verify Azure CLI was called with correct arguments
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == [
                "az",
                "account",
                "set",
                "--subscription",
                "12345678-1234-1234-1234-123456789abc",
            ]
            assert call_args[1]["check"] is True
            assert call_args[1]["capture_output"] is True
            assert call_args[1]["timeout"] == 30

        del os.environ["AZLIN_TEST_MODE"]

    def test_no_context_set(self, tmp_path):
        """Test error when no current context is set."""
        # Create config without current context
        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current=None, contexts={"production": ctx})

        os.environ["AZLIN_TEST_MODE"] = "true"
        ContextManager.save(config, str(config_path))

        # Should raise ContextError
        with pytest.raises(ContextError, match="No current context set"):
            ContextManager.ensure_subscription_active(str(config_path))

        del os.environ["AZLIN_TEST_MODE"]

    def test_subprocess_failure(self, tmp_path):
        """Test error handling when subprocess fails."""
        # Create config with context
        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="production", contexts={"production": ctx})

        os.environ["AZLIN_TEST_MODE"] = "true"
        ContextManager.save(config, str(config_path))

        # Mock subprocess.run to simulate failure
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = real_subprocess.CalledProcessError(
                returncode=1, cmd=["az", "account", "set"], stderr="Subscription not found"
            )

            # Should raise ContextError with details
            with pytest.raises(ContextError, match="Failed to switch Azure subscription"):
                ContextManager.ensure_subscription_active(str(config_path))

        del os.environ["AZLIN_TEST_MODE"]

    def test_custom_config_path(self, tmp_path):
        """Test using custom config path."""
        # Create config in custom location
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        config_path = custom_dir / "my_config.toml"

        ctx = Context(
            name="staging",
            subscription_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
        )
        config = ContextConfig(current="staging", contexts={"staging": ctx})

        os.environ["AZLIN_TEST_MODE"] = "true"
        ContextManager.save(config, str(config_path))

        # Mock subprocess.run
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            # Call with custom path
            result = ContextManager.ensure_subscription_active(str(config_path))

            # Verify correct subscription
            assert result == "11111111-1111-1111-1111-111111111111"

            # Verify Azure CLI called with correct subscription
            call_args = mock_run.call_args
            assert "11111111-1111-1111-1111-111111111111" in call_args[0][0]

        del os.environ["AZLIN_TEST_MODE"]

    def test_thread_safety(self, tmp_path):
        """Test that concurrent calls are thread-safe."""
        # Create config
        config_path = tmp_path / "config.toml"
        ctx = Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789abc",
            tenant_id="87654321-4321-4321-4321-cba987654321",
        )
        config = ContextConfig(current="production", contexts={"production": ctx})

        os.environ["AZLIN_TEST_MODE"] = "true"
        ContextManager.save(config, str(config_path))

        results = []
        errors = []

        # Mock subprocess.run at module level so all threads share the same mock
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            def call_ensure():
                try:
                    result = ContextManager.ensure_subscription_active(str(config_path))
                    results.append(result)
                except Exception as e:
                    errors.append(e)

            # Create multiple threads
            threads = [threading.Thread(target=call_ensure) for _ in range(10)]

            # Start all threads
            for t in threads:
                t.start()

            # Wait for all threads
            for t in threads:
                t.join()

        # Verify no errors and all calls succeeded
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r == "12345678-1234-1234-1234-123456789abc" for r in results)

        del os.environ["AZLIN_TEST_MODE"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
