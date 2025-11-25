# GitHub Runners


## Overview

This specification defines the GitHub Actions self-hosted runner fleet implementation for azlin, enabling VM pools to function as auto-scaling CI/CD runners.

## Architecture

### Component Diagram

```
CLI Command (azlin github-runner enable)
    ↓
RunnerLifecycleManager (Orchestrator)
    ↓
    ├─→ RunnerProvisioner (GitHub API Integration)
    ├─→ JobQueueMonitor (Queue Metrics)
    ├─→ AutoScaler (Scaling Decisions)
    └─→ VMProvisioner (Existing - VM Lifecycle)
```

## Module 1: RunnerProvisioner

**File**: `src/azlin/modules/github_runner_provisioner.py`

**Purpose**: Handle GitHub Actions runner registration/deregistration via REST API

### Data Models

```python
@dataclass
class RunnerConfig:
    """Configuration for a GitHub Actions runner."""
    repo_owner: str
    repo_name: str
    runner_name: str
    labels: list[str]
    runner_group: str | None = None

@dataclass
class RunnerRegistration:
    """Details of a registered runner."""
    runner_id: int
    runner_name: str
    registration_token: str
    token_expires_at: datetime

@dataclass
class RunnerInfo:
    """Runtime information about a runner."""
    runner_id: int
    runner_name: str
    status: Literal["online", "offline"]
    busy: bool
    labels: list[str]
```

### Public Interface

```python
class GitHubRunnerProvisioner:
    """Manage GitHub Actions runner registration via API."""

    @classmethod
    def get_registration_token(
        cls,
        repo_owner: str,
        repo_name: str,
        github_token: str
    ) -> str:
        """Get registration token from GitHub API.

        API: POST /repos/{owner}/{repo}/actions/runners/registration-token
        Token expires after 1 hour.
        """

    @classmethod
    def register_runner(
        cls,
        ssh_config: SSHConfig,
        config: RunnerConfig,
        registration_token: str
    ) -> int:
        """Register runner on VM and return runner ID.

        Steps:
        1. Download runner binary if needed
        2. Run ./config.sh with token and labels
        3. Extract runner ID from response
        4. Start runner service
        """

    @classmethod
    def deregister_runner(
        cls,
        repo_owner: str,
        repo_name: str,
        runner_id: int,
        github_token: str
    ) -> None:
        """Remove runner from GitHub.

        API: DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}
        """

    @classmethod
    def get_runner_info(
        cls,
        repo_owner: str,
        repo_name: str,
        runner_id: int,
        github_token: str
    ) -> RunnerInfo:
        """Get current runner status.

        API: GET /repos/{owner}/{repo}/actions/runners/{runner_id}
        """
```

### API Endpoints Used

- `POST /repos/{owner}/{repo}/actions/runners/registration-token`
- `DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}`
- `GET /repos/{owner}/{repo}/actions/runners/{runner_id}`

### Security Requirements

- HTTPS only for API calls
- Token validation before operations
- No token storage (environment variable only)
- Input sanitization for repo names and labels
- Timeout on API calls (30 seconds)

### Error Handling

```python
class RunnerProvisioningError(Exception):
    """Base error for runner provisioning."""

class RegistrationTokenError(RunnerProvisioningError):
    """Failed to get registration token."""

class RunnerRegistrationError(RunnerProvisioningError):
    """Failed to register runner."""

class RunnerDeregistrationError(RunnerProvisioningError):
    """Failed to deregister runner."""
```

## Module 2: JobQueueMonitor

**File**: `src/azlin/modules/github_queue_monitor.py`

**Purpose**: Monitor GitHub Actions job queue depth for scaling decisions

### Data Models

```python
@dataclass
class QueueMetrics:
    """Metrics about the GitHub Actions job queue."""
    pending_jobs: int
    in_progress_jobs: int
    queued_jobs: int
    total_jobs: int
    timestamp: datetime

    @property
    def needs_scaling(self) -> bool:
        """Quick check if scaling might be needed."""
        return self.pending_jobs > 0 or self.queued_jobs > 0
```

### Public Interface

```python
class GitHubJobQueueMonitor:
    """Monitor GitHub Actions job queue."""

    @classmethod
    def get_queue_metrics(
        cls,
        repo_owner: str,
        repo_name: str,
        labels: list[str] | None,
        github_token: str
    ) -> QueueMetrics:
        """Get current queue metrics for repository.

        API: GET /repos/{owner}/{repo}/actions/runs?status=queued
        API: GET /repos/{owner}/{repo}/actions/runs?status=in_progress

        If labels provided, filter jobs by runner labels.
        """

    @classmethod
    def get_pending_job_count(
        cls,
        repo_owner: str,
        repo_name: str,
        labels: list[str] | None,
        github_token: str
    ) -> int:
        """Get count of pending jobs (convenience method)."""
```

### API Endpoints Used

- `GET /repos/{owner}/{repo}/actions/runs?status=queued`
- `GET /repos/{owner}/{repo}/actions/runs?status=in_progress`
- `GET /repos/{owner}/{repo}/actions/runs?per_page=100`

### Filtering Logic

Jobs are filtered by checking workflow run labels against runner labels:
- If no labels specified: count all jobs
- If labels specified: count jobs where ALL labels match

## Module 3: AutoScaler

**File**: `src/azlin/modules/github_runner_autoscaler.py`

**Purpose**: Make intelligent scaling decisions based on queue metrics

### Data Models

```python
@dataclass
class ScalingConfig:
    """Configuration for autoscaling behavior."""
    min_runners: int = 0
    max_runners: int = 10
    jobs_per_runner: int = 2  # Target ratio
    scale_up_threshold: int = 2  # Pending jobs to trigger scale up
    scale_down_threshold: int = 0  # Idle runners to trigger scale down
    cooldown_seconds: int = 300  # Wait between scaling actions

@dataclass
class ScalingDecision:
    """Decision about scaling action."""
    action: Literal["scale_up", "scale_down", "maintain"]
    target_runner_count: int
    current_runner_count: int
    reason: str
```

### Public Interface

```python
class GitHubRunnerAutoScaler:
    """Make scaling decisions for runner fleet."""

    @classmethod
    def calculate_scaling_decision(
        cls,
        queue_metrics: QueueMetrics,
        current_runner_count: int,
        config: ScalingConfig,
        last_scaling_action: datetime | None = None
    ) -> ScalingDecision:
        """Calculate scaling decision based on metrics.

        Logic:
        1. Check cooldown period
        2. Calculate target runners = pending_jobs / jobs_per_runner
        3. Apply min/max constraints
        4. Determine action (up/down/maintain)
        """
```

### Scaling Algorithm

```
target_runners = ceil(pending_jobs / jobs_per_runner)
target_runners = max(min_runners, min(max_runners, target_runners))

if target_runners > current_runners + scale_up_threshold:
    action = "scale_up"
elif target_runners < current_runners - scale_down_threshold:
    action = "scale_down"
else:
    action = "maintain"
```

## Module 4: RunnerLifecycleManager

**File**: `src/azlin/modules/github_runner_lifecycle.py`

**Purpose**: Orchestrate complete ephemeral runner lifecycle

### Data Models

```python
@dataclass
class RunnerLifecycleConfig:
    """Configuration for runner lifecycle management."""
    runner_config: RunnerConfig
    vm_config: VMConfig
    github_token: str
    max_job_count: int = 1  # Ephemeral: 1 job per runner
    rotation_interval_hours: int = 24

@dataclass
class EphemeralRunner:
    """Details of an ephemeral runner."""
    vm_details: VMDetails
    runner_id: int
    runner_name: str
    created_at: datetime
    jobs_completed: int
    status: Literal["provisioning", "registered", "active", "draining", "destroyed"]
```

### Public Interface

```python
class GitHubRunnerLifecycleManager:
    """Manage complete runner lifecycle."""

    @classmethod
    def provision_ephemeral_runner(
        cls,
        config: RunnerLifecycleConfig
    ) -> EphemeralRunner:
        """Provision new ephemeral runner.

        Steps:
        1. Provision VM using VMProvisioner
        2. Get registration token
        3. Register runner on VM
        4. Configure as ephemeral (--ephemeral flag)
        5. Start runner service
        """

    @classmethod
    def destroy_runner(
        cls,
        runner: EphemeralRunner,
        config: RunnerLifecycleConfig
    ) -> None:
        """Destroy ephemeral runner.

        Steps:
        1. Stop runner service on VM
        2. Deregister from GitHub
        3. Delete VM
        """

    @classmethod
    def rotate_runner(
        cls,
        old_runner: EphemeralRunner,
        config: RunnerLifecycleConfig
    ) -> EphemeralRunner:
        """Rotate runner for security.

        Steps:
        1. Provision new runner
        2. Wait for new runner to be ready
        3. Destroy old runner
        """

    @classmethod
    def check_runner_health(
        cls,
        runner: EphemeralRunner,
        github_token: str
    ) -> bool:
        """Check if runner is healthy."""
```

## Module 5: CLI Integration

**File**: `src/azlin/commands/github_runner.py`

**Purpose**: Provide CLI commands for runner management

### Commands

```bash
# Enable runner fleet on a pool
azlin github-runner enable \
    --repo owner/repo \
    --pool ci-workers \
    --labels "linux,docker" \
    --min-runners 0 \
    --max-runners 10

# Disable runner fleet
azlin github-runner disable --pool ci-workers

# Show runner fleet status
azlin github-runner status --pool ci-workers

# Scale runner fleet manually
azlin github-runner scale --pool ci-workers --count 5
```

### Configuration Storage

Configuration stored in azlin config file:

```json
{
  "github_runner_fleets": {
    "ci-workers": {
      "repo_owner": "myorg",
      "repo_name": "myrepo",
      "labels": ["linux", "docker"],
      "min_runners": 0,
      "max_runners": 10,
      "enabled": true
    }
  }
}
```

## Testing Strategy

### Unit Tests

Each module has comprehensive unit tests:

1. **RunnerProvisioner**: Mock GitHub API responses
2. **JobQueueMonitor**: Mock API responses with various queue states
3. **AutoScaler**: Test scaling logic with different scenarios
4. **RunnerLifecycleManager**: Mock VM provisioning and API calls

### Integration Tests

Test end-to-end flows with mocked external services:

1. Provision ephemeral runner flow
2. Auto-scaling up flow
3. Auto-scaling down flow
4. Runner rotation flow

### Manual Testing

CLI commands tested manually:

1. Enable fleet on test pool
2. Verify runners register with GitHub
3. Trigger workflow and verify job execution
4. Verify auto-scaling behavior
5. Disable fleet and verify cleanup

## Security Considerations

### Token Management

- GitHub token from environment variable `GITHUB_TOKEN`
- Never store tokens in config files
- Tokens validated before use
- Registration tokens used immediately and discarded

### Input Validation

- Repository names: `^[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$`
- Pool names: `^[a-zA-Z0-9_-]+$`
- Labels: `^[a-zA-Z0-9._-]+$`
- Runner names: Unique identifiers generated

### API Security

- HTTPS only
- Timeout on all requests (30 seconds)
- Rate limit handling (exponential backoff)
- Error messages sanitized (no token exposure)

## Performance Considerations

### Polling Intervals

- Queue monitoring: Every 60 seconds
- Runner health checks: Every 120 seconds
- Scaling decisions: After each queue check

### Concurrency

- Use existing BatchExecutor for parallel operations
- Maximum 10 concurrent provisioning operations
- Graceful degradation on API rate limits

## Dependencies

### External

- `requests`: HTTP client for GitHub API
- Existing azlin modules: vm_provisioning, ssh_connector, config_manager

### Python Version

- Python 3.11+ (existing azlin requirement)

## Acceptance Criteria

1. ✓ Register VMs as GitHub Actions runners
2. ✓ Auto-scaling based on job queue depth
3. ✓ Ephemeral runners (per-job lifecycle)
4. ✓ Runner rotation for security
5. ✓ CLI command `azlin github-runner enable --repo owner/repo --pool pool-name`
6. ✓ No credential storage (token from environment)
7. ✓ Comprehensive test coverage (>80%)
8. ✓ Philosophy compliance (simplicity, modularity, zero-BS)
