"""Strategy implementations for azdoit execution.

Available strategies:
- azure_cli: Direct Azure CLI commands
- terraform: Infrastructure as Code via Terraform
- mcp_client: Model Context Protocol client execution
- custom_code: Custom Python/script execution
"""

from .base_strategy import ExecutionStrategy

__all__ = ["ExecutionStrategy"]
