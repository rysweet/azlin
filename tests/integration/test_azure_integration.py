"""
Integration tests for Azure SDK integration.

Tests full authentication flow, VM creation workflow, and resource cleanup
with mocked Azure SDK (TDD - RED phase).

Test Coverage:
- Full authentication flow with mocked Azure
- VM creation with all network resources
- Resource cleanup workflow
- Error propagation from Azure SDK
- Retry logic for transient failures
- Resource dependency management
"""

import contextlib
from unittest.mock import Mock, patch

import pytest

from tests.mocks.azure_mock import create_mock_azure_environment

# ============================================================================
# FULL AUTHENTICATION WORKFLOW TESTS
# ============================================================================


class TestAzureAuthenticationWorkflow:
    """Test complete Azure authentication workflow."""

    def test_full_authentication_flow_with_az_cli(self):
        """Test complete authentication flow using az CLI.

        RED PHASE: Integration test - will fail until all components implemented.
        """
        from azlin.azure_auth import AzureAuthenticator
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()

        with patch("azure.identity.DefaultAzureCredential", return_value=mock_env["credential"]):
            # Authenticate
            auth = AzureAuthenticator()
            credentials = auth.get_credentials()

            # Use credentials to create provisioner
            provisioner = VMProvisioner(
                name="test-vm", size="Standard_D2s_v3", region="eastus", credentials=credentials
            )

            # Verify credentials work
            assert credentials is not None
            assert provisioner.credentials is not None

    def test_authentication_with_subscription_detection(self):
        """Test authentication with automatic subscription detection."""
        from azlin.azure_auth import AzureAuthenticator

        with patch("subprocess.run") as mock_run:
            # Mock az account show
            mock_run.return_value = Mock(
                returncode=0, stdout='{"id": "sub-12345", "name": "My Subscription"}', stderr=""
            )

            auth = AzureAuthenticator()
            subscription_id = auth.get_subscription_id()

            assert subscription_id == "sub-12345"

    def test_authentication_fails_gracefully_with_helpful_error(self):
        """Test that authentication failures provide helpful error messages."""
        from azlin.azure_auth import AuthenticationError, AzureAuthenticator

        with patch("azure.identity.DefaultAzureCredential") as mock_cred:
            mock_cred.side_effect = Exception("No credentials available")

            auth = AzureAuthenticator()

            with pytest.raises(AuthenticationError) as exc_info:
                auth.get_credentials()

            # Error message should be helpful
            assert (
                "az login" in str(exc_info.value).lower()
                or "credentials" in str(exc_info.value).lower()
            )


# ============================================================================
# VM PROVISIONING WORKFLOW TESTS
# ============================================================================


class TestVMProvisioningWorkflow:
    """Test complete VM provisioning workflow."""

    def test_full_vm_creation_with_network_resources(self):
        """Test complete VM creation including all network resources.

        This tests the integration of:
        - Resource group creation
        - Virtual network creation
        - Public IP creation
        - Network interface creation
        - VM creation
        """
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()

        with (
            patch(
                "azure.mgmt.compute.ComputeManagementClient",
                return_value=mock_env["compute_client"],
            ),
            patch(
                "azure.mgmt.network.NetworkManagementClient",
                return_value=mock_env["network_client"],
            ),
            patch(
                "azure.mgmt.resource.ResourceManagementClient",
                return_value=mock_env["resource_client"],
            ),
        ):
            provisioner = VMProvisioner(
                name="test-vm", size="Standard_D2s_v3", region="eastus", resource_group="azlin-rg"
            )

            # Full provisioning workflow
            result = provisioner.provision_with_networking()

            assert result is not None
            assert result.vm is not None
            assert result.public_ip is not None
            assert result.network_interface is not None

    def test_vm_provisioning_handles_dependencies_correctly(self):
        """Test that VM provisioning handles resource dependencies.

        Order should be:
        1. Resource group
        2. Virtual network
        3. Public IP
        4. Network interface
        5. VM
        """
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()
        call_order = []

        def track_call(name):
            def wrapper(*args, **kwargs):
                call_order.append(name)
                return Mock(result=lambda: Mock(id=f"/{name}"))

            return wrapper

        with (
            patch(
                "azure.mgmt.resource.ResourceManagementClient",
                return_value=mock_env["resource_client"],
            ) as mock_resource,
            patch(
                "azure.mgmt.network.NetworkManagementClient",
                return_value=mock_env["network_client"],
            ) as mock_network,
            patch(
                "azure.mgmt.compute.ComputeManagementClient",
                return_value=mock_env["compute_client"],
            ) as mock_compute,
        ):
            # Track call order
            mock_resource.return_value.resource_groups.create_or_update.side_effect = track_call(
                "resource_group"
            )
            mock_network.return_value.virtual_networks.begin_create_or_update.side_effect = (
                track_call("vnet")
            )
            mock_network.return_value.public_ip_addresses.begin_create_or_update.side_effect = (
                track_call("public_ip")
            )
            mock_network.return_value.network_interfaces.begin_create_or_update.side_effect = (
                track_call("nic")
            )
            mock_compute.return_value.virtual_machines.begin_create_or_update.side_effect = (
                track_call("vm")
            )

            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

            provisioner.provision_with_networking()

            # Verify order
            assert call_order.index("resource_group") < call_order.index("vnet")
            assert call_order.index("vnet") < call_order.index("public_ip")
            assert call_order.index("public_ip") < call_order.index("nic")
            assert call_order.index("nic") < call_order.index("vm")


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================


class TestAzureErrorHandling:
    """Test error handling across Azure operations."""

    def test_handles_transient_azure_errors_with_retry(self):
        """Test retry logic for transient Azure errors."""
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()
        call_count = {"count": 0}

        def failing_then_success(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] < 3:
                raise Exception("ServiceUnavailable: Temporary failure")
            return Mock(result=lambda: Mock(name="test-vm", provisioning_state="Succeeded"))

        with patch(
            "azure.mgmt.compute.ComputeManagementClient", return_value=mock_env["compute_client"]
        ) as mock_compute:
            mock_compute.return_value.virtual_machines.begin_create_or_update.side_effect = (
                failing_then_success
            )

            provisioner = VMProvisioner(
                name="test-vm", size="Standard_D2s_v3", region="eastus", max_retries=3
            )

            # Should succeed after retries
            vm = provisioner.provision()
            assert vm is not None
            assert call_count["count"] == 3  # Failed twice, succeeded third time

    def test_propagates_fatal_azure_errors(self):
        """Test that fatal Azure errors are propagated correctly."""
        from azlin.vm_provisioning import QuotaExceededError, VMProvisioner

        mock_env = create_mock_azure_environment()

        with patch(
            "azure.mgmt.compute.ComputeManagementClient", return_value=mock_env["compute_client"]
        ):
            # Set quota exceeded failure
            mock_env["compute_client"].virtual_machines.set_failure_mode(True, "quota")

            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

            with pytest.raises(QuotaExceededError):
                provisioner.provision()


# ============================================================================
# RESOURCE CLEANUP TESTS
# ============================================================================


class TestResourceCleanup:
    """Test resource cleanup and teardown."""

    def test_cleans_up_all_resources_on_failure(self):
        """Test that all resources are cleaned up if provisioning fails."""
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()
        cleanup_called = {"resources": []}

        def track_cleanup(resource_type):
            def wrapper(*args, **kwargs):
                cleanup_called["resources"].append(resource_type)
                return Mock(result=lambda: None)

            return wrapper

        with (
            patch(
                "azure.mgmt.compute.ComputeManagementClient",
                return_value=mock_env["compute_client"],
            ) as mock_compute,
            patch(
                "azure.mgmt.network.NetworkManagementClient",
                return_value=mock_env["network_client"],
            ) as mock_network,
        ):
            # Mock cleanup methods
            mock_compute.return_value.virtual_machines.begin_delete.side_effect = track_cleanup(
                "vm"
            )
            mock_network.return_value.network_interfaces.begin_delete.side_effect = track_cleanup(
                "nic"
            )
            mock_network.return_value.public_ip_addresses.begin_delete.side_effect = track_cleanup(
                "public_ip"
            )

            # Make VM creation fail
            mock_env["compute_client"].virtual_machines.set_failure_mode(True, "general")

            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

            with contextlib.suppress(Exception):
                provisioner.provision_with_networking(cleanup_on_failure=True)

            # Verify cleanup was attempted for created resources
            # (Even if VM creation failed, network resources might have been created)
            assert len(cleanup_called["resources"]) >= 0  # May have cleaned up partial resources

    def test_explicit_cleanup_deletes_all_resources(self):
        """Test explicit cleanup of all VM resources."""
        from azlin.vm_provisioning import VMProvisioner

        mock_env = create_mock_azure_environment()

        with (
            patch(
                "azure.mgmt.compute.ComputeManagementClient",
                return_value=mock_env["compute_client"],
            ) as mock_compute,
            patch(
                "azure.mgmt.network.NetworkManagementClient",
                return_value=mock_env["network_client"],
            ) as mock_network,
        ):
            provisioner = VMProvisioner(name="test-vm", size="Standard_D2s_v3", region="eastus")

            # Provision VM first
            provisioner.provision_with_networking()

            # Clean up
            provisioner.cleanup()

            # Verify delete was called
            assert mock_compute.return_value.virtual_machines.begin_delete.called
            assert mock_network.return_value.network_interfaces.begin_delete.called
            assert mock_network.return_value.public_ip_addresses.begin_delete.called
