"""AWS CLI execution strategy.

Direct execution of AWS operations via aws CLI commands.
Supports EC2, S3, Lambda, RDS, and other AWS services.
"""

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


class AWSStrategy(ExecutionStrategy):
    """Execute AWS operations via direct aws CLI commands.

    Supports AWS services: EC2, S3, Lambda, RDS, VPC, IAM, and more.

    Example:
        >>> strategy = AWSStrategy()
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
        >>> if result.success:
        ...     print(f"Created: {result.resources_created}")
    """

    def __init__(self, timeout: int = 600):
        """Initialize AWS CLI strategy.

        Args:
            timeout: Command timeout in seconds (default: 10 minutes)
        """
        self.timeout = timeout

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if AWS CLI can handle this intent.

        AWS CLI can handle most AWS operations except:
        - Complex multi-resource orchestration (better with Terraform)
        - Custom code execution

        Args:
            context: Execution context

        Returns:
            True if AWS CLI can handle this
        """
        # Check if aws CLI is available
        valid, _ = self.validate(context)
        if not valid:
            return False

        # Check if intent mentions AWS services
        intent_text = context.user_request.lower()
        intent_type = context.intent.intent.lower()

        # Must be AWS-related
        aws_indicators = [
            "aws",
            "ec2",
            "s3",
            "lambda",
            "rds",
            "dynamodb",
            "cloudformation",
            "eks",
        ]
        if not any(indicator in intent_text or indicator in intent_type for indicator in aws_indicators):
            return False

        # Cannot handle custom code generation
        if "generate" in intent_type and "code" in intent_type:
            return False

        # Prefer Terraform for complex infrastructure
        return not any(
            keyword in intent_type
            for keyword in ["eks", "cluster", "kubernetes", "complex network", "multi-region"]
        )

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using AWS CLI commands.

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
                    strategy=Strategy.AWS_CLI,
                    error=error_msg,
                    failure_type=FailureType.VALIDATION_ERROR,
                )

            # Generate aws commands from intent
            commands = self._generate_commands(context)

            if context.dry_run:
                # Dry run: just show commands
                return ExecutionResult(
                    success=True,
                    strategy=Strategy.AWS_CLI,
                    commands_executed=commands,
                    dry_run=True,
                )

            # Execute commands
            all_resources = []
            outputs = {}

            for cmd in commands:
                # Execute command
                result = subprocess.run(
                    ["aws"] + cmd.split()[1:],  # Split "aws ..." into parts
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )

                if result.returncode != 0:
                    # Command failed
                    return ExecutionResult(
                        success=False,
                        strategy=Strategy.AWS_CLI,
                        error=result.stderr or result.stdout,
                        commands_executed=[cmd],
                        failure_type=self._classify_failure(result.stderr or result.stdout),
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
                strategy=Strategy.AWS_CLI,
                resources_created=all_resources,
                commands_executed=commands,
                outputs=outputs,
                duration=duration,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                strategy=Strategy.AWS_CLI,
                error=f"Command timed out after {self.timeout} seconds",
                failure_type=FailureType.TIMEOUT,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.AWS_CLI,
                error=str(e),
                failure_type=FailureType.INTERNAL_ERROR,
            )

    def validate(self, context: ExecutionContext) -> tuple[bool, str]:
        """Validate AWS CLI is available and configured.

        Args:
            context: Execution context

        Returns:
            (valid, error_message) tuple
        """
        # Check if aws CLI is installed
        try:
            result = subprocess.run(
                ["aws", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False, "AWS CLI not installed. Install with: pip install awscli"
        except FileNotFoundError:
            return False, "AWS CLI not found. Install with: pip install awscli"
        except Exception as e:
            return False, f"Error checking AWS CLI: {e}"

        # Check if AWS is configured
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return False, "AWS CLI not configured. Run: aws configure"
        except Exception as e:
            return False, f"Error checking AWS configuration: {e}"

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
        elif "create" in intent_type or "provision" in intent_type:
            if "ec2" in intent_type or "instance" in intent_type:
                return 120.0  # EC2 takes ~2 minutes to start
            elif "rds" in intent_type or "database" in intent_type:
                return 300.0  # RDS takes ~5 minutes
            elif "lambda" in intent_type or "function" in intent_type:
                return 10.0
            elif "s3" in intent_type or "bucket" in intent_type:
                return 3.0
            return 60.0
        elif "delete" in intent_type or "terminate" in intent_type:
            return 30.0
        elif "update" in intent_type or "modify" in intent_type:
            return 45.0

        return 30.0  # Default

    def _generate_commands(self, context: ExecutionContext) -> list[str]:
        """Generate AWS CLI commands from intent.

        Args:
            context: Execution context

        Returns:
            List of aws commands to execute
        """
        intent_type = context.intent.intent.lower()
        params = context.intent.parameters
        commands = []

        # EC2 Instance operations
        if "ec2" in intent_type or "instance" in intent_type:
            if "create" in intent_type or "provision" in intent_type or "launch" in intent_type:
                # Create EC2 instance
                instance_type = params.get("instance_type", "t2.micro")
                ami_id = params.get("ami_id", "ami-0c55b159cbfafe1f0")  # Amazon Linux 2 in us-east-1
                count = params.get("count", 1)
                name = params.get("name", f"instance-{int(time.time())}")

                cmd = f"aws ec2 run-instances --image-id {ami_id} --instance-type {instance_type} --count {count}"
                if "subnet_id" in params:
                    cmd += f" --subnet-id {params['subnet_id']}"
                if "security_group_ids" in params:
                    cmd += f" --security-group-ids {params['security_group_ids']}"
                cmd += f" --tag-specifications 'ResourceType=instance,Tags=[{{Key=Name,Value={name}}}]'"
                commands.append(cmd)

            elif "list" in intent_type or "describe" in intent_type:
                commands.append("aws ec2 describe-instances")

            elif "stop" in intent_type:
                instance_id = params.get("instance_id")
                if instance_id:
                    commands.append(f"aws ec2 stop-instances --instance-ids {instance_id}")

            elif "start" in intent_type:
                instance_id = params.get("instance_id")
                if instance_id:
                    commands.append(f"aws ec2 start-instances --instance-ids {instance_id}")

            elif "terminate" in intent_type or "delete" in intent_type:
                instance_id = params.get("instance_id")
                if instance_id:
                    commands.append(f"aws ec2 terminate-instances --instance-ids {instance_id}")

        # S3 Bucket operations
        elif "s3" in intent_type or "bucket" in intent_type:
            if "create" in intent_type:
                bucket_name = params.get("bucket_name", f"bucket-{int(time.time())}")
                region = params.get("region", "us-east-1")
                if region == "us-east-1":
                    commands.append(f"aws s3 mb s3://{bucket_name}")
                else:
                    commands.append(f"aws s3 mb s3://{bucket_name} --region {region}")

            elif "list" in intent_type:
                commands.append("aws s3 ls")

            elif "delete" in intent_type:
                bucket_name = params.get("bucket_name")
                if bucket_name:
                    commands.append(f"aws s3 rb s3://{bucket_name} --force")

            elif "sync" in intent_type or "upload" in intent_type:
                source = params.get("source", ".")
                bucket_name = params.get("bucket_name")
                if bucket_name:
                    commands.append(f"aws s3 sync {source} s3://{bucket_name}")

        # Lambda Function operations
        elif "lambda" in intent_type or "function" in intent_type:
            if "create" in intent_type or "deploy" in intent_type:
                function_name = params.get("function_name", f"function-{int(time.time())}")
                runtime = params.get("runtime", "python3.11")
                handler = params.get("handler", "lambda_function.lambda_handler")
                role_arn = params.get("role_arn")
                zip_file = params.get("zip_file", "function.zip")

                if role_arn:
                    cmd = f"aws lambda create-function --function-name {function_name} "
                    cmd += f"--runtime {runtime} --handler {handler} --role {role_arn} "
                    cmd += f"--zip-file fileb://{zip_file}"
                    commands.append(cmd)

            elif "list" in intent_type:
                commands.append("aws lambda list-functions")

            elif "invoke" in intent_type:
                function_name = params.get("function_name")
                if function_name:
                    commands.append(f"aws lambda invoke --function-name {function_name} response.json")

            elif "delete" in intent_type:
                function_name = params.get("function_name")
                if function_name:
                    commands.append(f"aws lambda delete-function --function-name {function_name}")

        # RDS Database operations
        elif "rds" in intent_type or "database" in intent_type:
            if "create" in intent_type:
                db_instance_id = params.get("db_instance_id", f"db-{int(time.time())}")
                db_instance_class = params.get("db_instance_class", "db.t3.micro")
                engine = params.get("engine", "postgres")
                master_username = params.get("master_username", "admin")
                master_password = params.get("master_password", "password123")
                allocated_storage = params.get("allocated_storage", 20)

                cmd = f"aws rds create-db-instance --db-instance-identifier {db_instance_id} "
                cmd += f"--db-instance-class {db_instance_class} --engine {engine} "
                cmd += f"--master-username {master_username} --master-user-password {master_password} "
                cmd += f"--allocated-storage {allocated_storage}"
                commands.append(cmd)

            elif "list" in intent_type or "describe" in intent_type:
                commands.append("aws rds describe-db-instances")

            elif "delete" in intent_type:
                db_instance_id = params.get("db_instance_id")
                if db_instance_id:
                    cmd = f"aws rds delete-db-instance --db-instance-identifier {db_instance_id} "
                    cmd += "--skip-final-snapshot"
                    commands.append(cmd)

        # If no specific commands generated, create a generic command
        if not commands:
            commands.append(f"aws {intent_type.replace('_', '-')}")

        return commands

    def _extract_resources(self, output: str, command: str) -> list[str]:
        """Extract resource IDs/ARNs from command output.

        Args:
            output: Command output
            command: Original command

        Returns:
            List of resource IDs
        """
        resources = []

        try:
            data = json.loads(output)

            # EC2 instances
            if "Instances" in data:
                for instance in data.get("Instances", []):
                    if "InstanceId" in instance:
                        resources.append(instance["InstanceId"])

            # S3 buckets (from mb command output or ls)
            if "Buckets" in data:
                for bucket in data.get("Buckets", []):
                    if "Name" in bucket:
                        resources.append(f"s3://{bucket['Name']}")

            # Lambda functions
            if "FunctionArn" in data:
                resources.append(data["FunctionArn"])
            if "Functions" in data:
                for func in data.get("Functions", []):
                    if "FunctionArn" in func:
                        resources.append(func["FunctionArn"])

            # RDS instances
            if "DBInstances" in data:
                for db in data.get("DBInstances", []):
                    if "DBInstanceIdentifier" in db:
                        resources.append(db["DBInstanceIdentifier"])
            if "DBInstance" in data:
                if "DBInstanceIdentifier" in data["DBInstance"]:
                    resources.append(data["DBInstance"]["DBInstanceIdentifier"])

        except json.JSONDecodeError:
            # Try regex patterns for common IDs
            # EC2 instance IDs: i-xxxxxxxxxxxxxxxxx
            resources.extend(re.findall(r"i-[0-9a-f]{17}", output))
            # S3 bucket names in output
            resources.extend(re.findall(r"s3://[\w-]+", output))
            # Lambda ARNs
            resources.extend(re.findall(r"arn:aws:lambda:[\w-]+:\d+:function:[\w-]+", output))
            # RDS instance IDs
            resources.extend(re.findall(r"db-[\w-]+", output))

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
        elif "throttling" in error_lower or "rate exceeded" in error_lower:
            return FailureType.QUOTA_EXCEEDED
        elif "access denied" in error_lower or "unauthorized" in error_lower or "forbidden" in error_lower:
            return FailureType.INSUFFICIENT_PERMISSIONS
        elif "not found" in error_lower or "does not exist" in error_lower:
            return FailureType.RESOURCE_NOT_FOUND
        elif "already exists" in error_lower or "duplicate" in error_lower:
            return FailureType.RESOURCE_CONFLICT
        elif "invalid" in error_lower or "malformed" in error_lower:
            return FailureType.VALIDATION_ERROR

        return FailureType.INTERNAL_ERROR
