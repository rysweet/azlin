"""Artifact generator - creates Terraform, Bicep, and documentation."""

from pathlib import Path

from azlin.doit.engine.models import ExecutionState
from azlin.doit.goals import GoalHierarchy, GoalStatus
from azlin.doit.strategies import get_strategy


class ArtifactGenerator:
    """Generate deployment artifacts from executed goals."""

    def __init__(self, output_dir: Path):
        """Initialize generator.

        Args:
            output_dir: Directory to write artifacts to
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, hierarchy: GoalHierarchy, state: ExecutionState) -> dict[str, Path]:
        """Generate all artifacts.

        Args:
            hierarchy: Goal hierarchy with completed goals
            state: Execution state

        Returns:
            Dict of artifact_type -> file_path
        """
        artifacts = {}

        # Generate Terraform
        tf_path = self.generate_terraform(hierarchy)
        if tf_path:
            artifacts["terraform"] = tf_path

        # Generate Terraform variables
        tfvars_path = self.generate_terraform_variables(hierarchy)
        if tfvars_path:
            artifacts["terraform_variables"] = tfvars_path

        # Generate Terraform outputs
        tfout_path = self.generate_terraform_outputs(hierarchy)
        if tfout_path:
            artifacts["terraform_outputs"] = tfout_path

        # Generate Bicep
        bicep_path = self.generate_bicep(hierarchy)
        if bicep_path:
            artifacts["bicep"] = bicep_path

        # Generate README
        readme_path = self.generate_readme(hierarchy, state)
        if readme_path:
            artifacts["readme"] = readme_path

        return artifacts

    def generate_terraform(self, hierarchy: GoalHierarchy) -> Path | None:
        """Generate main.tf with all resources."""
        completed = [g for g in hierarchy.goals if g.status == GoalStatus.COMPLETED]

        if not completed:
            return None

        tf_code = """terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

"""

        # Generate resource blocks
        for goal in completed:
            try:
                strategy = get_strategy(goal.type)
                resource_tf = strategy.generate_terraform(goal, hierarchy)
                tf_code += f"\n{resource_tf}\n"
            except Exception:
                # Skip if strategy not available
                pass

        path = self.output_dir / "main.tf"
        path.write_text(tf_code)
        return path

    def generate_terraform_variables(self, hierarchy: GoalHierarchy) -> Path | None:
        """Generate variables.tf with configurable parameters."""
        # Extract common parameters
        locations = set()
        environments = set()

        for goal in hierarchy.goals:
            if loc := goal.parameters.get("location"):
                locations.add(loc)
            if env := goal.parameters.get("tags", {}).get("Environment"):
                environments.add(env)

        location = next(iter(locations)) if locations else "eastus"
        environment = next(iter(environments)) if environments else "dev"

        tf_vars = f'''variable "location" {{
  description = "Azure region for resources"
  type        = string
  default     = "{location}"
}}

variable "environment" {{
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "{environment}"
}}

variable "tags" {{
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {{
    Environment = "{environment}"
    ManagedBy   = "Terraform"
    CreatedBy   = "azlin-doit"
  }}
}}
'''

        path = self.output_dir / "variables.tf"
        path.write_text(tf_vars)
        return path

    def generate_terraform_outputs(self, hierarchy: GoalHierarchy) -> Path | None:
        """Generate outputs.tf with useful output values."""
        completed = [g for g in hierarchy.goals if g.status == GoalStatus.COMPLETED]

        if not completed:
            return None

        outputs = []

        for goal in completed:
            if goal.outputs.get("defaultHostName"):
                # App Service
                outputs.append(
                    f'''output "{goal.name}_url" {{
  description = "URL of {goal.name}"
  value       = "https://${{azurerm_linux_web_app.{self._to_tf_name(goal.name)}.default_hostname}}"
}}'''
                )
            elif goal.outputs.get("documentEndpoint"):
                # Cosmos DB
                outputs.append(
                    f'''output "{goal.name}_endpoint" {{
  description = "Cosmos DB endpoint"
  value       = azurerm_cosmosdb_account.{self._to_tf_name(goal.name)}.endpoint
}}'''
                )

        if not outputs:
            return None

        path = self.output_dir / "outputs.tf"
        path.write_text("\n\n".join(outputs))
        return path

    def generate_bicep(self, hierarchy: GoalHierarchy) -> Path | None:
        """Generate main.bicep with all resources."""
        completed = [g for g in hierarchy.goals if g.status == GoalStatus.COMPLETED]

        if not completed:
            return None

        bicep_code = """@description('Azure region for resources')
param location string = resourceGroup().location

@description('Environment name')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'dev'

@description('Tags to apply to resources')
param tags object = {
  Environment: environment
  ManagedBy: 'Bicep'
  CreatedBy: 'azlin-doit'
}

"""

        # Generate resource blocks
        for goal in completed:
            try:
                strategy = get_strategy(goal.type)
                resource_bicep = strategy.generate_bicep(goal, hierarchy)
                bicep_code += f"\n{resource_bicep}\n"
            except Exception:
                # Skip if strategy not available
                pass

        path = self.output_dir / "main.bicep"
        path.write_text(bicep_code)
        return path

    def generate_readme(self, hierarchy: GoalHierarchy, state: ExecutionState) -> Path | None:
        """Generate README.md with deployment documentation."""
        completed, total = hierarchy.get_progress()
        elapsed = state.get_elapsed_time()

        readme = f"""# Azure Infrastructure Deployment

Generated by **azlin doit** - Autonomous Azure Infrastructure Agent

## Overview

This deployment creates {completed} Azure resources:

"""

        # List resources
        for goal in hierarchy.goals:
            if goal.status == GoalStatus.COMPLETED:
                readme += f"- **{goal.type.value}**: {goal.name}\n"

        readme += f"""
## Deployment Time

- **Total Time**: {elapsed:.1f}s ({elapsed / 60:.1f} minutes)
- **Resources Deployed**: {completed}/{total}

## Files Generated

- `main.tf` - Terraform configuration
- `variables.tf` - Terraform variables
- `outputs.tf` - Terraform outputs
- `main.bicep` - Bicep configuration
- `README.md` - This file

## Prerequisites

### For Terraform:
```bash
# Install Terraform (if not already installed)
brew install terraform  # macOS
# or
choco install terraform  # Windows

# Verify installation
terraform version
```

### For Bicep:
```bash
# Install Azure CLI with Bicep
az bicep install

# Verify installation
az bicep version
```

## Deployment Instructions

### Option 1: Using Terraform

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the configuration
terraform apply

# To destroy resources later
terraform destroy
```

### Option 2: Using Bicep

```bash
# Create resource group (if not exists)
az group create --name <resource-group-name> --location eastus

# Deploy Bicep template
az deployment group create \\
  --resource-group <resource-group-name> \\
  --template-file main.bicep

# To clean up later
az group delete --name <resource-group-name> --yes
```

## Architecture

"""

        # Add architecture diagram
        readme += self._generate_architecture_diagram(hierarchy)

        readme += """
## Post-Deployment Steps

1. **Verify Resources**: Check Azure Portal to confirm all resources are deployed
2. **Configure Secrets**: Ensure Key Vault contains required secrets
3. **Deploy Application**: Deploy your application code to App Service
4. **Test Connections**: Verify connectivity between resources
5. **Configure Custom Domains**: Set up custom domains and SSL certificates (if needed)
6. **Enable Monitoring**: Set up Application Insights and alerts

## Security Notes

This deployment follows Azure security best practices:

- ✅ Managed identities for authentication (no credentials in code)
- ✅ Secrets stored in Key Vault
- ✅ HTTPS enforced on all endpoints
- ✅ TLS 1.2 minimum
- ✅ RBAC for Key Vault access
- ✅ Public blob access disabled on storage

## Cost Estimation

Approximate monthly costs (may vary by region and usage):

"""

        # Add cost estimates
        readme += self._generate_cost_estimates(hierarchy)

        readme += """
## Troubleshooting

### Common Issues

**Issue**: Terraform/Bicep deployment fails with "name already exists"
**Solution**: Resource names must be globally unique. Modify names in variables or parameters.

**Issue**: App Service can't access Key Vault
**Solution**: Verify managed identity is enabled and has "Key Vault Secrets User" role.

**Issue**: Cosmos DB connection fails
**Solution**: Check that connection string is stored in Key Vault and referenced in app settings.

## Support

For issues or questions:
- Azure Documentation: https://learn.microsoft.com/azure/
- azlin GitHub: https://github.com/ruvnet/azlin

---

**Generated by azlin doit** - Autonomous goal-seeking infrastructure agent
"""

        path = self.output_dir / "README.md"
        path.write_text(readme)
        return path

    def _generate_architecture_diagram(self, hierarchy: GoalHierarchy) -> str:
        """Generate ASCII architecture diagram."""
        diagram = """```
┌──────────────┐
│   Internet   │
└──────┬───────┘
       │
"""

        # Check what's deployed
        has_apim = any(
            g.name.startswith("apim") and g.status == GoalStatus.COMPLETED for g in hierarchy.goals
        )
        has_app = any(
            g.name.startswith("app") and g.status == GoalStatus.COMPLETED for g in hierarchy.goals
        )
        has_cosmos = any(
            g.name.startswith("cosmos") and g.status == GoalStatus.COMPLETED
            for g in hierarchy.goals
        )
        has_kv = any(
            g.name.startswith("kv") and g.status == GoalStatus.COMPLETED for g in hierarchy.goals
        )
        has_storage = any(
            g.name.startswith("st") and g.status == GoalStatus.COMPLETED for g in hierarchy.goals
        )

        if has_apim:
            diagram += """       ▼
┌──────────────────┐
│ API Management   │
└────────┬─────────┘
         │
"""

        if has_app:
            diagram += """       ▼
┌──────────────┐      ┌─────────────┐
│  App Service │──────│  Key Vault  │
└──────┬───────┘      └──────┬──────┘
       │                     │
       │ Managed Identity    │
       │                     │
"""

        if has_cosmos or has_storage:
            diagram += "       ▼                     ▼\n"
            if has_cosmos:
                diagram += "┌──────────────┐"
            if has_storage:
                diagram += "      ┌─────────────┐\n"
            if has_cosmos:
                diagram += "│  Cosmos DB   │"
            if has_storage:
                diagram += "      │   Storage   │\n"
            if has_cosmos:
                diagram += "└──────────────┘"
            if has_storage:
                diagram += "      └─────────────┘\n"

        diagram += "```\n"
        return diagram

    def _generate_cost_estimates(self, hierarchy: GoalHierarchy) -> str:
        """Generate cost estimates for deployed resources."""
        estimates = []

        for goal in hierarchy.goals:
            if goal.status != GoalStatus.COMPLETED:
                continue

            if "app-service-plan" in goal.name or "plan-" in goal.name:
                sku = goal.parameters.get("sku", "B1")
                cost = {"B1": "$13", "S1": "$70", "P1V2": "$85"}.get(sku, "$13")
                estimates.append(f"- App Service Plan ({sku}): {cost}/month")
            elif goal.name.startswith("cosmos"):
                estimates.append("- Cosmos DB (400 RU/s): $24/month")
            elif goal.name.startswith("st"):
                estimates.append("- Storage Account: $1-5/month (usage-based)")
            elif goal.name.startswith("kv"):
                estimates.append("- Key Vault: $0 (basic operations)")
            elif goal.name.startswith("apim"):
                sku = goal.parameters.get("sku", "Developer")
                cost = {"Developer": "$50", "Standard": "$680", "Premium": "$2,800"}.get(sku, "$50")
                estimates.append(f"- API Management ({sku}): {cost}/month")

        if not estimates:
            return "- No cost estimates available\n\n"

        result = "\n".join(estimates)
        result += "\n\n**Note**: Costs are approximate and vary by region and usage.\n\n"
        return result

    def _to_tf_name(self, name: str) -> str:
        """Convert Azure name to Terraform resource name."""
        return name.replace("-", "_").replace(".", "_")
