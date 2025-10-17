"""
Test utilities for azlin CLI tests.

This module provides helper functions and classes for
common test operations and assertions.
"""

from pathlib import Path
from typing import Any, Optional
from unittest.mock import Mock


class AzureResponseBuilder:
    """Builder for creating fake Azure API responses.

    This class provides a fluent interface for building
    Azure API response objects for testing.
    """

    @staticmethod
    def create_vm_response(
        name: str, location: str, vm_size: str, state: str = "Succeeded"
    ) -> Mock:
        """Create a mock VM response.

        Args:
            name: VM name
            location: Azure region
            vm_size: VM SKU
            state: Provisioning state

        Returns:
            Mock object representing Azure VM
        """
        return Mock(
            id=f"/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/{name}",
            name=name,
            location=location,
            hardware_profile=Mock(vm_size=vm_size),
            provisioning_state=state,
            os_profile=Mock(computer_name=name, admin_username="azureuser"),
            network_profile=Mock(
                network_interfaces=[
                    Mock(
                        id=f"/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/{name}-nic"
                    )
                ]
            ),
        )

    @staticmethod
    def create_public_ip_response(name: str, ip_address: str, location: str = "eastus") -> Mock:
        """Create a mock public IP response.

        Args:
            name: Public IP resource name
            ip_address: IP address
            location: Azure region

        Returns:
            Mock object representing Azure Public IP
        """
        return Mock(
            id=f"/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/{name}",
            name=name,
            location=location,
            ip_address=ip_address,
            provisioning_state="Succeeded",
        )

    @staticmethod
    def create_error_response(error_code: str, message: str) -> Exception:
        """Create a mock Azure error response.

        Args:
            error_code: Azure error code
            message: Error message

        Returns:
            Exception with Azure error format
        """
        error = Exception(message)
        error.error_code = error_code
        return error


class SubprocessCapture:
    """Capture subprocess calls for verification.

    This class records all subprocess calls and provides
    methods to verify they were called correctly.
    """

    def __init__(self):
        self.calls: list[list[str]] = []

    def capture(self, cmd: list[str], **kwargs) -> Mock:
        """Capture a subprocess call.

        Args:
            cmd: Command and arguments
            **kwargs: Additional subprocess.run arguments

        Returns:
            Mock result object
        """
        self.calls.append(cmd)
        return Mock(returncode=0, stdout="", stderr="")

    def assert_called_with_command(self, command: str):
        """Assert that a command was called.

        Args:
            command: Command string to check for

        Raises:
            AssertionError: If command not found
        """
        for call in self.calls:
            if command in " ".join(call):
                return
        raise AssertionError(f"Expected command '{command}' not found in {self.calls}")

    def get_all_calls_as_strings(self) -> list[str]:
        """Get all calls as command strings."""
        return [" ".join(call) for call in self.calls]


class ConfigBuilder:
    """Builder for creating test configuration dictionaries.

    Provides a fluent interface for building azlin configurations.
    """

    def __init__(self):
        self.config: dict[str, Any] = {
            "vm": {},
            "tools": [],
            "ssh": {},
            "github": {},
            "notifications": {},
        }

    def with_vm(
        self, size: str = "Standard_D2s_v3", region: str = "eastus", name: Optional[str] = None
    ) -> "ConfigBuilder":
        """Configure VM settings."""
        self.config["vm"]["size"] = size
        self.config["vm"]["region"] = region
        if name:
            self.config["vm"]["name"] = name
        return self

    def with_tools(self, tools: list[str]) -> "ConfigBuilder":
        """Configure tools to install."""
        self.config["tools"] = tools
        return self

    def with_ssh(
        self, auto_connect: bool = True, key_path: str = "~/.ssh/azlin_rsa"
    ) -> "ConfigBuilder":
        """Configure SSH settings."""
        self.config["ssh"]["auto_connect"] = auto_connect
        self.config["ssh"]["key_path"] = key_path
        return self

    def with_github(self, auto_clone: bool = True, setup_auth: bool = True) -> "ConfigBuilder":
        """Configure GitHub settings."""
        self.config["github"]["auto_clone"] = auto_clone
        self.config["github"]["setup_gh_auth"] = setup_auth
        return self

    def with_notifications(self, enabled: bool = True) -> "ConfigBuilder":
        """Configure notifications."""
        self.config["notifications"]["imessr_enabled"] = enabled
        return self

    def build(self) -> dict[str, Any]:
        """Build and return the configuration."""
        return self.config


class FileSystemHelper:
    """Helper for file system operations in tests."""

    @staticmethod
    def create_ssh_config_file(path: Path, content: str):
        """Create an SSH config file.

        Args:
            path: Path to config file
            content: Config file content
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    @staticmethod
    def create_ssh_key_pair(key_path: Path, key_type: str = "rsa"):
        """Create fake SSH key pair files.

        Args:
            key_path: Path to private key file
            key_type: Key type ('rsa' or 'ed25519')
        """
        key_path.parent.mkdir(parents=True, exist_ok=True)

        private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-private-key\n-----END OPENSSH PRIVATE KEY-----"
        public_key = f"ssh-{key_type} AAAAB3NzaC1...fake-public-key azureuser@azlin"

        key_path.write_text(private_key)
        key_path.chmod(0o600)

        public_key_path = key_path.with_suffix(".pub")
        public_key_path.write_text(public_key)

    @staticmethod
    def assert_file_exists(path: Path, message: Optional[str] = None):
        """Assert that a file exists.

        Args:
            path: Path to check
            message: Optional error message

        Raises:
            AssertionError: If file doesn't exist
        """
        if not path.exists():
            msg = message or f"Expected file does not exist: {path}"
            raise AssertionError(msg)

    @staticmethod
    def assert_file_contains(path: Path, text: str):
        """Assert that a file contains specific text.

        Args:
            path: Path to file
            text: Text to search for

        Raises:
            AssertionError: If text not found
        """
        if not path.exists():
            raise AssertionError(f"File does not exist: {path}")

        content = path.read_text()
        if text not in content:
            raise AssertionError(f"Expected text '{text}' not found in {path}\nContent:\n{content}")


class TestDataFactory:
    """Factory for creating test data.

    Provides standard test data objects for consistent testing.
    """

    @staticmethod
    def create_standard_tools() -> list[str]:
        """Create standard list of 9 development tools."""
        return ["git", "gh", "python3", "node", "docker", "tmux", "vim", "zsh", "fzf"]

    @staticmethod
    def create_vm_sizes() -> dict[str, dict[str, Any]]:
        """Create map of VM sizes and their specifications."""
        return {
            "Standard_D2s_v3": {"vcpus": 2, "memory_gb": 8},
            "Standard_D4s_v3": {"vcpus": 4, "memory_gb": 16},
            "Standard_D8s_v3": {"vcpus": 8, "memory_gb": 32},
            "Standard_B2s": {"vcpus": 2, "memory_gb": 4},
        }

    @staticmethod
    def create_azure_regions() -> list[str]:
        """Create list of valid Azure regions."""
        return [
            "eastus",
            "eastus2",
            "westus",
            "westus2",
            "centralus",
            "northcentralus",
            "southcentralus",
            "westcentralus",
        ]


# ============================================================================
# ASSERTION HELPERS
# ============================================================================


def assert_command_executed(
    subprocess_calls: list[list[str]], command: str, message: Optional[str] = None
):
    """Assert that a command was executed.

    Args:
        subprocess_calls: List of subprocess calls
        command: Command to search for
        message: Optional error message

    Raises:
        AssertionError: If command not found
    """
    for call in subprocess_calls:
        if command in " ".join(call):
            return

    msg = message or f"Expected command '{command}' was not executed"
    calls_str = "\n".join([" ".join(call) for call in subprocess_calls])
    raise AssertionError(f"{msg}\n\nActual calls:\n{calls_str}")


def assert_azure_resource_created(resource_client: Mock, resource_type: str, resource_name: str):
    """Assert that an Azure resource was created.

    Args:
        resource_client: Mocked Azure client
        resource_type: Type of resource (e.g., 'vm', 'public_ip')
        resource_name: Name of resource

    Raises:
        AssertionError: If resource was not created
    """
    if resource_type == "vm":
        client = resource_client.virtual_machines
        method = "begin_create_or_update"
    elif resource_type == "public_ip":
        client = resource_client.public_ip_addresses
        method = "begin_create_or_update"
    elif resource_type == "network_interface":
        client = resource_client.network_interfaces
        method = "begin_create_or_update"
    else:
        raise ValueError(f"Unknown resource type: {resource_type}")

    create_method = getattr(client, method)
    if not create_method.called:
        raise AssertionError(f"Azure {resource_type} '{resource_name}' was not created")


def assert_ssh_config_entry_exists(
    ssh_config_path: Path, host: str, hostname: Optional[str] = None
):
    """Assert that SSH config contains an entry for a host.

    Args:
        ssh_config_path: Path to SSH config file
        host: Host alias to check for
        hostname: Optional hostname/IP to verify

    Raises:
        AssertionError: If entry not found
    """
    if not ssh_config_path.exists():
        raise AssertionError(f"SSH config file does not exist: {ssh_config_path}")

    content = ssh_config_path.read_text()

    if f"Host {host}" not in content:
        raise AssertionError(
            f"SSH config does not contain entry for Host {host}\nContent:\n{content}"
        )

    if hostname and f"HostName {hostname}" not in content:
        raise AssertionError(
            f"SSH config entry for {host} does not specify HostName {hostname}\nContent:\n{content}"
        )
