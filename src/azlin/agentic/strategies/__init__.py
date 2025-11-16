"""Strategy implementations for azdoit execution.

Available strategies:
- azure_cli: Direct Azure CLI commands
- terraform: Infrastructure as Code via Terraform
- custom_code: Custom Python/script execution
"""

from .azure_cli import AzureCLIStrategy
from .base_strategy import ExecutionStrategy
from .terraform_strategy import TerraformStrategy

__all__ = [
    "AzureCLIStrategy",
    "ExecutionStrategy",
    "TerraformStrategy",
]
