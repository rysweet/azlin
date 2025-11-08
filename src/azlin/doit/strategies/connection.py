"""Connection strategy - wire resources together."""

from azlin.doit.goals import Goal, GoalHierarchy, ResourceType
from azlin.doit.strategies.base import Strategy


class ConnectionStrategy(Strategy):
    """Strategy for connecting Azure resources."""

    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build command to establish connection.

        This typically involves:
        1. Storing secrets in Key Vault
        2. Granting managed identity access
        3. Configuring app settings
        """
        method = goal.parameters.get("method", "key_vault_secret")

        if method == "key_vault_secret":
            return self._build_keyvault_connection(goal, hierarchy)
        if method == "api_backend":
            return self._build_apim_backend(goal, hierarchy)
        return "echo 'Connection method not implemented'"

    def _build_keyvault_connection(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build commands to connect via Key Vault."""
        from_id = goal.parameters.get("from")
        to_id = goal.parameters.get("to")
        via_id = goal.parameters.get("via")

        if (
            not isinstance(from_id, str)
            or not isinstance(to_id, str)
            or not isinstance(via_id, str)
        ):
            return "echo 'Invalid connection parameters'"

        from_goal = hierarchy.get_goal(from_id)
        to_goal = hierarchy.get_goal(to_id)
        kv_goal = hierarchy.get_goal(via_id)

        if not (from_goal and to_goal and kv_goal):
            return "echo 'Missing required resources for connection'"

        # For Cosmos DB -> Key Vault -> App Service
        if to_goal.type == ResourceType.COSMOS_DB:
            rg = to_goal.parameters.get("resource_group", "")

            # Multi-step command:
            # 1. Get Cosmos connection string
            # 2. Store in Key Vault
            # 3. Grant App Service access to Key Vault
            # 4. Configure App Service app settings

            cmd = f"""
# Store Cosmos connection info in Key Vault
COSMOS_ENDPOINT=$(az cosmosdb show --name {to_goal.name} --resource-group {rg} --query documentEndpoint -o tsv) && \\
COSMOS_KEY=$(az cosmosdb keys list --name {to_goal.name} --resource-group {rg} --query primaryMasterKey -o tsv) && \\
az keyvault secret set --vault-name {kv_goal.name} --name cosmos-endpoint --value "$COSMOS_ENDPOINT" && \\
az keyvault secret set --vault-name {kv_goal.name} --name cosmos-key --value "$COSMOS_KEY" && \\
# Get App Service identity
APP_IDENTITY=$(az webapp show --name {from_goal.name} --resource-group {rg} --query identity.principalId -o tsv) && \\
# Grant Key Vault access
az role assignment create --role "Key Vault Secrets User" --assignee "$APP_IDENTITY" --scope $(az keyvault show --name {kv_goal.name} --query id -o tsv) && \\
# Configure app settings
az webapp config appsettings set --name {from_goal.name} --resource-group {rg} --settings \\
  COSMOS_ENDPOINT="@Microsoft.KeyVault(SecretUri=https://{kv_goal.name}.vault.azure.net/secrets/cosmos-endpoint/)" \\
  COSMOS_KEY="@Microsoft.KeyVault(SecretUri=https://{kv_goal.name}.vault.azure.net/secrets/cosmos-key/)" \\
  --output json
"""
            return cmd

        return "echo 'Connection type not implemented'"

    def _build_apim_backend(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build commands to configure APIM backend."""
        from_id = goal.parameters.get("from")  # APIM
        to_id = goal.parameters.get("to")  # App Service

        if not isinstance(from_id, str) or not isinstance(to_id, str):
            return "echo 'Invalid connection parameters'"

        apim_goal = hierarchy.get_goal(from_id)
        app_goal = hierarchy.get_goal(to_id)

        if not (apim_goal and app_goal):
            return "echo 'Missing required resources for APIM backend'"

        rg = apim_goal.parameters.get("resource_group", "")

        # Configure APIM backend pointing to App Service
        cmd = f"""
# Get App Service URL
APP_URL=$(az webapp show --name {app_goal.name} --resource-group {rg} --query defaultHostName -o tsv) && \\
# Create APIM backend
az apim api create \\
  --service-name {apim_goal.name} \\
  --resource-group {rg} \\
  --api-id {app_goal.name} \\
  --path / \\
  --display-name "{app_goal.name}" \\
  --protocols https \\
  --service-url "https://$APP_URL" \\
  --output json
"""
        return cmd

    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code for connection."""
        method = goal.parameters.get("method", "key_vault_secret")

        if method == "key_vault_secret":
            return self._generate_tf_keyvault_connection(goal, hierarchy)
        if method == "api_backend":
            return self._generate_tf_apim_backend(goal, hierarchy)
        return "# Connection not implemented"

    def _generate_tf_keyvault_connection(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform for Key Vault connection."""
        from_id = goal.parameters.get("from")
        to_id = goal.parameters.get("to")
        via_id = goal.parameters.get("via")

        if (
            not isinstance(from_id, str)
            or not isinstance(to_id, str)
            or not isinstance(via_id, str)
        ):
            return "# Invalid connection parameters"

        from_goal = hierarchy.get_goal(from_id)
        to_goal = hierarchy.get_goal(to_id)
        kv_goal = hierarchy.get_goal(via_id)

        if not (from_goal and to_goal and kv_goal):
            return "# Missing resources"

        from_tf = self._to_tf_name(from_goal.name)
        to_tf = self._to_tf_name(to_goal.name)
        kv_tf = self._to_tf_name(kv_goal.name)

        return f"""# Store Cosmos connection info in Key Vault
resource "azurerm_key_vault_secret" "cosmos_endpoint" {{
  name         = "cosmos-endpoint"
  value        = azurerm_cosmosdb_account.{to_tf}.endpoint
  key_vault_id = azurerm_key_vault.{kv_tf}.id

  depends_on = [azurerm_role_assignment.app_kv_access]
}}

resource "azurerm_key_vault_secret" "cosmos_key" {{
  name         = "cosmos-key"
  value        = azurerm_cosmosdb_account.{to_tf}.primary_key
  key_vault_id = azurerm_key_vault.{kv_tf}.id

  depends_on = [azurerm_role_assignment.app_kv_access]
}}

# Grant App Service access to Key Vault
resource "azurerm_role_assignment" "app_kv_access" {{
  scope                = azurerm_key_vault.{kv_tf}.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.{from_tf}.identity[0].principal_id
}}"""

    def _generate_tf_apim_backend(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform for APIM backend."""
        from_id = goal.parameters.get("from")
        to_id = goal.parameters.get("to")

        if not isinstance(from_id, str) or not isinstance(to_id, str):
            return "# Invalid connection parameters"

        apim_goal = hierarchy.get_goal(from_id)
        app_goal = hierarchy.get_goal(to_id)

        if not (apim_goal and app_goal):
            return "# Missing resources"

        apim_tf = self._to_tf_name(apim_goal.name)
        app_tf = self._to_tf_name(app_goal.name)

        return f'''resource "azurerm_api_management_api" "backend_api" {{
  name                = "{app_goal.name}"
  resource_group_name = azurerm_api_management.{apim_tf}.resource_group_name
  api_management_name = azurerm_api_management.{apim_tf}.name
  revision            = "1"
  display_name        = "{app_goal.name}"
  path                = ""
  protocols           = ["https"]
  service_url         = "https://${{azurerm_linux_web_app.{app_tf}.default_hostname}}"
}}'''

    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code for connection."""
        method = goal.parameters.get("method", "key_vault_secret")

        if method == "key_vault_secret":
            return "// Key Vault connection configured via app settings"
        if method == "api_backend":
            return "// APIM backend configured"
        return "// Connection not implemented"

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
