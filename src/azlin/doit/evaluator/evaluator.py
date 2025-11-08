"""Goal evaluator - determines if goals are achieved."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from azlin.doit.engine.models import ActionResult
from azlin.doit.goals import Goal, GoalStatus, ResourceType


@dataclass
class EvaluationResult:
    """Result of evaluating a goal."""

    goal_id: str
    status: GoalStatus
    confidence: float  # 0.0 to 1.0
    criteria_met: list[str] = field(default_factory=list)
    criteria_failed: list[str] = field(default_factory=list)
    evidence: dict[str, dict] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)
    teaching_notes: str = ""


class GoalEvaluator:
    """Evaluates whether goals have been achieved."""

    def __init__(self, prompts_dir: Path | None = None):
        """Initialize evaluator."""
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent / "prompts" / "doit"
        self.prompts_dir = prompts_dir
        self.evaluation_prompt = self._load_prompt("goal_evaluation.md")

    def _load_prompt(self, filename: str) -> str:
        """Load prompt file."""
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text()
        return ""

    def evaluate(self, goal: Goal, action_results: list[ActionResult]) -> EvaluationResult:
        """Evaluate if a goal has been achieved.

        Args:
            goal: Goal to evaluate
            action_results: Results from actions taken for this goal

        Returns:
            Evaluation result with status and confidence
        """
        # Get most recent result
        if not action_results:
            return EvaluationResult(
                goal_id=goal.id,
                status=GoalStatus.PENDING,
                confidence=1.0,
                criteria_failed=["No actions executed yet"],
                teaching_notes="Goal has not been attempted yet.",
            )

        latest = action_results[-1]

        # If last action failed, goal is not achieved
        if not latest.success:
            return self._evaluate_failure(goal, action_results)

        # Check resource-specific criteria
        if goal.type == ResourceType.RESOURCE_GROUP:
            return self._evaluate_resource_group(goal, latest)
        if goal.type == ResourceType.STORAGE_ACCOUNT:
            return self._evaluate_storage_account(goal, latest)
        if goal.type == ResourceType.KEY_VAULT:
            return self._evaluate_key_vault(goal, latest)
        if goal.type == ResourceType.COSMOS_DB:
            return self._evaluate_cosmos_db(goal, latest)
        if goal.type == ResourceType.APP_SERVICE_PLAN:
            return self._evaluate_app_service_plan(goal, latest)
        if goal.type == ResourceType.APP_SERVICE:
            return self._evaluate_app_service(goal, latest)
        if goal.type == ResourceType.API_MANAGEMENT:
            return self._evaluate_api_management(goal, latest)
        if goal.type == ResourceType.CONNECTION:
            return self._evaluate_connection(goal, latest)
        # Generic evaluation
        return self._evaluate_generic(goal, latest)

    def _evaluate_failure(self, goal: Goal, action_results: list[ActionResult]) -> EvaluationResult:
        """Evaluate a failed goal."""
        latest = action_results[-1]

        # Check if retryable
        if latest.is_transient_error and goal.can_retry():
            return EvaluationResult(
                goal_id=goal.id,
                status=GoalStatus.PENDING,  # Will retry
                confidence=0.5,
                criteria_failed=["Action failed with transient error"],
                teaching_notes=f"Transient error encountered: {latest.error}. Will retry.",
            )
        if latest.is_recoverable_error and goal.can_retry():
            return EvaluationResult(
                goal_id=goal.id,
                status=GoalStatus.PENDING,  # Will retry with adjustments
                confidence=0.3,
                criteria_failed=["Action failed with recoverable error"],
                teaching_notes=f"Recoverable error: {latest.error}. Will adjust parameters and retry.",
            )
        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.FAILED,
            confidence=1.0,
            criteria_failed=["Action failed and cannot recover"],
            evidence={"error": {"type": "unrecoverable", "message": latest.error}},
            teaching_notes=f"Goal failed: {latest.error}. No recovery strategy available.",
        )

    def _evaluate_resource_group(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate resource group deployment."""
        criteria_met = []
        criteria_failed = []
        evidence = {}

        # Check existence
        if result.resource_id:
            criteria_met.append("Resource group exists in Azure")
            evidence["existence"] = {
                "verified": True,
                "resource_id": result.resource_id,
            }
        else:
            criteria_failed.append("Resource group ID not found")

        # Check provisioning state
        if result.outputs.get("properties", {}).get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")
            evidence["provisioning"] = {"state": "Succeeded"}
        else:
            criteria_failed.append("Provisioning state not Succeeded")

        # Verify with az CLI
        verify_result = self._verify_resource_exists(
            "group", goal.name, goal.parameters.get("location")
        )
        if verify_result:
            criteria_met.append("Verified via az CLI")
            evidence["verification"] = {"verified": True, "method": "az_cli"}

        confidence = len(criteria_met) / (len(criteria_met) + len(criteria_failed))

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            criteria_failed=criteria_failed,
            evidence=evidence,
            teaching_notes=(
                f"Resource group '{goal.name}' deployed successfully. "
                f"This is the foundation for all other resources."
            ),
        )

    def _evaluate_storage_account(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate storage account deployment."""
        criteria_met = []
        criteria_failed = []

        if result.resource_id:
            criteria_met.append("Storage account exists")

        if result.outputs.get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")

        if result.outputs.get("primaryEndpoints"):
            criteria_met.append("Primary endpoints available")

        confidence = 1.0 if len(criteria_met) >= 2 else 0.6

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            criteria_failed=criteria_failed,
            teaching_notes=f"Storage account '{goal.name}' deployed with secure settings (HTTPS only, TLS 1.2).",
        )

    def _evaluate_key_vault(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate Key Vault deployment."""
        criteria_met = []

        if result.resource_id:
            criteria_met.append("Key Vault exists")

        if result.outputs.get("properties", {}).get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")

        if result.outputs.get("properties", {}).get("vaultUri"):
            criteria_met.append("Vault URI available")

        confidence = 1.0 if len(criteria_met) >= 2 else 0.6

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes=f"Key Vault '{goal.name}' deployed with RBAC authorization enabled.",
        )

    def _evaluate_cosmos_db(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate Cosmos DB deployment."""
        criteria_met = []

        if result.resource_id:
            criteria_met.append("Cosmos DB account exists")

        if result.outputs.get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")

        if result.outputs.get("documentEndpoint"):
            criteria_met.append("Document endpoint available")

        confidence = 1.0 if len(criteria_met) >= 2 else 0.6

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes=f"Cosmos DB '{goal.name}' deployed with Session consistency level.",
        )

    def _evaluate_app_service_plan(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate App Service Plan deployment."""
        criteria_met = []

        if result.resource_id:
            criteria_met.append("App Service Plan exists")

        if result.outputs.get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")

        confidence = 1.0 if len(criteria_met) >= 2 else 0.6

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes=f"App Service Plan '{goal.name}' deployed.",
        )

    def _evaluate_app_service(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate App Service deployment."""
        criteria_met = []

        if result.resource_id:
            criteria_met.append("App Service exists")

        if result.outputs.get("state") == "Running":
            criteria_met.append("App Service is running")

        if result.outputs.get("defaultHostName"):
            criteria_met.append("Default hostname assigned")

        if result.outputs.get("identity"):
            criteria_met.append("Managed identity configured")

        confidence = 1.0 if len(criteria_met) >= 3 else 0.7

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes=f"App Service '{goal.name}' deployed with managed identity for secure access to other resources.",
        )

    def _evaluate_api_management(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate API Management deployment."""
        criteria_met = []

        if result.resource_id:
            criteria_met.append("API Management exists")

        if result.outputs.get("provisioningState") == "Succeeded":
            criteria_met.append("Provisioning state is Succeeded")

        if result.outputs.get("gatewayUrl"):
            criteria_met.append("Gateway URL available")

        confidence = 1.0 if len(criteria_met) >= 2 else 0.6

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes=f"API Management '{goal.name}' deployed. Note: APIM provisioning can take 30-45 minutes.",
        )

    def _evaluate_connection(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Evaluate connection between resources."""
        criteria_met = []

        if result.success:
            criteria_met.append("Connection configured")

        confidence = 1.0 if result.success else 0.0

        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.COMPLETED if confidence > 0.8 else GoalStatus.FAILED,
            confidence=confidence,
            criteria_met=criteria_met,
            teaching_notes="Connection established between resources using managed identity and Key Vault.",
        )

    def _evaluate_generic(self, goal: Goal, result: ActionResult) -> EvaluationResult:
        """Generic evaluation for unknown resource types."""
        if result.success and result.resource_id:
            return EvaluationResult(
                goal_id=goal.id,
                status=GoalStatus.COMPLETED,
                confidence=0.8,
                criteria_met=["Resource created successfully"],
                teaching_notes=f"Resource '{goal.name}' of type {goal.type.value} deployed.",
            )
        return EvaluationResult(
            goal_id=goal.id,
            status=GoalStatus.FAILED,
            confidence=1.0,
            criteria_failed=["Resource creation failed"],
        )

    def _verify_resource_exists(
        self, resource_type: str, name: str, location: str | None = None
    ) -> bool:
        """Verify resource exists via az CLI."""
        try:
            if resource_type == "group":
                cmd_list = ["az", "group", "show", "--name", name, "--output", "json"]
            else:
                return True  # Skip verification for other types for now

            result = subprocess.run(
                cmd_list,
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            return result.returncode == 0

        except Exception:
            return False
