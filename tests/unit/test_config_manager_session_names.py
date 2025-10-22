"""Unit tests for session name resolution bug fix (issue #160).

This module tests the session name mapping functionality in ConfigManager,
specifically addressing the following bug scenarios:
- Self-referential session mappings (vm_name == session_name)
- Duplicate session names pointing to different VMs
- VM names used as session names
- Invalid session name resolution

Bug Context:
- Self-referential mappings like "simserv = simserv" cause lookup failures
- Duplicate session names create ambiguity
- get_vm_name_by_session() can return wrong VM name

Test Strategy:
Following TDD, these tests are written BEFORE the fix is implemented.
They should FAIL until proper validation and filtering is added.
"""

from pathlib import Path

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestSessionNameValidation:
    """Tests for session name validation during set_session_name().

    These tests verify that invalid session name mappings are rejected
    when being set, preventing corruption of the config file.
    """

    def test_reject_self_referential_mapping(self, tmp_path):
        """Test that self-referential mappings (vm_name == session_name) are rejected.

        Bug: Setting simserv="simserv" should be rejected as it creates
        confusion and breaks lookups.

        Expected: ValueError or ConfigError raised
        Current: FAILS - accepts invalid mapping
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        # This should raise an error
        with pytest.raises((ValueError, ConfigError), match="self-referential|same as VM name"):
            ConfigManager.set_session_name("simserv", "simserv", str(config_file))

    def test_reject_duplicate_session_name_different_vm(self, tmp_path):
        """Test that duplicate session names for different VMs are rejected.

        Bug: Two VMs cannot share the same session name as it creates
        ambiguity in reverse lookup.

        Expected: ValueError or ConfigError raised
        Current: FAILS - accepts duplicate session names
        """
        config_file = tmp_path / "config.toml"

        # Create config with existing session name
        config = AzlinConfig(session_names={"vm1": "dev"})
        ConfigManager.save_config(config, str(config_file))

        # Trying to set the same session name for different VM should fail
        with pytest.raises((ValueError, ConfigError), match="already in use|duplicate"):
            ConfigManager.set_session_name("vm2", "dev", str(config_file))

    def test_allow_duplicate_session_name_same_vm(self, tmp_path):
        """Test that updating the same VM's session name is allowed.

        Setting vm1="dev" twice should be allowed (idempotent operation).
        """
        config_file = tmp_path / "config.toml"

        # Set session name first time
        ConfigManager.set_session_name("vm1", "dev", str(config_file))

        # Setting same mapping again should succeed (idempotent)
        ConfigManager.set_session_name("vm1", "dev", str(config_file))

        config = ConfigManager.load_config(str(config_file))
        assert config.session_names == {"vm1": "dev"}

    def test_allow_changing_session_name_for_vm(self, tmp_path):
        """Test that changing a VM's session name is allowed.

        Updating vm1 from "dev" to "prod" should be allowed.
        """
        config_file = tmp_path / "config.toml"

        # Set initial session name
        ConfigManager.set_session_name("vm1", "dev", str(config_file))

        # Change to different session name (should succeed)
        ConfigManager.set_session_name("vm1", "prod", str(config_file))

        config = ConfigManager.load_config(str(config_file))
        assert config.session_names == {"vm1": "prod"}

    def test_reject_vm_name_as_session_name_for_different_vm(self, tmp_path):
        """Test that using an existing VM name as session name is rejected.

        Bug: If vm1 exists, setting vm2's session name to "vm1" creates
        confusion - is "vm1" a VM name or session name?

        Expected: ValueError or ConfigError raised
        Current: FAILS - accepts VM name as session name
        """
        config_file = tmp_path / "config.toml"

        # Create config with vm1 having a session name
        config = AzlinConfig(session_names={"vm1": "dev"})
        ConfigManager.save_config(config, str(config_file))

        # Trying to use "vm1" (an existing VM name) as session name for vm2 should fail
        with pytest.raises((ValueError, ConfigError), match="VM name|reserved|conflicts"):
            ConfigManager.set_session_name("vm2", "vm1", str(config_file))

    def test_reject_empty_session_name(self, tmp_path):
        """Test that empty session names are rejected.

        Session names must be non-empty strings.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        with pytest.raises((ValueError, ConfigError), match="empty|invalid"):
            ConfigManager.set_session_name("vm1", "", str(config_file))

    def test_reject_whitespace_only_session_name(self, tmp_path):
        """Test that whitespace-only session names are rejected.

        Session names must contain non-whitespace characters.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        with pytest.raises((ValueError, ConfigError), match="empty|invalid|whitespace"):
            ConfigManager.set_session_name("vm1", "   ", str(config_file))

    def test_reject_session_name_with_invalid_characters(self, tmp_path):
        """Test that session names with invalid characters are rejected.

        Session names should follow similar rules to VM names:
        alphanumeric, hyphens, underscores only.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        invalid_names = [
            "dev/prod",  # Slash
            "dev:prod",  # Colon
            "dev prod",  # Space
            "dev@prod",  # At sign
            "dev.prod.",  # Trailing dot
        ]

        for invalid_name in invalid_names:
            with pytest.raises((ValueError, ConfigError), match="invalid|characters"):
                ConfigManager.set_session_name("vm1", invalid_name, str(config_file))

    def test_accept_valid_session_name(self, tmp_path):
        """Test that valid session names are accepted.

        Valid session names should be allowed and stored correctly.
        """
        config_file = tmp_path / "config.toml"

        valid_names = [
            "dev",
            "prod",
            "dev-server",
            "dev_server",
            "server1",
            "my-dev-box-01",
        ]

        for i, valid_name in enumerate(valid_names):
            vm_name = f"vm{i}"
            ConfigManager.set_session_name(vm_name, valid_name, str(config_file))

            config = ConfigManager.load_config(str(config_file))
            assert config.session_names.get(vm_name) == valid_name


class TestSessionNameLookup:
    """Tests for get_vm_name_by_session() lookup with invalid entries.

    These tests verify that lookups handle invalid entries gracefully,
    either by filtering them out or returning appropriate errors.
    """

    def test_lookup_skips_self_referential_entry(self, tmp_path):
        """Test that lookup ignores self-referential entries.

        Bug: If config contains "simserv = simserv", looking up "simserv"
        should return None (not found) rather than "simserv".

        Expected: Returns None
        Current: FAILS - returns "simserv" (wrong)
        """
        config_file = tmp_path / "config.toml"

        # Manually create config with invalid self-referential entry
        # (simulating existing corrupted config)
        config = AzlinConfig(session_names={"simserv": "simserv"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should ignore self-referential entry
        result = ConfigManager.get_vm_name_by_session("simserv", str(config_file))
        assert result is None, "Should not return self-referential mapping"

    def test_lookup_with_multiple_matches_returns_none(self, tmp_path):
        """Test that lookup returns None when multiple VMs have same session name.

        Bug: If multiple VMs have the same session name, the lookup is
        ambiguous and should return None or raise an error.

        Expected: Returns None or raises ConfigError
        Current: FAILS - returns first match (arbitrary)
        """
        config_file = tmp_path / "config.toml"

        # Manually create config with duplicate session names
        # (simulating existing corrupted config)
        config = AzlinConfig(session_names={"vm1": "dev", "vm2": "dev"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should detect ambiguity
        result = ConfigManager.get_vm_name_by_session("dev", str(config_file))

        # Either return None (ambiguous) or raise error
        if result is not None:
            # If it returns a value, it should raise an error indicating ambiguity
            pytest.fail("Should return None or raise ConfigError for ambiguous lookup")

    def test_lookup_valid_session_name_works(self, tmp_path):
        """Test that normal lookup still works with valid entries.

        This ensures the fix doesn't break valid functionality.
        """
        config_file = tmp_path / "config.toml"

        # Create valid config
        config = AzlinConfig(session_names={"vm1": "dev", "vm2": "prod"})
        ConfigManager.save_config(config, str(config_file))

        # Valid lookups should work
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) == "vm1"
        assert ConfigManager.get_vm_name_by_session("prod", str(config_file)) == "vm2"

    def test_lookup_nonexistent_session_returns_none(self, tmp_path):
        """Test that lookup returns None for non-existent session names.

        This is the normal "not found" behavior.
        """
        config_file = tmp_path / "config.toml"

        config = AzlinConfig(session_names={"vm1": "dev"})
        ConfigManager.save_config(config, str(config_file))

        result = ConfigManager.get_vm_name_by_session("nonexistent", str(config_file))
        assert result is None

    def test_lookup_with_mixed_valid_invalid_entries(self, tmp_path):
        """Test that lookup filters invalid entries and finds valid ones.

        If config has both valid and invalid entries, lookup should:
        - Ignore self-referential entries
        - Ignore duplicate session names
        - Return valid unique mappings
        """
        config_file = tmp_path / "config.toml"

        # Create config with mixed valid/invalid entries
        config = AzlinConfig(
            session_names={
                "vm1": "dev",  # Valid
                "vm2": "prod",  # Valid
                "simserv": "simserv",  # Invalid: self-referential
                "vm3": "prod",  # Invalid: duplicate of vm2's session
            }
        )
        ConfigManager.save_config(config, str(config_file))

        # Valid lookups should work
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) == "vm1"

        # Self-referential should return None
        assert ConfigManager.get_vm_name_by_session("simserv", str(config_file)) is None

        # Duplicate should return None or raise error (ambiguous)
        result = ConfigManager.get_vm_name_by_session("prod", str(config_file))
        if result is not None:
            pytest.fail("Should return None for ambiguous duplicate session name")

    def test_lookup_by_vm_name_directly_returns_none(self, tmp_path):
        """Test that looking up a VM name (not session name) returns None.

        If vm1 has session name "dev", looking up "vm1" as a session
        should return None (it's a VM name, not a session name).
        """
        config_file = tmp_path / "config.toml"

        config = AzlinConfig(session_names={"vm1": "dev"})
        ConfigManager.save_config(config, str(config_file))

        # Looking up VM name should return None (not a session name)
        result = ConfigManager.get_vm_name_by_session("vm1", str(config_file))
        assert result is None


class TestSessionNameConfigMigration:
    """Tests for loading and cleaning up invalid config entries.

    These tests verify that when loading configs with invalid entries,
    the system either cleans them up or warns about them.
    """

    def test_load_config_with_self_referential_entry(self, tmp_path):
        """Test loading config with self-referential entry doesn't crash.

        Config should load successfully even with invalid entries.
        """
        config_file = tmp_path / "config.toml"

        # Manually create config with invalid entry
        config = AzlinConfig(session_names={"simserv": "simserv"})
        ConfigManager.save_config(config, str(config_file))

        # Loading should succeed (not crash)
        loaded_config = ConfigManager.load_config(str(config_file))
        assert loaded_config.session_names is not None

    def test_load_config_with_duplicate_session_names(self, tmp_path):
        """Test loading config with duplicate session names doesn't crash.

        Config should load successfully even with duplicate entries.
        """
        config_file = tmp_path / "config.toml"

        # Manually create config with duplicates
        config = AzlinConfig(session_names={"vm1": "dev", "vm2": "dev"})
        ConfigManager.save_config(config, str(config_file))

        # Loading should succeed
        loaded_config = ConfigManager.load_config(str(config_file))
        assert loaded_config.session_names is not None

    def test_validate_session_names_method_detects_issues(self, tmp_path):
        """Test that a validation method can detect invalid entries.

        This tests the existence of a validate_session_names() method
        or similar validation logic that can detect:
        - Self-referential mappings
        - Duplicate session names
        - Other invalid entries

        Expected: Method exists and returns list of issues
        Current: FAILS - method doesn't exist yet
        """
        config = AzlinConfig(
            session_names={
                "vm1": "dev",  # Valid
                "simserv": "simserv",  # Invalid: self-referential
                "vm2": "prod",  # Valid
                "vm3": "prod",  # Invalid: duplicate
            }
        )

        # This method should be added as part of the fix
        # It should detect and report invalid entries
        if hasattr(config, "validate_session_names"):
            issues = config.validate_session_names()
            assert len(issues) >= 2, "Should detect self-referential and duplicate"
        else:
            pytest.skip("validate_session_names() method not implemented yet")

    def test_cleanup_invalid_session_names_method(self, tmp_path):
        """Test that cleanup method removes invalid entries.

        This tests the existence of a cleanup_session_names() method
        that removes invalid entries from the config.

        Expected: Method exists and removes invalid entries
        Current: FAILS - method doesn't exist yet
        """
        config = AzlinConfig(
            session_names={
                "vm1": "dev",  # Valid
                "simserv": "simserv",  # Invalid: self-referential
                "vm2": "prod",  # Valid
            }
        )

        # This method should be added as part of the fix
        if hasattr(config, "cleanup_session_names"):
            config.cleanup_session_names()
            assert "simserv" not in config.session_names
            assert "vm1" in config.session_names
            assert "vm2" in config.session_names
        else:
            pytest.skip("cleanup_session_names() method not implemented yet")


class TestSessionNameEdgeCases:
    """Tests for edge cases in session name handling."""

    def test_none_session_name(self, tmp_path):
        """Test that None session name is rejected."""
        config_file = tmp_path / "config.toml"
        config_file.touch()

        with pytest.raises((ValueError, ConfigError, TypeError)):
            ConfigManager.set_session_name("vm1", None, str(config_file))

    def test_numeric_session_name(self, tmp_path):
        """Test that numeric session names are handled correctly.

        Numeric strings like "123" should be valid session names.
        """
        config_file = tmp_path / "config.toml"

        ConfigManager.set_session_name("vm1", "123", str(config_file))

        config = ConfigManager.load_config(str(config_file))
        assert config.session_names.get("vm1") == "123"

    def test_very_long_session_name(self, tmp_path):
        """Test that very long session names are rejected.

        Session names should have reasonable length limits (e.g., 64 chars).
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        # Azure VM names are limited to 64 characters
        # Session names should have similar or same limits
        very_long_name = "a" * 100

        with pytest.raises((ValueError, ConfigError), match="too long|length"):
            ConfigManager.set_session_name("vm1", very_long_name, str(config_file))

    def test_session_name_with_unicode(self, tmp_path):
        """Test that session names with unicode are rejected.

        Session names should be ASCII-only for compatibility.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        unicode_names = ["café", "测试", "🚀"]

        for unicode_name in unicode_names:
            with pytest.raises((ValueError, ConfigError), match="invalid|ascii|characters"):
                ConfigManager.set_session_name("vm1", unicode_name, str(config_file))

    def test_session_name_case_sensitivity(self, tmp_path):
        """Test that session names are case-sensitive.

        "Dev" and "dev" should be treated as different session names.
        """
        config_file = tmp_path / "config.toml"

        ConfigManager.set_session_name("vm1", "Dev", str(config_file))
        ConfigManager.set_session_name("vm2", "dev", str(config_file))

        config = ConfigManager.load_config(str(config_file))
        assert config.session_names.get("vm1") == "Dev"
        assert config.session_names.get("vm2") == "dev"

        # Lookups should be case-sensitive
        assert ConfigManager.get_vm_name_by_session("Dev", str(config_file)) == "vm1"
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) == "vm2"
        assert ConfigManager.get_vm_name_by_session("DEV", str(config_file)) is None

    def test_session_name_starting_with_hyphen(self, tmp_path):
        """Test that session names starting with hyphen are rejected.

        Similar to VM names, session names should not start with hyphen.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        with pytest.raises((ValueError, ConfigError), match="invalid|start"):
            ConfigManager.set_session_name("vm1", "-dev", str(config_file))

    def test_session_name_ending_with_hyphen(self, tmp_path):
        """Test that session names ending with hyphen are rejected.

        Similar to VM names, session names should not end with hyphen.
        """
        config_file = tmp_path / "config.toml"
        config_file.touch()

        with pytest.raises((ValueError, ConfigError), match="invalid|end"):
            ConfigManager.set_session_name("vm1", "dev-", str(config_file))

    def test_delete_session_name_removes_entry(self, tmp_path):
        """Test that deleting session name works correctly.

        This verifies existing delete_session_name() functionality.
        """
        config_file = tmp_path / "config.toml"

        # Set session name
        ConfigManager.set_session_name("vm1", "dev", str(config_file))

        # Verify it exists
        config = ConfigManager.load_config(str(config_file))
        assert config.session_names.get("vm1") == "dev"

        # Delete it
        deleted = ConfigManager.delete_session_name("vm1", str(config_file))
        assert deleted is True

        # Verify it's gone
        config = ConfigManager.load_config(str(config_file))
        assert "vm1" not in config.session_names

    def test_delete_nonexistent_session_name(self, tmp_path):
        """Test deleting non-existent session name returns False."""
        config_file = tmp_path / "config.toml"
        config_file.touch()

        deleted = ConfigManager.delete_session_name("nonexistent", str(config_file))
        assert deleted is False


class TestSessionNameIntegration:
    """Integration tests for session name functionality.

    These tests verify the end-to-end workflow of setting, getting,
    and looking up session names.
    """

    def test_full_workflow_set_get_lookup(self, tmp_path):
        """Test complete workflow: set -> get -> lookup."""
        config_file = tmp_path / "config.toml"

        # Set session name
        ConfigManager.set_session_name("my-vm", "dev-box", str(config_file))

        # Get session name by VM
        session_name = ConfigManager.get_session_name("my-vm", str(config_file))
        assert session_name == "dev-box"

        # Reverse lookup: get VM by session
        vm_name = ConfigManager.get_vm_name_by_session("dev-box", str(config_file))
        assert vm_name == "my-vm"

    def test_multiple_vms_with_unique_sessions(self, tmp_path):
        """Test multiple VMs each with unique session names."""
        config_file = tmp_path / "config.toml"

        # Set up multiple VMs
        ConfigManager.set_session_name("vm1", "dev", str(config_file))
        ConfigManager.set_session_name("vm2", "prod", str(config_file))
        ConfigManager.set_session_name("vm3", "staging", str(config_file))

        # Verify all lookups work
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) == "vm1"
        assert ConfigManager.get_vm_name_by_session("prod", str(config_file)) == "vm2"
        assert ConfigManager.get_vm_name_by_session("staging", str(config_file)) == "vm3"

        # Verify reverse lookups
        assert ConfigManager.get_session_name("vm1", str(config_file)) == "dev"
        assert ConfigManager.get_session_name("vm2", str(config_file)) == "prod"
        assert ConfigManager.get_session_name("vm3", str(config_file)) == "staging"

    def test_update_session_name_updates_lookup(self, tmp_path):
        """Test that updating session name updates both directions."""
        config_file = tmp_path / "config.toml"

        # Set initial session name
        ConfigManager.set_session_name("vm1", "dev", str(config_file))
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) == "vm1"

        # Update to new session name
        ConfigManager.set_session_name("vm1", "production", str(config_file))

        # Old session name should not resolve
        assert ConfigManager.get_vm_name_by_session("dev", str(config_file)) is None

        # New session name should resolve
        assert ConfigManager.get_vm_name_by_session("production", str(config_file)) == "vm1"

    def test_config_file_format_preserved(self, tmp_path):
        """Test that config file remains valid TOML after operations."""
        config_file = tmp_path / "config.toml"

        # Set multiple session names
        ConfigManager.set_session_name("vm1", "dev", str(config_file))
        ConfigManager.set_session_name("vm2", "prod", str(config_file))

        # Verify file is valid TOML and can be loaded
        config = ConfigManager.load_config(str(config_file))
        assert isinstance(config.session_names, dict)
        assert len(config.session_names) == 2

        # Verify manual TOML parsing works
        import tomli
        with open(config_file, "rb") as f:
            data = tomli.load(f)

        assert "session_names" in data
        assert data["session_names"]["vm1"] == "dev"
        assert data["session_names"]["vm2"] == "prod"
