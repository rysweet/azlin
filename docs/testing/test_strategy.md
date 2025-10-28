# Azlin CLI Test Strategy

## Overview

This document defines the comprehensive test strategy for the azlin CLI tool following TDD principles and the 60/30/10 testing pyramid.

## Testing Pyramid Distribution

- **60% Unit Tests**: Fast, isolated tests for individual functions and classes
- **30% Integration Tests**: Tests for module interactions and external service integrations
- **10% E2E Tests**: Complete workflow tests from CLI entry to VM provisioning

## Module Breakdown and Test Counts

Based on the 10 user requirements, we'll organize tests as follows:

### Unit Tests (60% - ~72 tests)

1. **CLI Interface Module** (12 tests)
   - Argument parsing (with --repo, without --repo)
   - Command validation
   - Help text generation
   - Error message formatting
   - Exit code handling
   - Configuration loading

2. **Azure Authentication Module** (10 tests)
   - Credential detection (az CLI, managed identity, env vars)
   - Token validation
   - Credential caching
   - Error handling for missing credentials
   - Mock Azure SDK responses

3. **VM Provisioning Module** (12 tests)
   - VM configuration building
   - Size validation (specific VM sizes)
   - Region validation
   - Ubuntu image selection
   - Network configuration
   - Resource group creation
   - Error handling for quota limits

4. **Tool Installation Module** (9 tests)
   - Installation script generation (for 9 tools)
   - Tool verification logic
   - Installation order validation
   - Error handling for failed installations

5. **SSH Configuration Module** (10 tests)
   - SSH key generation
   - SSH config file updates
   - Connection string building
   - Auto-connect logic
   - Known hosts management

6. **tmux Session Module** (8 tests)
   - Session creation commands
   - Session persistence verification
   - Session attachment logic
   - Error handling for tmux not installed

7. **GitHub Repository Module** (7 tests)
   - Repo URL parsing
   - Clone command generation
   - gh auth detection
   - Conditional cloning logic

8. **Progress Display Module** (4 tests)
   - Progress bar rendering
   - Status message formatting
   - Step tracking
   - Error display

### Integration Tests (30% - ~36 tests)

1. **Azure SDK Integration** (6 tests)
   - Full authentication flow with mocked Azure
   - VM creation with mocked Azure SDK
   - Resource cleanup with mocked Azure SDK
   - Error propagation from Azure SDK
   - Retry logic for transient failures

2. **SSH Integration** (6 tests)
   - Full SSH setup workflow
   - Key-based authentication flow
   - Auto-connect integration with VM provisioning
   - SSH config persistence

3. **GitHub Integration** (5 tests)
   - gh CLI detection and usage
   - Repository cloning workflow
   - gh auth flow integration
   - Conditional repo cloning based on --repo flag

4. **Tool Installation Integration** (6 tests)
   - Sequential installation of all 9 tools
   - Installation failure recovery
   - Tool verification after installation
   - Installation script execution

5. **Progress Display Integration** (5 tests)
   - Progress updates through full workflow
   - Error state display
   - Multi-step progress tracking
   - imessR notification integration

6. **Configuration Management** (4 tests)
   - Config file loading and merging
   - Environment variable overrides
   - Default configuration
   - Invalid configuration handling

7. **Error Recovery Integration** (4 tests)
   - Partial failure handling
   - Rollback on critical failures
   - State persistence for resumption
   - Error notification via imessR

### E2E Tests (10% - ~12 tests)

1. **Complete Workflow Tests** (4 tests)
   - Full workflow with --repo flag (mocked Azure/SSH)
   - Full workflow without --repo flag (mocked Azure/SSH)
   - Workflow with pre-existing VM
   - Workflow with authentication failure

2. **Failure Recovery Tests** (3 tests)
   - VM creation failure and recovery
   - Tool installation failure and partial success
   - Network failure during setup

3. **Edge Cases** (3 tests)
   - Multiple concurrent azlin runs
   - VM already exists with same name
   - SSH key already exists

4. **Notification Tests** (2 tests)
   - Success notification via imessR
   - Failure notification via imessR

## Mocking Strategy

### External Services to Mock

1. **Azure SDK**
   - Mock: `azure.identity`, `azure.mgmt.compute`, `azure.mgmt.network`, `azure.mgmt.resource`
   - Strategy: Create fake Azure responses for VM operations
   - Tools: `unittest.mock.Mock`, `pytest-mock`

2. **SSH/Subprocess**
   - Mock: `subprocess.run()`, `paramiko` (if used)
   - Strategy: Capture SSH commands, simulate successful connections
   - Tools: `unittest.mock.patch`, custom subprocess mock

3. **GitHub CLI (gh)**
   - Mock: `subprocess` calls to `gh` command
   - Strategy: Mock gh CLI responses, simulate auth flow
   - Tools: `unittest.mock.patch`

4. **File System Operations**
   - Mock: SSH config writes, key generation
   - Strategy: Use temporary directories, mock file operations
   - Tools: `pytest.tmpdir`, `unittest.mock.mock_open`

5. **imessR Service**
   - Mock: HTTP calls to imessR API
   - Strategy: Mock requests to notification service
   - Tools: `responses` library or `unittest.mock.patch`

### Mocking Patterns

```python
# Pattern 1: Azure SDK Mock
@pytest.fixture
def mock_azure_client():
    with patch('azure.mgmt.compute.ComputeManagementClient') as mock:
        mock.return_value.virtual_machines.begin_create_or_update.return_value.result.return_value = Mock(
            id='/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/test-vm',
            name='test-vm',
            location='eastus'
        )
        yield mock

# Pattern 2: Subprocess Mock
@pytest.fixture
def mock_subprocess():
    with patch('subprocess.run') as mock:
        mock.return_value = Mock(returncode=0, stdout='success', stderr='')
        yield mock

# Pattern 3: GitHub CLI Mock
@pytest.fixture
def mock_gh_cli():
    with patch('subprocess.run') as mock:
        def gh_side_effect(cmd, *args, **kwargs):
            if 'gh' in cmd and 'auth' in cmd:
                return Mock(returncode=0, stdout='Logged in as user')
            elif 'gh' in cmd and 'repo' in cmd:
                return Mock(returncode=0, stdout='')
            return Mock(returncode=1, stderr='command not found')
        mock.side_effect = gh_side_effect
        yield mock
```

## Test Infrastructure

### Directory Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── unit/                          # 60% - Unit tests
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_azure_auth.py
│   ├── test_vm_provisioning.py
│   ├── test_tool_installation.py
│   ├── test_ssh_config.py
│   ├── test_tmux_session.py
│   ├── test_github_repo.py
│   └── test_progress_display.py
├── integration/                   # 30% - Integration tests
│   ├── __init__.py
│   ├── test_azure_integration.py
│   ├── test_ssh_integration.py
│   ├── test_github_integration.py
│   ├── test_tool_installation_integration.py
│   ├── test_progress_integration.py
│   ├── test_config_management.py
│   └── test_error_recovery.py
├── e2e/                          # 10% - End-to-end tests
│   ├── __init__.py
│   ├── test_complete_workflow.py
│   ├── test_failure_recovery.py
│   ├── test_edge_cases.py
│   └── test_notifications.py
├── fixtures/                      # Test data and fixtures
│   ├── __init__.py
│   ├── azure_responses.py
│   ├── ssh_configs.py
│   └── sample_configs.py
└── mocks/                        # Custom mock implementations
    ├── __init__.py
    ├── azure_mock.py
    ├── subprocess_mock.py
    └── github_mock.py
```

### Shared Fixtures (conftest.py)

```python
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

@pytest.fixture
def temp_ssh_dir(tmp_path):
    """Temporary SSH directory for testing."""
    ssh_dir = tmp_path / '.ssh'
    ssh_dir.mkdir()
    return ssh_dir

@pytest.fixture
def temp_config_dir(tmp_path):
    """Temporary config directory for testing."""
    config_dir = tmp_path / '.azlin'
    config_dir.mkdir()
    return config_dir

@pytest.fixture
def mock_azure_credentials():
    """Mock Azure credentials."""
    with patch('azure.identity.DefaultAzureCredential') as mock:
        mock.return_value.get_token.return_value = Mock(
            token='fake-token',
            expires_on=9999999999
        )
        yield mock

@pytest.fixture
def sample_vm_config():
    """Sample VM configuration."""
    return {
        'name': 'test-vm',
        'size': 'Standard_D2s_v3',
        'region': 'eastus',
        'image': 'Canonical:0001-com-ubuntu-server-jammy:22_04-lts:latest'
    }

@pytest.fixture
def mock_progress_display():
    """Mock progress display to avoid output during tests."""
    with patch('azlin.progress.ProgressDisplay') as mock:
        yield mock.return_value
```

### Test Utilities

```python
# tests/utils.py
from typing import List, Dict, Any
from unittest.mock import Mock

class AzureResponseBuilder:
    """Builder for creating fake Azure API responses."""

    @staticmethod
    def create_vm_response(name: str, location: str, vm_size: str) -> Mock:
        return Mock(
            id=f'/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{name}',
            name=name,
            location=location,
            hardware_profile=Mock(vm_size=vm_size),
            provisioning_state='Succeeded'
        )

    @staticmethod
    def create_error_response(error_code: str, message: str) -> Exception:
        return Exception(f'{error_code}: {message}')

class SubprocessCapture:
    """Capture subprocess calls for verification."""

    def __init__(self):
        self.calls: List[List[str]] = []

    def capture(self, cmd: List[str], **kwargs) -> Mock:
        self.calls.append(cmd)
        return Mock(returncode=0, stdout='', stderr='')

    def assert_called_with_command(self, command: str):
        assert any(command in ' '.join(call) for call in self.calls), \
            f"Expected command '{command}' not found in {self.calls}"
```

## Test Data Fixtures

### Azure Responses (tests/fixtures/azure_responses.py)

```python
"""Sample Azure API responses for testing."""

SAMPLE_VM_RESPONSE = {
    'id': '/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/dev-vm',
    'name': 'dev-vm',
    'location': 'eastus',
    'properties': {
        'vmId': 'vm-12345',
        'hardwareProfile': {'vmSize': 'Standard_D2s_v3'},
        'storageProfile': {
            'imageReference': {
                'publisher': 'Canonical',
                'offer': '0001-com-ubuntu-server-jammy',
                'sku': '22_04-lts',
                'version': 'latest'
            }
        },
        'osProfile': {
            'computerName': 'dev-vm',
            'adminUsername': 'azureuser'
        },
        'networkProfile': {
            'networkInterfaces': [{
                'id': '/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/dev-vm-nic'
            }]
        },
        'provisioningState': 'Succeeded'
    }
}

SAMPLE_NETWORK_INTERFACE = {
    'id': '/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/networkInterfaces/dev-vm-nic',
    'properties': {
        'ipConfigurations': [{
            'properties': {
                'publicIPAddress': {
                    'id': '/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/dev-vm-ip'
                }
            }
        }]
    }
}

SAMPLE_PUBLIC_IP = {
    'id': '/subscriptions/sub-id/resourceGroups/azlin-rg/providers/Microsoft.Network/publicIPAddresses/dev-vm-ip',
    'properties': {
        'ipAddress': '20.123.45.67'
    }
}
```

### SSH Configurations (tests/fixtures/ssh_configs.py)

```python
"""Sample SSH configurations for testing."""

SAMPLE_SSH_CONFIG = """
Host azlin-dev
    HostName 20.123.45.67
    User azureuser
    IdentityFile ~/.ssh/azlin_rsa
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
"""

SAMPLE_SSH_KEY_PUBLIC = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... azureuser@azlin"
# Note: For testing, generate keys dynamically rather than including sample private keys
```

## TDD Approach

### Red-Green-Refactor Cycle

1. **RED**: Write failing tests first
   - Start with unit tests for core functionality
   - Tests should fail because implementation doesn't exist yet
   - Focus on testing behavior, not implementation

2. **GREEN**: Write minimal code to pass tests
   - Implement just enough to make tests pass
   - No premature optimization
   - Keep it simple and focused

3. **REFACTOR**: Improve code while keeping tests green
   - Extract common patterns
   - Improve naming and structure
   - Ensure tests still pass

### Test-First Examples

```python
# Example 1: CLI Argument Parsing (RED phase)
def test_cli_accepts_repo_argument():
    """Test that CLI accepts --repo argument."""
    # This test will fail - no implementation yet
    from azlin.cli import parse_args

    args = parse_args(['--repo', 'https://github.com/user/repo'])

    assert args.repo == 'https://github.com/user/repo'
    assert args.provision_vm is True  # Default

# Example 2: Azure Authentication (RED phase)
def test_azure_auth_detects_az_cli():
    """Test that Azure auth detects az CLI credentials."""
    from azlin.azure_auth import AzureAuthenticator

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout='{"accessToken": "token123"}')

        auth = AzureAuthenticator()
        credentials = auth.get_credentials()

        assert credentials is not None
        assert credentials.method == 'az_cli'

# Example 3: VM Provisioning (RED phase)
def test_vm_provisioner_creates_vm_with_correct_size():
    """Test VM provisioner uses correct VM size."""
    from azlin.vm_provisioning import VMProvisioner

    provisioner = VMProvisioner(size='Standard_D2s_v3', region='eastus')
    config = provisioner.build_vm_config()

    assert config.hardware_profile.vm_size == 'Standard_D2s_v3'
    assert config.location == 'eastus'
```

## Critical Test Scenarios

### Boundary Conditions

1. **Empty inputs**: Test with no --repo argument, empty config files
2. **Invalid inputs**: Test with invalid VM sizes, regions, repo URLs
3. **Missing tools**: Test behavior when gh CLI, tmux not installed
4. **Authentication failures**: Test all Azure auth methods failing
5. **Network failures**: Test SSH connection failures, Azure API timeouts

### Error Handling

1. **Azure quota exceeded**: VM creation fails due to quota
2. **SSH connection timeout**: Cannot connect to newly created VM
3. **Tool installation failure**: One or more of the 9 tools fails to install
4. **GitHub clone failure**: Repository doesn't exist or is private
5. **Partial completion**: VM created but tool installation fails

### State Management

1. **Resume after failure**: Test resuming from failed tool installation
2. **Cleanup on abort**: Test proper cleanup when user cancels
3. **Multiple runs**: Test running azlin multiple times with same config
4. **State file corruption**: Test recovery from corrupted state file

## Test Execution

### Running Tests

```bash
# Run all tests
pytest

# Run only unit tests (fast)
pytest tests/unit/

# Run with coverage
pytest --cov=azlin --cov-report=html

# Run specific test file
pytest tests/unit/test_cli.py

# Run tests matching pattern
pytest -k "test_azure"

# Run with verbose output
pytest -v

# Run tests in parallel
pytest -n auto
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      - name: Run unit tests
        run: pytest tests/unit/ --cov=azlin
      - name: Run integration tests
        run: pytest tests/integration/
      - name: Run E2E tests
        run: pytest tests/e2e/
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Test Quality Metrics

### Coverage Targets

- **Unit Tests**: 90%+ coverage of business logic
- **Integration Tests**: 80%+ coverage of integration points
- **E2E Tests**: 100% coverage of critical user workflows

### Performance Targets

- **Unit Tests**: < 5 seconds total
- **Integration Tests**: < 30 seconds total
- **E2E Tests**: < 2 minutes total
- **Full Suite**: < 3 minutes total

### Quality Gates

1. All tests must pass before merge
2. No decrease in code coverage
3. No new test warnings or failures
4. All new features must have tests
5. All bug fixes must have regression tests

## Dependencies

### Test Dependencies (pyproject.toml)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
    "pytest-asyncio>=0.21.0",
    "pytest-xdist>=3.3.0",  # Parallel test execution
    "responses>=0.23.0",     # HTTP mocking
    "freezegun>=1.2.0",      # Time mocking
]
```

## Maintenance

### When to Update Tests

1. **New features**: Add tests before implementing feature
2. **Bug fixes**: Add regression test before fixing bug
3. **Refactoring**: Ensure all tests still pass
4. **Dependency updates**: Verify mocks still work with new versions

### Test Maintenance Guidelines

1. **Keep tests focused**: One test per behavior
2. **Avoid test interdependence**: Tests should not depend on each other
3. **Use descriptive names**: Test name should describe the behavior
4. **Mock external services**: Never hit real Azure API in tests
5. **Keep tests fast**: Unit tests should run in milliseconds

## Summary

This test strategy provides:

- **Comprehensive coverage**: 120 tests following 60/30/10 pyramid
- **TDD approach**: Write tests first, then implementation
- **Strategic mocking**: Mock all external services (Azure, SSH, GitHub, imessR)
- **Clear organization**: Separate unit, integration, and E2E tests
- **Fast feedback**: Unit tests run in seconds
- **Maintainability**: Well-structured fixtures and utilities

The strategy ensures high confidence in the azlin CLI while maintaining fast test execution and clear test organization.
