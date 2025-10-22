"""Terraform execution strategy.

Infrastructure as Code approach using Terraform for Azure resources.
"""

import contextlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Strategy,
)


class TerraformStrategy(ExecutionStrategy):
    """Execute Azure operations via Terraform Infrastructure as Code.

    Generates .tf files, runs terraform init/plan/apply, and tracks state.

    Example:
        >>> strategy = TerraformStrategy()
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
        >>> if result.success:
        ...     print(f"Applied Terraform config: {result.metadata['terraform_dir']}")
    """

    def __init__(self, work_dir: Path | None = None):
        """Initialize Terraform strategy.

        Args:
            work_dir: Directory for Terraform files (default: temp dir)
        """
        self.work_dir = work_dir or Path(tempfile.gettempdir()) / "azlin-terraform"

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if Terraform can handle this intent.

        Terraform is best for:
        - Complex infrastructure (AKS, VNets, etc.)
        - Multi-resource provisioning
        - Repeatable deployments

        Args:
            context: Execution context

        Returns:
            True if Terraform should handle this
        """
        # Check if terraform is available
        valid, _ = self.validate(context)
        if not valid:
            return False

        intent_type = context.intent.intent.lower()

        # Terraform excels at infrastructure provisioning
        terraform_preferred = [
            "aks",
            "kubernetes",
            "cluster",
            "network",
            "vnet",
            "subnet",
            "infrastructure",
            "multi-region",
        ]

        if any(keyword in intent_type for keyword in terraform_preferred):
            return True

        # Also good for complex multi-resource setups
        if len(context.intent.azlin_commands) > 3:
            return True

        # Not ideal for simple queries
        return not any(keyword in intent_type for keyword in ["list", "show", "status", "query"])

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Terraform.

        Args:
            context: Execution context

        Returns:
            ExecutionResult with success status
        """
        start_time = time.time()

        try:
            # Validate prerequisites
            valid, error_msg = self.validate(context)
            if not valid:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.TERRAFORM,
                    error=error_msg,
                    failure_type=FailureType.VALIDATION_ERROR,
                )

            # Create work directory
            terraform_dir = self._create_work_directory(context)

            # Generate Terraform configuration
            config_files = self._generate_terraform_config(context, terraform_dir)

            if context.dry_run:
                # Dry run: show generated config
                output = "DRY RUN - Generated Terraform configuration:\n\n"
                for file_path, content in config_files.items():
                    output += f"=== {file_path} ===\n{content}\n\n"

                return ExecutionResult(
                    success=True,
                    strategy=Strategy.TERRAFORM,
                    output=output,
                    duration_seconds=time.time() - start_time,
                    metadata={
                        "terraform_dir": str(terraform_dir),
                        "config_files": list(config_files.keys()),
                        "dry_run": True,
                    },
                )

            # Initialize Terraform
            init_result = self._run_terraform_init(terraform_dir)
            if not init_result["success"]:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.TERRAFORM,
                    error=f"Terraform init failed: {init_result['error']}",
                    failure_type=FailureType.VALIDATION_ERROR,
                    duration_seconds=time.time() - start_time,
                )

            # Run terraform plan
            plan_result = self._run_terraform_plan(terraform_dir)
            if not plan_result["success"]:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.TERRAFORM,
                    error=f"Terraform plan failed: {plan_result['error']}",
                    failure_type=self._classify_failure(plan_result["error"]),
                    duration_seconds=time.time() - start_time,
                )

            # Run terraform apply
            apply_result = self._run_terraform_apply(terraform_dir)
            if not apply_result["success"]:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.TERRAFORM,
                    error=f"Terraform apply failed: {apply_result['error']}",
                    failure_type=self._classify_failure(apply_result["error"]),
                    duration_seconds=time.time() - start_time,
                )

            # Extract created resources from state
            resources_created = self._extract_resources_from_state(terraform_dir)

            # Success
            duration = time.time() - start_time
            output = (
                f"Terraform apply completed successfully\n\n"
                f"Plan output:\n{plan_result['output']}\n\n"
                f"Apply output:\n{apply_result['output']}"
            )

            return ExecutionResult(
                success=True,
                strategy=Strategy.TERRAFORM,
                output=output,
                resources_created=resources_created,
                duration_seconds=duration,
                metadata={
                    "terraform_dir": str(terraform_dir),
                    "config_files": list(config_files.keys()),
                },
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.TERRAFORM,
                error=f"Unexpected error: {e!s}",
                failure_type=FailureType.UNKNOWN,
                duration_seconds=time.time() - start_time,
            )

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate Terraform prerequisites.

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if terraform is installed
        if not shutil.which("terraform"):
            return False, "Terraform not installed (https://www.terraform.io/downloads)"

        # Check terraform version
        try:
            result = subprocess.run(
                ["terraform", "version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, "Terraform version check failed"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Terraform not found in PATH"

        # Check Azure authentication (needed for Terraform Azure provider)
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, "Not authenticated with Azure (run 'az login')"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Azure CLI required for Terraform (run 'az login')"

        return True, None

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate execution duration.

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds
        """
        # Terraform is slower than Azure CLI
        # Base: 2 minutes for init + plan + apply
        base = 120

        # Add time per resource
        resource_count = len(context.intent.parameters.get("resources", []))
        if resource_count == 0:
            resource_count = 1  # At least one resource

        base += resource_count * 60  # 1 minute per resource

        # Adjust for specific resource types
        intent_type = context.intent.intent.lower()
        if "aks" in intent_type or "cluster" in intent_type:
            # AKS takes 10-15 minutes
            base = 900

        return base

    def get_strategy_type(self) -> Strategy:
        """Get strategy type."""
        return Strategy.TERRAFORM

    def get_prerequisites(self) -> list[str]:
        """Get prerequisites."""
        return [
            "terraform >= 1.0 (https://www.terraform.io/downloads)",
            "az CLI authenticated (az login)",
            "Azure provider configured",
        ]

    def supports_dry_run(self) -> bool:
        """Terraform strategy supports dry-run."""
        return True

    def get_cost_factors(self, context: ExecutionContext) -> dict[str, Any]:
        """Get cost factors."""
        factors = {}

        params = context.intent.parameters
        if "vm_name" in params or "provision" in context.intent.intent:
            factors["vm_count"] = params.get("count", 1)
            factors["vm_size"] = params.get("vm_size", "Standard_B2s")

        if "storage" in context.intent.intent:
            factors["storage_gb"] = params.get("size_gb", 128)

        if "aks" in context.intent.intent.lower():
            factors["aks_nodes"] = params.get("node_count", 3)

        return factors

    def cleanup_on_failure(self, context: ExecutionContext, partial_resources: list[str]) -> None:
        """Clean up using terraform destroy.

        Args:
            context: Execution context
            partial_resources: List of resource IDs (not used, terraform manages this)
        """
        terraform_dir = self._create_work_directory(context)

        # Best effort cleanup
        with contextlib.suppress(subprocess.TimeoutExpired, Exception):
            subprocess.run(
                ["terraform", "destroy", "-auto-approve"],
                cwd=terraform_dir,
                capture_output=True,
                timeout=300,
                check=False,
            )

    def _create_work_directory(self, context: ExecutionContext) -> Path:
        """Create work directory for Terraform files.

        Args:
            context: Execution context

        Returns:
            Path to work directory
        """
        # Create directory named after objective ID
        terraform_dir = self.work_dir / context.objective_id
        terraform_dir.mkdir(parents=True, exist_ok=True)
        return terraform_dir

    def _generate_terraform_config(
        self, context: ExecutionContext, terraform_dir: Path
    ) -> dict[str, str]:
        """Generate Terraform configuration files.

        Args:
            context: Execution context
            terraform_dir: Directory for Terraform files

        Returns:
            Dictionary mapping file names to content
        """
        config_files = {}

        # Generate provider.tf
        provider_config = self._generate_provider_config(context)
        config_files["provider.tf"] = provider_config
        (terraform_dir / "provider.tf").write_text(provider_config)

        # Generate main.tf with resources
        main_config = self._generate_main_config(context)
        config_files["main.tf"] = main_config
        (terraform_dir / "main.tf").write_text(main_config)

        # Generate variables.tf
        variables_config = self._generate_variables_config(context)
        config_files["variables.tf"] = variables_config
        (terraform_dir / "variables.tf").write_text(variables_config)

        return config_files

    def _generate_provider_config(self, context: ExecutionContext) -> str:
        """Generate provider.tf content.

        Args:
            context: Execution context

        Returns:
            Terraform provider configuration
        """
        return """terraform {
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

    def _generate_main_config(self, context: ExecutionContext) -> str:
        """Generate main.tf content with resources.

        Args:
            context: Execution context

        Returns:
            Terraform main configuration
        """
        intent_type = context.intent.intent.lower()
        params = context.intent.parameters
        rg = context.resource_group or "azlin-rg"

        config = f'''# Resource Group
resource "azurerm_resource_group" "main" {{
  name     = "{rg}"
  location = var.location
}}

'''

        # Generate resource based on intent
        if "provision" in intent_type or "create vm" in intent_type:
            vm_name = params.get("vm_name", "vm")
            config += self._generate_vm_resource(vm_name)

        elif "aks" in intent_type or "cluster" in intent_type:
            cluster_name = params.get("cluster_name", "aks-cluster")
            node_count = params.get("node_count", 3)
            config += self._generate_aks_resource(cluster_name, node_count)

        elif "storage" in intent_type:
            storage_name = params.get("storage_name", "storage")
            config += self._generate_storage_resource(storage_name)

        return config

    def _generate_variables_config(self, context: ExecutionContext) -> str:
        """Generate variables.tf content.

        Args:
            context: Execution context

        Returns:
            Terraform variables configuration
        """
        return """variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "vm_size" {
  description = "VM size"
  type        = string
  default     = "Standard_B2s"
}
"""

    def _generate_vm_resource(self, vm_name: str) -> str:
        """Generate VM resource configuration.

        Args:
            vm_name: VM name

        Returns:
            Terraform VM resource configuration
        """
        return f'''# Virtual Machine
resource "azurerm_linux_virtual_machine" "{vm_name}" {{
  name                = "{vm_name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = var.vm_size
  admin_username      = "azureuser"

  network_interface_ids = [
    azurerm_network_interface.main.id,
  ]

  admin_ssh_key {{
    username   = "azureuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }}

  os_disk {{
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }}

  source_image_reference {{
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }}
}}

resource "azurerm_network_interface" "main" {{
  name                = "{vm_name}-nic"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {{
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
  }}
}}

resource "azurerm_virtual_network" "main" {{
  name                = "{vm_name}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_subnet" "main" {{
  name                 = "internal"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]
}}
'''

    def _generate_aks_resource(self, cluster_name: str, node_count: int) -> str:
        """Generate AKS resource configuration.

        Args:
            cluster_name: AKS cluster name
            node_count: Number of nodes

        Returns:
            Terraform AKS resource configuration
        """
        return f'''# AKS Cluster
resource "azurerm_kubernetes_cluster" "{cluster_name}" {{
  name                = "{cluster_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "{cluster_name}"

  default_node_pool {{
    name       = "default"
    node_count = {node_count}
    vm_size    = "Standard_D2_v2"
  }}

  identity {{
    type = "SystemAssigned"
  }}
}}
'''

    def _generate_storage_resource(self, storage_name: str) -> str:
        """Generate storage resource configuration.

        Args:
            storage_name: Storage account name

        Returns:
            Terraform storage resource configuration
        """
        # Storage account names must be lowercase and alphanumeric
        safe_name = re.sub(r"[^a-z0-9]", "", storage_name.lower())[:24]

        return f'''# Storage Account
resource "azurerm_storage_account" "{storage_name}" {{
  name                     = "{safe_name}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}}
'''

    def _run_terraform_init(self, terraform_dir: Path) -> dict[str, Any]:
        """Run terraform init.

        Args:
            terraform_dir: Terraform working directory

        Returns:
            Dictionary with success, output, and error
        """
        try:
            result = subprocess.run(
                ["terraform", "init"],
                cwd=terraform_dir,
                capture_output=True,
                timeout=120,
                text=True,
                check=False,
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Terraform init timed out",
            }

    def _run_terraform_plan(self, terraform_dir: Path) -> dict[str, Any]:
        """Run terraform plan.

        Args:
            terraform_dir: Terraform working directory

        Returns:
            Dictionary with success, output, and error
        """
        try:
            result = subprocess.run(
                ["terraform", "plan"],
                cwd=terraform_dir,
                capture_output=True,
                timeout=120,
                text=True,
                check=False,
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Terraform plan timed out",
            }

    def _run_terraform_apply(self, terraform_dir: Path) -> dict[str, Any]:
        """Run terraform apply.

        Args:
            terraform_dir: Terraform working directory

        Returns:
            Dictionary with success, output, and error
        """
        try:
            result = subprocess.run(
                ["terraform", "apply", "-auto-approve"],
                cwd=terraform_dir,
                capture_output=True,
                timeout=900,  # 15 minutes for apply
                text=True,
                check=False,
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Terraform apply timed out",
            }

    def _extract_resources_from_state(self, terraform_dir: Path) -> list[str]:
        """Extract created resource IDs from Terraform state.

        Args:
            terraform_dir: Terraform working directory

        Returns:
            List of Azure resource IDs
        """
        resources = []

        try:
            # Run terraform show -json
            result = subprocess.run(
                ["terraform", "show", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                timeout=30,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                state = json.loads(result.stdout)

                # Extract resource IDs from state
                if "values" in state and "root_module" in state["values"]:
                    resources.extend(
                        resource["values"]["id"]
                        for resource in state["values"]["root_module"].get("resources", [])
                        if "values" in resource and "id" in resource["values"]
                    )

        # Best effort extraction - if errors occur, return what we have
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            # Log but don't fail - resource extraction is best-effort
            import logging

            logging.debug(f"Resource extraction failed (non-critical): {e}")

        return resources

    def _classify_failure(self, error: str) -> FailureType:
        """Classify failure type from error message.

        Args:
            error: Error message

        Returns:
            FailureType enum
        """
        error_lower = error.lower()

        if "quota" in error_lower or "exceeded" in error_lower:
            return FailureType.QUOTA_EXCEEDED

        if "not found" in error_lower or "does not exist" in error_lower:
            return FailureType.RESOURCE_NOT_FOUND

        if "permission" in error_lower or "unauthorized" in error_lower:
            return FailureType.PERMISSION_DENIED

        if "timeout" in error_lower or "timed out" in error_lower:
            return FailureType.TIMEOUT

        if "network" in error_lower or "connection" in error_lower:
            return FailureType.NETWORK_ERROR

        if "invalid" in error_lower or "validation" in error_lower:
            return FailureType.VALIDATION_ERROR

        return FailureType.UNKNOWN
