# azdoit Implementation Guide

## Quick Reference

### Module Checklist

For each new module, ensure:

- [ ] Python interface defined with complete type hints
- [ ] Docstrings for all public methods
- [ ] Error handling with custom exceptions
- [ ] Unit tests with >80% coverage
- [ ] Integration tests for critical paths
- [ ] Module is self-contained (no circular dependencies)
- [ ] Configuration via dataclasses or JSON
- [ ] Observable (returns structured results)
- [ ] Idempotent where possible
- [ ] Follows naming conventions

### File Structure

```
src/azlin/agentic/
├── __init__.py                    # Public API exports
├── intent_parser.py               # [EXISTS]
├── command_executor.py            # [EXISTS]
├── strategy_selector.py           # [NEW]
├── objective_state.py             # [NEW]
├── cost_estimator.py              # [NEW]
├── recovery_agent.py              # [NEW]
├── terraform_generator.py         # [NEW]
├── mcp_client.py                  # [NEW]
├── mslearn_client.py              # [NEW]
├── errors.py                      # [NEW] Error hierarchy
├── config.py                      # [NEW] Configuration management
└── strategies/
    ├── __init__.py
    ├── base.py                    # [NEW] Base interface
    ├── azure_cli.py               # [NEW]
    ├── terraform.py               # [NEW]
    ├── mcp_server.py              # [NEW]
    └── custom_code.py             # [NEW]

tests/
├── unit/
│   ├── test_strategy_selector.py
│   ├── test_objective_state.py
│   ├── test_cost_estimator.py
│   ├── test_recovery_agent.py
│   ├── test_terraform_generator.py
│   ├── test_mcp_client.py
│   ├── test_mslearn_client.py
│   └── strategies/
│       ├── test_azure_cli.py
│       ├── test_terraform.py
│       ├── test_mcp_server.py
│       └── test_custom_code.py
└── integration/
    ├── test_end_to_end.py
    ├── test_strategy_selection.py
    ├── test_recovery_flow.py
    └── test_cost_estimation.py
```

## Implementation Order

### Phase 1: Foundation (Week 1)
1. **Create error hierarchy** (`errors.py`)
   - Define all exception classes
   - Add docstrings explaining when each is raised

2. **Base strategy interface** (`strategies/base.py`)
   - `ExecutionStrategy` abstract class
   - `ExecutionContext` dataclass
   - `ExecutionResult` dataclass
   - `StrategyType` enum

3. **Objective state manager** (`objective_state.py`)
   - `ObjectiveState` dataclass
   - `ObjectiveStateManager` class
   - JSON persistence
   - Unit tests

### Phase 2: Strategies (Week 2)
4. **Azure CLI strategy** (`strategies/azure_cli.py`)
   - Simplest strategy, build first
   - Reuse existing command execution patterns
   - Unit tests with mocked subprocess

5. **Strategy selector** (`strategy_selector.py`)
   - Scoring algorithm
   - Strategy selection logic
   - Unit tests with all strategies

6. **Terraform strategy** (`strategies/terraform.py`)
   - Terraform workspace management
   - HCL generation integration
   - Unit tests with temporary directories

### Phase 3: Supporting Services (Week 3)
7. **Terraform generator** (`terraform_generator.py`)
   - HCL template generation
   - Parameterization logic
   - Validation

8. **Cost estimator** (`cost_estimator.py`)
   - Azure pricing data loading
   - Cost calculation per resource type
   - Terraform config parsing

9. **MCP client** (`mcp_client.py`)
   - HTTP client setup
   - API method implementations
   - Error handling

10. **MS Learn client** (`mslearn_client.py`)
    - Search API integration
    - Result parsing
    - Caching (optional)

### Phase 4: Advanced Features (Week 4)
11. **MCP Server strategy** (`strategies/mcp_server.py`)
    - Depends on MCP client
    - Integration tests with real/mock server

12. **Custom code strategy** (`strategies/custom_code.py`)
    - Code generation prompts
    - Sandboxed execution
    - Security considerations

13. **Recovery agent** (`recovery_agent.py`)
    - Error analysis
    - Recovery plan generation
    - Integration with MS Learn client

### Phase 5: Integration (Week 5)
14. **CLI integration** (`cli.py`)
    - Update `azlin do` command
    - Add new flags for strategies, cost limits
    - User confirmation flows

15. **Configuration management** (`config.py`)
    - Load from `~/.azlin/azdoit/config.json`
    - Validation
    - Defaults

16. **End-to-end testing**
    - Full workflow tests
    - Real Azure integration tests
    - Error scenarios

## Detailed Implementation Guide

### 1. Error Hierarchy (`errors.py`)

```python
"""Error hierarchy for azdoit.

All custom exceptions inherit from AzDoItError for easy catching.
"""


class AzDoItError(Exception):
    """Base exception for azdoit.

    All azdoit exceptions inherit from this class.
    Catch this to handle all azdoit-specific errors.
    """
    pass


class IntentParseError(AzDoItError):
    """Error parsing natural language intent.

    Raised by IntentParser when:
    - Claude API returns invalid JSON
    - Response is missing required fields
    - Confidence is too low
    """
    pass


# ... (continue with all exception classes)
```

**Testing:**
```python
def test_exception_hierarchy():
    """All exceptions should inherit from AzDoItError."""
    assert issubclass(IntentParseError, AzDoItError)
    assert issubclass(StrategyError, AzDoItError)
    # etc.
```

### 2. Base Strategy Interface (`strategies/base.py`)

**Key Design Decisions:**
- Use `@dataclass` for data structures (automatic `__init__`, `__repr__`)
- Use `ABC` (Abstract Base Class) for interface enforcement
- Use `Enum` for strategy types (type-safe, serializable)

**Implementation Template:**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyType(Enum):
    """Execution strategy types."""
    AZURE_CLI = "azure_cli"
    TERRAFORM = "terraform"
    MCP_SERVER = "mcp_server"
    CUSTOM_CODE = "custom_code"


@dataclass
class ExecutionContext:
    """Context for strategy execution.

    This is the input to all strategies. Contains everything
    needed to execute the intent.
    """
    intent: Dict[str, Any]
    parameters: Dict[str, Any]
    resource_group: Optional[str] = None
    dry_run: bool = False
    verbose: bool = False
    cost_limit: Optional[float] = None

    def __post_init__(self):
        """Validate context after initialization."""
        if not self.intent:
            raise ValueError("intent cannot be empty")
        if not self.parameters:
            raise ValueError("parameters cannot be empty")


@dataclass
class ExecutionResult:
    """Result from strategy execution.

    This is the output from all strategies. Standardized format
    makes it easy to handle results uniformly.
    """
    success: bool
    strategy: StrategyType
    outputs: Dict[str, Any]
    resources_created: List[str] = field(default_factory=list)
    cost_estimate: Optional[float] = None
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExecutionStrategy(ABC):
    """Base interface for all execution strategies."""

    @abstractmethod
    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if strategy can handle this intent.

        Called by StrategySelector to filter viable strategies.

        Args:
            context: Execution context

        Returns:
            True if this strategy can execute the intent

        Example:
            >>> strategy = AzureCLIStrategy()
            >>> context = ExecutionContext(
            ...     intent={"intent": "provision_vm"},
            ...     parameters={"vm_name": "test"}
            ... )
            >>> strategy.can_handle(context)
            True
        """
        pass

    # ... (implement other abstract methods)
```

**Testing Strategy Interface:**

```python
import pytest
from azlin.agentic.strategies.base import ExecutionStrategy, ExecutionContext


class ConcreteStrategy(ExecutionStrategy):
    """Concrete implementation for testing."""

    def can_handle(self, context):
        return True

    def estimate_cost(self, context):
        return 10.0

    def execute(self, context):
        return ExecutionResult(success=True, strategy=StrategyType.AZURE_CLI, outputs={})

    def validate(self, result):
        return True

    def rollback(self, result):
        return True


def test_cannot_instantiate_abstract_class():
    """Cannot instantiate ExecutionStrategy directly."""
    with pytest.raises(TypeError):
        ExecutionStrategy()


def test_can_instantiate_concrete_class():
    """Can instantiate concrete implementation."""
    strategy = ConcreteStrategy()
    assert strategy is not None


def test_execution_context_validation():
    """ExecutionContext validates inputs."""
    with pytest.raises(ValueError, match="intent cannot be empty"):
        ExecutionContext(intent={}, parameters={"key": "value"})

    with pytest.raises(ValueError, match="parameters cannot be empty"):
        ExecutionContext(intent={"intent": "test"}, parameters={})
```

### 3. Objective State Manager (`objective_state.py`)

**Key Design Decisions:**
- JSON for persistence (human-readable, easy to debug)
- One file per objective (easy to manage, no database needed)
- UUID for objective IDs (globally unique, no collisions)

**Implementation Tips:**

```python
import json
import uuid
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ObjectiveState:
    """State of an objective."""
    objective_id: str
    created_at: str
    updated_at: str
    user_request: str
    intent: Dict[str, Any]
    parameters: Dict[str, Any]
    status: str
    selected_strategy: Optional[str]
    execution_results: List[Dict[str, Any]]
    resources_created: List[str]
    total_cost: float
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ObjectiveStateManager:
    """Manages objective state persistence."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".azlin" / "azdoit" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def create_objective(
        self,
        user_request: str,
        intent: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> ObjectiveState:
        """Create new objective."""
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

    def _save(self, state: ObjectiveState) -> None:
        """Save state to JSON file."""
        path = self.state_dir / f"{state.objective_id}.json"
        data = asdict(state)

        # Make JSON pretty and readable
        path.write_text(json.dumps(data, indent=2))

    def _get_path(self, objective_id: str) -> Path:
        """Get file path for objective."""
        return self.state_dir / f"{objective_id}.json"
```

**Testing State Manager:**

```python
import pytest
import tempfile
from pathlib import Path
from azlin.agentic.objective_state import ObjectiveStateManager


@pytest.fixture
def temp_state_dir():
    """Temporary directory for state files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_create_objective(temp_state_dir):
    """Should create objective and persist to disk."""
    manager = ObjectiveStateManager(temp_state_dir)

    state = manager.create_objective(
        user_request="create a vm",
        intent={"intent": "provision_vm"},
        parameters={"vm_name": "test"}
    )

    assert state.objective_id is not None
    assert state.status == "pending"
    assert state.total_cost == 0.0

    # Verify file exists
    file_path = temp_state_dir / f"{state.objective_id}.json"
    assert file_path.exists()

    # Verify contents
    import json
    data = json.loads(file_path.read_text())
    assert data["user_request"] == "create a vm"
    assert data["status"] == "pending"


def test_get_objective(temp_state_dir):
    """Should retrieve objective from disk."""
    manager = ObjectiveStateManager(temp_state_dir)

    created = manager.create_objective(
        user_request="test",
        intent={"intent": "test"},
        parameters={}
    )

    retrieved = manager.get_objective(created.objective_id)

    assert retrieved.objective_id == created.objective_id
    assert retrieved.user_request == created.user_request


def test_list_objectives(temp_state_dir):
    """Should list all objectives."""
    manager = ObjectiveStateManager(temp_state_dir)

    # Create multiple objectives
    obj1 = manager.create_objective("req1", {"intent": "test1"}, {})
    obj2 = manager.create_objective("req2", {"intent": "test2"}, {})

    objectives = manager.list_objectives()

    assert len(objectives) == 2
    ids = {obj.objective_id for obj in objectives}
    assert obj1.objective_id in ids
    assert obj2.objective_id in ids


def test_cleanup_old_objectives(temp_state_dir):
    """Should delete old objectives."""
    manager = ObjectiveStateManager(temp_state_dir)

    # Create objective with old timestamp
    obj = manager.create_objective("old", {"intent": "test"}, {})

    # Manually modify timestamp to be 60 days old
    state = manager.get_objective(obj.objective_id)
    from datetime import datetime, timedelta
    old_date = datetime.utcnow() - timedelta(days=60)
    state.created_at = old_date.isoformat()
    manager._save(state)

    # Cleanup objectives older than 30 days
    deleted = manager.cleanup_old_objectives(days=30)

    assert deleted == 1
    assert len(manager.list_objectives()) == 0
```

### 4. Azure CLI Strategy (`strategies/azure_cli.py`)

**Implementation Tips:**

- Reuse patterns from existing `CommandExecutor`
- Use `subprocess.run()` with list args (not string) for security
- Parse JSON output with `--output json` flag
- Extract resource IDs from output

```python
import subprocess
import json
import time
from typing import List, Dict, Any
from .base import ExecutionStrategy, ExecutionContext, ExecutionResult, StrategyType


class AzureCLIStrategy(ExecutionStrategy):
    """Execute via Azure CLI commands."""

    def can_handle(self, context: ExecutionContext) -> bool:
        """Most operations supported by Azure CLI."""
        supported = {
            "provision_vm", "list_vms", "start_vm", "stop_vm",
            "delete_vm", "create_storage", "list_storage"
        }
        return context.intent.get("intent") in supported

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute using Azure CLI."""
        start_time = time.time()

        try:
            commands = self._generate_commands(context)
            resources = []
            outputs = {}

            for cmd in commands:
                if context.dry_run:
                    outputs[cmd] = "[DRY RUN]"
                    continue

                result = self._run_command(cmd, context.verbose)

                if result["returncode"] != 0:
                    return ExecutionResult(
                        success=False,
                        strategy=StrategyType.AZURE_CLI,
                        outputs=outputs,
                        resources_created=resources,
                        execution_time=time.time() - start_time,
                        error=result["stderr"]
                    )

                outputs[cmd] = result["stdout"]

                # Extract resource IDs from JSON output
                try:
                    output_json = json.loads(result["stdout"])
                    resource_id = output_json.get("id")
                    if resource_id:
                        resources.append(resource_id)
                except json.JSONDecodeError:
                    # Output not JSON, skip resource extraction
                    pass

            return ExecutionResult(
                success=True,
                strategy=StrategyType.AZURE_CLI,
                outputs=outputs,
                resources_created=resources,
                execution_time=time.time() - start_time
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=StrategyType.AZURE_CLI,
                outputs={},
                resources_created=[],
                execution_time=time.time() - start_time,
                error=str(e)
            )

    def _generate_commands(self, context: ExecutionContext) -> List[str]:
        """Generate Azure CLI commands for intent."""
        intent = context.intent.get("intent")

        if intent == "provision_vm":
            vm_name = context.parameters.get("vm_name")
            rg = context.resource_group or f"rg-{vm_name}"
            return [
                f"az group create --name {rg} --location eastus --output json",
                f"az vm create --name {vm_name} --resource-group {rg} --image Ubuntu2204 --output json"
            ]

        # Add more intent handlers...

        return []

    def _run_command(self, cmd: str, verbose: bool) -> Dict[str, Any]:
        """Run Azure CLI command."""
        cmd_list = cmd.split()  # Simple split, improve for quoted args

        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=300
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
```

**Testing Azure CLI Strategy:**

```python
import pytest
from unittest.mock import Mock, patch
from azlin.agentic.strategies.azure_cli import AzureCLIStrategy
from azlin.agentic.strategies.base import ExecutionContext


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for testing."""
    with patch("subprocess.run") as mock:
        yield mock


def test_can_handle_provision_vm():
    """Should handle VM provisioning."""
    strategy = AzureCLIStrategy()
    context = ExecutionContext(
        intent={"intent": "provision_vm"},
        parameters={"vm_name": "test"}
    )

    assert strategy.can_handle(context) is True


def test_can_handle_unsupported_intent():
    """Should not handle unsupported intent."""
    strategy = AzureCLIStrategy()
    context = ExecutionContext(
        intent={"intent": "unsupported"},
        parameters={}
    )

    assert strategy.can_handle(context) is False


def test_execute_dry_run(mock_subprocess):
    """Dry run should not execute commands."""
    strategy = AzureCLIStrategy()
    context = ExecutionContext(
        intent={"intent": "provision_vm"},
        parameters={"vm_name": "test"},
        dry_run=True
    )

    result = strategy.execute(context)

    assert result.success is True
    assert mock_subprocess.call_count == 0  # No actual execution


def test_execute_success(mock_subprocess):
    """Should execute commands and return success."""
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout='{"id": "/subscriptions/.../resourceGroups/test-rg"}',
        stderr=""
    )

    strategy = AzureCLIStrategy()
    context = ExecutionContext(
        intent={"intent": "provision_vm"},
        parameters={"vm_name": "test"}
    )

    result = strategy.execute(context)

    assert result.success is True
    assert len(result.resources_created) > 0
    assert mock_subprocess.call_count > 0


def test_execute_failure(mock_subprocess):
    """Should return failure result on error."""
    mock_subprocess.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="Error: Resource group not found"
    )

    strategy = AzureCLIStrategy()
    context = ExecutionContext(
        intent={"intent": "provision_vm"},
        parameters={"vm_name": "test"}
    )

    result = strategy.execute(context)

    assert result.success is False
    assert result.error is not None
    assert "not found" in result.error
```

## Best Practices

### Type Hints

Always use full type hints:

```python
# Good
def estimate_cost(self, vm_size: str, region: str = "eastus") -> float:
    pass

# Bad
def estimate_cost(self, vm_size, region="eastus"):
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def execute(self, context: ExecutionContext) -> ExecutionResult:
    """Execute intent using this strategy.

    Executes the operation specified in the context using
    strategy-specific implementation.

    Args:
        context: Execution context with intent and parameters

    Returns:
        Execution result with success status, outputs, and resources

    Raises:
        StrategyExecutionError: If execution fails critically

    Example:
        >>> strategy = AzureCLIStrategy()
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
        >>> print(result.success)
        True
    """
    pass
```

### Error Handling

Be explicit about errors:

```python
# Good
try:
    result = subprocess.run(cmd, capture_output=True, timeout=300)
except subprocess.TimeoutExpired as e:
    return ExecutionResult(
        success=False,
        error=f"Command timed out after 300s: {e}"
    )
except FileNotFoundError as e:
    return ExecutionResult(
        success=False,
        error=f"Command not found: {e}"
    )

# Bad
try:
    result = subprocess.run(cmd)
except Exception as e:
    # Too broad, loses information
    return ExecutionResult(success=False, error=str(e))
```

### Configuration

Use dataclasses for configuration:

```python
from dataclasses import dataclass

@dataclass
class StrategyConfig:
    """Configuration for strategy selection."""
    prefer_terraform: bool = False
    prefer_mcp: bool = False
    max_cost: Optional[float] = None
    require_idempotent: bool = True

# Load from dict
config = StrategyConfig(**config_dict)
```

### Testing

Structure tests clearly:

```python
def test_feature_name():
    """Should do X when Y happens."""
    # Arrange
    strategy = AzureCLIStrategy()
    context = ExecutionContext(...)

    # Act
    result = strategy.execute(context)

    # Assert
    assert result.success is True
    assert len(result.resources_created) > 0
```

## Common Pitfalls

### 1. Circular Dependencies

**Problem:**
```python
# strategy_selector.py
from .strategies.azure_cli import AzureCLIStrategy  # Bad

# strategies/azure_cli.py
from ..strategy_selector import StrategySelector  # Circular!
```

**Solution:**
```python
# Use TYPE_CHECKING for type hints only
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..strategy_selector import StrategySelector

# Or import inside function
def some_method(self):
    from ..strategy_selector import StrategySelector
    selector = StrategySelector()
```

### 2. Mutable Default Arguments

**Problem:**
```python
def execute(self, resources: List[str] = []):  # Bad! Shared between calls
    resources.append("new")
```

**Solution:**
```python
from typing import Optional, List

def execute(self, resources: Optional[List[str]] = None):
    if resources is None:
        resources = []
    resources.append("new")
```

### 3. Not Handling API Failures

**Problem:**
```python
response = requests.get(url)  # Might raise exception
data = response.json()  # Might fail
```

**Solution:**
```python
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
except requests.RequestException as e:
    raise MCPError(f"MCP Server request failed: {e}") from e
except json.JSONDecodeError as e:
    raise MCPError(f"Invalid JSON response: {e}") from e
```

### 4. Not Cleaning Up Resources

**Problem:**
```python
def execute(self, context):
    workspace = create_temp_workspace()
    # If error happens here, workspace is leaked
    result = do_work(workspace)
    cleanup_workspace(workspace)
```

**Solution:**
```python
import tempfile
from pathlib import Path

def execute(self, context):
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        result = do_work(workspace)
        # Automatically cleaned up
    return result
```

## Integration Checklist

Before merging:

- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Type checking passes (`mypy`)
- [ ] Linting passes (`ruff` or `flake8`)
- [ ] Documentation updated
- [ ] Examples added
- [ ] Error handling tested
- [ ] Rollback tested
- [ ] Cost estimation verified
- [ ] State persistence works
- [ ] CLI integration tested
- [ ] Dry-run mode works
- [ ] Verbose output useful
- [ ] User confirmation flows
- [ ] Recovery scenarios tested

## Performance Considerations

### Caching

Cache expensive operations:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_vm_price(self, vm_size: str, region: str) -> float:
    """Get VM price (cached)."""
    # Expensive API call
    return fetch_price_from_api(vm_size, region)
```

### Async for Independent Operations

Use asyncio for parallel operations:

```python
import asyncio

async def estimate_all_costs(self, contexts: List[ExecutionContext]) -> List[float]:
    """Estimate costs for multiple contexts in parallel."""
    tasks = [self._estimate_cost_async(ctx) for ctx in contexts]
    return await asyncio.gather(*tasks)
```

### Lazy Loading

Don't load everything upfront:

```python
class StrategySelector:
    def __init__(self):
        self._strategies = None  # Not loaded yet

    @property
    def strategies(self):
        """Lazy load strategies."""
        if self._strategies is None:
            self._strategies = self._load_strategies()
        return self._strategies
```

## Security Considerations

### 1. Command Injection

**Always use list args, never string concatenation:**

```python
# Good
subprocess.run(["az", "vm", "create", "--name", vm_name])

# Bad - vulnerable to injection
subprocess.run(f"az vm create --name {vm_name}", shell=True)
```

### 2. API Key Exposure

**Never log or persist API keys:**

```python
# Good
logger.info(f"Using API key: {api_key[:8]}...")

# Bad
logger.info(f"Using API key: {api_key}")
```

### 3. File Path Traversal

**Validate file paths:**

```python
def get_objective(self, objective_id: str) -> ObjectiveState:
    # Validate UUID format
    try:
        uuid.UUID(objective_id)
    except ValueError:
        raise ValueError(f"Invalid objective ID: {objective_id}")

    path = self.state_dir / f"{objective_id}.json"

    # Ensure path is within state_dir
    if not path.resolve().is_relative_to(self.state_dir.resolve()):
        raise ValueError(f"Invalid path: {path}")

    return self._load(path)
```

## Next Steps

After completing implementation:

1. **Update README.md** with new features
2. **Add examples** to documentation
3. **Create tutorial** for new users
4. **Performance benchmarks** for strategies
5. **Cost optimization** recommendations
6. **Security audit** of all user inputs
7. **User feedback** collection
8. **Monitoring** and telemetry (optional)

## Questions & Support

For questions during implementation:

1. Check existing patterns in codebase
2. Review this guide and API contracts
3. Look at similar modules for inspiration
4. Test incrementally, don't write too much at once
5. Ask for clarification when contracts are ambiguous

Remember: **Ruthless simplicity**. If something feels too complex, it probably is.
