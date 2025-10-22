# azdoit Enhancement API Contracts

This document defines the API contracts for all azdoit enhancement modules following the **bricks & studs** philosophy.

## Design Principles

1. **Self-contained modules** - Each module is a "brick" with clear boundaries
2. **Stable interfaces** - Public APIs are "studs" that modules connect through
3. **Type safety** - Full type hints for all public methods
4. **Observable** - Return structured results, not side effects
5. **Idempotent** - Operations can be safely retried
6. **Testable** - Clear inputs/outputs for easy testing
7. **Regeneratable** - Can rebuild any module from this specification

## Module Overview

```
agentic/
├── intent_parser.py          [EXISTS] - Natural language → Intent
├── command_executor.py       [EXISTS] - Execute commands
├── strategy_selector.py      [NEW] - Choose execution strategy
├── objective_state.py        [NEW] - Persist objectives to JSON
├── cost_estimator.py         [NEW] - Azure cost estimation
├── recovery_agent.py         [NEW] - Failure recovery & research
├── terraform_generator.py    [NEW] - Generate Terraform HCL
├── mcp_client.py            [NEW] - Azure MCP Server client
├── mslearn_client.py        [NEW] - MS Learn search
└── strategies/
    ├── base.py              [NEW] - Strategy interface
    ├── azure_cli.py         [NEW] - Azure CLI strategy
    ├── terraform.py         [NEW] - Terraform strategy
    ├── mcp_server.py        [NEW] - MCP Server strategy
    └── custom_code.py       [NEW] - Python code gen strategy
```

---

## 1. Strategy System

### 1.1 Base Strategy Interface (`strategies/base.py`)

**Purpose**: Define the contract all execution strategies must implement.

```python
"""Base strategy interface for azdoit execution."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyType(Enum):
    """Available execution strategies."""
    AZURE_CLI = "azure_cli"
    TERRAFORM = "terraform"
    MCP_SERVER = "mcp_server"
    CUSTOM_CODE = "custom_code"


@dataclass
class ExecutionContext:
    """Context passed to all strategies."""
    intent: Dict[str, Any]           # Original parsed intent
    parameters: Dict[str, Any]        # Extracted parameters
    resource_group: Optional[str]     # Target resource group
    dry_run: bool = False            # Preview mode
    verbose: bool = False            # Detailed output
    cost_limit: Optional[float] = None  # Max cost in USD


@dataclass
class ExecutionResult:
    """Standard result from all strategies."""
    success: bool
    strategy: StrategyType
    outputs: Dict[str, Any]          # Strategy-specific outputs
    resources_created: List[str]     # Azure resource IDs
    cost_estimate: Optional[float]   # Estimated cost in USD
    execution_time: float            # Seconds
    error: Optional[str] = None      # Error message if failed
    metadata: Dict[str, Any] = None  # Additional info


class ExecutionStrategy(ABC):
    """Base interface for execution strategies."""

    @abstractmethod
    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if this strategy can handle the intent.

        Args:
            context: Execution context with intent

        Returns:
            True if strategy can handle this intent
        """
        pass

    @abstractmethod
    def estimate_cost(self, context: ExecutionContext) -> float:
        """Estimate cost of executing this intent.

        Args:
            context: Execution context

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute the intent using this strategy.

        Args:
            context: Execution context

        Returns:
            Execution result with outputs and status
        """
        pass

    @abstractmethod
    def validate(self, result: ExecutionResult) -> bool:
        """Validate that execution succeeded as intended.

        Args:
            result: Execution result to validate

        Returns:
            True if validation passed
        """
        pass

    @abstractmethod
    def rollback(self, result: ExecutionResult) -> bool:
        """Rollback changes if execution failed.

        Args:
            result: Failed execution result

        Returns:
            True if rollback succeeded
        """
        pass
```

### 1.2 Strategy Selector (`strategy_selector.py`)

**Purpose**: Choose the best execution strategy for a given intent.

```python
"""Strategy selector for choosing optimal execution approach."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .strategies.base import ExecutionContext, ExecutionStrategy, StrategyType


@dataclass
class StrategyScore:
    """Scoring result for a strategy."""
    strategy: StrategyType
    score: float              # 0.0 to 1.0
    can_handle: bool
    cost_estimate: float      # USD
    reasons: List[str]        # Why this score


class StrategySelector:
    """Selects optimal execution strategy for intents."""

    def __init__(self, strategies: Optional[Dict[StrategyType, ExecutionStrategy]] = None):
        """Initialize strategy selector.

        Args:
            strategies: Map of strategy types to implementations.
                       If None, loads all available strategies.
        """
        self.strategies = strategies or self._load_strategies()

    def select(
        self,
        context: ExecutionContext,
        preferences: Optional[Dict[str, Any]] = None
    ) -> ExecutionStrategy:
        """Select best strategy for the given intent.

        Args:
            context: Execution context with intent
            preferences: Optional user preferences
                - prefer_terraform: bool
                - max_cost: float
                - require_idempotent: bool

        Returns:
            Best matching strategy

        Raises:
            NoStrategyFoundError: If no strategy can handle intent
        """
        scores = self.score_strategies(context, preferences)

        # Filter to strategies that can handle
        viable = [s for s in scores if s.can_handle]
        if not viable:
            raise NoStrategyFoundError(
                f"No strategy can handle intent: {context.intent['intent']}"
            )

        # Apply preferences and cost constraints
        viable = self._apply_constraints(viable, context, preferences)

        # Select highest scoring
        best = max(viable, key=lambda s: s.score)
        return self.strategies[best.strategy]

    def score_strategies(
        self,
        context: ExecutionContext,
        preferences: Optional[Dict[str, Any]] = None
    ) -> List[StrategyScore]:
        """Score all strategies for the intent.

        Args:
            context: Execution context
            preferences: Optional preferences

        Returns:
            List of strategy scores, sorted by score descending
        """
        scores = []

        for strategy_type, strategy in self.strategies.items():
            can_handle = strategy.can_handle(context)

            if can_handle:
                cost = strategy.estimate_cost(context)
                score = self._calculate_score(
                    strategy_type, context, cost, preferences
                )
            else:
                cost = 0.0
                score = 0.0

            reasons = self._explain_score(
                strategy_type, can_handle, score, cost, preferences
            )

            scores.append(StrategyScore(
                strategy=strategy_type,
                score=score,
                can_handle=can_handle,
                cost_estimate=cost,
                reasons=reasons
            ))

        return sorted(scores, key=lambda s: s.score, reverse=True)

    def _load_strategies(self) -> Dict[StrategyType, ExecutionStrategy]:
        """Load all available strategy implementations."""
        from .strategies.azure_cli import AzureCLIStrategy
        from .strategies.custom_code import CustomCodeStrategy
        from .strategies.mcp_server import MCPServerStrategy
        from .strategies.terraform import TerraformStrategy

        return {
            StrategyType.AZURE_CLI: AzureCLIStrategy(),
            StrategyType.TERRAFORM: TerraformStrategy(),
            StrategyType.MCP_SERVER: MCPServerStrategy(),
            StrategyType.CUSTOM_CODE: CustomCodeStrategy(),
        }

    def _calculate_score(
        self,
        strategy_type: StrategyType,
        context: ExecutionContext,
        cost: float,
        preferences: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate score for a strategy (0.0 to 1.0)."""
        # Scoring logic based on:
        # - Intent complexity
        # - Cost efficiency
        # - User preferences
        # - Strategy capabilities
        pass

    def _apply_constraints(
        self,
        scores: List[StrategyScore],
        context: ExecutionContext,
        preferences: Optional[Dict[str, Any]]
    ) -> List[StrategyScore]:
        """Apply cost and preference constraints."""
        pass

    def _explain_score(
        self,
        strategy_type: StrategyType,
        can_handle: bool,
        score: float,
        cost: float,
        preferences: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate human-readable reasons for score."""
        pass


class NoStrategyFoundError(Exception):
    """Raised when no strategy can handle an intent."""
    pass
```

### 1.3 Azure CLI Strategy (`strategies/azure_cli.py`)

**Purpose**: Execute intents using Azure CLI commands.

```python
"""Azure CLI execution strategy."""

import subprocess
from typing import List

from .base import ExecutionContext, ExecutionResult, ExecutionStrategy, StrategyType


class AzureCLIStrategy(ExecutionStrategy):
    """Executes intents via Azure CLI commands."""

    def __init__(self):
        """Initialize Azure CLI strategy."""
        self._verify_azure_cli()

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if intent can be executed via Azure CLI.

        Args:
            context: Execution context

        Returns:
            True if Azure CLI can handle this intent
        """
        # Most Azure operations supported
        supported_intents = {
            "provision_vm", "list_vms", "start_vm", "stop_vm",
            "delete_vm", "create_storage", "list_storage",
            "cost_report", "resource_list"
        }
        return context.intent.get("intent") in supported_intents

    def estimate_cost(self, context: ExecutionContext) -> float:
        """Estimate cost of Azure CLI execution.

        Azure CLI itself is free, but we estimate resource costs.

        Args:
            context: Execution context

        Returns:
            Estimated resource cost in USD
        """
        from ..cost_estimator import AzureCostEstimator

        estimator = AzureCostEstimator()
        return estimator.estimate_intent(context.intent, context.parameters)

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute intent using Azure CLI.

        Args:
            context: Execution context

        Returns:
            Execution result
        """
        commands = self._generate_commands(context)

        resources_created = []
        outputs = {}
        start_time = time.time()

        try:
            for cmd in commands:
                if context.dry_run:
                    print(f"[DRY RUN] Would execute: {cmd}")
                    continue

                result = self._run_command(cmd, context.verbose)

                if not result["success"]:
                    return ExecutionResult(
                        success=False,
                        strategy=StrategyType.AZURE_CLI,
                        outputs=outputs,
                        resources_created=resources_created,
                        cost_estimate=self.estimate_cost(context),
                        execution_time=time.time() - start_time,
                        error=result["stderr"]
                    )

                # Track created resources
                resources = self._extract_resources(result["stdout"])
                resources_created.extend(resources)
                outputs[cmd] = result["stdout"]

            return ExecutionResult(
                success=True,
                strategy=StrategyType.AZURE_CLI,
                outputs=outputs,
                resources_created=resources_created,
                cost_estimate=self.estimate_cost(context),
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=StrategyType.AZURE_CLI,
                outputs=outputs,
                resources_created=resources_created,
                cost_estimate=0.0,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    def validate(self, result: ExecutionResult) -> bool:
        """Validate Azure CLI execution.

        Args:
            result: Execution result

        Returns:
            True if resources exist and are in expected state
        """
        if not result.success:
            return False

        # Verify resources exist
        for resource_id in result.resources_created:
            if not self._resource_exists(resource_id):
                return False

        return True

    def rollback(self, result: ExecutionResult) -> bool:
        """Rollback failed Azure CLI execution.

        Args:
            result: Failed execution result

        Returns:
            True if cleanup succeeded
        """
        success = True

        for resource_id in result.resources_created:
            try:
                self._delete_resource(resource_id)
            except Exception:
                success = False

        return success

    def _verify_azure_cli(self) -> None:
        """Verify Azure CLI is installed and authenticated."""
        pass

    def _generate_commands(self, context: ExecutionContext) -> List[str]:
        """Generate Azure CLI commands for intent."""
        pass

    def _run_command(self, cmd: str, verbose: bool) -> Dict[str, Any]:
        """Run Azure CLI command."""
        pass

    def _extract_resources(self, output: str) -> List[str]:
        """Extract resource IDs from command output."""
        pass

    def _resource_exists(self, resource_id: str) -> bool:
        """Check if Azure resource exists."""
        pass

    def _delete_resource(self, resource_id: str) -> None:
        """Delete Azure resource."""
        pass
```

### 1.4 Terraform Strategy (`strategies/terraform.py`)

**Purpose**: Execute intents using Terraform infrastructure as code.

```python
"""Terraform execution strategy."""

import tempfile
from pathlib import Path
from typing import Dict, Optional

from .base import ExecutionContext, ExecutionResult, ExecutionStrategy, StrategyType


class TerraformStrategy(ExecutionStrategy):
    """Executes intents via Terraform infrastructure as code."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        """Initialize Terraform strategy.

        Args:
            workspace_dir: Directory for Terraform workspaces
        """
        self.workspace_dir = workspace_dir or Path(tempfile.gettempdir()) / "azdoit_terraform"
        self.workspace_dir.mkdir(exist_ok=True)
        self._verify_terraform()

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if intent can be executed via Terraform.

        Terraform is best for:
        - Infrastructure provisioning
        - Multi-resource deployments
        - Reproducible environments

        Not ideal for:
        - One-off commands
        - Simple queries
        - Immediate operations

        Args:
            context: Execution context

        Returns:
            True if Terraform should handle this
        """
        terraform_intents = {
            "provision_vm", "create_storage", "setup_networking",
            "provision_fleet", "create_environment"
        }

        intent = context.intent.get("intent")

        # Check if multi-resource deployment
        multi_resource = context.parameters.get("count", 1) > 1

        return intent in terraform_intents or multi_resource

    def estimate_cost(self, context: ExecutionContext) -> float:
        """Estimate cost using Terraform plan.

        Args:
            context: Execution context

        Returns:
            Estimated cost in USD
        """
        from ..terraform_generator import TerraformGenerator
        from ..cost_estimator import AzureCostEstimator

        generator = TerraformGenerator()
        config = generator.generate(context.intent, context.parameters)

        estimator = AzureCostEstimator()
        return estimator.estimate_terraform(config)

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute intent using Terraform.

        Workflow:
        1. Generate Terraform configuration
        2. Initialize Terraform workspace
        3. Run terraform plan
        4. Apply if not dry-run
        5. Extract outputs and resource IDs

        Args:
            context: Execution context

        Returns:
            Execution result
        """
        from ..terraform_generator import TerraformGenerator

        workspace = self._create_workspace(context)
        generator = TerraformGenerator()

        start_time = time.time()

        try:
            # Generate configuration
            config = generator.generate(context.intent, context.parameters)
            config_path = workspace / "main.tf"
            config_path.write_text(config)

            # Initialize
            self._run_terraform("init", workspace, context.verbose)

            # Plan
            plan_output = self._run_terraform("plan", workspace, context.verbose)

            if context.dry_run:
                return ExecutionResult(
                    success=True,
                    strategy=StrategyType.TERRAFORM,
                    outputs={"plan": plan_output},
                    resources_created=[],
                    cost_estimate=self.estimate_cost(context),
                    execution_time=time.time() - start_time
                )

            # Apply
            apply_output = self._run_terraform(
                "apply -auto-approve", workspace, context.verbose
            )

            # Extract resources
            state = self._get_terraform_state(workspace)
            resources_created = self._extract_resource_ids(state)

            return ExecutionResult(
                success=True,
                strategy=StrategyType.TERRAFORM,
                outputs={
                    "plan": plan_output,
                    "apply": apply_output,
                    "state": state
                },
                resources_created=resources_created,
                cost_estimate=self.estimate_cost(context),
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=StrategyType.TERRAFORM,
                outputs={},
                resources_created=[],
                cost_estimate=0.0,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    def validate(self, result: ExecutionResult) -> bool:
        """Validate Terraform execution.

        Args:
            result: Execution result

        Returns:
            True if Terraform state is consistent with Azure
        """
        pass

    def rollback(self, result: ExecutionResult) -> bool:
        """Rollback using terraform destroy.

        Args:
            result: Failed execution result

        Returns:
            True if destroy succeeded
        """
        pass

    def _verify_terraform(self) -> None:
        """Verify Terraform is installed."""
        pass

    def _create_workspace(self, context: ExecutionContext) -> Path:
        """Create Terraform workspace for this execution."""
        pass

    def _run_terraform(self, cmd: str, workspace: Path, verbose: bool) -> str:
        """Run Terraform command in workspace."""
        pass

    def _get_terraform_state(self, workspace: Path) -> Dict[str, Any]:
        """Get Terraform state as JSON."""
        pass

    def _extract_resource_ids(self, state: Dict[str, Any]) -> List[str]:
        """Extract Azure resource IDs from Terraform state."""
        pass
```

### 1.5 MCP Server Strategy (`strategies/mcp_server.py`)

**Purpose**: Execute intents using Azure MCP Server.

```python
"""Azure MCP Server execution strategy."""

from typing import Dict

from .base import ExecutionContext, ExecutionResult, ExecutionStrategy, StrategyType


class MCPServerStrategy(ExecutionStrategy):
    """Executes intents via Azure MCP Server."""

    def __init__(self, server_url: Optional[str] = None):
        """Initialize MCP Server strategy.

        Args:
            server_url: MCP Server endpoint. If None, uses default.
        """
        from ..mcp_client import AzureMCPClient

        self.client = AzureMCPClient(server_url)

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if MCP Server can handle intent.

        MCP Server is ideal for:
        - High-level resource operations
        - Managed Azure services
        - Operations with built-in best practices

        Args:
            context: Execution context

        Returns:
            True if MCP Server supports this operation
        """
        # Query MCP Server for capabilities
        capabilities = self.client.get_capabilities()
        intent = context.intent.get("intent")

        return intent in capabilities.get("supported_operations", [])

    def estimate_cost(self, context: ExecutionContext) -> float:
        """Estimate cost via MCP Server.

        Args:
            context: Execution context

        Returns:
            Estimated cost in USD
        """
        return self.client.estimate_cost(
            context.intent.get("intent"),
            context.parameters
        )

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute intent via MCP Server.

        Args:
            context: Execution context

        Returns:
            Execution result
        """
        start_time = time.time()

        try:
            response = self.client.execute(
                operation=context.intent.get("intent"),
                parameters=context.parameters,
                dry_run=context.dry_run
            )

            return ExecutionResult(
                success=response.get("success", False),
                strategy=StrategyType.MCP_SERVER,
                outputs=response.get("outputs", {}),
                resources_created=response.get("resources", []),
                cost_estimate=response.get("cost", 0.0),
                execution_time=time.time() - start_time,
                error=response.get("error")
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=StrategyType.MCP_SERVER,
                outputs={},
                resources_created=[],
                cost_estimate=0.0,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    def validate(self, result: ExecutionResult) -> bool:
        """Validate MCP Server execution.

        Args:
            result: Execution result

        Returns:
            True if validation passed
        """
        if not result.success:
            return False

        return self.client.validate(result.resources_created)

    def rollback(self, result: ExecutionResult) -> bool:
        """Rollback via MCP Server.

        Args:
            result: Failed execution result

        Returns:
            True if rollback succeeded
        """
        try:
            self.client.rollback(result.resources_created)
            return True
        except Exception:
            return False
```

### 1.6 Custom Code Strategy (`strategies/custom_code.py`)

**Purpose**: Generate and execute custom Python code for complex intents.

```python
"""Custom code generation strategy."""

import tempfile
from pathlib import Path
from typing import Optional

from .base import ExecutionContext, ExecutionResult, ExecutionStrategy, StrategyType


class CustomCodeStrategy(ExecutionStrategy):
    """Generates and executes custom Python code for complex intents."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize custom code strategy.

        Args:
            api_key: Anthropic API key for code generation
        """
        import os

        import anthropic

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required for code generation")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if custom code is needed.

        Custom code is a fallback for:
        - Complex multi-step operations
        - Custom logic not supported by other strategies
        - Operations requiring API calls

        Args:
            context: Execution context

        Returns:
            True (can handle anything, but lowest priority)
        """
        # Always can handle, but should be last resort
        return True

    def estimate_cost(self, context: ExecutionContext) -> float:
        """Estimate cost of custom code execution.

        Args:
            context: Execution context

        Returns:
            Estimated cost including API calls
        """
        # Estimate based on complexity
        from ..cost_estimator import AzureCostEstimator

        estimator = AzureCostEstimator()
        resource_cost = estimator.estimate_intent(
            context.intent, context.parameters
        )

        # Add API call cost estimate
        api_cost = 0.02  # Rough estimate for Claude API

        return resource_cost + api_cost

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Generate and execute custom code.

        Workflow:
        1. Generate Python code using Claude
        2. Save to temporary file
        3. Execute in isolated environment
        4. Capture outputs and resources

        Args:
            context: Execution context

        Returns:
            Execution result
        """
        start_time = time.time()

        try:
            # Generate code
            code = self._generate_code(context)

            if context.dry_run:
                return ExecutionResult(
                    success=True,
                    strategy=StrategyType.CUSTOM_CODE,
                    outputs={"generated_code": code},
                    resources_created=[],
                    cost_estimate=self.estimate_cost(context),
                    execution_time=time.time() - start_time
                )

            # Execute code
            result = self._execute_code(code, context)

            return ExecutionResult(
                success=result["success"],
                strategy=StrategyType.CUSTOM_CODE,
                outputs={
                    "generated_code": code,
                    "execution_output": result["output"]
                },
                resources_created=result["resources"],
                cost_estimate=self.estimate_cost(context),
                execution_time=time.time() - start_time,
                error=result.get("error")
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=StrategyType.CUSTOM_CODE,
                outputs={},
                resources_created=[],
                cost_estimate=0.0,
                execution_time=time.time() - start_time,
                error=str(e)
            )

    def validate(self, result: ExecutionResult) -> bool:
        """Validate custom code execution.

        Args:
            result: Execution result

        Returns:
            True if execution succeeded
        """
        # Basic validation - code ran without errors
        return result.success and result.error is None

    def rollback(self, result: ExecutionResult) -> bool:
        """Attempt rollback of custom code execution.

        Args:
            result: Failed execution result

        Returns:
            True if rollback succeeded
        """
        # Best effort cleanup of created resources
        pass

    def _generate_code(self, context: ExecutionContext) -> str:
        """Generate Python code using Claude."""
        pass

    def _execute_code(self, code: str, context: ExecutionContext) -> Dict[str, Any]:
        """Execute generated code in isolated environment."""
        pass
```

---

## 2. State Management

### 2.1 Objective State Manager (`objective_state.py`)

**Purpose**: Persist objectives and execution state to JSON.

```python
"""Objective state persistence for azdoit."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .strategies.base import ExecutionResult, StrategyType


@dataclass
class ObjectiveState:
    """Persistent state for an objective."""
    objective_id: str
    created_at: str
    updated_at: str
    user_request: str
    intent: Dict[str, Any]
    parameters: Dict[str, Any]
    status: str  # pending, in_progress, completed, failed
    selected_strategy: Optional[StrategyType]
    execution_results: List[ExecutionResult]
    resources_created: List[str]
    total_cost: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = None


class ObjectiveStateManager:
    """Manages persistent state for objectives."""

    def __init__(self, state_dir: Optional[Path] = None):
        """Initialize state manager.

        Args:
            state_dir: Directory for state files. Defaults to ~/.azlin/azdoit/state
        """
        self.state_dir = state_dir or Path.home() / ".azlin" / "azdoit" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def create_objective(
        self,
        user_request: str,
        intent: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> ObjectiveState:
        """Create a new objective.

        Args:
            user_request: Original user request
            intent: Parsed intent
            parameters: Extracted parameters

        Returns:
            New objective state
        """
        import uuid

        objective_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        state = ObjectiveState(
            objective_id=objective_id,
            created_at=now,
            updated_at=now,
            user_request=user_request,
            intent=intent,
            parameters=parameters,
            status="pending",
            selected_strategy=None,
            execution_results=[],
            resources_created=[],
            total_cost=0.0
        )

        self._save(state)
        return state

    def update_objective(
        self,
        objective_id: str,
        status: Optional[str] = None,
        strategy: Optional[StrategyType] = None,
        result: Optional[ExecutionResult] = None,
        error: Optional[str] = None
    ) -> ObjectiveState:
        """Update objective state.

        Args:
            objective_id: Objective ID
            status: New status
            strategy: Selected strategy
            result: Execution result to append
            error: Error message

        Returns:
            Updated state
        """
        state = self.get_objective(objective_id)

        state.updated_at = datetime.utcnow().isoformat()

        if status:
            state.status = status

        if strategy:
            state.selected_strategy = strategy

        if result:
            state.execution_results.append(result)
            state.resources_created.extend(result.resources_created)
            state.total_cost += result.cost_estimate or 0.0

        if error:
            state.error = error
            state.status = "failed"

        self._save(state)
        return state

    def get_objective(self, objective_id: str) -> ObjectiveState:
        """Get objective by ID.

        Args:
            objective_id: Objective ID

        Returns:
            Objective state

        Raises:
            ObjectiveNotFoundError: If objective doesn't exist
        """
        path = self._get_path(objective_id)

        if not path.exists():
            raise ObjectiveNotFoundError(f"Objective {objective_id} not found")

        data = json.loads(path.read_text())
        return self._deserialize(data)

    def list_objectives(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[ObjectiveState]:
        """List objectives.

        Args:
            status: Filter by status
            limit: Maximum number to return

        Returns:
            List of objectives, sorted by created_at descending
        """
        objectives = []

        for path in sorted(
            self.state_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]:
            try:
                data = json.loads(path.read_text())
                obj = self._deserialize(data)

                if status is None or obj.status == status:
                    objectives.append(obj)
            except Exception:
                # Skip corrupted files
                continue

        return objectives

    def delete_objective(self, objective_id: str) -> None:
        """Delete objective state.

        Args:
            objective_id: Objective ID
        """
        path = self._get_path(objective_id)
        if path.exists():
            path.unlink()

    def cleanup_old_objectives(self, days: int = 30) -> int:
        """Delete objectives older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of objectives deleted
        """
        from datetime import timedelta

        threshold = datetime.utcnow() - timedelta(days=days)
        deleted = 0

        for objective in self.list_objectives():
            created = datetime.fromisoformat(objective.created_at)
            if created < threshold:
                self.delete_objective(objective.objective_id)
                deleted += 1

        return deleted

    def _save(self, state: ObjectiveState) -> None:
        """Save objective state to disk."""
        path = self._get_path(state.objective_id)
        data = self._serialize(state)
        path.write_text(json.dumps(data, indent=2))

    def _get_path(self, objective_id: str) -> Path:
        """Get file path for objective."""
        return self.state_dir / f"{objective_id}.json"

    def _serialize(self, state: ObjectiveState) -> Dict[str, Any]:
        """Convert state to JSON-serializable dict."""
        data = asdict(state)

        # Convert enums and dataclasses
        if data["selected_strategy"]:
            data["selected_strategy"] = data["selected_strategy"].value

        data["execution_results"] = [
            {
                **asdict(r),
                "strategy": r.strategy.value
            }
            for r in state.execution_results
        ]

        return data

    def _deserialize(self, data: Dict[str, Any]) -> ObjectiveState:
        """Convert JSON dict to state object."""
        # Convert strategy enum
        if data["selected_strategy"]:
            data["selected_strategy"] = StrategyType(data["selected_strategy"])

        # Convert execution results
        data["execution_results"] = [
            ExecutionResult(
                **{
                    **r,
                    "strategy": StrategyType(r["strategy"])
                }
            )
            for r in data["execution_results"]
        ]

        return ObjectiveState(**data)


class ObjectiveNotFoundError(Exception):
    """Raised when objective is not found."""
    pass
```

### JSON Schema for Objective State

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": [
    "objective_id", "created_at", "updated_at", "user_request",
    "intent", "parameters", "status", "execution_results",
    "resources_created", "total_cost"
  ],
  "properties": {
    "objective_id": {
      "type": "string",
      "format": "uuid"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    },
    "user_request": {
      "type": "string",
      "description": "Original natural language request"
    },
    "intent": {
      "type": "object",
      "required": ["intent", "parameters", "confidence", "azlin_commands"],
      "properties": {
        "intent": {"type": "string"},
        "parameters": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "azlin_commands": {"type": "array"}
      }
    },
    "parameters": {
      "type": "object",
      "description": "Extracted execution parameters"
    },
    "status": {
      "type": "string",
      "enum": ["pending", "in_progress", "completed", "failed"]
    },
    "selected_strategy": {
      "type": "string",
      "enum": ["azure_cli", "terraform", "mcp_server", "custom_code"],
      "nullable": true
    },
    "execution_results": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "success", "strategy", "outputs", "resources_created",
          "cost_estimate", "execution_time"
        ],
        "properties": {
          "success": {"type": "boolean"},
          "strategy": {"type": "string"},
          "outputs": {"type": "object"},
          "resources_created": {"type": "array", "items": {"type": "string"}},
          "cost_estimate": {"type": "number", "nullable": true},
          "execution_time": {"type": "number"},
          "error": {"type": "string", "nullable": true},
          "metadata": {"type": "object", "nullable": true}
        }
      }
    },
    "resources_created": {
      "type": "array",
      "items": {"type": "string"},
      "description": "All Azure resource IDs created"
    },
    "total_cost": {
      "type": "number",
      "description": "Total cost in USD"
    },
    "error": {
      "type": "string",
      "nullable": true
    },
    "metadata": {
      "type": "object",
      "nullable": true
    }
  }
}
```

---

## 3. Supporting Services

### 3.1 Cost Estimator (`cost_estimator.py`)

**Purpose**: Estimate Azure resource costs before execution.

```python
"""Azure cost estimation for azdoit."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CostEstimate:
    """Cost estimate result."""
    total_cost: float  # USD
    breakdown: Dict[str, float]  # Per-resource costs
    confidence: float  # 0.0 to 1.0
    monthly_recurring: float  # Ongoing monthly cost
    upfront: float  # One-time costs
    currency: str = "USD"


class AzureCostEstimator:
    """Estimates Azure resource costs."""

    def __init__(self, pricing_api_key: Optional[str] = None):
        """Initialize cost estimator.

        Args:
            pricing_api_key: Azure Pricing API key. If None, uses defaults.
        """
        self.pricing_api_key = pricing_api_key
        self._load_pricing_data()

    def estimate_intent(
        self,
        intent: Dict[str, Any],
        parameters: Dict[str, Any],
        region: str = "eastus"
    ) -> float:
        """Estimate cost for an intent.

        Args:
            intent: Parsed intent
            parameters: Intent parameters
            region: Azure region

        Returns:
            Estimated cost in USD
        """
        intent_type = intent.get("intent")

        if intent_type == "provision_vm":
            return self.estimate_vm(
                vm_size=parameters.get("vm_size", "Standard_D2s_v3"),
                count=parameters.get("count", 1),
                region=region
            )

        elif intent_type == "create_storage":
            return self.estimate_storage(
                size_gb=parameters.get("size", 100),
                storage_type=parameters.get("type", "Standard_LRS"),
                region=region
            )

        # Add more intent types...

        return 0.0

    def estimate_vm(
        self,
        vm_size: str,
        count: int = 1,
        region: str = "eastus",
        hours: int = 24
    ) -> float:
        """Estimate VM cost.

        Args:
            vm_size: Azure VM size (e.g., Standard_D2s_v3)
            count: Number of VMs
            region: Azure region
            hours: Hours to estimate for

        Returns:
            Estimated cost in USD
        """
        hourly_rate = self._get_vm_price(vm_size, region)
        return hourly_rate * count * hours

    def estimate_storage(
        self,
        size_gb: int,
        storage_type: str = "Standard_LRS",
        region: str = "eastus"
    ) -> float:
        """Estimate storage cost.

        Args:
            size_gb: Storage size in GB
            storage_type: Storage SKU
            region: Azure region

        Returns:
            Estimated monthly cost in USD
        """
        monthly_rate_per_gb = self._get_storage_price(storage_type, region)
        return monthly_rate_per_gb * size_gb

    def estimate_terraform(self, terraform_config: str) -> float:
        """Estimate cost from Terraform configuration.

        Parses Terraform HCL and estimates cost of all resources.

        Args:
            terraform_config: Terraform configuration HCL

        Returns:
            Estimated total cost in USD
        """
        resources = self._parse_terraform_resources(terraform_config)
        total = 0.0

        for resource in resources:
            if resource["type"] == "azurerm_virtual_machine":
                total += self.estimate_vm(
                    vm_size=resource["properties"].get("vm_size"),
                    region=resource["properties"].get("location", "eastus")
                )
            elif resource["type"] == "azurerm_storage_account":
                total += self.estimate_storage(
                    size_gb=resource["properties"].get("size", 100),
                    storage_type=resource["properties"].get("account_tier", "Standard")
                )
            # Add more resource types...

        return total

    def get_detailed_estimate(
        self,
        intent: Dict[str, Any],
        parameters: Dict[str, Any],
        region: str = "eastus"
    ) -> CostEstimate:
        """Get detailed cost estimate with breakdown.

        Args:
            intent: Parsed intent
            parameters: Intent parameters
            region: Azure region

        Returns:
            Detailed cost estimate
        """
        breakdown = {}
        total = 0.0
        monthly = 0.0
        upfront = 0.0

        # Calculate per-resource costs
        # ...

        return CostEstimate(
            total_cost=total,
            breakdown=breakdown,
            confidence=0.85,
            monthly_recurring=monthly,
            upfront=upfront
        )

    def _load_pricing_data(self) -> None:
        """Load Azure pricing data."""
        # Load from Azure Pricing API or local cache
        pass

    def _get_vm_price(self, vm_size: str, region: str) -> float:
        """Get hourly price for VM size in region."""
        pass

    def _get_storage_price(self, storage_type: str, region: str) -> float:
        """Get monthly price per GB for storage type."""
        pass

    def _parse_terraform_resources(self, config: str) -> List[Dict[str, Any]]:
        """Parse resources from Terraform configuration."""
        pass
```

### 3.2 Recovery Agent (`recovery_agent.py`)

**Purpose**: Research errors and retry failed operations.

```python
"""Recovery agent for handling failures."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .strategies.base import ExecutionContext, ExecutionResult


@dataclass
class RecoveryPlan:
    """Plan for recovering from failure."""
    strategy: str  # retry, modify_params, change_strategy, escalate
    reasoning: str
    modifications: Dict[str, Any]
    retry_context: Optional[ExecutionContext]
    confidence: float  # 0.0 to 1.0


class RecoveryAgent:
    """Researches failures and attempts recovery."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize recovery agent.

        Args:
            api_key: Anthropic API key for research
        """
        import os

        import anthropic

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def analyze_failure(
        self,
        context: ExecutionContext,
        result: ExecutionResult
    ) -> RecoveryPlan:
        """Analyze failure and create recovery plan.

        Args:
            context: Original execution context
            result: Failed execution result

        Returns:
            Recovery plan
        """
        from .mslearn_client import MSLearnClient

        # Research the error
        error_analysis = self._analyze_error(result.error)

        # Search MS Learn for solutions
        mslearn = MSLearnClient()
        docs = mslearn.search(error_analysis["query"])

        # Generate recovery plan using Claude
        plan = self._generate_recovery_plan(
            context, result, error_analysis, docs
        )

        return plan

    def attempt_recovery(
        self,
        context: ExecutionContext,
        result: ExecutionResult,
        max_attempts: int = 3
    ) -> Optional[ExecutionResult]:
        """Attempt to recover from failure.

        Args:
            context: Original execution context
            result: Failed execution result
            max_attempts: Maximum recovery attempts

        Returns:
            Successful result if recovery worked, None otherwise
        """
        for attempt in range(max_attempts):
            plan = self.analyze_failure(context, result)

            if plan.strategy == "escalate":
                # Can't auto-recover, need human intervention
                return None

            if plan.strategy == "retry" and plan.retry_context:
                # Execute with modified context
                from .strategy_selector import StrategySelector

                selector = StrategySelector()
                strategy = selector.select(plan.retry_context)

                new_result = strategy.execute(plan.retry_context)

                if new_result.success:
                    return new_result

                # Update for next attempt
                result = new_result

        return None

    def _analyze_error(self, error: str) -> Dict[str, Any]:
        """Analyze error message to understand root cause.

        Args:
            error: Error message

        Returns:
            Analysis with error type, category, search query
        """
        import json

        system_prompt = """Analyze this Azure error message.

Output JSON only:
{
    "error_type": "quota | permission | resource_not_found | network | ...",
    "category": "transient | configuration | permanent",
    "root_cause": "Brief explanation",
    "query": "Search query for MS Learn docs",
    "is_recoverable": true/false
}"""

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Error: {error}"}]
        )

        response_text = message.content[0].text
        start = response_text.find("{")
        end = response_text.rfind("}") + 1

        if start >= 0 and end > start:
            return json.loads(response_text[start:end])

        return {
            "error_type": "unknown",
            "category": "permanent",
            "root_cause": "Unable to analyze error",
            "query": error[:100],
            "is_recoverable": False
        }

    def _generate_recovery_plan(
        self,
        context: ExecutionContext,
        result: ExecutionResult,
        error_analysis: Dict[str, Any],
        docs: List[Dict[str, str]]
    ) -> RecoveryPlan:
        """Generate recovery plan using Claude and documentation.

        Args:
            context: Original context
            result: Failed result
            error_analysis: Error analysis
            docs: Relevant MS Learn documentation

        Returns:
            Recovery plan
        """
        import json

        system_prompt = """You are a recovery agent for Azure operations.

Given a failed execution, error analysis, and relevant documentation,
create a recovery plan.

Output JSON only:
{
    "strategy": "retry | modify_params | change_strategy | escalate",
    "reasoning": "Why this approach",
    "modifications": {
        "parameter changes or strategy change"
    },
    "confidence": 0.0-1.0
}"""

        user_message = {
            "context": {
                "intent": context.intent,
                "parameters": context.parameters,
                "strategy": result.strategy.value
            },
            "error": result.error,
            "error_analysis": error_analysis,
            "documentation": docs[:3]  # Top 3 relevant docs
        }

        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(user_message)}]
        )

        response_text = message.content[0].text
        start = response_text.find("{")
        end = response_text.rfind("}") + 1

        if start >= 0 and end > start:
            plan_data = json.loads(response_text[start:end])

            # Create modified context if needed
            retry_context = None
            if plan_data["strategy"] in ["retry", "modify_params"]:
                retry_context = ExecutionContext(
                    intent=context.intent,
                    parameters={
                        **context.parameters,
                        **plan_data["modifications"]
                    },
                    resource_group=context.resource_group,
                    dry_run=context.dry_run,
                    verbose=context.verbose
                )

            return RecoveryPlan(
                strategy=plan_data["strategy"],
                reasoning=plan_data["reasoning"],
                modifications=plan_data["modifications"],
                retry_context=retry_context,
                confidence=plan_data["confidence"]
            )

        # Fallback: escalate
        return RecoveryPlan(
            strategy="escalate",
            reasoning="Unable to generate recovery plan",
            modifications={},
            retry_context=None,
            confidence=0.0
        )
```

### 3.3 Terraform Generator (`terraform_generator.py`)

**Purpose**: Generate Terraform HCL configurations from intents.

```python
"""Terraform configuration generator."""

from typing import Any, Dict


class TerraformGenerator:
    """Generates Terraform configurations from intents."""

    def __init__(self):
        """Initialize Terraform generator."""
        pass

    def generate(
        self,
        intent: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> str:
        """Generate Terraform configuration for intent.

        Args:
            intent: Parsed intent
            parameters: Intent parameters

        Returns:
            Terraform HCL configuration
        """
        intent_type = intent.get("intent")

        if intent_type == "provision_vm":
            return self.generate_vm(parameters)
        elif intent_type == "create_storage":
            return self.generate_storage(parameters)
        elif intent_type == "provision_fleet":
            return self.generate_fleet(parameters)

        raise ValueError(f"Cannot generate Terraform for intent: {intent_type}")

    def generate_vm(self, parameters: Dict[str, Any]) -> str:
        """Generate VM Terraform configuration.

        Args:
            parameters: VM parameters

        Returns:
            Terraform HCL
        """
        vm_name = parameters.get("vm_name", "azlin-vm")
        vm_size = parameters.get("vm_size", "Standard_D2s_v3")
        region = parameters.get("region", "eastus")

        return f'''
terraform {{
  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }}
  }}
}}

provider "azurerm" {{
  features {{}}
}}

resource "azurerm_resource_group" "main" {{
  name     = "rg-{vm_name}"
  location = "{region}"
}}

resource "azurerm_virtual_network" "main" {{
  name                = "vnet-{vm_name}"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_subnet" "main" {{
  name                 = "subnet-{vm_name}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}}

resource "azurerm_network_interface" "main" {{
  name                = "nic-{vm_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {{
    name                          = "internal"
    subnet_id                     = azurerm_subnet.main.id
    private_ip_address_allocation = "Dynamic"
  }}
}}

resource "azurerm_linux_virtual_machine" "main" {{
  name                = "{vm_name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  size                = "{vm_size}"

  network_interface_ids = [
    azurerm_network_interface.main.id,
  ]

  os_disk {{
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }}

  source_image_reference {{
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }}

  admin_username = "azureuser"
  admin_ssh_key {{
    username   = "azureuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }}
}}

output "vm_id" {{
  value = azurerm_linux_virtual_machine.main.id
}}

output "private_ip" {{
  value = azurerm_network_interface.main.private_ip_address
}}
'''

    def generate_storage(self, parameters: Dict[str, Any]) -> str:
        """Generate storage Terraform configuration.

        Args:
            parameters: Storage parameters

        Returns:
            Terraform HCL
        """
        pass

    def generate_fleet(self, parameters: Dict[str, Any]) -> str:
        """Generate multi-VM fleet configuration.

        Args:
            parameters: Fleet parameters

        Returns:
            Terraform HCL
        """
        pass

    def validate_config(self, config: str) -> bool:
        """Validate Terraform configuration syntax.

        Args:
            config: Terraform HCL

        Returns:
            True if valid
        """
        # Could use terraform validate or HCL parser
        pass
```

### 3.4 MCP Client (`mcp_client.py`)

**Purpose**: Client for Azure MCP Server integration.

```python
"""Azure MCP Server client."""

from typing import Any, Dict, List, Optional


class AzureMCPClient:
    """Client for Azure MCP Server."""

    def __init__(self, server_url: Optional[str] = None):
        """Initialize MCP client.

        Args:
            server_url: MCP Server URL. If None, uses default.
        """
        self.server_url = server_url or "https://azure-mcp.azurewebsites.net"
        self._session = None

    def get_capabilities(self) -> Dict[str, Any]:
        """Get MCP Server capabilities.

        Returns:
            Capabilities dict with supported operations
        """
        response = self._request("GET", "/capabilities")
        return response.json()

    def execute(
        self,
        operation: str,
        parameters: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Execute operation via MCP Server.

        Args:
            operation: Operation name
            parameters: Operation parameters
            dry_run: Preview mode

        Returns:
            Execution result
        """
        payload = {
            "operation": operation,
            "parameters": parameters,
            "dry_run": dry_run
        }

        response = self._request("POST", "/execute", json=payload)
        return response.json()

    def estimate_cost(
        self,
        operation: str,
        parameters: Dict[str, Any]
    ) -> float:
        """Estimate cost via MCP Server.

        Args:
            operation: Operation name
            parameters: Operation parameters

        Returns:
            Estimated cost in USD
        """
        payload = {
            "operation": operation,
            "parameters": parameters
        }

        response = self._request("POST", "/estimate", json=payload)
        return response.json().get("cost", 0.0)

    def validate(self, resource_ids: List[str]) -> bool:
        """Validate resources exist via MCP Server.

        Args:
            resource_ids: Azure resource IDs

        Returns:
            True if all resources exist
        """
        payload = {"resource_ids": resource_ids}
        response = self._request("POST", "/validate", json=payload)
        return response.json().get("valid", False)

    def rollback(self, resource_ids: List[str]) -> None:
        """Rollback resources via MCP Server.

        Args:
            resource_ids: Azure resource IDs to delete
        """
        payload = {"resource_ids": resource_ids}
        self._request("POST", "/rollback", json=payload)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make HTTP request to MCP Server."""
        import requests

        if self._session is None:
            self._session = requests.Session()

        url = f"{self.server_url}{path}"
        response = self._session.request(method, url, **kwargs)
        response.raise_for_status()

        return response
```

### 3.5 MS Learn Client (`mslearn_client.py`)

**Purpose**: Search Microsoft Learn documentation.

```python
"""Microsoft Learn documentation search client."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DocResult:
    """Documentation search result."""
    title: str
    url: str
    excerpt: str
    relevance_score: float


class MSLearnClient:
    """Client for searching Microsoft Learn documentation."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize MS Learn client.

        Args:
            api_key: Bing Search API key for enhanced search
        """
        self.api_key = api_key

    def search(
        self,
        query: str,
        limit: int = 10,
        scope: str = "azure"
    ) -> List[DocResult]:
        """Search Microsoft Learn documentation.

        Args:
            query: Search query
            limit: Maximum results
            scope: Documentation scope (azure, dotnet, etc.)

        Returns:
            List of documentation results
        """
        # Construct search query
        search_url = f"https://learn.microsoft.com/api/search"

        params = {
            "q": query,
            "scope": scope,
            "locale": "en-us",
            "top": limit
        }

        results = self._search_api(search_url, params)

        return [
            DocResult(
                title=r["title"],
                url=r["url"],
                excerpt=r["excerpt"],
                relevance_score=r.get("score", 0.0)
            )
            for r in results
        ]

    def search_error(
        self,
        error_message: str,
        limit: int = 5
    ) -> List[DocResult]:
        """Search for error-specific documentation.

        Args:
            error_message: Error message to search
            limit: Maximum results

        Returns:
            List of relevant docs
        """
        # Extract key terms from error
        query = self._extract_error_terms(error_message)
        return self.search(f"azure error {query}", limit=limit)

    def get_quickstart(self, service: str) -> Optional[DocResult]:
        """Get quickstart guide for Azure service.

        Args:
            service: Azure service name (e.g., "virtual-machines")

        Returns:
            Quickstart documentation
        """
        results = self.search(
            f"azure {service} quickstart",
            limit=1
        )

        return results[0] if results else None

    def _search_api(self, url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Make search API request."""
        import requests

        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get("results", [])

    def _extract_error_terms(self, error: str) -> str:
        """Extract key search terms from error message."""
        # Simple extraction - could be enhanced with NLP
        # Remove stack traces, paths, etc.
        import re

        # Extract error code if present
        error_code_match = re.search(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)*Error\b', error)
        if error_code_match:
            return error_code_match.group(0)

        # Return first sentence
        sentences = error.split('.')
        return sentences[0][:100] if sentences else error[:100]
```

---

## 4. Integration with Existing Code

### 4.1 Enhanced IntentParser Integration

The existing `IntentParser` remains unchanged, but we extend its usage:

```python
# In cli.py or orchestrator
from azlin.agentic.intent_parser import IntentParser
from azlin.agentic.strategy_selector import StrategySelector
from azlin.agentic.objective_state import ObjectiveStateManager
from azlin.agentic.strategies.base import ExecutionContext

def handle_do_command(user_request: str, **options):
    """Enhanced do command with strategy selection."""

    # Parse intent (existing)
    parser = IntentParser()
    intent = parser.parse(user_request, context=get_azure_context())

    # Create objective (new)
    state_manager = ObjectiveStateManager()
    objective = state_manager.create_objective(
        user_request=user_request,
        intent=intent,
        parameters=intent["parameters"]
    )

    # Select strategy (new)
    context = ExecutionContext(
        intent=intent,
        parameters=intent["parameters"],
        resource_group=options.get("resource_group"),
        dry_run=options.get("dry_run", False),
        verbose=options.get("verbose", False),
        cost_limit=options.get("cost_limit")
    )

    selector = StrategySelector()

    try:
        strategy = selector.select(context, preferences=options)

        # Update objective
        state_manager.update_objective(
            objective.objective_id,
            status="in_progress",
            strategy=strategy.strategy_type
        )

        # Execute
        result = strategy.execute(context)

        # Update with result
        state_manager.update_objective(
            objective.objective_id,
            status="completed" if result.success else "failed",
            result=result,
            error=result.error
        )

        # Handle failure
        if not result.success and not options.get("no_recovery"):
            from azlin.agentic.recovery_agent import RecoveryAgent

            recovery = RecoveryAgent()
            recovered_result = recovery.attempt_recovery(context, result)

            if recovered_result:
                result = recovered_result
                state_manager.update_objective(
                    objective.objective_id,
                    status="completed",
                    result=result
                )

        return result

    except Exception as e:
        state_manager.update_objective(
            objective.objective_id,
            error=str(e)
        )
        raise
```

### 4.2 Configuration Schema

Configuration file: `~/.azlin/azdoit/config.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "anthropic_api_key": {
      "type": "string",
      "description": "Anthropic API key for Claude"
    },
    "strategy_preferences": {
      "type": "object",
      "properties": {
        "prefer_terraform": {
          "type": "boolean",
          "default": false
        },
        "prefer_mcp": {
          "type": "boolean",
          "default": false
        },
        "max_cost": {
          "type": "number",
          "description": "Maximum cost in USD for operations"
        },
        "require_idempotent": {
          "type": "boolean",
          "default": true
        }
      }
    },
    "mcp_server": {
      "type": "object",
      "properties": {
        "enabled": {
          "type": "boolean",
          "default": false
        },
        "url": {
          "type": "string",
          "format": "uri"
        }
      }
    },
    "terraform": {
      "type": "object",
      "properties": {
        "workspace_dir": {
          "type": "string",
          "description": "Directory for Terraform workspaces"
        },
        "backend": {
          "type": "object",
          "description": "Terraform backend configuration"
        }
      }
    },
    "cost_estimation": {
      "type": "object",
      "properties": {
        "enabled": {
          "type": "boolean",
          "default": true
        },
        "require_confirmation": {
          "type": "boolean",
          "default": true,
          "description": "Require confirmation if cost exceeds threshold"
        },
        "confirmation_threshold": {
          "type": "number",
          "default": 10.0,
          "description": "Cost threshold in USD for confirmation"
        }
      }
    },
    "recovery": {
      "type": "object",
      "properties": {
        "enabled": {
          "type": "boolean",
          "default": true
        },
        "max_attempts": {
          "type": "integer",
          "default": 3
        },
        "use_mslearn": {
          "type": "boolean",
          "default": true,
          "description": "Search MS Learn docs for error solutions"
        }
      }
    },
    "state": {
      "type": "object",
      "properties": {
        "directory": {
          "type": "string",
          "description": "Directory for objective state files"
        },
        "cleanup_days": {
          "type": "integer",
          "default": 30,
          "description": "Days to keep old objectives"
        }
      }
    }
  }
}
```

---

## 5. Error Hierarchy

```python
"""Error hierarchy for azdoit."""


class AzDoItError(Exception):
    """Base exception for azdoit."""
    pass


class IntentParseError(AzDoItError):
    """Error parsing natural language intent."""
    pass


class StrategyError(AzDoItError):
    """Base exception for strategy errors."""
    pass


class NoStrategyFoundError(StrategyError):
    """No strategy can handle the intent."""
    pass


class StrategyExecutionError(StrategyError):
    """Error executing strategy."""
    pass


class StateError(AzDoItError):
    """Error with objective state management."""
    pass


class ObjectiveNotFoundError(StateError):
    """Objective not found."""
    pass


class CostEstimationError(AzDoItError):
    """Error estimating costs."""
    pass


class RecoveryError(AzDoItError):
    """Error during recovery attempt."""
    pass


class TerraformError(StrategyError):
    """Error with Terraform operations."""
    pass


class MCPError(StrategyError):
    """Error with MCP Server operations."""
    pass


class AzureCLIError(StrategyError):
    """Error with Azure CLI operations."""
    pass


class CodeGenerationError(StrategyError):
    """Error generating custom code."""
    pass


class ValidationError(AzDoItError):
    """Error validating execution results."""
    pass
```

---

## 6. Testing Contracts

Each module must provide:

### 6.1 Unit Test Interface

```python
# Example: tests/unit/test_strategy_selector.py

import pytest
from azlin.agentic.strategy_selector import StrategySelector
from azlin.agentic.strategies.base import ExecutionContext, StrategyType


class TestStrategySelector:
    """Unit tests for strategy selector."""

    def test_select_azure_cli_for_simple_vm(self):
        """Should select Azure CLI for simple VM provisioning."""
        context = ExecutionContext(
            intent={"intent": "provision_vm"},
            parameters={"vm_name": "test"},
            resource_group="test-rg"
        )

        selector = StrategySelector()
        strategy = selector.select(context)

        assert strategy.strategy_type == StrategyType.AZURE_CLI

    def test_select_terraform_for_fleet(self):
        """Should select Terraform for multi-VM fleet."""
        context = ExecutionContext(
            intent={"intent": "provision_fleet"},
            parameters={"count": 5},
            resource_group="test-rg"
        )

        selector = StrategySelector()
        strategy = selector.select(context, {"prefer_terraform": True})

        assert strategy.strategy_type == StrategyType.TERRAFORM

    def test_no_strategy_found_raises_error(self):
        """Should raise error if no strategy can handle intent."""
        context = ExecutionContext(
            intent={"intent": "unsupported_operation"},
            parameters={},
            resource_group="test-rg"
        )

        selector = StrategySelector()

        with pytest.raises(NoStrategyFoundError):
            selector.select(context)
```

### 6.2 Integration Test Interface

```python
# Example: tests/integration/test_end_to_end.py

import pytest
from azlin.agentic import handle_do_command


class TestEndToEnd:
    """Integration tests for complete workflows."""

    @pytest.mark.azure
    def test_provision_vm_end_to_end(self):
        """Full workflow: parse → select → execute → validate."""
        result = handle_do_command(
            "create a vm called test-vm",
            dry_run=True,
            resource_group="test-rg"
        )

        assert result.success
        assert len(result.resources_created) > 0

    @pytest.mark.azure
    @pytest.mark.slow
    def test_recovery_from_quota_error(self):
        """Should recover from quota exceeded error."""
        # Simulate quota error and verify recovery
        pass
```

---

## Summary

These API contracts define:

1. **Strategy System**: Pluggable execution strategies with standard interface
2. **State Management**: Persistent objective tracking with JSON storage
3. **Supporting Services**: Cost estimation, recovery, Terraform gen, MCP client, MS Learn search
4. **Integration Points**: Clean integration with existing IntentParser/CommandExecutor
5. **Configuration**: JSON schema for user preferences and settings
6. **Error Handling**: Complete exception hierarchy
7. **Testing**: Clear contracts for unit and integration tests

All modules follow the **bricks & studs** philosophy:
- Self-contained with clear boundaries
- Stable public interfaces
- Fully type-hinted
- Observable with structured results
- Regeneratable from these specifications

Next steps:
1. Review and approve these contracts
2. Generate module implementations from specs
3. Write tests following test contracts
4. Integrate with existing code via integration points
