"""Cosmos DB deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy
from azlin.doit.strategies.base import Strategy


class CosmosDBStrategy(Strategy):
    """Strategy for deploying Azure Cosmos DB."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create Cosmos DB."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        kind = goal.parameters.get("kind", "GlobalDocumentDB")

        cmd = (
            f"az cosmosdb create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--locations regionName={location} failoverPriority=0 "
            f"--kind {kind} "
            f"--default-consistency-level Session "
            f"--output json"
        )

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        kind = goal.parameters.get("kind", "GlobalDocumentDB")

        return f'''resource "azurerm_cosmosdb_account" "{self._to_tf_name(goal.name)}" {{
  name                = "{goal.name}"
  location            = "{location}"
  resource_group_name = azurerm_resource_group.{self._to_tf_name(rg)}.name
  offer_type          = "Standard"
  kind                = "{kind}"

  consistency_policy {{
    consistency_level = "Session"
  }}

  geo_location {{
    location          = "{location}"
    failover_priority = 0
  }}

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        kind = goal.parameters.get("kind", "GlobalDocumentDB")

        return f"""resource cosmosAccount '{goal.name}' 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {{
  name: '{goal.name}'
  location: '{location}'
  kind: '{kind}'
  properties: {{
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {{
      defaultConsistencyLevel: 'Session'
    }}
    locations: [
      {{
        locationName: '{location}'
        failoverPriority: 0
        isZoneRedundant: false
      }}
    ]
  }}
}}"""

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
