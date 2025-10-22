"""GCP gcloud CLI execution strategy.

Direct execution of GCP operations via gcloud CLI commands.
Supports Compute Engine, Cloud Storage, Cloud Functions, Cloud SQL, and more.
"""

import json
import re
import subprocess
import time

from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Strategy,
)


class GCPStrategy(ExecutionStrategy):
    """Execute GCP operations via direct gcloud CLI commands.

    Supports GCP services: Compute Engine, Cloud Storage, Cloud Functions,
    Cloud SQL, GKE, and more.

    Example:
        >>> strategy = GCPStrategy()
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
        >>> if result.success:
        ...     print(f"Created: {result.resources_created}")
    """

    def __init__(self, timeout: int = 600):
        """Initialize GCP CLI strategy.

        Args:
            timeout: Command timeout in seconds (default: 10 minutes)
        """
        self.timeout = timeout

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if gcloud CLI can handle this intent.

        GCP CLI can handle most GCP operations except:
        - Complex multi-resource orchestration (better with Terraform)
        - Custom code execution

        Args:
            context: Execution context

        Returns:
            True if gcloud CLI can handle this
        """
        # Check if gcloud CLI is available
        valid, _ = self.validate(context)
        if not valid:
            return False

        # Check if intent mentions GCP services
        intent_type = context.intent.intent.lower()
        params_str = str(context.intent.parameters).lower()

        # Must be GCP-related
        gcp_indicators = [
            "gcp",
            "google cloud",
            "compute engine",
            "gce",
            "cloud storage",
            "gcs",
            "cloud functions",
            "cloud sql",
            "gke",
        ]
        if not any(
            indicator in params_str or indicator in intent_type for indicator in gcp_indicators
        ):
            return False

        # Cannot handle custom code generation
        if "generate" in intent_type and "code" in intent_type:
            return False

        # Prefer Terraform for complex infrastructure
        return not any(
            keyword in intent_type
            for keyword in ["gke", "cluster", "kubernetes", "complex network", "multi-region"]
        )

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using gcloud CLI commands.

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
                    strategy=Strategy.GCP_CLI,
                    error=error_msg,
                    failure_type=FailureType.VALIDATION_ERROR,
                )

            # Generate gcloud commands from intent
            commands = self._generate_commands(context)

            if context.dry_run:
                # Dry run: just show commands
                commands_str = "\n".join(commands)
                return ExecutionResult(
                    success=True,
                    strategy=Strategy.GCP_CLI,
                    output=f"Dry run - would execute:\n{commands_str}",
                    metadata={"commands": commands, "dry_run": True},
                )

            # Execute commands
            all_resources = []
            outputs = {}

            for cmd in commands:
                # Execute command
                result = subprocess.run(
                    ["gcloud", *cmd.split()[1:]],  # Split "gcloud ..." into parts
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )

                if result.returncode != 0:
                    # Command failed
                    return ExecutionResult(
                        success=False,
                        strategy=Strategy.GCP_CLI,
                        error=result.stderr or result.stdout,
                        failure_type=self._classify_failure(result.stderr or result.stdout),
                        metadata={"command": cmd},
                    )

                # Extract resources from output
                resources = self._extract_resources(result.stdout, cmd)
                all_resources.extend(resources)

                # Parse JSON output if available
                try:
                    output_json = json.loads(result.stdout)
                    outputs.update({f"cmd_{len(outputs)}": output_json})
                except json.JSONDecodeError:
                    # Not JSON, store as text
                    if result.stdout.strip():
                        outputs[f"cmd_{len(outputs)}"] = result.stdout.strip()

            duration = time.time() - start_time

            return ExecutionResult(
                success=True,
                strategy=Strategy.GCP_CLI,
                resources_created=all_resources,
                duration_seconds=duration,
                output="\n".join(f"{k}: {v}" for k, v in outputs.items()),
                metadata={"commands": commands, "outputs": outputs},
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                strategy=Strategy.GCP_CLI,
                error=f"Command timed out after {self.timeout} seconds",
                failure_type=FailureType.TIMEOUT,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.GCP_CLI,
                error=str(e),
                failure_type=FailureType.INTERNAL_ERROR,
            )

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        """Validate gcloud CLI is available and configured.

        Args:
            context: Execution context

        Returns:
            (valid, error_message) tuple
        """
        # Check if gcloud CLI is installed
        try:
            result = subprocess.run(
                ["gcloud", "version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return (
                    False,
                    "gcloud CLI not installed. Install from: https://cloud.google.com/sdk/docs/install",
                )
        except FileNotFoundError:
            return (
                False,
                "gcloud CLI not found. Install from: https://cloud.google.com/sdk/docs/install",
            )
        except Exception as e:
            return False, f"Error checking gcloud CLI: {e}"

        # Check if gcloud is configured with a project
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return False, "gcloud CLI not configured. Run: gcloud init"
        except Exception as e:
            return False, f"Error checking gcloud configuration: {e}"

        return True, ""

    def estimate_duration(self, context: ExecutionContext) -> float:
        """Estimate execution duration in seconds.

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds
        """
        intent_type = context.intent.intent.lower()

        # Base estimates for common operations
        if "list" in intent_type or "describe" in intent_type or "get" in intent_type:
            return 5.0
        if "create" in intent_type or "provision" in intent_type:
            if "compute" in intent_type or "instance" in intent_type or "vm" in intent_type:
                return 90.0  # GCE instances take ~1.5 minutes
            if "sql" in intent_type or "database" in intent_type:
                return 300.0  # Cloud SQL takes ~5 minutes
            if "function" in intent_type:
                return 15.0
            if "bucket" in intent_type or "storage" in intent_type:
                return 3.0
            return 60.0
        if "delete" in intent_type or "terminate" in intent_type:
            return 30.0
        if "update" in intent_type or "modify" in intent_type:
            return 45.0

        return 30.0  # Default

    def _generate_commands(self, context: ExecutionContext) -> list[str]:  # noqa: C901
        """Generate gcloud CLI commands from intent.

        Args:
            context: Execution context

        Returns:
            List of gcloud commands to execute
        """
        intent_type = context.intent.intent.lower()
        params = context.intent.parameters
        commands = []

        # Compute Engine Instance operations
        if "compute" in intent_type or "instance" in intent_type or "vm" in intent_type:
            if "create" in intent_type or "provision" in intent_type or "launch" in intent_type:
                # Create Compute Engine instance
                instance_name = params.get("name", f"instance-{int(time.time())}")
                machine_type = params.get("machine_type", "e2-micro")
                zone = params.get("zone", "us-central1-a")
                image_family = params.get("image_family", "debian-11")
                image_project = params.get("image_project", "debian-cloud")

                cmd = f"gcloud compute instances create {instance_name} "
                cmd += f"--zone={zone} --machine-type={machine_type} "
                cmd += f"--image-family={image_family} --image-project={image_project}"

                if "boot_disk_size" in params:
                    cmd += f" --boot-disk-size={params['boot_disk_size']}"
                if "tags" in params:
                    tags = (
                        ",".join(params["tags"])
                        if isinstance(params["tags"], list)
                        else params["tags"]
                    )
                    cmd += f" --tags={tags}"

                commands.append(cmd)

            elif "list" in intent_type or "describe" in intent_type:
                zone = params.get("zone", "")
                if zone:
                    commands.append(f"gcloud compute instances list --zone={zone} --format=json")
                else:
                    commands.append("gcloud compute instances list --format=json")

            elif "stop" in intent_type:
                instance_name = params.get("name")
                zone = params.get("zone", "us-central1-a")
                if instance_name:
                    commands.append(f"gcloud compute instances stop {instance_name} --zone={zone}")

            elif "start" in intent_type:
                instance_name = params.get("name")
                zone = params.get("zone", "us-central1-a")
                if instance_name:
                    commands.append(f"gcloud compute instances start {instance_name} --zone={zone}")

            elif "delete" in intent_type or "terminate" in intent_type:
                instance_name = params.get("name")
                zone = params.get("zone", "us-central1-a")
                if instance_name:
                    commands.append(
                        f"gcloud compute instances delete {instance_name} --zone={zone} --quiet"
                    )

        # Cloud Storage Bucket operations
        elif "storage" in intent_type or "bucket" in intent_type or "gcs" in intent_type:
            if "create" in intent_type:
                bucket_name = params.get("bucket_name", f"bucket-{int(time.time())}")
                location = params.get("location", "us")
                storage_class = params.get("storage_class", "STANDARD")

                cmd = f"gcloud storage buckets create gs://{bucket_name} "
                cmd += f"--location={location} --default-storage-class={storage_class}"
                commands.append(cmd)

            elif "list" in intent_type:
                commands.append("gcloud storage buckets list --format=json")

            elif "delete" in intent_type:
                bucket_name = params.get("bucket_name")
                if bucket_name:
                    commands.append(f"gcloud storage buckets delete gs://{bucket_name} --quiet")

            elif "copy" in intent_type or "upload" in intent_type:
                source = params.get("source", ".")
                bucket_name = params.get("bucket_name")
                if bucket_name:
                    commands.append(f"gcloud storage cp -r {source} gs://{bucket_name}")

        # Cloud Functions operations
        elif "function" in intent_type:
            if "create" in intent_type or "deploy" in intent_type:
                function_name = params.get("function_name", f"function-{int(time.time())}")
                runtime = params.get("runtime", "python311")
                trigger = params.get("trigger", "http")
                region = params.get("region", "us-central1")
                entry_point = params.get("entry_point", "main")
                source = params.get("source", ".")

                cmd = f"gcloud functions deploy {function_name} "
                cmd += f"--runtime={runtime} --trigger-{trigger} "
                cmd += f"--region={region} --entry-point={entry_point} "
                cmd += f"--source={source}"

                if trigger == "http":
                    cmd += " --allow-unauthenticated"

                commands.append(cmd)

            elif "list" in intent_type:
                commands.append("gcloud functions list --format=json")

            elif "call" in intent_type or "invoke" in intent_type:
                function_name = params.get("function_name")
                region = params.get("region", "us-central1")
                if function_name:
                    cmd = f"gcloud functions call {function_name} --region={region}"
                    if "data" in params:
                        cmd += f" --data='{json.dumps(params['data'])}'"
                    commands.append(cmd)

            elif "delete" in intent_type:
                function_name = params.get("function_name")
                region = params.get("region", "us-central1")
                if function_name:
                    commands.append(
                        f"gcloud functions delete {function_name} --region={region} --quiet"
                    )

        # Cloud SQL Database operations
        elif "sql" in intent_type or "database" in intent_type:
            if "create" in intent_type:
                instance_name = params.get("instance_name", f"db-{int(time.time())}")
                database_version = params.get("database_version", "POSTGRES_14")
                tier = params.get("tier", "db-f1-micro")
                region = params.get("region", "us-central1")

                cmd = f"gcloud sql instances create {instance_name} "
                cmd += f"--database-version={database_version} --tier={tier} "
                cmd += f"--region={region}"

                commands.append(cmd)

            elif "list" in intent_type or "describe" in intent_type:
                commands.append("gcloud sql instances list --format=json")

            elif "delete" in intent_type:
                instance_name = params.get("instance_name")
                if instance_name:
                    commands.append(f"gcloud sql instances delete {instance_name} --quiet")

        # If no specific commands generated, create a generic command
        if not commands:
            # Try to construct a reasonable gcloud command
            service = "compute"  # default
            if "storage" in intent_type:
                service = "storage"
            elif "function" in intent_type:
                service = "functions"
            elif "sql" in intent_type:
                service = "sql"

            commands.append(f"gcloud {service} {intent_type.replace('_', '-')}")

        return commands

    def _extract_resources(self, output: str, command: str) -> list[str]:
        """Extract resource IDs/names from command output.

        Args:
            output: Command output
            command: Original command

        Returns:
            List of resource IDs/names
        """
        resources = []

        try:
            data = json.loads(output)

            # Compute Engine instances
            if isinstance(data, list):
                for item in data:
                    if "name" in item:
                        # Add full resource URI if available, else just name
                        if "selfLink" in item:
                            resources.append(item["selfLink"])
                        else:
                            resources.append(item["name"])

            # Single resource creation
            elif isinstance(data, dict):
                if "name" in data:
                    resources.append(data["name"])
                if "selfLink" in data:
                    resources.append(data["selfLink"])

        except json.JSONDecodeError:
            # Try regex patterns for common identifiers
            # GCP resource names
            resources.extend(re.findall(r"projects/[\w-]+/[\w/]+/[\w-]+", output))
            # Instance names
            resources.extend(re.findall(r"instance-[\w-]+", output))
            # Bucket names
            resources.extend(re.findall(r"gs://[\w-]+", output))
            # Function names
            resources.extend(re.findall(r"function-[\w-]+", output))

        return resources

    def _classify_failure(self, error_message: str) -> FailureType:
        """Classify failure based on error message.

        Args:
            error_message: Error message from command

        Returns:
            FailureType enum value
        """
        error_lower = error_message.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return FailureType.TIMEOUT
        if "quota" in error_lower or "rate limit" in error_lower or "limit exceeded" in error_lower:
            return FailureType.QUOTA_EXCEEDED
        if (
            "permission" in error_lower
            or "unauthorized" in error_lower
            or "forbidden" in error_lower
        ):
            return FailureType.INSUFFICIENT_PERMISSIONS
        if "not found" in error_lower or "does not exist" in error_lower:
            return FailureType.RESOURCE_NOT_FOUND
        if "already exists" in error_lower or "duplicate" in error_lower:
            return FailureType.RESOURCE_CONFLICT
        if "invalid" in error_lower or "malformed" in error_lower or "bad request" in error_lower:
            return FailureType.VALIDATION_ERROR

        return FailureType.INTERNAL_ERROR
