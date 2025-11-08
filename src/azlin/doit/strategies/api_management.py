"""API Management deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy
from azlin.doit.strategies.base import Strategy


class APIManagementStrategy(Strategy):
    """Strategy for deploying Azure API Management."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create API Management.

        Note: APIM deployment takes 30-45 minutes.
        """
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Developer")
        publisher_name = goal.parameters.get("publisher_name", "Organization")
        publisher_email = goal.parameters.get("publisher_email", "admin@example.com")

        cmd = (
            f"az apim create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--location {location} "
            f"--sku-name {sku} "
            f"--publisher-name \"{publisher_name}\" "
            f"--publisher-email {publisher_email} "
            f"--no-wait "  # Don't wait for completion (takes too long)
            f"--output json"
        )

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Developer")
        publisher_name = goal.parameters.get("publisher_name", "Organization")
        publisher_email = goal.parameters.get("publisher_email", "admin@example.com")

        # Parse SKU (e.g., "Developer" -> name: Developer, capacity: 1)
        sku_parts = sku.split("_")
        sku_name = sku_parts[0]
        capacity = sku_parts[1] if len(sku_parts) > 1 else "1"

        return f'''resource "azurerm_api_management" "{self._to_tf_name(goal.name)}" {{
  name                = "{goal.name}"
  location            = "{location}"
  resource_group_name = azurerm_resource_group.{self._to_tf_name(rg)}.name
  publisher_name      = "{publisher_name}"
  publisher_email     = "{publisher_email}"

  sku_name = "{sku_name}_{capacity}"

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "Developer")
        publisher_name = goal.parameters.get("publisher_name", "Organization")
        publisher_email = goal.parameters.get("publisher_email", "admin@example.com")

        return f'''resource apiManagement '{goal.name}' 'Microsoft.ApiManagement/service@2023-05-01-preview' = {{
  name: '{goal.name}'
  location: '{location}'
  sku: {{
    name: '{sku}'
    capacity: 1
  }}
  properties: {{
    publisherEmail: '{publisher_email}'
    publisherName: '{publisher_name}'
  }}
}}'''

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
