"""Tests for default help behavior and new command aliases.

Issue #16: Change default behavior to show help instead of provisioning.
"""

import pytest
from click.testing import CliRunner
from azlin.cli import main


class TestDefaultHelpBehavior:
    """Test that azlin with no args shows help (TDD: RED phase)."""

    def test_azlin_no_args_shows_help(self):
        """Test that 'azlin' with no arguments shows help text.
        
        RED PHASE: This will fail - currently provisions VM.
        """
        runner = CliRunner()
        result = runner.invoke(main, [])
        
        # Should show help text
        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        assert "azlin" in result.output.lower()
        
        # Should NOT start provisioning
        assert "Provisioning" not in result.output
        assert "Creating VM" not in result.output

    def test_azlin_help_flag_shows_help(self):
        """Test that 'azlin --help' shows help text."""
        runner = CliRunner()
        result = runner.invoke(main, ['--help'])
        
        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        assert "azlin" in result.output.lower()


class TestNewCommand:
    """Test azlin new command for VM provisioning (TDD: RED phase)."""

    @pytest.mark.parametrize("command", ["new", "vm", "create"])
    def test_new_command_exists(self, command):
        """Test that new/vm/create commands exist.
        
        RED PHASE: These commands don't exist yet.
        """
        runner = CliRunner()
        result = runner.invoke(main, [command, '--help'])
        
        # Should show help for the command
        assert result.exit_code == 0
        assert "Usage:" in result.output or "usage:" in result.output.lower()
        # Should not show "No such command" error
        assert "No such command" not in result.output
        assert "Error" not in result.output

    @pytest.mark.parametrize("command", ["new", "vm", "create"])
    def test_new_command_help_describes_provisioning(self, command):
        """Test that new command help describes VM provisioning.
        
        RED PHASE: Command doesn't exist yet.
        """
        runner = CliRunner()
        result = runner.invoke(main, [command, '--help'])
        
        assert result.exit_code == 0
        # Should describe provisioning
        assert any(word in result.output.lower() for word in 
                   ["provision", "create", "vm", "virtual machine"])

    def test_new_command_accepts_repo_option(self):
        """Test that 'azlin new --repo <url>' works.
        
        RED PHASE: Command doesn't exist yet.
        """
        runner = CliRunner()
        result = runner.invoke(main, ['new', '--repo', 'https://github.com/test/repo', '--help'])
        
        # Should accept --repo option
        assert result.exit_code == 0 or "--repo" in result.output

    def test_new_command_accepts_vm_size_option(self):
        """Test that 'azlin new --vm-size' works.
        
        RED PHASE: Command doesn't exist yet.
        """
        runner = CliRunner()
        result = runner.invoke(main, ['new', '--vm-size', 'Standard_B2s', '--help'])
        
        # Should accept --vm-size option
        assert result.exit_code == 0 or "--vm-size" in result.output

    def test_new_command_accepts_pool_option(self):
        """Test that 'azlin new --pool 5' works.
        
        RED PHASE: Command doesn't exist yet.
        """
        runner = CliRunner()
        result = runner.invoke(main, ['new', '--pool', '5', '--help'])
        
        # Should accept --pool option
        assert result.exit_code == 0 or "--pool" in result.output


class TestBackwardCompatibility:
    """Test that existing commands still work."""

    def test_list_command_still_works(self):
        """Test that 'azlin list' still works."""
        runner = CliRunner()
        result = runner.invoke(main, ['list', '--help'])
        
        assert result.exit_code == 0
        assert "list" in result.output.lower()

    def test_status_command_still_works(self):
        """Test that 'azlin status' still works."""
        runner = CliRunner()
        result = runner.invoke(main, ['status', '--help'])
        
        assert result.exit_code == 0
        assert "status" in result.output.lower()

    def test_connect_command_still_works(self):
        """Test that 'azlin connect' still works."""
        runner = CliRunner()
        result = runner.invoke(main, ['connect', '--help'])
        
        assert result.exit_code == 0
        assert "connect" in result.output.lower()
