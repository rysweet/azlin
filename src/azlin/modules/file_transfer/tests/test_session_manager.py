"""Unit tests for session_manager module."""

import pytest
from unittest.mock import Mock
from azlin.modules.file_transfer import (
    SessionManager,
    VMSession,
    InvalidSessionNameError,
    SessionNotFoundError,
    MultipleSessionsError
)


class TestSessionNameValidation:
    """Test session name validation."""

    def test_accepts_alphanumeric_name(self):
        """Should accept alphanumeric names"""
        result = SessionManager.validate_session_name("vm123")
        assert result == "vm123"

    def test_accepts_hyphens(self):
        """Should accept hyphens"""
        result = SessionManager.validate_session_name("my-vm-name")
        assert result == "my-vm-name"

    def test_accepts_underscores(self):
        """Should accept underscores"""
        result = SessionManager.validate_session_name("my_vm_name")
        assert result == "my_vm_name"

    def test_accepts_mixed_valid_chars(self):
        """Should accept mixed valid characters"""
        result = SessionManager.validate_session_name("VM-test_123")
        assert result == "VM-test_123"

    def test_rejects_empty_name(self):
        """Should reject empty names"""
        with pytest.raises(InvalidSessionNameError, match="empty"):
            SessionManager.validate_session_name("")

    def test_rejects_whitespace_only(self):
        """Should reject whitespace-only names"""
        with pytest.raises(InvalidSessionNameError, match="empty"):
            SessionManager.validate_session_name("   ")

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace"""
        result = SessionManager.validate_session_name("  vm123  ")
        assert result == "vm123"

    def test_rejects_too_long_name(self):
        """Should reject names longer than MAX_LENGTH"""
        long_name = "a" * 65
        with pytest.raises(InvalidSessionNameError, match="too long"):
            SessionManager.validate_session_name(long_name)


class TestSessionNameSecurity:
    """Test session name security against injection."""

    def test_rejects_semicolon(self):
        """Should reject semicolons"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm;rm")

    def test_rejects_pipe(self):
        """Should reject pipes"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm|cat")

    def test_rejects_ampersand(self):
        """Should reject ampersands"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm&whoami")

    def test_rejects_dollar_sign(self):
        """Should reject dollar signs"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm$test")

    def test_rejects_backtick(self):
        """Should reject backticks"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm`whoami`")

    def test_rejects_parentheses(self):
        """Should reject parentheses"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm(test)")

    def test_rejects_spaces(self):
        """Should reject spaces"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("vm name")


class TestSessionPathParsing:
    """Test session:path notation parsing."""

    def test_parses_local_path(self):
        """Should parse local paths without session"""
        session, path = SessionManager.parse_session_path("test.txt")
        assert session is None
        assert path == "test.txt"

    def test_parses_session_path(self):
        """Should parse session:path notation"""
        session, path = SessionManager.parse_session_path("vm1:~/test.txt")
        assert session == "vm1"
        assert path == "~/test.txt"

    def test_parses_path_with_multiple_colons(self):
        """Should handle paths with multiple colons"""
        session, path = SessionManager.parse_session_path("vm1:C:/Users/test.txt")
        assert session == "vm1"
        assert path == "C:/Users/test.txt"

    def test_rejects_empty_path_after_colon(self):
        """Should reject empty path after colon"""
        with pytest.raises(InvalidSessionNameError, match="empty"):
            SessionManager.parse_session_path("vm1:")

    def test_rejects_invalid_session_name(self):
        """Should reject invalid session names in session:path"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.parse_session_path("evil;rm:file.txt")


class TestGetVMSession:
    """Test VM session lookup."""

    def test_finds_exact_match(self):
        """Should find VM with exact name match"""
        # Mock VM
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "running"
        mock_vm.public_ip = "1.2.3.4"

        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = [mock_vm]
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        session = SessionManager.get_vm_session("test-vm", vm_manager, config_manager)

        assert session.name == "test-vm"
        assert session.public_ip == "1.2.3.4"
        assert session.user == "azureuser"

    def test_finds_prefix_match(self):
        """Should find VM with prefix match"""
        # Mock VM
        mock_vm = Mock()
        mock_vm.name = "test-vm-001"
        mock_vm.power_state = "running"
        mock_vm.public_ip = "1.2.3.4"

        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = [mock_vm]
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        session = SessionManager.get_vm_session("test", vm_manager, config_manager)

        assert session.name == "test-vm-001"

    def test_rejects_multiple_matches(self):
        """Should reject ambiguous session names"""
        # Mock VMs
        mock_vm1 = Mock()
        mock_vm1.name = "test-vm-001"
        mock_vm1.power_state = "running"

        mock_vm2 = Mock()
        mock_vm2.name = "test-vm-002"
        mock_vm2.power_state = "running"

        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = [mock_vm1, mock_vm2]
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        with pytest.raises(MultipleSessionsError):
            SessionManager.get_vm_session("test", vm_manager, config_manager)

    def test_rejects_no_match(self):
        """Should reject when no VMs match"""
        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = []
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        with pytest.raises(SessionNotFoundError):
            SessionManager.get_vm_session("nonexistent", vm_manager, config_manager)

    def test_rejects_stopped_vm(self):
        """Should reject VMs that are not running"""
        # Mock VM
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "stopped"

        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = [mock_vm]
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        with pytest.raises(SessionNotFoundError, match="not running"):
            SessionManager.get_vm_session("test-vm", vm_manager, config_manager)

    def test_rejects_vm_without_ip(self):
        """Should reject VMs without public IP"""
        # Mock VM
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "running"
        mock_vm.public_ip = None

        # Mock managers
        vm_manager = Mock()
        vm_manager.list_vms.return_value = [mock_vm]
        config_manager = Mock()
        config_manager.get_default_resource_group.return_value = "test-rg"

        with pytest.raises(SessionNotFoundError, match="no public IP"):
            SessionManager.get_vm_session("test-vm", vm_manager, config_manager)
