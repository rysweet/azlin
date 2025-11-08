"""App Service deployment strategy."""

from azlin.doit.goals import Goal, GoalHierarchy, ResourceType
from azlin.doit.strategies.base import Strategy


class AppServicePlanStrategy(Strategy):
    """Strategy for deploying Azure App Service Plan."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create App Service Plan."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "B1")
        os_type = goal.parameters.get("os_type", "Linux")

        cmd = (
            f"az appservice plan create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--location {location} "
            f"--sku {sku} "
            f"--is-linux {str(os_type == 'Linux').lower()} "
            f"--output json"
        )

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "B1")
        os_type = goal.parameters.get("os_type", "Linux")

        return f'''resource "azurerm_service_plan" "{self._to_tf_name(goal.name)}" {{
  name                = "{goal.name}"
  location            = "{location}"
  resource_group_name = azurerm_resource_group.{self._to_tf_name(rg)}.name
  os_type             = "{os_type}"
  sku_name            = "{sku}"

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        sku = goal.parameters.get("sku", "B1")
        os_type = goal.parameters.get("os_type", "Linux")

        return f'''resource appServicePlan '{goal.name}' 'Microsoft.Web/serverfarms@2023-01-01' = {{
  name: '{goal.name}'
  location: '{location}'
  sku: {{
    name: '{sku}'
  }}
  kind: '{os_type.lower()}'
  properties: {{
    reserved: {str(os_type == 'Linux').lower()}
  }}
}}'''

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")


class AppServiceStrategy(Strategy):
    """Strategy for deploying Azure App Service."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build az CLI command to create App Service."""
        rg = goal.parameters.get("resource_group", "")
        plan_id = goal.parameters.get("service_plan_id", "")
        runtime = goal.parameters.get("runtime", "node|18-lts")
        managed_identity = goal.parameters.get("managed_identity", False)

        # Get plan name from hierarchy
        plan_goal = hierarchy.get_goal(plan_id)
        plan_name = plan_goal.name if plan_goal else ""

        cmd = (
            f"az webapp create "
            f"--name {goal.name} "
            f"--resource-group {rg} "
            f"--plan {plan_name} "
            f"--runtime \"{runtime}\" "
        )

        if managed_identity:
            cmd += "--assign-identity "

        cmd += "--output json"

        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code."""
        rg = goal.parameters.get("resource_group", "")
        location = goal.parameters.get("location", "eastus")
        plan_id = goal.parameters.get("service_plan_id", "")
        runtime = goal.parameters.get("runtime", "node|18-lts")
        managed_identity = goal.parameters.get("managed_identity", False)

        # Parse runtime
        runtime_parts = runtime.split("|")
        runtime_name = runtime_parts[0] if len(runtime_parts) > 0 else "node"
        runtime_version = runtime_parts[1] if len(runtime_parts) > 1 else "18-lts"

        # Get plan name from hierarchy
        plan_goal = hierarchy.get_goal(plan_id)
        plan_tf_name = self._to_tf_name(plan_goal.name) if plan_goal else "plan"

        identity_block = ""
        if managed_identity:
            identity_block = '''
  identity {
    type = "SystemAssigned"
  }'''

        return f'''resource "azurerm_linux_web_app" "{self._to_tf_name(goal.name)}" {{
  name                = "{goal.name}"
  location            = "{location}"
  resource_group_name = azurerm_resource_group.{self._to_tf_name(rg)}.name
  service_plan_id     = azurerm_service_plan.{plan_tf_name}.id

  site_config {{
    always_on = false

    application_stack {{
      {runtime_name}_version = "{runtime_version}"
    }}
  }}
{identity_block}

  tags = azurerm_resource_group.{self._to_tf_name(rg)}.tags
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code."""
        location = goal.parameters.get("location", "eastus")
        plan_id = goal.parameters.get("service_plan_id", "")
        runtime = goal.parameters.get("runtime", "node|18-lts")
        managed_identity = goal.parameters.get("managed_identity", False)

        # Get plan name from hierarchy
        plan_goal = hierarchy.get_goal(plan_id)
        plan_name = plan_goal.name if plan_goal else ""

        # Parse runtime
        runtime_parts = runtime.split("|")
        runtime_str = runtime_parts[1] if len(runtime_parts) > 1 else "18-lts"

        identity_block = ""
        if managed_identity:
            identity_block = '''
  identity: {
    type: 'SystemAssigned'
  }'''

        return f'''resource appService '{goal.name}' 'Microsoft.Web/sites@2023-01-01' = {{
  name: '{goal.name}'
  location: '{location}'
  properties: {{
    serverFarmId: resourceId('Microsoft.Web/serverfarms', '{plan_name}')
    siteConfig: {{
      linuxFxVersion: 'NODE|{runtime_str}'
      alwaysOn: false
    }}
    httpsOnly: true
  }}
{identity_block}
}}'''

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
