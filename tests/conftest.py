"""
Shared test fixtures and configuration for azlin CLI tests.

This module provides common fixtures used across all test types:
- Mock Azure credentials and clients
- Temporary directories for SSH/config
- Sample VM configurations
- Progress display mocks
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest

# ============================================================================
# DIRECTORY FIXTURES
# ============================================================================


@pytest.fixture
def temp_ssh_dir(tmp_path):
    """Temporary SSH directory for testing.

    Creates a temporary .ssh directory with proper permissions
    for testing SSH key generation and config file operations.
    """
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    return ssh_dir


@pytest.fixture
def temp_config_dir(tmp_path):
    """Temporary config directory for testing.

    Creates a temporary .azlin directory for testing
    configuration file operations.
    """
    config_dir = tmp_path / ".azlin"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_home_dir(tmp_path, monkeypatch):
    """Temporary home directory for testing.

    Sets HOME environment variable to temporary directory
    for testing home directory operations without affecting
    real user home directory.
    """
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    return home_dir


# ============================================================================
# AZURE MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_azure_credentials():
    """Mock Azure DefaultAzureCredential.

    Provides a fake Azure credential that returns a valid token
    without attempting real authentication.
    """
    with patch("azure.identity.DefaultAzureCredential") as mock:
        mock_cred = Mock()
        mock_cred.get_token.return_value = Mock(
            token="fake-azure-token-12345", expires_on=9999999999
        )
        mock.return_value = mock_cred
        yield mock


@pytest.fixture
def mock_azure_compute_client():
    """Mock Azure ComputeManagementClient.

    Provides a fake Azure Compute client for testing VM operations
    without making actual Azure API calls.
    """
    with patch("azure.mgmt.compute.ComputeManagementClient") as mock:
        # Mock VM creation
        mock_vm_poller = Mock()
        mock_vm_poller.result.return_value = Mock(
            id="/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            name="test-vm",
            location="eastus",
            provisioning_state="Succeeded",
            hardware_profile=Mock(vm_size="Standard_D2s_v3"),
        )

        mock_client = Mock()
        mock_client.virtual_machines.begin_create_or_update.return_value = mock_vm_poller
        mock.return_value = mock_client
        yield mock


@pytest.fixture
def mock_azure_network_client():
    """Mock Azure NetworkManagementClient.

    Provides a fake Azure Network client for testing network
    operations without making actual Azure API calls.
    """
    with patch("azure.mgmt.network.NetworkManagementClient") as mock:
        mock_client = Mock()

        # Mock public IP creation
        mock_ip_poller = Mock()
        mock_ip_poller.result.return_value = Mock(
            id="/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/test-ip",
            ip_address="20.123.45.67",
        )
        mock_client.public_ip_addresses.begin_create_or_update.return_value = mock_ip_poller

        # Mock NIC creation
        mock_nic_poller = Mock()
        mock_nic_poller.result.return_value = Mock(
            id="/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/test-nic"
        )
        mock_client.network_interfaces.begin_create_or_update.return_value = mock_nic_poller

        mock.return_value = mock_client
        yield mock


@pytest.fixture
def mock_azure_resource_client():
    """Mock Azure ResourceManagementClient.

    Provides a fake Azure Resource client for testing resource
    group operations without making actual Azure API calls.
    """
    with patch("azure.mgmt.resource.ResourceManagementClient") as mock:
        mock_client = Mock()

        # Mock resource group creation
        mock_client.resource_groups.create_or_update.return_value = Mock(
            id="/subscriptions/sub-id/resourceGroups/azlin-rg", name="azlin-rg", location="eastus"
        )

        mock.return_value = mock_client
        yield mock


# ============================================================================
# SUBPROCESS MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.run for successful command execution.

    Returns successful result (returncode=0) for all subprocess calls.
    """
    with patch("subprocess.run") as mock:
        mock.return_value = Mock(returncode=0, stdout="success", stderr="")
        yield mock


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess.run for failed command execution.

    Returns failure result (returncode=1) for all subprocess calls.
    """
    with patch("subprocess.run") as mock:
        mock.return_value = Mock(returncode=1, stdout="", stderr="command failed")
        yield mock


# ============================================================================
# GITHUB CLI MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_gh_cli_authenticated():
    """Mock gh CLI as authenticated.

    Simulates gh CLI being installed and user authenticated.
    """
    with patch("subprocess.run") as mock:

        def gh_side_effect(cmd, *args, **kwargs):
            if isinstance(cmd, list) and "gh" in cmd[0]:
                if "auth" in cmd and "status" in cmd:
                    return Mock(
                        returncode=0, stdout="Logged in to github.com as testuser", stderr=""
                    )
                elif "repo" in cmd and "clone" in cmd:
                    return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stderr="command not found")

        mock.side_effect = gh_side_effect
        yield mock


@pytest.fixture
def mock_gh_cli_not_installed():
    """Mock gh CLI as not installed.

    Simulates gh CLI not being available in PATH.
    """
    with patch("shutil.which") as mock_which:

        def which_side_effect(cmd):
            if cmd == "gh":
                return None
            return f"/usr/bin/{cmd}"

        mock_which.side_effect = which_side_effect
        yield mock_which


# ============================================================================
# CONFIGURATION FIXTURES
# ============================================================================


@pytest.fixture
def sample_vm_config() -> dict[str, Any]:
    """Sample VM configuration for testing.

    Returns a valid VM configuration dictionary with all required fields.
    """
    return {
        "name": "test-vm",
        "size": "Standard_D2s_v3",
        "region": "eastus",
        "image": {
            "publisher": "Canonical",
            "offer": "0001-com-ubuntu-server-jammy",
            "sku": "22_04-lts",
            "version": "latest",
        },
        "admin_username": "azureuser",
        "resource_group": "azlin-rg",
    }


@pytest.fixture
def sample_azlin_config() -> dict[str, Any]:
    """Sample azlin configuration for testing.

    Returns a complete azlin configuration with all optional fields.
    """
    return {
        "vm": {"size": "Standard_D2s_v3", "region": "eastus", "image": "ubuntu-22.04"},
        "tools": ["git", "gh", "python3", "node", "docker", "tmux", "vim", "zsh", "fzf"],
        "ssh": {"key_path": "~/.ssh/azlin_rsa", "auto_connect": True},
        "tmux": {"session_name": "dev", "auto_attach": True},
        "github": {"auto_clone": True, "setup_gh_auth": True},
        "notifications": {"imessr_enabled": True},
    }


# ============================================================================
# PROGRESS DISPLAY FIXTURES
# ============================================================================


@pytest.fixture
def mock_progress_display():
    """Mock progress display to avoid output during tests.

    Captures progress display calls without printing to stdout.
    """
    with patch("azlin.progress.ProgressDisplay") as mock:
        mock_instance = Mock()
        mock_instance.start = Mock()
        mock_instance.update = Mock()
        mock_instance.complete = Mock()
        mock_instance.error = Mock()
        mock.return_value = mock_instance
        yield mock_instance


# ============================================================================
# SSH MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_ssh_keygen():
    """Mock SSH key generation.

    Simulates ssh-keygen command for testing SSH key creation.
    """
    with patch("subprocess.run") as mock:

        def keygen_side_effect(cmd, *args, **kwargs):
            if isinstance(cmd, list) and "ssh-keygen" in cmd[0]:
                # Create fake key files
                key_path = None
                for i, arg in enumerate(cmd):
                    if arg == "-f" and i + 1 < len(cmd):
                        key_path = Path(cmd[i + 1])
                        break

                if key_path:
                    key_path.write_text(
                        "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key\n-----END OPENSSH PRIVATE KEY-----"
                    )
                    key_path.with_suffix(".pub").write_text("ssh-rsa AAAAB...fake-key")

                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stderr="command not found")

        mock.side_effect = keygen_side_effect
        yield mock


@pytest.fixture
def mock_ssh_connection():
    """Mock SSH connection for testing auto-connect.

    Simulates successful SSH connection without making actual connection.
    """
    with patch("subprocess.run") as mock:

        def ssh_side_effect(cmd, *args, **kwargs):
            if isinstance(cmd, list) and "ssh" in cmd[0]:
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stderr="connection failed")

        mock.side_effect = ssh_side_effect
        yield mock


# ============================================================================
# NOTIFICATION MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_imessr_client():
    """Mock imessR client for testing notifications.

    Simulates imessR API calls without making actual HTTP requests.
    """
    with patch("requests.post") as mock:
        mock.return_value = Mock(status_code=200, json=lambda: {"success": True})
        yield mock


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def capture_subprocess_calls():
    """Fixture to capture all subprocess calls for verification.

    Returns a list that accumulates all subprocess.run calls made during test.
    """
    calls = []

    with patch("subprocess.run") as mock:

        def capture_call(cmd, *args, **kwargs):
            calls.append({"cmd": cmd, "kwargs": kwargs})
            return Mock(returncode=0, stdout="", stderr="")

        mock.side_effect = capture_call
        yield calls
