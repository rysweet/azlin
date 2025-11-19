"""Unit tests for tag CLI commands - Issue #185: Tag Management Commands.

These tests verify the tag subcommands: add, remove, list.
Uses TDD approach - these tests will FAIL until the commands are implemented.

Test Coverage:
- azlin tag add: Adding single and multiple tags
- azlin tag remove: Removing tags by key
- azlin tag list: Displaying VM tags
- Input validation and error handling
- Resource group resolution
- TagManager integration
"""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from azlin.cli import main as cli
from azlin.tag_manager import TagManagerError


class TestTagAddCommand:
    """Test 'azlin tag add' command - Issue #185."""

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_single_tag_success(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test adding a single tag to a VM successfully.

        Expected command: azlin tag add myvm environment=production

        This test verifies:
        - Command parses single key=value tag
        - TagManager.add_tags() called with correct parameters
        - Success message displayed
        - Exit code 0

        Expected to FAIL until command is implemented.
        """
        # Mock config to return resource group
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_add_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "environment=production"])

        # Verify command succeeded
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Successfully added" in result.output

        # Verify TagManager.add_tags was called correctly
        mock_add_tags.assert_called_once_with("myvm", "test-rg", {"environment": "production"})

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_multiple_tags_success(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test adding multiple tags to a VM in a single command.

        Expected command: azlin tag add myvm env=prod team=backend version=1.0

        This test verifies:
        - Command parses multiple key=value tags
        - All tags passed to TagManager.add_tags()
        - Success message displayed

        Expected to FAIL until command is implemented.
        """
        # Mock config to return resource group
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_add_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(
            cli, ["tag", "add", "myvm", "env=prod", "team=backend", "version=1.0"]
        )

        # Verify command succeeded
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify all tags were passed
        mock_add_tags.assert_called_once_with(
            "myvm", "test-rg", {"env": "prod", "team": "backend", "version": "1.0"}
        )

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_with_spaces_in_value(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test adding tag with spaces in value.

        Expected command: azlin tag add myvm "description=Production Web Server"

        This test verifies tag values with spaces are handled correctly.

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_add_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "description=Production Web Server"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        mock_add_tags.assert_called_once_with(
            "myvm", "test-rg", {"description": "Production Web Server"}
        )

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_with_resource_group_flag(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test adding tags with explicit --resource-group flag.

        Expected command: azlin tag add myvm env=prod --resource-group custom-rg

        This test verifies:
        - --resource-group flag overrides config
        - Custom resource group used for tag operation

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="default-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_add_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(
            cli, ["tag", "add", "myvm", "env=prod", "--resource-group", "custom-rg"]
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify custom resource group was used
        mock_add_tags.assert_called_once_with("myvm", "custom-rg", {"env": "prod"})

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_add_invalid_format_no_equals(self, mock_config_load, mock_get_vm, mock_ensure_sub):
        """Test adding tag with invalid format (missing =).

        Expected command: azlin tag add myvm invalid_tag

        This test verifies:
        - Invalid format rejected
        - Error message explains required format
        - Exit code non-zero

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "invalid_tag"])

        # Verify command failed with appropriate error
        assert result.exit_code != 0, "Should fail with invalid tag format"
        assert "key=value" in result.output.lower() or "invalid" in result.output.lower()

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_add_empty_key(self, mock_config_load, mock_get_vm, mock_ensure_sub):
        """Test adding tag with empty key.

        Expected command: azlin tag add myvm =value

        This test verifies empty keys are rejected.

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "=value"])

        assert result.exit_code != 0, "Should fail with empty key"
        assert "invalid" in result.output.lower() or "empty" in result.output.lower()

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_tagmanager_error(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test handling TagManager errors during tag add.

        This test verifies:
        - TagManagerError exceptions are caught
        - Error message displayed to user
        - Non-zero exit code

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="nonexistent-vm")
        mock_add_tags.side_effect = TagManagerError("VM not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "nonexistent-vm", "env=prod"])

        assert result.exit_code != 0, "Should fail when TagManager raises error"
        assert "error" in result.output.lower() or "failed" in result.output.lower()

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_add_no_resource_group_in_config(self, mock_config_load, mock_ensure_sub):
        """Test tag add fails gracefully when no resource group configured.

        This test verifies:
        - Missing resource group handled appropriately
        - User prompted to configure or provide --resource-group

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group=None)

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "env=prod"])

        assert result.exit_code != 0, "Should fail without resource group"
        assert (
            "resource group" in result.output.lower() or "resource-group" in result.output.lower()
        )


class TestTagRemoveCommand:
    """Test 'azlin tag remove' command - Issue #185."""

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.remove_tags")
    def test_tag_remove_single_key_success(
        self, mock_remove_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test removing a single tag from a VM.

        Expected command: azlin tag remove myvm environment

        This test verifies:
        - Command parses tag key to remove
        - TagManager.remove_tags() called correctly
        - Success message displayed

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_remove_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "remove", "myvm", "environment"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "removed" in result.output.lower() or "success" in result.output.lower()

        # Verify TagManager.remove_tags called with correct parameters
        mock_remove_tags.assert_called_once_with("myvm", "test-rg", ["environment"])

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.remove_tags")
    def test_tag_remove_multiple_keys_success(
        self, mock_remove_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test removing multiple tags from a VM.

        Expected command: azlin tag remove myvm env team version

        This test verifies multiple tag keys can be removed in one command.

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_remove_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "remove", "myvm", "env", "team", "version"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify all keys were passed
        mock_remove_tags.assert_called_once_with("myvm", "test-rg", ["env", "team", "version"])

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.remove_tags")
    def test_tag_remove_with_resource_group_flag(
        self, mock_remove_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test removing tags with explicit --resource-group flag.

        Expected command: azlin tag remove myvm env --resource-group custom-rg

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="default-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_remove_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(
            cli, ["tag", "remove", "myvm", "env", "--resource-group", "custom-rg"]
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify custom resource group was used
        mock_remove_tags.assert_called_once_with("myvm", "custom-rg", ["env"])

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.remove_tags")
    def test_tag_remove_tagmanager_error(
        self, mock_remove_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test handling TagManager errors during tag remove.

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_remove_tags.side_effect = TagManagerError("Tag key not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "remove", "myvm", "nonexistent-key"])

        assert result.exit_code != 0, "Should fail when TagManager raises error"
        assert "error" in result.output.lower() or "failed" in result.output.lower()


class TestTagListCommand:
    """Test 'azlin tag list' command - Issue #185."""

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.get_tags")
    def test_tag_list_success_with_tags(
        self, mock_get_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test listing tags from a VM with tags.

        Expected command: azlin tag list myvm

        This test verifies:
        - Command retrieves tags from VM
        - Tags displayed in readable format
        - Exit code 0

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_get_tags.return_value = {
            "environment": "production",
            "team": "backend",
            "version": "1.0",
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "list", "myvm"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify all tags are displayed
        assert "environment" in result.output
        assert "production" in result.output
        assert "team" in result.output
        assert "backend" in result.output
        assert "version" in result.output
        assert "1.0" in result.output

        # Verify get_tags was called correctly
        mock_get_tags.assert_called_once_with("myvm", "test-rg")

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.get_tags")
    def test_tag_list_vm_with_no_tags(
        self, mock_get_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test listing tags from a VM with no tags.

        This test verifies:
        - Empty tag dict handled gracefully
        - Appropriate message displayed (e.g., "No tags found")

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_get_tags.return_value = {}

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "list", "myvm"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert (
            "no tags" in result.output.lower()
            or "no tags found" in result.output.lower()
            or "empty" in result.output.lower()
        )

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.get_tags")
    def test_tag_list_with_resource_group_flag(
        self, mock_get_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test listing tags with explicit --resource-group flag.

        Expected command: azlin tag list myvm --resource-group custom-rg

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="default-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_get_tags.return_value = {"env": "prod"}

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "list", "myvm", "--resource-group", "custom-rg"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify custom resource group was used
        mock_get_tags.assert_called_once_with("myvm", "custom-rg")

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.get_tags")
    def test_tag_list_tagmanager_error(
        self, mock_get_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test handling TagManager errors during tag list.

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="nonexistent-vm")
        mock_get_tags.side_effect = TagManagerError("VM not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "list", "nonexistent-vm"])

        assert result.exit_code != 0, "Should fail when TagManager raises error"
        assert "error" in result.output.lower() or "failed" in result.output.lower()


class TestTagCommandEdgeCases:
    """Test edge cases and boundary conditions for tag commands."""

    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_group_without_subcommand_shows_help(self, mock_config_load):
        """Test 'azlin tag' without subcommand shows help.

        Expected command: azlin tag

        This test verifies:
        - Help text displayed when no subcommand given
        - Lists available subcommands (add, remove, list)

        Expected to FAIL until command is implemented.
        """
        runner = CliRunner()
        result = runner.invoke(cli, ["tag"])

        # Should show help text
        assert "add" in result.output.lower()
        assert "remove" in result.output.lower()
        assert "list" in result.output.lower()

    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_add_with_no_tags_provided(self, mock_config_load):
        """Test 'azlin tag add' with no tags fails appropriately.

        Expected command: azlin tag add myvm

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm"])

        # Should fail - need at least one tag
        assert result.exit_code != 0, "Should fail when no tags provided"

    @patch("azlin.commands.tag.ConfigManager.load_config")
    def test_tag_remove_with_no_keys_provided(self, mock_config_load):
        """Test 'azlin tag remove' with no keys fails appropriately.

        Expected command: azlin tag remove myvm

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "remove", "myvm"])

        # Should fail - need at least one key
        assert result.exit_code != 0, "Should fail when no keys provided"

    @patch(
        "azlin.context_manager.ContextManager.ensure_subscription_active",
        return_value="test-sub-id",
    )
    @patch("azlin.commands.tag.VMManager.get_vm")
    @patch("azlin.commands.tag.ConfigManager.load_config")
    @patch("azlin.commands.tag.TagManager.add_tags")
    def test_tag_add_with_equals_in_value(
        self, mock_add_tags, mock_config_load, mock_get_vm, mock_ensure_sub
    ):
        """Test adding tag with '=' character in the value.

        Expected command: azlin tag add myvm "url=https://example.com?foo=bar"

        This test verifies values containing '=' are handled correctly
        (only first '=' splits key and value).

        Expected to FAIL until command is implemented.
        """
        mock_config_load.return_value = Mock(default_resource_group="test-rg")
        mock_get_vm.return_value = Mock(name="myvm")
        mock_add_tags.return_value = None

        runner = CliRunner()
        result = runner.invoke(cli, ["tag", "add", "myvm", "url=https://example.com?foo=bar"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        mock_add_tags.assert_called_once_with(
            "myvm", "test-rg", {"url": "https://example.com?foo=bar"}
        )
