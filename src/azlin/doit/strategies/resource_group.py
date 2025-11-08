"""Resource Group deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy
from azlin.doit.strategies.base import Strategy


class ResourceGroupStrategy(Strategy):
    """Strategy for deploying Azure Resource Groups."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create resource group."""
        location = goal.parameters.get("location", "eastus")
        tags = goal.parameters.get("tags", {})

        # Build tags string
        tag_parts = [f"{k}={v}" for k, v in tags.items()]
        tags_str = " ".join(tag_parts) if tag_parts else ""

        cmd = f"az group create --name {goal.name} --location {location} "

        if tags_str:
            cmd += f"--tags {tags_str} "

        cmd += "--output json"

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        location = goal.parameters.get("location", "eastus")
        tags = goal.parameters.get("tags", {})

        tags_tf = "\n    ".join([f'"{k}" = "{v}"' for k, v in tags.items()])

        return f'''resource "azurerm_resource_group" "{self._to_tf_name(goal.name)}" {{
  name     = "{goal.name}"
  location = "{location}"

  tags = {{
    {tags_tf}
  }}
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        # Resource groups are typically created at subscription level
        # Not usually in Bicep templates themselves
        return f"// Resource group '{goal.name}' should be created before deployment"

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
