"""Strategy implementations for azdoit execution.

Available strategies:
- azure_cli: Direct Azure CLI commands
- terraform: Infrastructure as Code via Terraform
- mcp_client: Model Context Protocol client execution
- custom_code: Custom Python/script execution
"""

from .azure_cli import AzureCLIStrategy
from .base_strategy import ExecutionStrategy
from .mcp_client_strategy import MCPClientStrategy
from .terraform_strategy import TerraformStrategy

__all__ = [
    "AzureCLIStrategy",
    "ExecutionStrategy",
    "MCPClientStrategy",
    "TerraformStrategy",
]
