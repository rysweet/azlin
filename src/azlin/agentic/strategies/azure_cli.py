"""Azure CLI execution strategy.

Direct execution of Azure operations via az CLI commands.
"""

import contextlib
import json
import re
import subprocess
import time
from typing import Any

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Strategy,
)


class AzureCLIStrategy(ExecutionStrategy):
    """Execute Azure operations via direct az CLI commands.

    This is the fastest and simplest strategy for most operations.

    Example:
        >>> strategy = AzureCLIStrategy()
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
        >>> if result.success:
        ...     print(f"Created: {result.resources_created}")
    """

    def __init__(self, timeout: int = 600):
        """Initialize Azure CLI strategy.

        Args:
            timeout: Command timeout in seconds (default: 10 minutes)
        """
        self.timeout = timeout

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if Azure CLI can handle this intent.

        Azure CLI can handle most Azure operations except:
        - Complex multi-resource orchestration (better with Terraform)
        - Custom code execution

        Args:
            context: Execution context

        Returns:
            True if Azure CLI can handle this
        """
        # Check if az CLI is available
        valid, _ = self.validate(context)
        if not valid:
            return False

        # Azure CLI can handle most intents
        intent_type = context.intent.intent.lower()

        # Cannot handle custom code generation
        if "generate" in intent_type and "code" in intent_type:
            return False

        # Prefer Terraform for complex infrastructure
        return not any(
            keyword in intent_type
            for keyword in ["aks", "cluster", "kubernetes", "complex network", "multi-region"]
        )

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Azure CLI commands.

        Args:
            context: Execution context with intent and parameters

        Returns:
            ExecutionResult with success status and details
        """
        start_time = time.time()

        try:
            # Validate prerequisites
            valid, error_msg = self.validate(context)
            if not valid:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.AZURE_CLI,
                    error=error_msg,
                    failure_type=FailureType.VALIDATION_ERROR,
                )

            # Generate az commands from intent
            commands = self._generate_commands(context)

            if context.dry_run:
                # Dry run: just show commands
                output = "DRY RUN - Commands to execute:\n"
                output += "\n".join(f"  {cmd}" for cmd in commands)
                return ExecutionResult(
                    success=True,
                    strategy=Strategy.AZURE_CLI,
                    output=output,
                    duration_seconds=time.time() - start_time,
                    metadata={"commands": commands, "dry_run": True},
                )

            # Execute commands
            resources_created = []
            outputs = []

            for i, cmd in enumerate(commands, 1):
                # Execute command
                result = self._execute_command(cmd)

                if not result["success"]:
                    # Command failed
                    failure_type = self._classify_failure(result["error"])
                    return ExecutionResult(
                        success=False,
                        strategy=Strategy.AZURE_CLI,
                        output="\n".join(outputs),
                        error=result["error"],
                        failure_type=failure_type,
                        resources_created=resources_created,
                        duration_seconds=time.time() - start_time,
                        metadata={"failed_command": cmd, "command_index": i},
                    )

                outputs.append(result["output"])

                # Extract created resources
                created = self._extract_resources(result["output"], cmd)
                resources_created.extend(created)

            # Success
            duration = time.time() - start_time
            return ExecutionResult(
                success=True,
                strategy=Strategy.AZURE_CLI,
                output="\n".join(outputs),
                resources_created=resources_created,
                duration_seconds=duration,
                metadata={
                    "commands_executed": len(commands),
                    "commands": commands,
                },
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error=f"Unexpected error: {e!s}",
                failure_type=FailureType.UNKNOWN,
                duration_seconds=time.time() - start_time,
            )

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate Azure CLI prerequisites.

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if az CLI is installed
        try:
            result = subprocess.run(
                ["az", "--version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, "Azure CLI not installed"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False, "Azure CLI not found in PATH"

        # Check authentication
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, "Not authenticated with Azure (run 'az login')"
        except subprocess.TimeoutExpired:
            return False, "Azure authentication check timed out"

        return True, None

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate execution duration.

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds
        """
        # Base duration: 30 seconds per command
        command_count = len(context.intent.azlin_commands)
        base = 30 * max(1, command_count)

        # Adjust for specific operations
        intent_type = context.intent.intent.lower()

        if "provision" in intent_type or "create vm" in intent_type:
            # VM provisioning takes 5-10 minutes
            base = 600

        elif "delete" in intent_type or "kill" in intent_type:
            # Deletion is faster
            base = 120

        elif "list" in intent_type or "show" in intent_type:
            # Query operations are fast
            base = 10

        return base

    def get_strategy_type(self) -> Strategy:
        """Get strategy type."""
        return Strategy.AZURE_CLI

    def get_prerequisites(self) -> list[str]:
        """Get prerequisites for Azure CLI strategy."""
        return [
            "az CLI installed (https://aka.ms/azure-cli)",
            "Authenticated with Azure (az login)",
            "Active Azure subscription",
        ]

    def supports_dry_run(self) -> bool:
        """Azure CLI strategy supports dry-run."""
        return True

    def get_cost_factors(self, context: ExecutionContext) -> dict[str, Any]:
        """Get cost-related factors.

        Args:
            context: Execution context

        Returns:
            Dictionary of cost factors
        """
        factors = {}

        # Extract VM details
        params = context.intent.parameters
        if "vm_name" in params or "provision" in context.intent.intent:
            factors["vm_count"] = params.get("count", 1)
            factors["vm_size"] = params.get("vm_size", "Standard_B2s")

        # Extract storage details
        if "storage" in context.intent.intent:
            factors["storage_gb"] = params.get("size_gb", 128)

        return factors

    def cleanup_on_failure(self, context: ExecutionContext, partial_resources: list[str]) -> None:
        """Clean up partially created resources.

        Args:
            context: Execution context
            partial_resources: List of resource IDs to clean up
        """
        for resource_id in partial_resources:
            # Best effort cleanup, ignore errors
            with contextlib.suppress(subprocess.TimeoutExpired, Exception):
                cmd = ["az", "resource", "delete", "--ids", resource_id]
                subprocess.run(cmd, capture_output=True, timeout=30, check=False)

    def _generate_commands(self, context: ExecutionContext) -> list[str]:
        """Generate az CLI commands from intent.

        Args:
            context: Execution context

        Returns:
            List of az CLI command strings
        """
        commands = []

        # If intent already has azlin_commands, convert them to az commands
        for azlin_cmd in context.intent.azlin_commands:
            cmd = azlin_cmd.get("command", "")
            args = azlin_cmd.get("args", [])

            # Convert azlin command to az command
            az_cmd = self._convert_azlin_to_az(cmd, args, context)
            if az_cmd:
                commands.append(az_cmd)

        # If no commands generated, try to infer from intent
        if not commands:
            commands = self._infer_commands_from_intent(context)

        return commands

    def _convert_azlin_to_az(
        self, cmd: str, args: list[str], context: ExecutionContext
    ) -> str | None:
        """Convert azlin command to equivalent az CLI command.

        Args:
            cmd: Azlin command name
            args: Command arguments
            context: Execution context

        Returns:
            az CLI command string or None
        """
        # This is a simplified conversion
        # Real implementation would handle all azlin commands

        if cmd == "new":
            # azlin new -> az vm create
            vm_name = context.intent.parameters.get("vm_name", "vm")
            rg = context.resource_group or "azlin-rg"
            return f"az vm create --name {vm_name} --resource-group {rg} --image Ubuntu2204"

        if cmd == "list":
            # azlin list -> az vm list
            return "az vm list --output table"

        if cmd == "kill":
            # azlin kill -> az vm delete
            vm_name = context.intent.parameters.get("vm_name", "")
            rg = context.resource_group or "azlin-rg"
            return f"az vm delete --name {vm_name} --resource-group {rg} --yes"

        return None

    def _infer_commands_from_intent(self, context: ExecutionContext) -> list[str]:
        """Infer az commands from intent when no explicit commands provided.

        Args:
            context: Execution context

        Returns:
            List of az CLI commands
        """
        intent_type = context.intent.intent.lower()
        params = context.intent.parameters
        rg = context.resource_group or "azlin-rg"

        commands = []

        if "provision" in intent_type or "create vm" in intent_type:
            vm_name = params.get("vm_name", "vm-" + str(int(time.time())))
            commands.append(
                f"az vm create --name {vm_name} --resource-group {rg} --image Ubuntu2204"
            )

        elif "list" in intent_type and "vm" in intent_type:
            commands.append("az vm list --output table")

        elif "delete" in intent_type or "kill" in intent_type:
            vm_name = params.get("vm_name", "")
            if vm_name:
                commands.append(f"az vm delete --name {vm_name} --resource-group {rg} --yes")

        return commands

    def _execute_command(self, cmd: str) -> dict[str, Any]:
        """Execute a single az CLI command.

        Args:
            cmd: Command string to execute

        Returns:
            Dictionary with success, output, and error
        """
        try:
            # Parse command string into args
            args = cmd.split()

            result = subprocess.run(
                args,
                capture_output=True,
                timeout=self.timeout,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout.strip(),
                    "error": None,
                }
            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": f"Command timed out after {self.timeout} seconds",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": f"Execution error: {e!s}",
            }

    def _extract_resources(self, output: str, cmd: str) -> list[str]:
        """Extract created resource IDs from command output.

        Args:
            output: Command output
            cmd: Command that was executed

        Returns:
            List of resource IDs
        """
        resources = []

        try:
            # Try to parse as JSON
            data = json.loads(output)

            # Extract resource ID if present
            if isinstance(data, dict):
                if "id" in data:
                    resources.append(data["id"])
                elif "resourceId" in data:
                    resources.append(data["resourceId"])

        except json.JSONDecodeError:
            # Not JSON, try regex extraction
            # Look for Azure resource ID patterns
            pattern = r"/subscriptions/[a-f0-9-]+/resourceGroups/[^/]+/providers/[^/]+/[^/]+/[\w-]+"
            matches = re.findall(pattern, output)
            resources.extend(matches)

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

        if (
            "permission" in error_lower
            or "unauthorized" in error_lower
            or "forbidden" in error_lower
        ):
            return FailureType.PERMISSION_DENIED

        if "timeout" in error_lower or "timed out" in error_lower:
            return FailureType.TIMEOUT

        if "network" in error_lower or "connection" in error_lower:
            return FailureType.NETWORK_ERROR

        if "invalid" in error_lower or "validation" in error_lower:
            return FailureType.VALIDATION_ERROR

        return FailureType.UNKNOWN
