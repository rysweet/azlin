## Azlin CLI Test Suite

Comprehensive test suite following TDD principles and the 60/30/10 testing pyramid.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=azlin --cov-report=html

# Run specific test level
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

## Directory Structure

```
tests/
├── README.md                    # This file
├── __init__.py                  # Test suite initialization
├── conftest.py                  # Shared fixtures (15+ fixtures)
├── utils.py                     # Test utilities and helpers
│
├── unit/                        # 60% - Unit tests (72 tests)
│   ├── test_cli.py             # CLI argument parsing (24 tests)
│   ├── test_azure_auth.py      # Azure authentication (20 tests)
│   └── test_vm_provisioning.py # VM provisioning (28 tests)
│
├── integration/                 # 30% - Integration tests (36 tests)
│   └── test_azure_integration.py # Azure SDK integration (11 tests)
│
├── e2e/                         # 10% - End-to-end tests (12 tests)
│   └── test_complete_workflow.py # Complete workflows (12 tests)
│
├── fixtures/                    # Test data
│   ├── azure_responses.py      # Azure API response fixtures
│   ├── ssh_configs.py          # SSH configuration fixtures
│   └── sample_configs.py       # Sample azlin configs
│
└── mocks/                       # Mock implementations
    ├── azure_mock.py           # Azure SDK mocks
    ├── subprocess_mock.py      # Subprocess/SSH mocks
    └── github_mock.py          # GitHub CLI/API mocks
```

## Test Levels

### Unit Tests (60%)
**Location:** `tests/unit/`
**Purpose:** Test individual functions and classes in isolation
**Characteristics:**
- Fast execution (< 5 seconds total)
- Heavy use of mocking
- No external dependencies
- 90%+ code coverage target

**Modules:**
- `test_cli.py` - CLI argument parsing and configuration
- `test_azure_auth.py` - Azure credential detection and validation
- `test_vm_provisioning.py` - VM configuration and provisioning logic

### Integration Tests (30%)
**Location:** `tests/integration/`
**Purpose:** Test module interactions and external service integration
**Characteristics:**
- Moderate execution time (< 30 seconds total)
- Strategic mocking of external services
- Tests component integration
- 80%+ code coverage target

**Modules:**
- `test_azure_integration.py` - Full Azure SDK integration workflow

### E2E Tests (10%)
**Location:** `tests/e2e/`
**Purpose:** Test complete user workflows
**Characteristics:**
- Longer execution time (< 2 minutes total)
- Minimal mocking (only external services)
- Tests entire application flow
- 100% coverage of critical paths

**Modules:**
- `test_complete_workflow.py` - Complete CLI workflows

## Fixtures

### Shared Fixtures (`conftest.py`)

#### Directory Fixtures
- `temp_ssh_dir` - Temporary SSH directory
- `temp_config_dir` - Temporary azlin config directory
- `temp_home_dir` - Temporary home directory with $HOME set

#### Azure Fixtures
- `mock_azure_credentials` - Mock Azure authentication
- `mock_azure_compute_client` - Mock VM operations
- `mock_azure_network_client` - Mock network operations
- `mock_azure_resource_client` - Mock resource group operations

#### Subprocess Fixtures
- `mock_subprocess_success` - Successful subprocess execution
- `mock_subprocess_failure` - Failed subprocess execution
- `capture_subprocess_calls` - Capture all subprocess calls

#### GitHub Fixtures
- `mock_gh_cli_authenticated` - Authenticated gh CLI
- `mock_gh_cli_not_installed` - gh CLI not available

#### SSH Fixtures
- `mock_ssh_keygen` - SSH key generation
- `mock_ssh_connection` - SSH connection simulation

#### Configuration Fixtures
- `sample_vm_config` - Sample VM configuration
- `sample_azlin_config` - Complete azlin configuration

## Mock Implementations

### Azure Mocks (`mocks/azure_mock.py`)

**Classes:**
- `MockAzureCredential` - Azure authentication
- `MockVirtualMachine` - VM resource
- `MockPublicIPAddress` - Public IP resource
- `MockNetworkInterface` - Network interface
- `MockResourceGroup` - Resource group
- `MockPoller` - Long-running operations
- `MockComputeManagementClient` - Complete compute client
- `MockNetworkManagementClient` - Complete network client
- `MockResourceManagementClient` - Complete resource client

**Usage:**
```python
from tests.mocks.azure_mock import create_mock_azure_environment

def test_vm_provisioning():
    mock_env = create_mock_azure_environment()

    with patch('azure.mgmt.compute.ComputeManagementClient',
               return_value=mock_env['compute_client']):
        # Test code here
        pass
```

### Subprocess Mocks (`mocks/subprocess_mock.py`)

**Classes:**
- `SubprocessCallCapture` - Record subprocess calls
- `CommandRouter` - Route commands to handlers

**Pre-configured Handlers:**
- `ssh_keygen_handler` - SSH key generation
- `ssh_connection_handler` - SSH connections
- `gh_cli_handler` - GitHub CLI commands
- `apt_install_handler` - Package installation
- `tmux_handler` - tmux operations

**Usage:**
```python
from tests.mocks.subprocess_mock import create_configured_router

def test_ssh_commands():
    router = create_configured_router()

    with patch('subprocess.run', router.route):
        # Test code here
        pass
```

### GitHub Mocks (`mocks/github_mock.py`)

**Classes:**
- `MockGitHubCLI` - Complete gh CLI simulation
- `MockGitHubAPI` - GitHub REST API simulation
- `GitHubMockFactory` - Pre-configured scenarios

**Usage:**
```python
from tests.mocks.github_mock import GitHubMockFactory, create_mock_gh_subprocess_handler

def test_github_operations():
    gh_cli, gh_api = GitHubMockFactory.create_authenticated_scenario()
    handler = create_mock_gh_subprocess_handler(gh_cli)

    with patch('subprocess.run', handler):
        # Test code here
        pass
```

## Test Utilities

### AzureResponseBuilder
Create realistic Azure API responses:

```python
from tests.utils import AzureResponseBuilder

vm = AzureResponseBuilder.create_vm_response(
    name='test-vm',
    location='eastus',
    vm_size='Standard_D2s_v3'
)
```

### SubprocessCapture
Record and verify subprocess calls:

```python
from tests.utils import SubprocessCapture

capture = SubprocessCapture()
with patch('subprocess.run', capture.capture):
    # Code that calls subprocess
    pass

capture.assert_called_with_command('ssh-keygen')
```

### ConfigBuilder
Fluent configuration builder:

```python
from tests.utils import ConfigBuilder

config = (ConfigBuilder()
    .with_vm(size='Standard_D2s_v3', region='eastus')
    .with_tools(['git', 'python3', 'docker'])
    .with_ssh(auto_connect=True)
    .build())
```

### FileSystemHelper
File operations and assertions:

```python
from tests.utils import FileSystemHelper

FileSystemHelper.create_ssh_key_pair(Path('~/.ssh/azlin_rsa'))
FileSystemHelper.assert_file_exists(Path('~/.ssh/azlin_rsa'))
FileSystemHelper.assert_file_contains(Path('~/.ssh/config'), 'Host azlin-dev')
```

## Test Data Fixtures

### Azure Responses (`fixtures/azure_responses.py`)
```python
from tests.fixtures.azure_responses import (
    SAMPLE_VM_RESPONSE,
    SAMPLE_PUBLIC_IP,
    SAMPLE_NETWORK_INTERFACE,
    QUOTA_EXCEEDED_ERROR,
    create_vm_response
)
```

### SSH Configurations (`fixtures/ssh_configs.py`)
```python
from tests.fixtures.ssh_configs import (
    SAMPLE_SSH_CONFIG,
    SAMPLE_SSH_KEY_PRIVATE,
    SAMPLE_SSH_KEY_PUBLIC,
    create_ssh_config_entry
)
```

### Azlin Configurations (`fixtures/sample_configs.py`)
```python
from tests.fixtures.sample_configs import (
    MINIMAL_CONFIG,
    COMPLETE_CONFIG,
    CONFIG_WITH_CUSTOM_TOOLS,
    create_config
)
```

## Running Tests

### All Tests
```bash
pytest
```

### Unit Tests Only
```bash
pytest tests/unit/
```

### Integration Tests Only
```bash
pytest tests/integration/
```

### E2E Tests Only
```bash
pytest tests/e2e/
```

### Specific Test File
```bash
pytest tests/unit/test_cli.py
```

### Specific Test Class
```bash
pytest tests/unit/test_cli.py::TestCLIArgumentParsing
```

### Specific Test
```bash
pytest tests/unit/test_cli.py::TestCLIArgumentParsing::test_cli_accepts_repo_argument
```

### With Coverage
```bash
# Generate coverage report
pytest --cov=azlin --cov-report=html

# View coverage report
open htmlcov/index.html
```

### With Verbose Output
```bash
pytest -v
```

### With Output Capture Disabled
```bash
pytest -s
```

### In Parallel
```bash
pytest -n auto
```

### Matching Pattern
```bash
# Run tests matching "auth"
pytest -k auth

# Run tests matching "azure" but not "integration"
pytest -k "azure and not integration"
```

## Writing Tests

### Test Naming Convention
- Test files: `test_<module>.py`
- Test classes: `Test<Feature>`
- Test functions: `test_<behavior>`

Examples:
- `test_cli.py::TestCLIArgumentParsing::test_cli_accepts_repo_argument`
- `test_azure_auth.py::TestAzureCredentialDetection::test_detects_az_cli_credentials`

### Test Structure (Arrange-Act-Assert)
```python
def test_something():
    # Arrange - Set up test data and mocks
    mock_env = create_mock_azure_environment()

    # Act - Execute the code under test
    result = function_to_test()

    # Assert - Verify the results
    assert result.success is True
    mock_env['compute_client'].some_method.assert_called_once()
```

### Using Fixtures
```python
def test_with_fixtures(mock_azure_credentials, temp_ssh_dir):
    # Fixtures are automatically set up
    result = authenticate()
    assert result is not None
```

### Parameterized Tests
```python
@pytest.mark.parametrize('vm_size,expected', [
    ('Standard_D2s_v3', True),
    ('Standard_D4s_v3', True),
    ('InvalidSize', False)
])
def test_vm_size_validation(vm_size, expected):
    result = validate_vm_size(vm_size)
    assert result == expected
```

### Testing Exceptions
```python
def test_raises_error():
    with pytest.raises(AuthenticationError):
        authenticate_with_invalid_credentials()
```

### Mocking Example
```python
@patch('azlin.azure_auth.DefaultAzureCredential')
def test_authentication(mock_credential):
    mock_credential.return_value.get_token.return_value = Mock(token='fake-token')

    auth = AzureAuthenticator()
    credentials = auth.get_credentials()

    assert credentials is not None
```

## Best Practices

### 1. Test Isolation
- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### 2. Clear Test Names
- Test names should describe the behavior being tested
- Use descriptive assertion messages
- Document complex test scenarios

### 3. Mock External Services
- Never make real API calls in tests
- Use provided mock implementations
- Mock at the boundary (e.g., Azure SDK, subprocess)

### 4. Fast Tests
- Unit tests should run in milliseconds
- Integration tests in seconds
- E2E tests in minutes
- Use parallelization for speed

### 5. Meaningful Assertions
- Test behavior, not implementation details
- Use specific assertions (not just `assert result`)
- Verify mock interactions when relevant

### 6. Maintenance
- Keep tests updated with code changes
- Remove obsolete tests
- Refactor test code like production code

## TDD Workflow

### Red-Green-Refactor

1. **RED**: Write a failing test
```python
def test_new_feature():
    result = new_feature()
    assert result.works is True
```

2. **GREEN**: Write minimal code to make it pass
```python
def new_feature():
    return Mock(works=True)
```

3. **REFACTOR**: Improve the code
```python
def new_feature():
    # Proper implementation
    return FeatureResult(works=True)
```

### TDD Best Practices
- Write tests before implementation
- Start with simplest test case
- Make one test pass at a time
- Commit after each green phase
- Refactor with confidence

## Debugging Tests

### Run with Print Statements
```bash
pytest -s
```

### Drop into Debugger on Failure
```bash
pytest --pdb
```

### Show Local Variables
```bash
pytest -l
```

### Stop on First Failure
```bash
pytest -x
```

### Re-run Failed Tests
```bash
pytest --lf  # Last failed
pytest --ff  # Failed first
```

## CI/CD Integration

### GitHub Actions
Tests run automatically on:
- Every push
- Every pull request
- Scheduled (nightly)

### Coverage Requirements
- Unit tests: 90%+
- Integration tests: 80%+
- E2E tests: 100% of critical paths

### Quality Gates
- All tests must pass
- Coverage must not decrease
- No new warnings

## Documentation

- **docs/testing/test_strategy.md** - Overall test strategy and planning
- **MOCKING_STRATEGY.md** - Detailed mocking approach
- **TEST_IMPLEMENTATION_SUMMARY.md** - Implementation summary
- **tests/README.md** - This file

## Support

For questions or issues with the test suite:
1. Check this README
2. Review docs/testing/test_strategy.md
3. Check MOCKING_STRATEGY.md
4. Review test examples in existing tests
5. Check PATTERNS.md for testing patterns

## Contributing

When adding new tests:
1. Follow TDD workflow (RED-GREEN-REFACTOR)
2. Use existing fixtures and mocks
3. Add new fixtures/mocks to shared files
4. Follow naming conventions
5. Update documentation if adding new patterns
6. Ensure tests are fast and isolated
