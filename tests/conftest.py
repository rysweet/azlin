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
            token="fake-azure-token-12345",  # noqa: S106 - test fixture, not a real credential
            expires_on=9999999999,
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
                if "repo" in cmd and "clone" in cmd:
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
# CLI TEST HELPERS (PR #191 Feedback)
# ============================================================================


def assert_option_accepted(result):
    """Assert that a CLI option was accepted (no syntax error).

    This helper replaces repeated assertions like:
        assert "no such option" not in result.output.lower()

    Args:
        result: Click CliRunner result object
    """
    assert "no such option" not in result.output.lower(), (
        f"Option should be accepted, but got error: {result.output}"
    )


def assert_option_rejected(result, option_name: str):
    """Assert that a CLI option was rejected with clear error.

    This helper validates both exit code and error message.

    Args:
        result: Click CliRunner result object
        option_name: The option that should be rejected (e.g., '--invalid')
    """
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for invalid option {option_name}, "
        f"but got exit_code={result.exit_code}"
    )
    assert "no such option" in result.output.lower(), (
        f"Expected 'no such option' error for {option_name}, "
        f"but got: {result.output}"
    )


def assert_command_succeeds(result):
    """Assert that a command executed successfully (exit code 0).

    Args:
        result: Click CliRunner result object
    """
    assert result.exit_code == 0, (
        f"Expected successful execution (exit_code=0), "
        f"but got exit_code={result.exit_code}: {result.output}"
    )


def assert_command_fails(result, expected_error: str = None):
    """Assert that a command failed with non-zero exit code.

    Args:
        result: Click CliRunner result object
        expected_error: Optional substring to look for in error output
    """
    assert result.exit_code != 0, (
        f"Expected command to fail (non-zero exit code), "
        f"but got exit_code=0: {result.output}"
    )

    if expected_error:
        assert expected_error.lower() in result.output.lower(), (
            f"Expected error containing '{expected_error}', "
            f"but got: {result.output}"
        )


def assert_missing_argument_error(result):
    """Assert that command failed due to missing required argument.

    Args:
        result: Click CliRunner result object
    """
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for missing argument, "
        f"but got exit_code={result.exit_code}"
    )
    assert "missing argument" in result.output.lower() or "usage:" in result.output.lower(), (
        f"Expected 'missing argument' or 'usage' error, but got: {result.output}"
    )


def assert_unexpected_argument_error(result):
    """Assert that command failed due to unexpected positional argument.

    Args:
        result: Click CliRunner result object
    """
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for unexpected argument, "
        f"but got exit_code={result.exit_code}"
    )
    assert (
        "got unexpected extra argument" in result.output.lower()
        or "unexpected" in result.output.lower()
    ), f"Expected 'unexpected argument' error, but got: {result.output}"


def assert_invalid_value_error(result, value_type: str = None):
    """Assert that command failed due to invalid option value.

    Args:
        result: Click CliRunner result object
        value_type: Optional type description (e.g., 'integer')
    """
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for invalid value, "
        f"but got exit_code={result.exit_code}"
    )

    error_indicators = ["invalid", "error"]
    if value_type:
        error_indicators.append(value_type.lower())

    has_error = any(indicator in result.output.lower() for indicator in error_indicators)
    assert has_error, (
        f"Expected error containing {error_indicators}, but got: {result.output}"
    )


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def cli_runner():
    """Provide a Click CliRunner for testing CLI commands.

    Returns:
        CliRunner: Configured Click test runner

    Usage:
        def test_command(cli_runner):
            result = cli_runner.invoke(main, ["command", "args"])
            assert_command_succeeds(result)
    """
    from click.testing import CliRunner

    return CliRunner()


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


# ============================================================================
# AZDOIT ENHANCEMENT FIXTURES (PR #156 Enhancements)
# ============================================================================


@pytest.fixture
def temp_objectives_dir(temp_config_dir):
    """Create temporary objectives directory for state persistence."""
    objectives_dir = temp_config_dir / "objectives"
    objectives_dir.mkdir()
    return objectives_dir


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for Claude API calls."""
    import json

    mock_client = Mock()
    mock_message = Mock()
    mock_content = Mock()
    mock_content.text = json.dumps(
        {
            "intent": "provision_vm",
            "parameters": {"vm_name": "test-vm"},
            "confidence": 0.95,
            "azlin_commands": [{"command": "azlin new", "args": ["--name", "test-vm"]}],
        }
    )
    mock_message.content = [mock_content]
    mock_client.messages.create.return_value = mock_message
    return mock_client


# Azure MCP Server Fixtures
@pytest.fixture
def mock_mcp_server():
    """Mock Azure MCP Server client."""
    mock = Mock()
    mock.connect.return_value = True
    mock.is_connected.return_value = True
    mock.list_tools.return_value = [
        {"name": "azure_vm_create", "description": "Create Azure VM"},
        {"name": "azure_storage_create", "description": "Create storage account"},
    ]
    return mock


@pytest.fixture
def mcp_tool_response():
    """Sample MCP tool response."""
    return {
        "success": True,
        "result": {
            "resource_id": "/subscriptions/test/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            "status": "Succeeded",
        },
        "cost_estimate": 0.12,
    }


# Cost Estimation Fixtures
@pytest.fixture
def mock_azure_pricing_api():
    """Mock Azure Pricing API responses."""
    mock = Mock()
    mock.get_vm_pricing.return_value = {
        "Standard_D2s_v3": {"hourly": 0.096, "monthly": 70.08},
        "Standard_D4s_v3": {"hourly": 0.192, "monthly": 140.16},
    }
    mock.get_storage_pricing.return_value = {
        "Standard_LRS": {"per_gb_month": 0.0184},
        "Premium_LRS": {"per_gb_month": 0.135},
    }
    return mock


@pytest.fixture
def sample_cost_estimate():
    """Sample cost estimate structure."""
    return {
        "objective_id": "obj_123",
        "estimated_cost": 150.00,
        "confidence": 0.85,
        "breakdown": {
            "compute": 70.08,
            "storage": 18.40,
            "network": 5.00,
            "other": 56.52,
        },
        "resources": [
            {
                "type": "vm",
                "name": "test-vm",
                "size": "Standard_D2s_v3",
                "estimated_monthly": 70.08,
            },
            {
                "type": "storage",
                "name": "test-storage",
                "size_gb": 1000,
                "tier": "Standard_LRS",
                "estimated_monthly": 18.40,
            },
        ],
    }


# State Persistence Fixtures
@pytest.fixture
def sample_objective_state():
    """Sample objective state for testing."""
    return {
        "id": "obj_20251020_001",
        "natural_language": "Create an AKS cluster with 3 nodes",
        "parsed_intent": {
            "intent": "provision_aks",
            "parameters": {
                "cluster_name": "test-aks",
                "node_count": 3,
                "node_size": "Standard_D2s_v3",
            },
            "confidence": 0.92,
        },
        "selected_strategy": "terraform",
        "status": "in_progress",
        "created_at": "2025-10-20T12:00:00Z",
        "updated_at": "2025-10-20T12:05:00Z",
        "execution_history": [
            {
                "timestamp": "2025-10-20T12:01:00Z",
                "action": "strategy_selected",
                "details": {"strategy": "terraform"},
            },
            {
                "timestamp": "2025-10-20T12:02:00Z",
                "action": "terraform_generated",
                "details": {"file": "aks_cluster.tf"},
            },
        ],
        "cost_estimate": 210.24,
        "retry_count": 0,
        "max_retries": 5,
    }


# Terraform Fixtures
@pytest.fixture
def sample_terraform_config():
    """Sample Terraform configuration."""
    return """
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "main" {
  name     = "rg-test"
  location = "eastus"
}

resource "azurerm_kubernetes_cluster" "aks" {
  name                = "test-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "testaks"

  default_node_pool {
    name       = "default"
    node_count = 3
    vm_size    = "Standard_D2s_v3"
  }

  identity {
    type = "SystemAssigned"
  }
}
"""


@pytest.fixture
def mock_terraform_executor():
    """Mock Terraform command executor."""
    mock = Mock()
    mock.validate.return_value = {"valid": True, "error_count": 0}
    mock.plan.return_value = {
        "changes": {"add": 2, "change": 0, "remove": 0},
        "resources": ["azurerm_resource_group.main", "azurerm_kubernetes_cluster.aks"],
    }
    mock.apply.return_value = {"success": True, "outputs": {}}
    return mock


# Strategy Selector Fixtures
@pytest.fixture
def sample_objectives_for_strategy():
    """Sample objectives for strategy selection testing."""
    return {
        "simple_vm": {
            "intent": "provision_vm",
            "parameters": {"vm_name": "simple-vm", "size": "Standard_B2s"},
            "complexity": "simple",
        },
        "aks_cluster": {
            "intent": "provision_aks",
            "parameters": {"cluster_name": "my-aks", "node_count": 5},
            "complexity": "complex",
        },
        "custom_network": {
            "intent": "configure_advanced_network",
            "parameters": {"vnet_count": 3, "peering": True},
            "complexity": "very_complex",
        },
        "query_state": {
            "intent": "get_vm_metrics",
            "parameters": {"vm_name": "test-vm", "metrics": ["cpu", "memory"]},
            "complexity": "query",
        },
    }


# MS Learn Fixtures
@pytest.fixture
def mock_mslearn_client():
    """Mock MS Learn documentation client."""
    mock = Mock()
    mock.search.return_value = [
        {
            "title": "Quickstart: Create an AKS cluster",
            "url": "https://learn.microsoft.com/azure/aks/quickstart",
            "relevance": 0.95,
        },
        {
            "title": "Tutorial: Deploy an application to AKS",
            "url": "https://learn.microsoft.com/azure/aks/tutorial-kubernetes-deploy-application",
            "relevance": 0.88,
        },
    ]
    return mock


# Failure Recovery Fixtures
@pytest.fixture
def sample_failure_scenarios():
    """Sample failure scenarios for testing recovery."""
    return {
        "quota_exceeded": {
            "error": "QuotaExceeded: Regional vCPU quota exceeded",
            "error_code": "QuotaExceeded",
            "is_recoverable": True,
            "suggested_action": "research_alternative_region",
        },
        "invalid_parameter": {
            "error": "InvalidParameter: VM size not available in region",
            "error_code": "InvalidParameter",
            "is_recoverable": True,
            "suggested_action": "research_available_sizes",
        },
        "authentication_failed": {
            "error": "AuthenticationFailed: Invalid credentials",
            "error_code": "AuthenticationFailed",
            "is_recoverable": False,
            "suggested_action": "prompt_user_reauth",
        },
        "timeout": {
            "error": "OperationTimeout: Deployment timed out after 30 minutes",
            "error_code": "OperationTimeout",
            "is_recoverable": True,
            "suggested_action": "retry_with_backoff",
        },
    }


# Auto Mode Integration Fixtures
@pytest.fixture
def mock_auto_mode_hooks():
    """Mock auto mode integration hooks."""
    mock = Mock()
    mock.on_objective_start.return_value = None
    mock.on_strategy_selected.return_value = None
    mock.on_execution_complete.return_value = None
    mock.on_failure.return_value = None
    return mock


# ============================================================================
# SERVICE PRINCIPAL AUTHENTICATION FIXTURES (Issue #177)
# ============================================================================


@pytest.fixture
def sample_sp_config_dict():
    """Sample service principal configuration dictionary."""
    return {
        "client_id": "12345678-1234-1234-1234-123456789012",
        "tenant_id": "87654321-4321-4321-4321-210987654321",
        "subscription_id": "abcdef00-0000-0000-0000-000000abcdef",
        "auth_method": "client_secret",
    }


@pytest.fixture
def sample_sp_config_with_certificate_dict(tmp_path):
    """Sample service principal configuration with certificate."""
    cert_file = tmp_path / "test-cert.pem"
    cert_file.write_text(
        "-----BEGIN CERTIFICATE-----\nfake-cert-content\n-----END CERTIFICATE-----"
    )
    cert_file.chmod(0o600)

    return {
        "client_id": "12345678-1234-1234-1234-123456789012",
        "tenant_id": "87654321-4321-4321-4321-210987654321",
        "subscription_id": "abcdef00-0000-0000-0000-000000abcdef",
        "auth_method": "certificate",
        "certificate_path": str(cert_file),
    }


@pytest.fixture
def temp_sp_config_file(tmp_path):
    """Create temporary service principal config file."""
    config_file = tmp_path / "sp-config.toml"
    config_file.write_text(
        """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"

# Secrets should be stored in environment variables
# Set AZLIN_SP_CLIENT_SECRET environment variable
"""
    )
    config_file.chmod(0o600)
    return config_file


@pytest.fixture
def temp_sp_config_with_cert(tmp_path):
    """Create temporary SP config file with certificate."""
    # Create certificate file
    cert_file = tmp_path / "cert.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake-cert\n-----END CERTIFICATE-----")
    cert_file.chmod(0o600)

    # Create config file
    config_file = tmp_path / "sp-config-cert.toml"
    config_file.write_text(
        f"""
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "{cert_file}"
"""
    )
    config_file.chmod(0o600)

    return {"config_file": config_file, "cert_file": cert_file}


@pytest.fixture
def mock_sp_credentials():
    """Mock service principal credentials dictionary."""
    return {
        "AZURE_CLIENT_ID": "12345678-1234-1234-1234-123456789012",
        "AZURE_CLIENT_SECRET": "mock-secret-value",
        "AZURE_TENANT_ID": "87654321-4321-4321-4321-210987654321",
        "AZURE_SUBSCRIPTION_ID": "abcdef00-0000-0000-0000-000000abcdef",
    }


@pytest.fixture
def mock_sp_certificate_credentials(tmp_path):
    """Mock service principal credentials with certificate."""
    cert_file = tmp_path / "mock-cert.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\nmock\n-----END CERTIFICATE-----")
    cert_file.chmod(0o600)

    return {
        "AZURE_CLIENT_ID": "12345678-1234-1234-1234-123456789012",
        "AZURE_CLIENT_CERTIFICATE_PATH": str(cert_file),
        "AZURE_TENANT_ID": "87654321-4321-4321-4321-210987654321",
        "AZURE_SUBSCRIPTION_ID": "abcdef00-0000-0000-0000-000000abcdef",
    }


@pytest.fixture
def mock_sp_env_vars(monkeypatch):
    """Mock service principal environment variables."""
    monkeypatch.setenv("AZURE_CLIENT_ID", "12345678-1234-1234-1234-123456789012")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-secret-value")
    monkeypatch.setenv("AZURE_TENANT_ID", "87654321-4321-4321-4321-210987654321")
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "abcdef00-0000-0000-0000-000000abcdef")


@pytest.fixture
def mock_azlin_sp_secret_env_var(monkeypatch):
    """Mock AZLIN_SP_CLIENT_SECRET environment variable."""
    monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "azlin-test-secret")


@pytest.fixture
def clean_sp_environment(monkeypatch):
    """Clean service principal environment variables."""
    sp_env_vars = [
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_CLIENT_CERTIFICATE_PATH",
        "AZLIN_SP_CLIENT_SECRET",
    ]
    for var in sp_env_vars:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def mock_certificate_file(tmp_path):
    """Create mock certificate file with proper formatting."""
    cert_file = tmp_path / "test-cert.pem"
    cert_content = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRKKzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX
aWRnaXRzIFB0eSBMdGQwHhcNMTkwNzA4MDAwMDAwWhcNMjkwNzA1MDAwMDAwWjBF
MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50
ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB
-----END CERTIFICATE-----"""
    cert_file.write_text(cert_content)
    cert_file.chmod(0o600)
    return cert_file


@pytest.fixture
def mock_expired_certificate_file(tmp_path):
    """Create mock expired certificate file."""
    cert_file = tmp_path / "expired-cert.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\nexpired\n-----END CERTIFICATE-----")
    cert_file.chmod(0o600)
    return cert_file


@pytest.fixture
def mock_insecure_certificate_file(tmp_path):
    """Create certificate file with insecure permissions."""
    cert_file = tmp_path / "insecure-cert.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\ninsecure\n-----END CERTIFICATE-----")
    cert_file.chmod(0o644)  # Insecure permissions
    return cert_file


@pytest.fixture
def mock_certificate_expiration_check():
    """Mock certificate expiration checking."""
    from datetime import datetime, timedelta

    with patch(
        "azlin.service_principal_auth.ServicePrincipalManager._get_certificate_expiration"
    ) as mock:
        # Default: certificate expires in 90 days (safe)
        mock.return_value = datetime.now() + timedelta(days=90)
        yield mock


@pytest.fixture
def sample_sp_config_toml_content():
    """Sample TOML content for SP configuration."""
    return """
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "client_secret"

# Security: Client secret must be stored in environment variable
# Set AZLIN_SP_CLIENT_SECRET before running azlin commands
# Example: export AZLIN_SP_CLIENT_SECRET="your-secret-here"
"""


@pytest.fixture
def sample_sp_config_cert_toml_content(tmp_path):
    """Sample TOML content for SP configuration with certificate."""
    cert_file = tmp_path / "cert.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
    cert_file.chmod(0o600)

    return f"""
[service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
subscription_id = "abcdef00-0000-0000-0000-000000abcdef"
auth_method = "certificate"
certificate_path = "{cert_file}"
"""


@pytest.fixture
def mock_azure_sp_authentication():
    """Mock Azure service principal authentication flow."""
    with patch("subprocess.run") as mock_run:
        # Mock successful az login with service principal
        def sp_auth_side_effect(cmd, *args, **kwargs):
            if "az" in cmd and "login" in cmd and "--service-principal" in cmd:
                return Mock(returncode=0, stdout="Login successful", stderr="")
            if "az" in cmd and "account" in cmd and "show" in cmd:
                return Mock(
                    returncode=0,
                    stdout='{"id": "abcdef00-0000-0000-0000-000000abcdef", "tenantId": "87654321-4321-4321-4321-210987654321"}',
                    stderr="",
                )
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = sp_auth_side_effect
        yield mock_run


@pytest.fixture
def mock_sp_credential_validation():
    """Mock service principal credential validation."""
    with patch("azlin.service_principal_auth.ServicePrincipalManager.validate_config") as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def capture_sp_logs(caplog):
    """Capture service principal related logs."""
    import logging

    caplog.set_level(logging.DEBUG)
    return caplog
