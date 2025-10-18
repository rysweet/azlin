"""Unit tests for tag_manager module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from azlin.tag_manager import TagManager, TagManagerError
from azlin.vm_manager import VMInfo


class TestTagManager:
    """Tests for TagManager class."""

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_single(self, mock_run):
        """Test adding a single tag to a VM."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"tags": {"env": "dev"}}', stderr=""
        )

        TagManager.add_tags("test-vm", "test-rg", {"env": "dev"})

        # Verify the correct command was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "az" in cmd
        assert "vm" in cmd
        assert "update" in cmd
        assert "--name" in cmd
        assert "test-vm" in cmd
        assert "--resource-group" in cmd
        assert "test-rg" in cmd
        assert "--set" in cmd

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_multiple(self, mock_run):
        """Test adding multiple tags to a VM."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"tags": {"env": "dev", "team": "backend", "project": "api"}}',
            stderr="",
        )

        tags = {"env": "dev", "team": "backend", "project": "api"}
        TagManager.add_tags("test-vm", "test-rg", tags)

        # Verify command was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "az" in cmd
        assert "vm" in cmd
        assert "update" in cmd

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_vm_not_found(self, mock_run):
        """Test adding tags to non-existent VM raises error."""
        mock_run.side_effect = Exception("ResourceNotFound")

        with pytest.raises(TagManagerError) as exc_info:
            TagManager.add_tags("missing-vm", "test-rg", {"env": "dev"})

        assert "Failed to add tags" in str(exc_info.value)

    @patch("azlin.tag_manager.subprocess.run")
    def test_remove_tags_single(self, mock_run):
        """Test removing a single tag from a VM."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"tags": {}}', stderr="")

        TagManager.remove_tags("test-vm", "test-rg", ["env"])

        # Verify the correct command was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "az" in cmd
        assert "vm" in cmd
        assert "update" in cmd
        assert "--name" in cmd
        assert "test-vm" in cmd
        assert "--resource-group" in cmd
        assert "test-rg" in cmd
        assert "--remove" in cmd

    @patch("azlin.tag_manager.subprocess.run")
    def test_remove_tags_multiple(self, mock_run):
        """Test removing multiple tags from a VM."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"tags": {}}', stderr="")

        TagManager.remove_tags("test-vm", "test-rg", ["env", "team", "project"])

        # Verify command was called
        mock_run.assert_called_once()

    @patch("azlin.tag_manager.subprocess.run")
    def test_remove_tags_vm_not_found(self, mock_run):
        """Test removing tags from non-existent VM raises error."""
        mock_run.side_effect = Exception("ResourceNotFound")

        with pytest.raises(TagManagerError) as exc_info:
            TagManager.remove_tags("missing-vm", "test-rg", ["env"])

        assert "Failed to remove tags" in str(exc_info.value)

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_success(self, mock_run):
        """Test getting tags from a VM."""
        vm_data = {"name": "test-vm", "tags": {"env": "dev", "team": "backend", "project": "api"}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(vm_data), stderr="")

        tags = TagManager.get_tags("test-vm", "test-rg")

        assert tags == {"env": "dev", "team": "backend", "project": "api"}
        mock_run.assert_called_once()

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_no_tags(self, mock_run):
        """Test getting tags from VM with no tags."""
        vm_data = {"name": "test-vm", "tags": {}}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(vm_data), stderr="")

        tags = TagManager.get_tags("test-vm", "test-rg")

        assert tags == {}

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_null_tags(self, mock_run):
        """Test getting tags from VM with null tags field."""
        vm_data = {"name": "test-vm", "tags": None}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(vm_data), stderr="")

        tags = TagManager.get_tags("test-vm", "test-rg")

        assert tags == {}

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_vm_not_found(self, mock_run):
        """Test getting tags from non-existent VM raises error."""
        mock_run.side_effect = Exception("ResourceNotFound")

        with pytest.raises(TagManagerError) as exc_info:
            TagManager.get_tags("missing-vm", "test-rg")

        assert "Failed to get tags" in str(exc_info.value)

    def test_filter_vms_by_tag_exact_match(self):
        """Test filtering VMs by tag with exact key=value match."""
        vms = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "dev", "team": "backend"},
            ),
            VMInfo(
                name="vm2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "prod", "team": "frontend"},
            ),
            VMInfo(
                name="vm3",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "dev", "team": "frontend"},
            ),
        ]

        # Filter by env=dev
        filtered = TagManager.filter_vms_by_tag(vms, "env=dev")
        assert len(filtered) == 2
        assert filtered[0].name == "vm1"
        assert filtered[1].name == "vm3"

    def test_filter_vms_by_tag_key_only(self):
        """Test filtering VMs by tag key only (any value)."""
        vms = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "dev", "team": "backend"},
            ),
            VMInfo(
                name="vm2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"project": "api"},
            ),
            VMInfo(
                name="vm3",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "prod"},
            ),
        ]

        # Filter by 'env' key (any value)
        filtered = TagManager.filter_vms_by_tag(vms, "env")
        assert len(filtered) == 2
        assert filtered[0].name == "vm1"
        assert filtered[1].name == "vm3"

    def test_filter_vms_by_tag_no_match(self):
        """Test filtering VMs when no VMs match the tag."""
        vms = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "dev"},
            ),
            VMInfo(
                name="vm2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={"env": "prod"},
            ),
        ]

        # Filter by non-existent tag
        filtered = TagManager.filter_vms_by_tag(vms, "team=backend")
        assert len(filtered) == 0

    def test_filter_vms_by_tag_no_tags(self):
        """Test filtering VMs when VMs have no tags."""
        vms = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags=None,
            ),
            VMInfo(
                name="vm2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                tags={},
            ),
        ]

        # Filter should return empty list
        filtered = TagManager.filter_vms_by_tag(vms, "env=dev")
        assert len(filtered) == 0

    def test_filter_vms_empty_list(self):
        """Test filtering empty VM list."""
        filtered = TagManager.filter_vms_by_tag([], "env=dev")
        assert len(filtered) == 0

    def test_parse_tag_filter_exact_match(self):
        """Test parsing tag filter with key=value."""
        key, value = TagManager.parse_tag_filter("env=dev")
        assert key == "env"
        assert value == "dev"

    def test_parse_tag_filter_key_only(self):
        """Test parsing tag filter with key only."""
        key, value = TagManager.parse_tag_filter("env")
        assert key == "env"
        assert value is None

    def test_parse_tag_filter_with_equals_in_value(self):
        """Test parsing tag filter where value contains equals sign."""
        key, value = TagManager.parse_tag_filter("url=http://example.com")
        assert key == "url"
        assert value == "http://example.com"

    def test_validate_tag_key_valid(self):
        """Test validating valid tag keys."""
        assert TagManager.validate_tag_key("env") is True
        assert TagManager.validate_tag_key("my-tag") is True
        assert TagManager.validate_tag_key("my_tag") is True
        assert TagManager.validate_tag_key("my.tag") is True
        assert TagManager.validate_tag_key("MyTag123") is True

    def test_validate_tag_key_invalid(self):
        """Test validating invalid tag keys."""
        assert TagManager.validate_tag_key("") is False
        assert TagManager.validate_tag_key("my tag") is False  # spaces not allowed
        assert TagManager.validate_tag_key("my@tag") is False  # @ not allowed
        assert TagManager.validate_tag_key("my/tag") is False  # / not allowed

    def test_validate_tag_value_valid(self):
        """Test validating valid tag values."""
        assert TagManager.validate_tag_value("dev") is True
        assert TagManager.validate_tag_value("my-value") is True
        assert TagManager.validate_tag_value("my_value") is True
        assert TagManager.validate_tag_value("my value") is True  # spaces allowed
        assert TagManager.validate_tag_value("") is True  # empty allowed

    def test_parse_tag_assignment_valid(self):
        """Test parsing valid tag assignments."""
        key, value = TagManager.parse_tag_assignment("env=dev")
        assert key == "env"
        assert value == "dev"

        key, value = TagManager.parse_tag_assignment("team=backend-api")
        assert key == "team"
        assert value == "backend-api"

    def test_parse_tag_assignment_invalid(self):
        """Test parsing invalid tag assignments raises error."""
        with pytest.raises(TagManagerError) as exc_info:
            TagManager.parse_tag_assignment("invalid")
        assert "Invalid tag format" in str(exc_info.value)

        with pytest.raises(TagManagerError) as exc_info:
            TagManager.parse_tag_assignment("=value")
        assert "Invalid tag format" in str(exc_info.value)

        with pytest.raises(TagManagerError) as exc_info:
            TagManager.parse_tag_assignment("key=")
        assert "Invalid tag format" in str(exc_info.value)
