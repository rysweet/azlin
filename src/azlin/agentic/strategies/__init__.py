"""Strategy implementations for azdoit execution.

Available strategies:
- azure_cli: Direct Azure CLI commands
- aws_cli: Direct AWS CLI commands
- gcp_cli: Direct GCP gcloud CLI commands
- terraform: Infrastructure as Code via Terraform
- mcp_client: Model Context Protocol client execution
- custom_code: Custom Python/script execution
"""

from .aws_strategy import AWSStrategy
from .azure_cli import AzureCLIStrategy
from .base_strategy import ExecutionStrategy
from .gcp_strategy import GCPStrategy
from .mcp_client_strategy import MCPClientStrategy
from .terraform_strategy import TerraformStrategy

__all__ = [
    "AWSStrategy",
    "AzureCLIStrategy",
    "ExecutionStrategy",
    "GCPStrategy",
    "MCPClientStrategy",
    "TerraformStrategy",
]
