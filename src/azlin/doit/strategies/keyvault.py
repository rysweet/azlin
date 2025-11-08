"""Key Vault deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy
from azlin.doit.strategies.base import Strategy


class KeyVaultStrategy(Strategy):
    """Strategy for deploying Azure Key Vault."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create Key Vault."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "standard")
        enable_rbac = goal.parameters.get("enable_rbac", True)

        cmd = (
            f"az keyvault create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--location {location} "
            f"--sku {sku} "
        )

        if enable_rbac:
            cmd += "--enable-rbac-authorization true "

        # Add tags if available
        tags = self.get_tags_string()
        if tags:
            cmd += f"--tags {tags} "

        cmd += "--output json"

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "standard")
        enable_rbac = goal.parameters.get("enable_rbac", True)

        return f'''resource "azurerm_key_vault" "{self._to_tf_name(goal.name)}" {{
  name                       = "{goal.name}"
  location                   = "{location}"
  resource_group_name        = azurerm_resource_group.{self._to_tf_name(rg)}.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "{sku}"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  enable_rbac_authorization = {str(enable_rbac).lower()}

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}

data "azurerm_client_config" "current" {{}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "standard")
        enable_rbac = goal.parameters.get("enable_rbac", True)

        return f"""resource keyVault '{goal.name}' 'Microsoft.KeyVault/vaults@2023-07-01' = {{
  name: '{goal.name}'
  location: '{location}'
  properties: {{
    sku: {{
      family: 'A'
      name: '{sku}'
    }}
    tenantId: subscription().tenantId
    enableRbacAuthorization: {str(enable_rbac).lower()}
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false
  }}
}}"""

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
