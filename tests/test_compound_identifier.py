"""Tests for compound VM:session identifier parsing and resolution.

Test-Driven Development (TDD) approach following testing pyramid:
- 60% Unit tests (fast, focused on parse/format functions)
- 30% Integration tests (resolve_to_vm with various scenarios)
- 10% E2E tests (CLI integration and backward compatibility)

Target test ratio: 3:1 (300 lines for ~100 lines implementation)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from azlin.compound_identifier import (
    parse_identifier,
    resolve_to_vm,
    format_display,
    CompoundIdentifierError,
    AmbiguousIdentifierError,
)
from azlin.vm_manager import VMInfo


# =============================================================================
# UNIT TESTS (60% of coverage) - Fast, focused tests
# =============================================================================


class TestParseIdentifier:
    """Unit tests for parse_identifier function.

    Tests all format variations:
    - Simple name (vm-name or session-name)
    - Compound format (vm-name:session-name)
    - Session-only format (:session-name)
    - Edge cases (empty, multiple colons, invalid chars)
    """

    def test_parse_simple_vm_name(self):
        """Parse simple VM name without colon."""
        vm_name, session_name = parse_identifier("myvm")

        assert vm_name == "myvm"
        assert session_name is None

    def test_parse_simple_session_name(self):
        """Parse simple session name (backward compat check)."""
        # When no colon, should treat as simple identifier
        # Resolution logic will determine if it's VM or session
        vm_name, session_name = parse_identifier("dev-session")

        assert vm_name == "dev-session"
        assert session_name is None

    def test_parse_compound_identifier(self):
        """Parse compound format: vm-name:session-name."""
        vm_name, session_name = parse_identifier("azlin-vm:dev")

        assert vm_name == "azlin-vm"
        assert session_name == "dev"

    def test_parse_session_only_identifier(self):
        """Parse session-only format: :session-name."""
        vm_name, session_name = parse_identifier(":dev")

        assert vm_name is None
        assert session_name == "dev"

    def test_parse_empty_string(self):
        """Parse empty string should raise error."""
        with pytest.raises(CompoundIdentifierError, match="empty"):
            parse_identifier("")

    def test_parse_whitespace_only(self):
        """Parse whitespace-only string should raise error."""
        with pytest.raises(CompoundIdentifierError, match="empty"):
            parse_identifier("   ")

    def test_parse_multiple_colons(self):
        """Parse identifier with multiple colons should raise error."""
        with pytest.raises(CompoundIdentifierError, match="multiple colons"):
            parse_identifier("vm:session:extra")

    def test_parse_colon_only(self):
        """Parse identifier with only colon should raise error."""
        with pytest.raises(CompoundIdentifierError, match="empty"):
            parse_identifier(":")

    def test_parse_empty_vm_name(self):
        """Parse identifier with empty VM part should be session-only."""
        vm_name, session_name = parse_identifier(":session")

        assert vm_name is None
        assert session_name == "session"

    def test_parse_empty_session_name(self):
        """Parse identifier with empty session part (vm:) is valid for disambiguation."""
        vm_name, session_name = parse_identifier("vm:")

        assert vm_name == "vm"
        assert session_name is None

    def test_parse_with_leading_whitespace(self):
        """Parse identifier with leading whitespace (trimmed)."""
        vm_name, session_name = parse_identifier("  myvm:dev")

        assert vm_name == "myvm"
        assert session_name == "dev"

    def test_parse_with_trailing_whitespace(self):
        """Parse identifier with trailing whitespace (trimmed)."""
        vm_name, session_name = parse_identifier("myvm:dev  ")

        assert vm_name == "myvm"
        assert session_name == "dev"

    def test_parse_special_characters_allowed(self):
        """Parse identifier with valid special characters (hyphens, underscores)."""
        vm_name, session_name = parse_identifier("my-vm_01:dev_session-2")

        assert vm_name == "my-vm_01"
        assert session_name == "dev_session-2"

    def test_parse_numbers_allowed(self):
        """Parse identifier with numbers."""
        vm_name, session_name = parse_identifier("vm123:session456")

        assert vm_name == "vm123"
        assert session_name == "session456"


class TestFormatDisplay:
    """Unit tests for format_display function.

    Tests display formatting for:
    - Simple VM name (no session)
    - VM with session name (compound format)
    - Edge cases (empty fields, None values)
    """

    def test_format_display_simple_vm(self):
        """Format display for VM without session name."""
        vm = VMInfo(
            name="azlin-vm",
            resource_group="rg",
            location="eastus",
            power_state="VM running",
            session_name=None,
        )

        display = format_display(vm)
        assert display == "azlin-vm"

    def test_format_display_with_session(self):
        """Format display for VM with session name (compound format)."""
        vm = VMInfo(
            name="azlin-vm",
            resource_group="rg",
            location="eastus",
            power_state="VM running",
            session_name="dev",
        )

        display = format_display(vm)
        assert display == "azlin-vm:dev"

    def test_format_display_empty_session(self):
        """Format display when session name is empty string."""
        vm = VMInfo(
            name="azlin-vm",
            resource_group="rg",
            location="eastus",
            power_state="VM running",
            session_name="",
        )

        display = format_display(vm)
        assert display == "azlin-vm"

    def test_format_display_preserves_vm_name(self):
        """Format display preserves exact VM name."""
        vm = VMInfo(
            name="my-special-vm-name",
            resource_group="rg",
            location="eastus",
            power_state="VM running",
            session_name="test",
        )

        display = format_display(vm)
        assert display == "my-special-vm-name:test"


# =============================================================================
# INTEGRATION TESTS (30% of coverage) - Component interaction
# =============================================================================


class TestResolveToVM:
    """Integration tests for resolve_to_vm function.

    Tests resolution logic with various VM lists and identifiers:
    - Simple name resolution (VM or session)
    - Compound identifier resolution
    - Ambiguity detection and error handling
    - Config file integration
    - Multiple match scenarios
    """

    @pytest.fixture
    def sample_vms(self):
        """Sample VM list for testing."""
        return [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="rg1",
                location="westus",
                power_state="VM running",
                session_name="prod",
            ),
            VMInfo(
                name="azlin-vm-3",
                resource_group="rg2",
                location="eastus",
                power_state="VM stopped",
                session_name=None,
            ),
        ]

    def test_resolve_simple_vm_name_exact_match(self, sample_vms):
        """Resolve simple VM name with exact match."""
        vm = resolve_to_vm("azlin-vm-1", sample_vms, config_path=None)

        assert vm.name == "azlin-vm-1"
        assert vm.session_name == "dev"

    def test_resolve_simple_session_name_exact_match(self, sample_vms):
        """Resolve simple session name with exact match."""
        vm = resolve_to_vm("dev", sample_vms, config_path=None)

        assert vm.name == "azlin-vm-1"
        assert vm.session_name == "dev"

    def test_resolve_compound_identifier_exact_match(self, sample_vms):
        """Resolve compound identifier with exact match."""
        vm = resolve_to_vm("azlin-vm-1:dev", sample_vms, config_path=None)

        assert vm.name == "azlin-vm-1"
        assert vm.session_name == "dev"

    def test_resolve_session_only_identifier(self, sample_vms):
        """Resolve session-only identifier (:session-name)."""
        vm = resolve_to_vm(":prod", sample_vms, config_path=None)

        assert vm.name == "azlin-vm-2"
        assert vm.session_name == "prod"

    def test_resolve_no_match_raises_error(self, sample_vms):
        """Resolve with no matching VM should raise error."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("nonexistent", sample_vms, config_path=None)

    def test_resolve_ambiguous_simple_name_raises_error(self):
        """Resolve ambiguous simple name (matches multiple VMs) raises error."""
        # Two VMs with "dev" - one as VM name, one as session name
        vms = [
            VMInfo(
                name="dev",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
            VMInfo(
                name="azlin-vm",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
        ]

        with pytest.raises(AmbiguousIdentifierError, match="Multiple VMs"):
            resolve_to_vm("dev", vms, config_path=None)

    def test_resolve_compound_mismatch_raises_error(self, sample_vms):
        """Resolve compound identifier where VM exists but session doesn't match."""
        with pytest.raises(CompoundIdentifierError, match="session name mismatch"):
            resolve_to_vm("azlin-vm-1:wrong-session", sample_vms, config_path=None)

    def test_resolve_compound_no_session_name_raises_error(self, sample_vms):
        """Resolve compound identifier where VM has no session name."""
        with pytest.raises(CompoundIdentifierError, match="no session name"):
            resolve_to_vm("azlin-vm-3:dev", sample_vms, config_path=None)

    def test_resolve_empty_vm_list(self):
        """Resolve with empty VM list should raise error."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("any-vm", [], config_path=None)

    def test_resolve_partial_vm_name_match(self, sample_vms):
        """Resolve should NOT match partial VM names (exact match only)."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("vm-1", sample_vms, config_path=None)

    def test_resolve_partial_session_name_match(self, sample_vms):
        """Resolve should NOT match partial session names (exact match only)."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("de", sample_vms, config_path=None)

    def test_resolve_case_sensitive_vm_name(self, sample_vms):
        """Resolve should be case-sensitive for VM names."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("AZLIN-VM-1", sample_vms, config_path=None)

    def test_resolve_case_sensitive_session_name(self, sample_vms):
        """Resolve should be case-sensitive for session names."""
        with pytest.raises(CompoundIdentifierError, match="not found"):
            resolve_to_vm("DEV", sample_vms, config_path=None)

    def test_resolve_with_config_file_session_mapping(self, sample_vms, tmp_path):
        """Resolve using config file for session name mapping."""
        # Create mock config file
        config_file = tmp_path / "config.toml"
        config_content = """
[sessions.dev]
vm = "azlin-vm-1"
resource_group = "rg1"
"""
        config_file.write_text(config_content)

        # Resolve should find VM via config mapping
        vm = resolve_to_vm("dev", sample_vms, config_path=str(config_file))

        assert vm.name == "azlin-vm-1"
        assert vm.session_name == "dev"

    def test_resolve_config_file_not_found_fallback(self, sample_vms):
        """Resolve with non-existent config file should fallback to VM list search."""
        vm = resolve_to_vm("azlin-vm-1", sample_vms, config_path="/nonexistent/config.toml")

        assert vm.name == "azlin-vm-1"

    def test_resolve_multiple_vms_same_session_raises_error(self):
        """Resolve when multiple VMs have same session name raises ambiguity error."""
        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="rg1",
                location="westus",
                power_state="VM running",
                session_name="dev",  # Duplicate session name
            ),
        ]

        with pytest.raises(AmbiguousIdentifierError, match="Multiple VMs"):
            resolve_to_vm("dev", vms, config_path=None)

    def test_resolve_prioritizes_vm_name_over_session(self, sample_vms):
        """When ambiguous, compound format is required - simple name alone should error."""
        # Add VM where name matches another VM's session
        vms = sample_vms + [
            VMInfo(
                name="dev",  # Same as azlin-vm-1's session name
                resource_group="rg3",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
        ]

        # Ambiguous - should raise error
        with pytest.raises(AmbiguousIdentifierError):
            resolve_to_vm("dev", vms, config_path=None)

        # But compound format should work
        vm = resolve_to_vm("dev:", vms, config_path=None)
        assert vm.name == "dev"


class TestConfigFileIntegration:
    """Integration tests for config file session mapping."""

    def test_load_session_from_config(self, tmp_path):
        """Load session name mapping from config file."""
        config_file = tmp_path / "config.toml"
        config_content = """
[sessions.production]
vm = "azlin-prod-vm"
resource_group = "prod-rg"

[sessions.staging]
vm = "azlin-stage-vm"
resource_group = "stage-rg"
"""
        config_file.write_text(config_content)

        vms = [
            VMInfo(
                name="azlin-prod-vm",
                resource_group="prod-rg",
                location="eastus",
                power_state="VM running",
                session_name="production",
            ),
        ]

        vm = resolve_to_vm("production", vms, config_path=str(config_file))
        assert vm.name == "azlin-prod-vm"

    def test_config_file_malformed_falls_back(self, tmp_path):
        """Malformed config file should fallback to VM list search."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid toml {{")

        vms = [
            VMInfo(
                name="azlin-vm",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
        ]

        vm = resolve_to_vm("azlin-vm", vms, config_path=str(config_file))
        assert vm.name == "azlin-vm"


# =============================================================================
# E2E TESTS (10% of coverage) - Full workflow tests
# =============================================================================


class TestCLIIntegration:
    """E2E tests for CLI command integration.

    Tests that compound identifiers work with azlin commands:
    - ssh command
    - list command
    - exec command
    - Backward compatibility with simple names
    """

    @pytest.fixture
    def mock_vm_manager(self):
        """Mock VM manager for CLI tests."""
        with patch("azlin.cli.get_vm_list") as mock_get_vms:
            vms = [
                VMInfo(
                    name="azlin-vm-1",
                    resource_group="rg1",
                    location="eastus",
                    power_state="VM running",
                    public_ip="1.2.3.4",
                    session_name="dev",
                ),
                VMInfo(
                    name="azlin-vm-2",
                    resource_group="rg1",
                    location="westus",
                    power_state="VM running",
                    public_ip="5.6.7.8",
                    session_name="prod",
                ),
            ]
            mock_get_vms.return_value = vms
            yield mock_get_vms

    def test_ssh_command_with_compound_identifier(self, mock_vm_manager):
        """SSH command accepts compound identifier."""
        # This test will fail until CLI integration is complete
        from azlin.cli import ssh_command

        with patch("subprocess.run") as mock_run:
            ssh_command("azlin-vm-1:dev")

            # Should resolve to correct VM and SSH
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "1.2.3.4" in call_args  # Should use correct IP

    def test_ssh_command_with_session_only_identifier(self, mock_vm_manager):
        """SSH command accepts session-only identifier."""
        from azlin.cli import ssh_command

        with patch("subprocess.run") as mock_run:
            ssh_command(":prod")

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "5.6.7.8" in call_args

    def test_list_command_displays_compound_format(self, mock_vm_manager):
        """List command displays VMs in compound format when they have sessions."""
        from azlin.cli import list_command

        with patch("azlin.cli.print") as mock_print:
            list_command()

            # Should display compound format for VMs with sessions
            output = str(mock_print.call_args_list)
            assert "azlin-vm-1:dev" in output or "dev" in output

    def test_exec_command_with_compound_identifier(self, mock_vm_manager):
        """Exec command accepts compound identifier."""
        from azlin.cli import exec_command

        with patch("azlin.remote_exec.execute_remote_command") as mock_exec:
            exec_command("azlin-vm-1:dev", "ls -la")

            mock_exec.assert_called_once()
            # Verify correct VM was targeted
            call_vm = mock_exec.call_args[0][0]
            assert call_vm.name == "azlin-vm-1"

    def test_backward_compatibility_simple_vm_name(self, mock_vm_manager):
        """Simple VM names still work (backward compatibility)."""
        from azlin.cli import ssh_command

        with patch("subprocess.run") as mock_run:
            ssh_command("azlin-vm-1")

            mock_run.assert_called_once()

    def test_backward_compatibility_simple_session_name(self, mock_vm_manager):
        """Simple session names still work (backward compatibility)."""
        from azlin.cli import ssh_command

        with patch("subprocess.run") as mock_run:
            ssh_command("dev")

            mock_run.assert_called_once()

    def test_error_handling_ambiguous_identifier_in_cli(self):
        """CLI handles ambiguous identifier errors gracefully."""
        vms = [
            VMInfo(
                name="dev",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
            VMInfo(
                name="azlin-vm",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
        ]

        with patch("azlin.cli.get_vm_list", return_value=vms):
            from azlin.cli import ssh_command

            with pytest.raises(AmbiguousIdentifierError) as exc_info:
                ssh_command("dev")

            # Error message should suggest using compound format
            assert "azlin-vm:dev" in str(exc_info.value)


class TestBackwardCompatibility:
    """E2E tests ensuring backward compatibility with existing behavior."""

    def test_existing_simple_names_work(self):
        """Existing code using simple VM names continues to work."""
        vms = [
            VMInfo(
                name="my-vm",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
        ]

        vm = resolve_to_vm("my-vm", vms, config_path=None)
        assert vm.name == "my-vm"

    def test_existing_session_names_work(self):
        """Existing code using session names continues to work."""
        vms = [
            VMInfo(
                name="azlin-vm",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name="my-session",
            ),
        ]

        vm = resolve_to_vm("my-session", vms, config_path=None)
        assert vm.session_name == "my-session"

    def test_config_file_based_resolution_unchanged(self, tmp_path):
        """Config file-based session resolution continues to work."""
        config_file = tmp_path / "config.toml"
        config_content = """
[sessions.legacy]
vm = "legacy-vm"
resource_group = "legacy-rg"
"""
        config_file.write_text(config_content)

        vms = [
            VMInfo(
                name="legacy-vm",
                resource_group="legacy-rg",
                location="eastus",
                power_state="VM running",
                session_name="legacy",
            ),
        ]

        vm = resolve_to_vm("legacy", vms, config_path=str(config_file))
        assert vm.name == "legacy-vm"


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorMessages:
    """Tests for clear, actionable error messages."""

    def test_ambiguous_error_suggests_compound_format(self):
        """Ambiguous identifier error suggests using compound format."""
        vms = [
            VMInfo(
                name="dev",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name=None,
            ),
            VMInfo(
                name="prod-vm",
                resource_group="rg1",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
        ]

        with pytest.raises(AmbiguousIdentifierError) as exc_info:
            resolve_to_vm("dev", vms, config_path=None)

        error_msg = str(exc_info.value)
        assert "dev:" in error_msg or "prod-vm:dev" in error_msg
        assert "compound format" in error_msg.lower()

    def test_not_found_error_lists_available_identifiers(self):
        """Not found error lists available VMs and sessions."""
        vms = [
            VMInfo(
                name="azlin-vm-1",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name="dev",
            ),
            VMInfo(
                name="azlin-vm-2",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name="prod",
            ),
        ]

        with pytest.raises(CompoundIdentifierError) as exc_info:
            resolve_to_vm("nonexistent", vms, config_path=None)

        error_msg = str(exc_info.value)
        assert "azlin-vm-1" in error_msg or "dev" in error_msg
        assert "Available" in error_msg or "available" in error_msg

    def test_session_mismatch_error_shows_actual_session(self):
        """Session mismatch error shows actual session name."""
        vms = [
            VMInfo(
                name="azlin-vm",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name="actual-session",
            ),
        ]

        with pytest.raises(CompoundIdentifierError) as exc_info:
            resolve_to_vm("azlin-vm:wrong-session", vms, config_path=None)

        error_msg = str(exc_info.value)
        assert "actual-session" in error_msg
        assert "wrong-session" in error_msg


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================


class TestPerformance:
    """Performance tests for identifier resolution."""

    def test_resolve_with_large_vm_list(self):
        """Resolution should be fast even with large VM lists."""
        import time

        # Create 1000 VMs
        vms = [
            VMInfo(
                name=f"azlin-vm-{i}",
                resource_group="rg",
                location="eastus",
                power_state="VM running",
                session_name=f"session-{i}",
            )
            for i in range(1000)
        ]

        start = time.time()
        vm = resolve_to_vm("azlin-vm-500:session-500", vms, config_path=None)
        elapsed = time.time() - start

        assert vm.name == "azlin-vm-500"
        assert elapsed < 0.1  # Should resolve in < 100ms

    def test_parse_identifier_is_fast(self):
        """Parsing should be very fast (< 1ms)."""
        import time

        start = time.time()
        for _ in range(10000):
            parse_identifier("vm-name:session-name")
        elapsed = time.time() - start

        assert elapsed < 0.1  # 10k parses in < 100ms
