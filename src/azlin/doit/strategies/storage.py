"""Storage Account deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy, ResourceType
from azlin.doit.strategies.base import Strategy


class StorageStrategy(Strategy):
    """Strategy for deploying Azure Storage Accounts."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create storage account."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Standard_LRS")
        https_only = goal.parameters.get("https_only", True)

        cmd = (
            f"az storage account create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--location {location} "
            f"--sku {sku} "
            f"--kind StorageV2 "
            f"--https-only {'true' if https_only else 'false'} "
            f"--min-tls-version TLS1_2 "
            f"--allow-blob-public-access false "
            f"--output json"
        )

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Standard_LRS")

        # Parse SKU
        tier, replication = sku.split("_")

        return f'''resource "azurerm_storage_account" "{self._to_tf_name(goal.name)}" {{
  name                     = "{goal.name}"
  resource_group_name      = azurerm_resource_group.{self._to_tf_name(rg)}.name
  location                 = "{location}"
  account_tier             = "{tier}"
  account_replication_type = "{replication}"
  account_kind             = "StorageV2"

  # Security settings
  https_traffic_only_enabled = true
  min_tls_version           = "TLS1_2"
  allow_blob_public_access  = false

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Standard_LRS")

        return f'''resource storageAccount '{goal.name}' 'Microsoft.Storage/storageAccounts@2023-01-01' = {{
  name: '{goal.name}'
  location: '{location}'
  sku: {{
    name: '{sku}'
  }}
  kind: 'StorageV2'
  properties: {{
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }}
}}'''

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
