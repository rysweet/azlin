"""Integration tests for tag CLI commands.

Tests the CLI interface to tag management commands.
Uses Click's CliRunner for isolated command testing.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from azlin.cli import main
from azlin.vm_manager import VMInfo


@pytest.fixture
def runner():
    """Create Click CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock config with default values."""
    config = MagicMock()
    config.default_resource_group = "test-rg"
    config.default_region = "westus2"
    return config


@pytest.fixture
def mock_vm():
    """Mock VM info."""
    return VMInfo(
        name="test-vm",
        resource_group="test-rg",
        location="westus2",
        power_state="VM running",
        public_ip="20.1.2.3",
        tags={"environment": "development", "team": "backend"},
    )


class TestTagAddCommand:
    """Test 'azlin tag add' command."""

    @patch("azlin.commands.tag.TagManager.add_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_single_tag(
        self, mock_load_config, mock_get_vm, mock_add_tags, runner, mock_config, mock_vm
    ):
        """Adding a single tag should succeed."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(main, ["tag", "add", "test-vm", "project=web"])

        assert result.exit_code == 0
        assert "Successfully added 1 tag(s)" in result.output
        assert "test-vm" in result.output
        mock_add_tags.assert_called_once_with("test-vm", "test-rg", {"project": "web"})

    @patch("azlin.commands.tag.TagManager.add_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_multiple_tags(
        self, mock_load_config, mock_get_vm, mock_add_tags, runner, mock_config, mock_vm
    ):
        """Adding multiple tags should succeed."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(main, ["tag", "add", "test-vm", "project=web", "team=backend"])

        assert result.exit_code == 0
        assert "Successfully added 2 tag(s)" in result.output
        mock_add_tags.assert_called_once_with(
            "test-vm", "test-rg", {"project": "web", "team": "backend"}
        )

    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_vm_not_found(self, mock_load_config, mock_get_vm, runner, mock_config):
        """Adding tags to non-existent VM should fail."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = None

        result = runner.invoke(main, ["tag", "add", "nonexistent-vm", "project=web"])

        assert result.exit_code == 1
        assert "VM 'nonexistent-vm' not found" in result.output

    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_invalid_tag_format(
        self, mock_load_config, mock_get_vm, runner, mock_config, mock_vm
    ):
        """Adding tag without '=' should fail."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(main, ["tag", "add", "test-vm", "invalidtag"])

        assert result.exit_code == 1
        assert "Invalid tag format" in result.output

    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_no_config(self, mock_load_config, mock_get_vm, runner):
        """Adding tags without config should fail."""
        from azlin.config_manager import ConfigError

        mock_load_config.side_effect = ConfigError("No config found")

        result = runner.invoke(main, ["tag", "add", "test-vm", "project=web"])

        assert result.exit_code == 1
        assert "No config found" in result.output

    @patch("azlin.commands.tag.TagManager.add_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_with_custom_resource_group(
        self, mock_load_config, mock_get_vm, mock_add_tags, runner, mock_config, mock_vm
    ):
        """Adding tags with custom resource group should work."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(
            main, ["tag", "add", "test-vm", "project=web", "--resource-group", "custom-rg"]
        )

        assert result.exit_code == 0
        mock_get_vm.assert_called_once_with("test-vm", "custom-rg")
        mock_add_tags.assert_called_once_with("test-vm", "custom-rg", {"project": "web"})


class TestTagRemoveCommand:
    """Test 'azlin tag remove' command."""

    @patch("azlin.commands.tag.TagManager.remove_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_remove_single_tag(
        self, mock_load_config, mock_get_vm, mock_remove_tags, runner, mock_config, mock_vm
    ):
        """Removing a single tag should succeed."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(main, ["tag", "remove", "test-vm", "environment"])

        assert result.exit_code == 0
        assert "Successfully removed 1 tag(s)" in result.output
        assert "test-vm" in result.output
        mock_remove_tags.assert_called_once_with("test-vm", "test-rg", ["environment"])

    @patch("azlin.commands.tag.TagManager.remove_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_remove_multiple_tags(
        self, mock_load_config, mock_get_vm, mock_remove_tags, runner, mock_config, mock_vm
    ):
        """Removing multiple tags should succeed."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(main, ["tag", "remove", "test-vm", "environment", "team"])

        assert result.exit_code == 0
        assert "Successfully removed 2 tag(s)" in result.output
        mock_remove_tags.assert_called_once_with("test-vm", "test-rg", ["environment", "team"])

    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_remove_vm_not_found(self, mock_load_config, mock_get_vm, runner, mock_config):
        """Removing tags from non-existent VM should fail."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = None

        result = runner.invoke(main, ["tag", "remove", "nonexistent-vm", "environment"])

        assert result.exit_code == 1
        assert "VM 'nonexistent-vm' not found" in result.output

    @patch("azlin.commands.tag.TagManager.remove_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_remove_with_custom_resource_group(
        self, mock_load_config, mock_get_vm, mock_remove_tags, runner, mock_config, mock_vm
    ):
        """Removing tags with custom resource group should work."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        result = runner.invoke(
            main, ["tag", "remove", "test-vm", "environment", "--resource-group", "custom-rg"]
        )

        assert result.exit_code == 0
        mock_get_vm.assert_called_once_with("test-vm", "custom-rg")
        mock_remove_tags.assert_called_once_with("test-vm", "custom-rg", ["environment"])


class TestTagListCommand:
    """Test 'azlin tag list' command."""

    @patch("azlin.commands.tag.TagManager.get_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_list_tags(
        self, mock_load_config, mock_get_vm, mock_get_tags, runner, mock_config, mock_vm
    ):
        """Listing tags should display all tags."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm
        mock_get_tags.return_value = {"environment": "development", "team": "backend"}

        result = runner.invoke(main, ["tag", "list", "test-vm"])

        assert result.exit_code == 0
        assert "Tags for VM 'test-vm'" in result.output
        assert "environment=development" in result.output
        assert "team=backend" in result.output
        assert "Total: 2 tag(s)" in result.output

    @patch("azlin.commands.tag.TagManager.get_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_list_no_tags(
        self, mock_load_config, mock_get_vm, mock_get_tags, runner, mock_config, mock_vm
    ):
        """Listing tags on VM with no tags should show message."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm
        mock_get_tags.return_value = {}

        result = runner.invoke(main, ["tag", "list", "test-vm"])

        assert result.exit_code == 0
        assert "VM 'test-vm' has no tags" in result.output

    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_list_vm_not_found(self, mock_load_config, mock_get_vm, runner, mock_config):
        """Listing tags on non-existent VM should fail."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = None

        result = runner.invoke(main, ["tag", "list", "nonexistent-vm"])

        assert result.exit_code == 1
        assert "VM 'nonexistent-vm' not found" in result.output

    @patch("azlin.commands.tag.TagManager.get_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_list_with_custom_resource_group(
        self, mock_load_config, mock_get_vm, mock_get_tags, runner, mock_config, mock_vm
    ):
        """Listing tags with custom resource group should work."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm
        mock_get_tags.return_value = {"environment": "production"}

        result = runner.invoke(main, ["tag", "list", "test-vm", "--resource-group", "custom-rg"])

        assert result.exit_code == 0
        mock_get_vm.assert_called_once_with("test-vm", "custom-rg")
        mock_get_tags.assert_called_once_with("test-vm", "custom-rg")


class TestTagIntegrationScenarios:
    """Test full tag lifecycle scenarios."""

    @patch("azlin.commands.tag.TagManager.get_tags")
    @patch("azlin.commands.tag.TagManager.remove_tags")
    @patch("azlin.commands.tag.TagManager.add_tags")
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_add_list_remove_cycle(
        self,
        mock_load_config,
        mock_get_vm,
        mock_add_tags,
        mock_remove_tags,
        mock_get_tags,
        runner,
        mock_config,
        mock_vm,
    ):
        """Test adding, listing, then removing tags."""
        mock_load_config.return_value = mock_config
        mock_get_vm.return_value = mock_vm

        # Add tags
        mock_get_tags.return_value = {}
        result = runner.invoke(main, ["tag", "add", "test-vm", "project=web", "team=backend"])
        assert result.exit_code == 0
        assert "Successfully added 2 tag(s)" in result.output

        # List tags
        mock_get_tags.return_value = {"project": "web", "team": "backend"}
        result = runner.invoke(main, ["tag", "list", "test-vm"])
        assert result.exit_code == 0
        assert "project=web" in result.output
        assert "team=backend" in result.output

        # Remove tags
        result = runner.invoke(main, ["tag", "remove", "test-vm", "project", "team"])
        assert result.exit_code == 0
        assert "Successfully removed 2 tag(s)" in result.output

        # Verify all operations called correct methods
        mock_add_tags.assert_called_once()
        mock_remove_tags.assert_called_once()
        mock_get_tags.assert_called_once()
