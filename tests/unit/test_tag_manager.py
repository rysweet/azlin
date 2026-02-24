"""Unit tests for tag_manager module.

Tests TagManager class with mocked Azure CLI subprocess calls:
- Tag CRUD operations (add, list, remove)
- VM discovery via tags (list_managed_vms)
- Tag format validation and parsing
- Error handling (Azure API failures, timeouts, bad JSON)
- Edge cases (empty tags, special characters, null tags)
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from azlin.tag_manager import TagManager, TagManagerError
from azlin.vm_manager import VMInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vm_info(name="test-vm", resource_group="test-rg", tags=None, **kwargs):
    """Create a VMInfo with sensible defaults."""
    defaults = {
        "name": name,
        "resource_group": resource_group,
        "location": "eastus",
        "power_state": "VM running",
        "tags": tags,
    }
    defaults.update(kwargs)
    return VMInfo(**defaults)


def _make_subprocess_result(stdout="", stderr="", returncode=0):
    """Create a CompletedProcess result."""
    return subprocess.CompletedProcess(
        args=["az"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ===========================================================================
# Tag key/value validation
# ===========================================================================


class TestTagValidation:
    """Tests for tag key and value validation."""

    def test_valid_tag_keys(self):
        assert TagManager.validate_tag_key("managed-by") is True
        assert TagManager.validate_tag_key("azlin_session") is True
        assert TagManager.validate_tag_key("my.tag.key") is True
        assert TagManager.validate_tag_key("Simple123") is True

    def test_invalid_tag_keys(self):
        assert TagManager.validate_tag_key("") is False
        assert TagManager.validate_tag_key("key with spaces") is False
        assert TagManager.validate_tag_key("key=value") is False
        assert TagManager.validate_tag_key("key;drop") is False

    def test_validate_tag_value_always_true(self):
        # Azure allows most characters in tag values
        assert TagManager.validate_tag_value("") is True
        assert TagManager.validate_tag_value("any value here") is True
        assert TagManager.validate_tag_value("special!@#$%") is True


# ===========================================================================
# Session name validation
# ===========================================================================


class TestSessionNameValidation:
    """Tests for session name validation."""

    def test_valid_session_names(self):
        assert TagManager.validate_session_name("my-session") is True
        assert TagManager.validate_session_name("session_01") is True
        assert TagManager.validate_session_name("a") is True

    def test_empty_session_name(self):
        assert TagManager.validate_session_name("") is False

    def test_too_long_session_name(self):
        assert TagManager.validate_session_name("a" * 65) is False

    def test_invalid_characters_in_session_name(self):
        assert TagManager.validate_session_name("has spaces") is False
        assert TagManager.validate_session_name("has.dots") is False
        assert TagManager.validate_session_name("has=equals") is False


# ===========================================================================
# Tag filter parsing
# ===========================================================================


class TestParseTagFilter:
    """Tests for parse_tag_filter."""

    def test_key_only_filter(self):
        key, value = TagManager.parse_tag_filter("managed-by")
        assert key == "managed-by"
        assert value is None

    def test_key_value_filter(self):
        key, value = TagManager.parse_tag_filter("managed-by=azlin")
        assert key == "managed-by"
        assert value == "azlin"

    def test_value_with_equals(self):
        key, value = TagManager.parse_tag_filter("config=a=b=c")
        assert key == "config"
        assert value == "a=b=c"


# ===========================================================================
# Tag assignment parsing
# ===========================================================================


class TestParseTagAssignment:
    """Tests for parse_tag_assignment."""

    def test_valid_assignment(self):
        key, value = TagManager.parse_tag_assignment("env=production")
        assert key == "env"
        assert value == "production"

    def test_missing_equals(self):
        with pytest.raises(TagManagerError, match="Expected format: key=value"):
            TagManager.parse_tag_assignment("noequals")

    def test_empty_key(self):
        with pytest.raises(TagManagerError, match="Tag key cannot be empty"):
            TagManager.parse_tag_assignment("=value")

    def test_empty_value(self):
        with pytest.raises(TagManagerError, match="Tag value cannot be empty"):
            TagManager.parse_tag_assignment("key=")

    def test_invalid_key_characters(self):
        with pytest.raises(TagManagerError, match="Invalid tag key"):
            TagManager.parse_tag_assignment("bad key=value")


# ===========================================================================
# filter_vms_by_tag
# ===========================================================================


class TestFilterVmsByTag:
    """Tests for filter_vms_by_tag (pure logic, no subprocess)."""

    def test_filter_by_key_only(self):
        vms = [
            _make_vm_info("vm1", tags={"env": "prod"}),
            _make_vm_info("vm2", tags={"env": "dev"}),
            _make_vm_info("vm3", tags={"other": "x"}),
        ]
        result = TagManager.filter_vms_by_tag(vms, "env")
        assert len(result) == 2
        assert {v.name for v in result} == {"vm1", "vm2"}

    def test_filter_by_key_value(self):
        vms = [
            _make_vm_info("vm1", tags={"env": "prod"}),
            _make_vm_info("vm2", tags={"env": "dev"}),
        ]
        result = TagManager.filter_vms_by_tag(vms, "env=prod")
        assert len(result) == 1
        assert result[0].name == "vm1"

    def test_filter_skips_vms_with_no_tags(self):
        vms = [
            _make_vm_info("vm1", tags=None),
            _make_vm_info("vm2", tags={"env": "prod"}),
        ]
        result = TagManager.filter_vms_by_tag(vms, "env")
        assert len(result) == 1

    def test_filter_no_match(self):
        vms = [_make_vm_info("vm1", tags={"env": "prod"})]
        result = TagManager.filter_vms_by_tag(vms, "missing-key")
        assert result == []


# ===========================================================================
# _extract_resource_group_from_vm_data
# ===========================================================================


class TestExtractResourceGroup:
    """Tests for _extract_resource_group_from_vm_data."""

    def test_extract_from_id(self):
        vm_data = {
            "id": "/subscriptions/xxx/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/vm1"
        }
        assert TagManager._extract_resource_group_from_vm_data(vm_data) == "my-rg"

    def test_fallback_to_resource_group_field(self):
        vm_data = {"id": "", "resourceGroup": "fallback-rg"}
        assert TagManager._extract_resource_group_from_vm_data(vm_data) == "fallback-rg"

    def test_returns_none_when_missing(self):
        vm_data = {"id": "/no/resource/groups/here"}
        assert TagManager._extract_resource_group_from_vm_data(vm_data) is None


# ===========================================================================
# add_tags (mocked subprocess)
# ===========================================================================


class TestAddTags:
    """Tests for add_tags with mocked subprocess."""

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_success(self, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout="{}")
        TagManager.add_tags("vm1", "rg1", {"env": "prod"})
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--set" in cmd
        assert "tags.env=prod" in cmd

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_invalid_key_raises(self, mock_run):
        with pytest.raises(TagManagerError, match="Invalid tag key"):
            TagManager.add_tags("vm1", "rg1", {"bad key": "value"})
        mock_run.assert_not_called()

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_subprocess_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="ResourceNotFound")
        with pytest.raises(TagManagerError, match="Failed to add tags"):
            TagManager.add_tags("vm1", "rg1", {"env": "prod"})

    @patch("azlin.tag_manager.subprocess.run")
    def test_add_tags_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("az", 120)
        with pytest.raises(TagManagerError, match="timed out"):
            TagManager.add_tags("vm1", "rg1", {"env": "prod"})


# ===========================================================================
# remove_tags (mocked subprocess)
# ===========================================================================


class TestRemoveTags:
    """Tests for remove_tags with mocked subprocess."""

    @patch("azlin.tag_manager.subprocess.run")
    def test_remove_tags_success(self, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout="{}")
        TagManager.remove_tags("vm1", "rg1", ["env", "owner"])
        cmd = mock_run.call_args[0][0]
        assert cmd.count("--remove") == 2

    @patch("azlin.tag_manager.subprocess.run")
    def test_remove_tags_subprocess_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="NotFound")
        with pytest.raises(TagManagerError, match="Failed to remove tags"):
            TagManager.remove_tags("vm1", "rg1", ["env"])


# ===========================================================================
# get_tags (mocked subprocess)
# ===========================================================================


class TestGetTags:
    """Tests for get_tags with mocked subprocess."""

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_success(self, mock_run):
        vm_data = {"tags": {"managed-by": "azlin", "env": "dev"}}
        mock_run.return_value = _make_subprocess_result(stdout=json.dumps(vm_data))
        tags = TagManager.get_tags("vm1", "rg1")
        assert tags == {"managed-by": "azlin", "env": "dev"}

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_null_tags(self, mock_run):
        vm_data = {"tags": None}
        mock_run.return_value = _make_subprocess_result(stdout=json.dumps(vm_data))
        tags = TagManager.get_tags("vm1", "rg1")
        assert tags == {}

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_no_tags_key(self, mock_run):
        vm_data = {"name": "vm1"}
        mock_run.return_value = _make_subprocess_result(stdout=json.dumps(vm_data))
        tags = TagManager.get_tags("vm1", "rg1")
        assert tags == {}

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_bad_json(self, mock_run):
        mock_run.return_value = _make_subprocess_result(stdout="not json")
        with pytest.raises(TagManagerError, match="Failed to parse"):
            TagManager.get_tags("vm1", "rg1")

    @patch("azlin.tag_manager.subprocess.run")
    def test_get_tags_subprocess_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="Error")
        with pytest.raises(TagManagerError, match="Failed to get tags"):
            TagManager.get_tags("vm1", "rg1")


# ===========================================================================
# Session management (get_session_name, set_session_name, delete_session_name)
# ===========================================================================


class TestSessionManagement:
    """Tests for session name tag operations."""

    @patch.object(TagManager, "get_tags")
    def test_get_session_name_found(self, mock_get_tags):
        mock_get_tags.return_value = {"azlin-session": "my-session"}
        result = TagManager.get_session_name("vm1", "rg1")
        assert result == "my-session"

    @patch.object(TagManager, "get_tags")
    def test_get_session_name_not_set(self, mock_get_tags):
        mock_get_tags.return_value = {"managed-by": "azlin"}
        result = TagManager.get_session_name("vm1", "rg1")
        assert result is None

    @patch.object(TagManager, "get_tags")
    def test_get_session_name_on_error(self, mock_get_tags):
        mock_get_tags.side_effect = TagManagerError("fail")
        result = TagManager.get_session_name("vm1", "rg1")
        assert result is None

    @patch.object(TagManager, "add_tags")
    def test_set_session_name_success(self, mock_add):
        result = TagManager.set_session_name("vm1", "rg1", "my-session")
        assert result is True
        mock_add.assert_called_once_with("vm1", "rg1", {TagManager.TAG_SESSION: "my-session"})

    def test_set_session_name_invalid(self):
        with pytest.raises(ValueError, match="Invalid session name"):
            TagManager.set_session_name("vm1", "rg1", "bad session name!")

    @patch.object(TagManager, "remove_tags")
    def test_delete_session_name_success(self, mock_remove):
        result = TagManager.delete_session_name("vm1", "rg1")
        assert result is True
        mock_remove.assert_called_once_with("vm1", "rg1", [TagManager.TAG_SESSION])

    @patch.object(TagManager, "remove_tags")
    def test_delete_session_name_failure(self, mock_remove):
        mock_remove.side_effect = TagManagerError("fail")
        result = TagManager.delete_session_name("vm1", "rg1")
        assert result is False


# ===========================================================================
# set_managed_tags
# ===========================================================================


class TestSetManagedTags:
    """Tests for set_managed_tags."""

    @patch.object(TagManager, "add_tags")
    def test_set_managed_tags_basic(self, mock_add):
        result = TagManager.set_managed_tags("vm1", "rg1")
        assert result is True
        tags = mock_add.call_args[0][2]
        assert tags["managed-by"] == "azlin"
        assert "azlin-created" in tags

    @patch.object(TagManager, "add_tags")
    def test_set_managed_tags_with_owner_and_session(self, mock_add):
        result = TagManager.set_managed_tags("vm1", "rg1", owner="testuser", session_name="sess-1")
        assert result is True
        tags = mock_add.call_args[0][2]
        assert tags["azlin-owner"] == "testuser"
        assert tags["azlin-session"] == "sess-1"

    def test_set_managed_tags_invalid_session(self):
        with pytest.raises(ValueError, match="Invalid session name"):
            TagManager.set_managed_tags("vm1", "rg1", session_name="bad name!")


# ===========================================================================
# list_managed_vms (with resource_group -- uses VMManager cache path)
# ===========================================================================


class TestListManagedVms:
    """Tests for list_managed_vms."""

    @patch("azlin.vm_manager.VMManager.list_vms_with_cache")
    def test_list_managed_vms_with_rg(self, mock_list):
        vm_managed = _make_vm_info("azlin-vm1", tags={"managed-by": "azlin"})
        vm_unmanaged = _make_vm_info("other-vm", tags={"env": "prod"})
        mock_list.return_value = ([vm_managed, vm_unmanaged], False)
        vms, was_cached = TagManager.list_managed_vms(resource_group="rg1")
        assert len(vms) == 1
        assert vms[0].name == "azlin-vm1"

    @patch("azlin.tag_manager.AzureCLIExecutor")
    def test_list_managed_vms_multi_rg_empty(self, mock_executor_cls):
        """When no resource_group, uses CLI query path."""
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            "success": True,
            "stdout": "[]",
            "stderr": "",
            "returncode": 0,
        }
        mock_executor_cls.return_value = mock_executor
        vms, was_cached = TagManager.list_managed_vms(resource_group=None)
        assert vms == []
        assert was_cached is False
