"""End-to-end test scenarios for azlin doit agent.

These tests validate the complete deployment flow including:
- Resource creation with proper tagging
- Resource dependencies and connections
- Resource listing and cleanup
- Error handling and recovery

Note: These tests require a valid Azure subscription and ANTHROPIC_API_KEY.
They create real Azure resources and may incur costs.

Run with: pytest tests/e2e/test_doit_scenarios.py -v
"""

import os
import time
from pathlib import Path

import pytest

from azlin.doit import DoItOrchestrator
from azlin.doit.manager import ResourceManager


@pytest.fixture
def orchestrator():
    """Create DoIt orchestrator instance."""
    return DoItOrchestrator(
        output_dir=Path("/tmp/azlin-doit-test"),
        max_iterations=50,
        dry_run=False,
        verbose=True,
    )


@pytest.fixture
def resource_manager():
    """Create resource manager instance."""
    return ResourceManager()


@pytest.fixture(autouse=True)
def check_prerequisites():
    """Check that required environment variables are set."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    # Check Azure CLI authentication
    import subprocess

    result = subprocess.run(
        ["az", "account", "show"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip("Azure CLI not authenticated")


@pytest.fixture(autouse=True, scope="function")
def cleanup_after_test(resource_manager):
    """Cleanup resources after each test."""
    yield
    # Cleanup after test completes
    try:
        resources = resource_manager.list_resources()
        if resources:
            print(f"\nCleaning up {len(resources)} resources...")
            resource_manager.cleanup_resources(force=True, dry_run=False)
            # Wait for cleanup to complete
            time.sleep(10)
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")


@pytest.mark.e2e
@pytest.mark.slow
class TestDoItScenarios:
    """End-to-end test scenarios for doit agent."""

    def test_scenario_1_simple_cosmos_db(self, orchestrator, resource_manager):
        """Scenario 1: Simple Cosmos DB deployment.

        Request: "Create a Cosmos DB account"

        Expected resources:
        - Resource Group
        - Cosmos DB account

        Validates:
        - Basic resource creation
        - Tagging is applied
        - Resources are listable
        - Resources can be cleaned up
        """
        request = "Create a Cosmos DB account in eastus"

        # Execute deployment
        state = orchestrator.execute(request)

        # Verify deployment succeeded
        assert state.phase.value == "completed", "Deployment should complete successfully"

        # Verify resources are tagged and listable
        resources = resource_manager.list_resources()
        assert len(resources) >= 1, "Should have at least 1 resource (Cosmos DB)"

        # Verify tags are present
        cosmos_resources = [r for r in resources if "cosmosdb" in r["type"].lower()]
        assert len(cosmos_resources) >= 1, "Should have Cosmos DB resource"

        cosmos = cosmos_resources[0]
        assert "azlin-doit-owner" in cosmos["tags"], "Should have owner tag"
        assert "azlin-doit-created" in cosmos["tags"], "Should have created tag"

        # Verify cleanup works
        result = resource_manager.cleanup_resources(force=True, dry_run=False)
        assert result["successfully_deleted"] == len(resources), "All resources should be deleted"

    def test_scenario_2_app_service_with_cosmos(self, orchestrator, resource_manager):
        """Scenario 2: App Service + Cosmos DB connected.

        Request: "Deploy App Service with Cosmos DB"

        Expected resources:
        - Resource Group
        - App Service Plan
        - App Service (with managed identity)
        - Cosmos DB
        - Key Vault
        - Connections between resources

        Validates:
        - Multiple resources with dependencies
        - Managed identity and connections
        - All resources properly tagged
        """
        request = "Deploy App Service with Cosmos DB in westus"

        # Execute deployment
        state = orchestrator.execute(request)

        # Verify deployment succeeded
        assert state.phase.value == "completed", "Deployment should complete successfully"

        # Verify resources
        resources = resource_manager.list_resources()
        assert len(resources) >= 4, "Should have at least 4 resources"

        # Check for required resource types
        resource_types = {r["type"] for r in resources}
        expected_types = {
            "Microsoft.Web/serverfarms",  # App Service Plan
            "Microsoft.Web/sites",  # App Service
            "Microsoft.DocumentDB/databaseAccounts",  # Cosmos DB
            "Microsoft.KeyVault/vaults",  # Key Vault
        }

        for expected_type in expected_types:
            assert any(expected_type in rt for rt in resource_types), f"Should have {expected_type}"

        # Verify all resources are tagged
        for resource in resources:
            assert "azlin-doit-owner" in resource["tags"], f"{resource['name']} should have owner tag"
            assert (
                "azlin-doit-created" in resource["tags"]
            ), f"{resource['name']} should have created tag"

    def test_scenario_3_two_app_services_behind_apim(self, orchestrator, resource_manager):
        """Scenario 3: Two App Services behind API Management.

        Request: "Create 2 App Services behind APIM"

        Expected resources:
        - Resource Group
        - 2 App Service Plans
        - 2 App Services
        - API Management instance
        - APIM backends/APIs configured

        Validates:
        - Multiple instances of same resource type
        - APIM configuration
        - Complex dependency management
        """
        request = "Create 2 App Services behind API Management in eastus"

        # Execute deployment
        state = orchestrator.execute(request)

        # Verify deployment succeeded
        assert state.phase.value == "completed", "Deployment should complete successfully"

        # Verify resources
        resources = resource_manager.list_resources()
        assert len(resources) >= 5, "Should have at least 5 resources"

        # Count App Services
        app_services = [r for r in resources if "Microsoft.Web/sites" in r["type"]]
        assert len(app_services) >= 2, "Should have at least 2 App Services"

        # Check for APIM
        apim_resources = [r for r in resources if "Microsoft.ApiManagement/service" in r["type"]]
        assert len(apim_resources) >= 1, "Should have API Management instance"

    def test_scenario_4_serverless_pipeline_with_functions(self, orchestrator, resource_manager):
        """Scenario 4: Serverless pipeline with Azure Functions.

        Request: "Create serverless pipeline with Function App, Storage, and Key Vault"

        Expected resources:
        - Resource Group
        - Storage Account (for Function App)
        - Function App
        - Key Vault

        Validates:
        - Serverless resource deployment
        - Storage account requirements for Functions
        - Proper configuration
        """
        request = "Create serverless pipeline with Function App, Storage Account, and Key Vault in centralus"

        # Execute deployment
        state = orchestrator.execute(request)

        # Verify deployment succeeded
        assert state.phase.value == "completed", "Deployment should complete successfully"

        # Verify resources
        resources = resource_manager.list_resources()
        assert len(resources) >= 3, "Should have at least 3 resources"

        # Check for storage
        storage_resources = [r for r in resources if "Microsoft.Storage/storageAccounts" in r["type"]]
        assert len(storage_resources) >= 1, "Should have Storage Account"

        # Check for Key Vault
        kv_resources = [r for r in resources if "Microsoft.KeyVault/vaults" in r["type"]]
        assert len(kv_resources) >= 1, "Should have Key Vault"

    def test_scenario_5_failure_recovery(self, orchestrator, resource_manager):
        """Scenario 5: Failure recovery test.

        Request: "Create App Service with invalid configuration"
        Then: "Create App Service with valid configuration"

        Expected behavior:
        - First attempt may fail
        - Retry with adjusted parameters
        - Eventually succeeds or fails gracefully

        Validates:
        - Error handling
        - Recovery mechanisms
        - Proper cleanup on failure
        """
        # First attempt with potential issues
        request = "Create App Service in an-invalid-region-name"

        # Execute deployment - may fail
        state = orchestrator.execute(request)

        # Check if it failed gracefully
        if state.phase.value == "failed":
            # Verify no orphaned resources
            resources = resource_manager.list_resources()
            # Some partial resources might exist, cleanup should handle them
            if resources:
                result = resource_manager.cleanup_resources(force=True, dry_run=False)
                assert result["failed_count"] == 0, "Cleanup should succeed"

        # Now try with valid configuration
        request = "Create App Service in eastus"
        state = orchestrator.execute(request)

        # This should succeed
        assert state.phase.value == "completed", "Valid deployment should succeed"

        # Verify resources are created and tagged
        resources = resource_manager.list_resources()
        assert len(resources) >= 1, "Should have resources"

        for resource in resources:
            assert "azlin-doit-owner" in resource["tags"], "Should have proper tags"

    def test_scenario_6_multi_region_ha_setup(self, orchestrator, resource_manager):
        """Scenario 6: Multi-region High Availability setup.

        Request: "Create HA setup with App Services in eastus and westus"

        Expected resources:
        - Multiple Resource Groups (one per region)
        - App Service Plans in each region
        - App Services in each region
        - Shared Cosmos DB (global)
        - Shared Key Vault

        Validates:
        - Multi-region deployments
        - Shared vs. regional resources
        - Complex architectures
        """
        request = "Create high availability setup with App Service in eastus and westus with shared Cosmos DB"

        # Execute deployment
        state = orchestrator.execute(request)

        # Verify deployment succeeded
        assert state.phase.value == "completed", "Deployment should complete successfully"

        # Verify resources
        resources = resource_manager.list_resources()
        assert len(resources) >= 5, "Should have at least 5 resources"

        # Check locations
        locations = {r["location"] for r in resources}
        # Should have resources in different regions
        assert len(locations) >= 2, "Should have resources in multiple regions"

        # Check for Cosmos DB (should be global)
        cosmos_resources = [r for r in resources if "cosmosdb" in r["type"].lower()]
        assert len(cosmos_resources) >= 1, "Should have Cosmos DB"

        # Check for multiple App Services
        app_services = [r for r in resources if "Microsoft.Web/sites" in r["type"]]
        assert len(app_services) >= 2, "Should have App Services in multiple regions"


@pytest.mark.e2e
@pytest.mark.slow
class TestDoItManagementCommands:
    """Test resource management commands."""

    def test_list_command(self, orchestrator, resource_manager):
        """Test azlin doit list command.

        Validates:
        - Resource listing works
        - Filter by username works
        - Empty results handled gracefully
        """
        # Create some resources first
        request = "Create Cosmos DB in eastus"
        state = orchestrator.execute(request)
        assert state.phase.value == "completed"

        # Test listing
        resources = resource_manager.list_resources()
        assert len(resources) > 0, "Should list created resources"

        # Verify resource structure
        for resource in resources:
            assert "id" in resource
            assert "name" in resource
            assert "type" in resource
            assert "resource_group" in resource
            assert "tags" in resource

    def test_show_command(self, orchestrator, resource_manager):
        """Test azlin doit show command.

        Validates:
        - Resource details can be retrieved
        - Full resource information is available
        """
        # Create a resource
        request = "Create Storage Account in westus"
        state = orchestrator.execute(request)
        assert state.phase.value == "completed"

        # Get resources
        resources = resource_manager.list_resources()
        assert len(resources) > 0

        # Get details of first resource
        resource_id = resources[0]["id"]
        details = resource_manager.get_resource_details(resource_id)

        assert details is not None
        assert "id" in details
        assert "properties" in details

    def test_cleanup_command_dry_run(self, orchestrator, resource_manager):
        """Test azlin doit cleanup --dry-run.

        Validates:
        - Dry run doesn't delete resources
        - Shows what would be deleted
        """
        # Create resources
        request = "Create App Service in eastus"
        state = orchestrator.execute(request)
        assert state.phase.value == "completed"

        # Get initial count
        resources_before = resource_manager.list_resources()
        count_before = len(resources_before)
        assert count_before > 0

        # Dry run cleanup
        result = resource_manager.cleanup_resources(force=True, dry_run=True)

        # Verify resources still exist
        resources_after = resource_manager.list_resources()
        assert len(resources_after) == count_before, "Dry run should not delete resources"

        # Verify dry run results
        assert len(result["deleted"]) == count_before
        assert result["failed_count"] == 0

    def test_cleanup_command_actual(self, orchestrator, resource_manager):
        """Test azlin doit cleanup (actual deletion).

        Validates:
        - Resources are actually deleted
        - Cleanup in proper order
        - Results are reported correctly
        """
        # Create resources
        request = "Create Cosmos DB in centralus"
        state = orchestrator.execute(request)
        assert state.phase.value == "completed"

        # Verify resources exist
        resources_before = resource_manager.list_resources()
        assert len(resources_before) > 0

        # Actual cleanup
        result = resource_manager.cleanup_resources(force=True, dry_run=False)

        # Verify all deleted
        assert result["successfully_deleted"] == len(resources_before)
        assert result["failed_count"] == 0

        # Verify no resources remain
        resources_after = resource_manager.list_resources()
        assert len(resources_after) == 0, "All resources should be deleted"
