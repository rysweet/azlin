# Exhaustive CLI Command Syntax Test Suite Specification

## Document Metadata

- **Version**: 1.0.0
- **Created**: 2025-10-27
- **Target**: 300+ comprehensive syntax tests for all 33 CLI commands
- **Test Framework**: pytest
- **Test Type**: Unit tests using Click's CliRunner

## 1. Test Organization Structure

### 1.1 Directory Layout

```
tests/
└── unit/
    └── cli/
        ├── __init__.py
        ├── conftest.py                      # CLI-specific fixtures
        │
        ├── test_cli_core.py                 # Core CLI tests (help, version)
        │
        ├── provisioning/                    # VM provisioning commands
        │   ├── test_new_command.py
        │   ├── test_vm_command.py
        │   └── test_create_command.py
        │
        ├── lifecycle/                       # VM lifecycle commands
        │   ├── test_start_command.py
        │   ├── test_stop_command.py
        │   ├── test_kill_command.py
        │   ├── test_destroy_command.py
        │   ├── test_killall_command.py
        │   └── test_prune_command.py
        │
        ├── information/                     # Information/status commands
        │   ├── test_list_command.py
        │   ├── test_status_command.py
        │   ├── test_ps_command.py
        │   ├── test_w_command.py
        │   └── test_top_command.py
        │
        ├── connection/                      # Connection commands
        │   ├── test_connect_command.py
        │   ├── test_session_command.py
        │   └── test_clone_command.py
        │
        ├── file_operations/                 # File transfer commands
        │   ├── test_cp_command.py
        │   └── test_sync_command.py
        │
        ├── maintenance/                     # Maintenance commands
        │   ├── test_update_command.py
        │   └── test_os_update_command.py
        │
        ├── monitoring/                      # Monitoring commands
        │   └── test_cost_command.py
        │
        ├── automation/                      # Automation commands (existing)
        │   ├── test_do_command.py
        │   └── test_doit_command.py
        │
        ├── groups/                          # Command groups
        │   ├── test_batch_group.py          # batch command, start, stop, sync
        │   ├── test_env_group.py            # env list, set, delete, clear, export, import
        │   ├── test_keys_group.py           # keys list, rotate, backup, export
        │   ├── test_snapshot_group.py       # snapshot create, list, restore, etc.
        │   ├── test_storage_group.py        # storage create, list, mount, unmount, etc.
        │   └── test_template_group.py       # template list, create, delete, etc.
        │
        └── integration/                     # Cross-command integration tests
            ├── test_option_combinations.py  # Test complex option combinations
            └── test_command_chaining.py     # Test command workflows
```

### 1.2 File Naming Conventions

- **Pattern**: `test_<command_name>_command.py` for single commands
- **Pattern**: `test_<group_name>_group.py` for command groups
- **Class naming**: `Test<CommandName><Category>` (e.g., `TestNewCommandSyntax`)
- **Test method naming**: `test_<scenario>_<expected_outcome>` (e.g., `test_missing_required_arg_shows_error`)

## 2. Command Inventory

### 2.1 Primary Commands (27)

**Provisioning (3)**:
- `azlin new` - Create new VM (alias for `vm`)
- `azlin vm` - Create new VM
- `azlin create` - Create new VM (alternative)

**Lifecycle Management (6)**:
- `azlin start` - Start stopped VM
- `azlin stop` - Stop running VM
- `azlin kill` - Delete single VM
- `azlin destroy` - Delete single VM (alias)
- `azlin killall` - Delete all VMs in resource group
- `azlin prune` - Clean up unused resources

**Information/Status (5)**:
- `azlin list` - List VMs
- `azlin status` - Show VM status
- `azlin ps` - Show running processes
- `azlin w` - Show who's logged in
- `azlin top` - Show resource usage

**Connection (3)**:
- `azlin connect` - SSH to VM
- `azlin session` - Manage tmux sessions
- `azlin clone` - Clone VM

**File Operations (2)**:
- `azlin cp` - Copy files to/from VM
- `azlin sync` - Sync directories

**Maintenance (2)**:
- `azlin update` - Update azlin
- `azlin os-update` - Update VM OS

**Monitoring (1)**:
- `azlin cost` - Show cost information

**Automation (2)**:
- `azlin do` - Execute command on VM
- `azlin doit` - Natural language automation

**Core (3)**:
- `azlin help` - Show help
- `azlin --version` - Show version
- `azlin` (no args) - Show default help

### 2.2 Command Groups (6)

**batch** (4 subcommands):
- `azlin batch command` - Run command on multiple VMs
- `azlin batch start` - Start multiple VMs
- `azlin batch stop` - Stop multiple VMs
- `azlin batch sync` - Sync to multiple VMs

**env** (6 subcommands):
- `azlin env list` - List environment variables
- `azlin env set` - Set environment variable
- `azlin env delete` - Delete environment variable
- `azlin env clear` - Clear all environment variables
- `azlin env export` - Export environment to file
- `azlin env import` - Import environment from file

**keys** (4 subcommands):
- `azlin keys list` - List SSH keys
- `azlin keys rotate` - Rotate SSH keys
- `azlin keys backup` - Backup SSH keys
- `azlin keys export` - Export SSH keys

**snapshot** (8 subcommands):
- `azlin snapshot create` - Create snapshot
- `azlin snapshot list` - List snapshots
- `azlin snapshot restore` - Restore snapshot
- `azlin snapshot delete` - Delete snapshot
- `azlin snapshot enable` - Enable auto-snapshots
- `azlin snapshot disable` - Disable auto-snapshots
- `azlin snapshot status` - Show snapshot status
- `azlin snapshot sync` - Sync snapshots

**storage** (6 subcommands):
- `azlin storage create` - Create NFS storage
- `azlin storage list` - List storage accounts
- `azlin storage mount` - Mount NFS storage
- `azlin storage unmount` - Unmount NFS storage
- `azlin storage status` - Show storage status
- `azlin storage delete` - Delete storage account

**template** (5 subcommands):
- `azlin template list` - List templates
- `azlin template create` - Create template
- `azlin template delete` - Delete template
- `azlin template export` - Export template
- `azlin template import` - Import template

**Total Commands**: 27 primary + 33 subcommands = 60 command variants

## 3. Test Categories

### 3.1 Syntax Validation Tests (5-8 tests per command)

**Test cases**:
1. **No arguments** - When required args missing
2. **Required arguments only** - Minimal valid syntax
3. **Optional arguments** - Each optional arg individually
4. **Empty string arguments** - Args that are present but empty
5. **Whitespace-only arguments** - Args with only spaces/tabs
6. **Maximum arguments** - All options provided
7. **Positional argument order** - Verify correct ordering
8. **Extra unexpected arguments** - Too many args

**Example pattern**:
```python
class TestNewCommandSyntax:
    """Test syntax validation for 'azlin new' command."""

    def test_no_arguments_shows_help(self):
        """Test that 'azlin new' with no args shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["new"])

        assert result.exit_code == 0
        assert "Usage:" in result.output or "Options:" in result.output

    def test_with_repo_only_succeeds(self):
        """Test that 'azlin new --repo URL' is valid minimal syntax."""
        runner = CliRunner()
        with patch("azlin.vm_manager.VMManager.create_vm"):
            result = runner.invoke(main, ["new", "--repo", "https://github.com/user/repo"])

            # Should succeed (or fail for other reasons, not syntax)
            assert "Error: Missing" not in result.output

    def test_empty_string_repo_shows_error(self):
        """Test that 'azlin new --repo \"\"' shows validation error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", ""])

        assert result.exit_code != 0
        assert "empty" in result.output.lower() or "invalid" in result.output.lower()
```

### 3.2 Option Combination Tests (8-12 tests per command)

**Test cases**:
1. **Mutually exclusive options** - Options that can't be used together
2. **Dependent options** - Options that require other options
3. **Conflicting option values** - Options with incompatible values
4. **Boolean flag combinations** - Multiple flags together
5. **Short + long form mixing** - `-rg` and `--resource-group`
6. **Repeated options** - Same option specified multiple times
7. **Option order independence** - Options in different orders
8. **All compatible options** - Maximum valid combination

**Example pattern**:
```python
class TestNewCommandOptions:
    """Test option combinations for 'azlin new' command."""

    def test_pool_and_name_are_mutually_exclusive(self):
        """Test that --pool and --name cannot be used together."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "new",
            "--repo", "https://github.com/user/repo",
            "--pool", "3",
            "--name", "custom-vm"
        ])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or "cannot use" in result.output.lower()

    def test_short_and_long_form_resource_group(self):
        """Test that -rg and --resource-group are equivalent."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            # Test with --resource-group
            result1 = runner.invoke(main, ["new", "--repo", "...", "--resource-group", "test-rg"])

            # Test with -rg
            result2 = runner.invoke(main, ["new", "--repo", "...", "-rg", "test-rg"])

            # Both should call create_vm with same resource_group
            assert mock_create.call_count == 2
            call1_kwargs = mock_create.call_args_list[0][1]
            call2_kwargs = mock_create.call_args_list[1][1]
            assert call1_kwargs.get("resource_group") == call2_kwargs.get("resource_group")

    def test_all_valid_options_together(self):
        """Test maximum valid option combination."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm"):
            result = runner.invoke(main, [
                "new",
                "--repo", "https://github.com/user/repo",
                "--vm-size", "Standard_D2s_v3",
                "--region", "eastus",
                "--resource-group", "test-rg",
                "--config", "/path/to/config.yaml",
                "--template", "python-dev",
                "--nfs-storage", "my-storage",
                "--no-auto-connect"
            ])

            # Should succeed (assuming mocks are proper)
            assert "cannot use" not in result.output.lower()
```

### 3.3 Alias Tests (2-3 tests per alias)

**Test cases**:
1. **Alias equivalence** - Alias produces same result as primary command
2. **Alias with options** - Alias works with all options
3. **Alias help text** - Help shows alias relationship

**Example pattern**:
```python
class TestCommandAliases:
    """Test command aliases (vm/new/create, kill/destroy)."""

    def test_vm_and_new_are_equivalent(self):
        """Test that 'azlin vm' and 'azlin new' are identical."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            # Test with 'vm'
            result1 = runner.invoke(main, ["vm", "--repo", "https://..."])

            mock_create.reset_mock()

            # Test with 'new'
            result2 = runner.invoke(main, ["new", "--repo", "https://..."])

            # Both should call same underlying function
            assert mock_create.call_count == 1  # Each should call once
            # Exit codes should match
            assert result1.exit_code == result2.exit_code

    def test_kill_and_destroy_are_equivalent(self):
        """Test that 'azlin kill' and 'azlin destroy' are identical."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.delete_vm") as mock_delete:
            result1 = runner.invoke(main, ["kill", "test-vm", "--force"])
            mock_delete.reset_mock()
            result2 = runner.invoke(main, ["destroy", "test-vm", "--force"])

            assert result1.exit_code == result2.exit_code
```

### 3.4 Error Handling Tests (6-10 tests per command)

**Test cases**:
1. **Invalid option values** - Wrong type, out of range
2. **Unknown options** - Options that don't exist
3. **Invalid argument format** - Malformed inputs
4. **Missing required dependencies** - Azure not configured
5. **Resource not found** - VM doesn't exist
6. **Permission errors** - No access to resource
7. **Network errors** - Azure API unavailable
8. **Timeout scenarios** - Long-running operations
9. **Partial failures** - Some operations succeed, some fail
10. **Graceful degradation** - Non-critical failures

**Example pattern**:
```python
class TestNewCommandErrors:
    """Test error handling for 'azlin new' command."""

    def test_invalid_vm_size_shows_error(self):
        """Test that invalid VM size shows clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "...", "--vm-size", "InvalidSize"])

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "not valid" in result.output.lower()

    def test_invalid_region_shows_error(self):
        """Test that invalid region shows clear error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "...", "--region", "mars-central"])

        assert result.exit_code != 0
        assert "region" in result.output.lower()

    def test_unknown_option_shows_error(self):
        """Test that unknown option shows helpful error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--unknown-option", "value"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "unknown option" in result.output.lower()

    def test_missing_azure_credentials_shows_clear_message(self):
        """Test that missing Azure credentials shows helpful error."""
        runner = CliRunner()

        with patch("azure.identity.DefaultAzureCredential", side_effect=Exception("No credentials")):
            result = runner.invoke(main, ["new", "--repo", "https://..."])

            assert result.exit_code != 0
            assert "credential" in result.output.lower() or "authentication" in result.output.lower()
```

### 3.5 Help Text Tests (3-4 tests per command)

**Test cases**:
1. **Command help with --help** - Shows full help text
2. **Command help with -h** - Short form works
3. **Help text completeness** - All options documented
4. **Example usage shown** - Help includes examples

**Example pattern**:
```python
class TestNewCommandHelp:
    """Test help text for 'azlin new' command."""

    def test_help_flag_shows_usage(self):
        """Test that 'azlin new --help' shows complete usage."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Options:" in result.output

    def test_help_documents_all_options(self):
        """Test that help text includes all available options."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        required_options = [
            "--repo",
            "--vm-size",
            "--region",
            "--resource-group",
            "--name",
            "--pool",
            "--no-auto-connect",
            "--config",
            "--template",
            "--nfs-storage"
        ]

        for option in required_options:
            assert option in result.output, f"Option {option} not documented in help"

    def test_help_includes_examples(self):
        """Test that help text includes usage examples."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        # Check for example patterns
        assert "example" in result.output.lower() or "azlin new" in result.output.lower()

    def test_short_help_flag_works(self):
        """Test that -h works as alias for --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "-h"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
```

## 4. Test Patterns and Templates

### 4.1 Basic Command Test Template

```python
"""Unit tests for 'azlin <command>' command syntax."""

from unittest.mock import patch, Mock
import pytest
from click.testing import CliRunner
from azlin.cli import main


class Test<Command>CommandSyntax:
    """Test basic syntax validation for '<command>' command."""

    def test_no_arguments_behavior(self):
        """Test command behavior with no arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["<command>"])

        # Define expected behavior (error, help, or success)
        assert result.exit_code == 0  # or != 0 for error

    def test_required_arguments_only(self):
        """Test command with only required arguments."""
        runner = CliRunner()
        with patch("<mock_path>"):
            result = runner.invoke(main, ["<command>", "<required_arg>"])

            assert result.exit_code == 0

    def test_with_all_options(self):
        """Test command with all available options."""
        runner = CliRunner()
        with patch("<mock_path>"):
            result = runner.invoke(main, [
                "<command>",
                "<required_arg>",
                "--option1", "value1",
                "--option2", "value2"
            ])

            assert result.exit_code == 0


class Test<Command>CommandOptions:
    """Test option combinations for '<command>' command."""

    def test_mutually_exclusive_options(self):
        """Test that mutually exclusive options show error."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "<command>",
            "--option1", "value1",
            "--option2", "value2"  # Conflicts with option1
        ])

        assert result.exit_code != 0
        assert "cannot use" in result.output.lower()

    def test_option_value_validation(self):
        """Test that invalid option values show error."""
        runner = CliRunner()
        result = runner.invoke(main, ["<command>", "--option", "invalid_value"])

        assert result.exit_code != 0


class Test<Command>CommandErrors:
    """Test error handling for '<command>' command."""

    def test_unknown_option_shows_error(self):
        """Test that unknown options show helpful error."""
        runner = CliRunner()
        result = runner.invoke(main, ["<command>", "--unknown-option", "value"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_missing_resource_shows_error(self):
        """Test that missing resource shows clear error."""
        runner = CliRunner()
        with patch("<mock_path>", side_effect=Exception("Not found")):
            result = runner.invoke(main, ["<command>", "nonexistent"])

            assert result.exit_code != 0
            assert "not found" in result.output.lower()


class Test<Command>CommandHelp:
    """Test help text for '<command>' command."""

    def test_help_flag_shows_complete_usage(self):
        """Test that --help shows complete usage information."""
        runner = CliRunner()
        result = runner.invoke(main, ["<command>", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Options:" in result.output
```

### 4.2 Command Group Test Template

```python
"""Unit tests for 'azlin <group>' command group syntax."""

from unittest.mock import patch, Mock
import pytest
from click.testing import CliRunner
from azlin.cli import main


class Test<Group>GroupSyntax:
    """Test basic syntax for '<group>' command group."""

    def test_group_without_subcommand_shows_help(self):
        """Test that 'azlin <group>' shows available subcommands."""
        runner = CliRunner()
        result = runner.invoke(main, ["<group>"])

        assert result.exit_code == 0
        assert "Commands:" in result.output or "Usage:" in result.output

    def test_group_help_flag(self):
        """Test that 'azlin <group> --help' shows group help."""
        runner = CliRunner()
        result = runner.invoke(main, ["<group>", "--help"])

        assert result.exit_code == 0
        assert "<subcommand1>" in result.output
        assert "<subcommand2>" in result.output


class Test<Group><Subcommand>Syntax:
    """Test syntax for '<group> <subcommand>' command."""

    def test_subcommand_no_arguments(self):
        """Test subcommand with no arguments."""
        runner = CliRunner()
        result = runner.invoke(main, ["<group>", "<subcommand>"])

        # Define expected behavior
        assert result.exit_code == 0  # or != 0

    def test_subcommand_with_required_arguments(self):
        """Test subcommand with required arguments."""
        runner = CliRunner()
        with patch("<mock_path>"):
            result = runner.invoke(main, [
                "<group>",
                "<subcommand>",
                "<required_arg>"
            ])

            assert result.exit_code == 0

    def test_subcommand_with_options(self):
        """Test subcommand with options."""
        runner = CliRunner()
        with patch("<mock_path>"):
            result = runner.invoke(main, [
                "<group>",
                "<subcommand>",
                "--option", "value"
            ])

            assert result.exit_code == 0


class Test<Group><Subcommand>Errors:
    """Test error handling for '<group> <subcommand>' command."""

    def test_invalid_subcommand_shows_error(self):
        """Test that invalid subcommand shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["<group>", "invalid-subcommand"])

        assert result.exit_code != 0
        assert "no such command" in result.output.lower()

    def test_missing_required_argument_shows_error(self):
        """Test that missing required argument shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["<group>", "<subcommand>"])

        assert result.exit_code != 0
        assert "required" in result.output.lower() or "missing" in result.output.lower()
```

## 5. Test Coverage Goals

### 5.1 Minimum Tests Per Command

| Command Type | Min Tests | Coverage Target |
|--------------|-----------|-----------------|
| Simple command (no args) | 8 | 95%+ |
| Command with 1-3 options | 12 | 95%+ |
| Command with 4-8 options | 18 | 95%+ |
| Command with 9+ options | 25 | 95%+ |
| Command group (no subcommands) | 5 | 95%+ |
| Subcommand (simple) | 10 | 95%+ |
| Subcommand (complex) | 15 | 95%+ |

### 5.2 Test Distribution

**Total Test Count Target**: 300-350 tests

**Breakdown by category**:
- Syntax validation: ~100 tests (30%)
- Option combinations: ~120 tests (35%)
- Error handling: ~80 tests (24%)
- Help text: ~40 tests (12%)
- Alias tests: ~10 tests (3%)

**Breakdown by command complexity**:
- Core commands (3): ~15 tests
- Simple commands (10): ~120 tests (12 per command)
- Medium commands (12): ~216 tests (18 per command)
- Complex commands (5): ~125 tests (25 per command)
- Command groups (6 groups, 33 subcommands): ~190 tests (~5 per subcommand)

**Total**: ~666 tests (exceeds minimum to ensure exhaustive coverage)

### 5.3 Priority Levels

**Priority 1 (Implement First)** - Core functionality:
1. `azlin new` / `azlin vm` / `azlin create` (provisioning)
2. `azlin list` (information)
3. `azlin connect` (connection)
4. `azlin kill` / `azlin destroy` (cleanup)
5. `azlin help` / `azlin --version` (core)

**Priority 2 (Implement Second)** - Common operations:
6. `azlin start` / `azlin stop` (lifecycle)
7. `azlin status` (information)
8. `azlin cp` / `azlin sync` (file operations)
9. `azlin session` (connection)
10. `azlin killall` (cleanup)

**Priority 3 (Implement Third)** - Advanced features:
11. `azlin batch` group (batch operations)
12. `azlin env` group (environment management)
13. `azlin storage` group (storage management)
14. `azlin snapshot` group (snapshot management)
15. `azlin template` group (template management)

**Priority 4 (Implement Last)** - Specialized:
16. `azlin keys` group (key management)
17. `azlin cost` (monitoring)
18. `azlin update` / `azlin os-update` (maintenance)
19. `azlin prune` (cleanup)
20. `azlin do` / `azlin doit` (automation)

## 6. Success Criteria

### 6.1 Quantitative Metrics

1. **Test Count**: Minimum 300 tests (target 350+)
2. **Coverage**: 95%+ line coverage for CLI module
3. **Pass Rate**: 100% of tests pass
4. **Execution Time**: Full suite completes in < 30 seconds
5. **Flakiness**: 0% flaky tests (100% deterministic)

### 6.2 Qualitative Metrics

1. **Completeness**: Every command has tests for all categories
2. **Clarity**: Test names clearly describe what is being tested
3. **Maintainability**: Tests follow consistent patterns
4. **Documentation**: Each test has clear docstring
5. **Independence**: Tests don't depend on each other
6. **Determinism**: Tests produce same results every run

### 6.3 Coverage Requirements

**Per Command**:
- All arguments tested (positional and optional)
- All option combinations tested
- All error conditions tested
- Help text verified
- Aliases verified (where applicable)

**Per Test File**:
- Minimum 4 test classes per command
- Minimum 8 tests per command
- All code paths exercised
- All error messages validated

## 7. Test Fixtures and Utilities

### 7.1 Required Fixtures (add to conftest.py)

```python
@pytest.fixture
def cli_runner():
    """CliRunner instance for testing Click commands."""
    return CliRunner()


@pytest.fixture
def mock_vm_manager():
    """Mock VMManager for testing without Azure API calls."""
    with patch("azlin.vm_manager.VMManager") as mock:
        mock_instance = Mock()
        mock_instance.create_vm.return_value = {
            "name": "test-vm",
            "status": "Running",
            "ip": "20.123.45.67"
        }
        mock_instance.list_vms.return_value = [
            {"name": "vm1", "status": "Running"},
            {"name": "vm2", "status": "Stopped"}
        ]
        mock_instance.get_vm.return_value = {"name": "test-vm", "status": "Running"}
        mock_instance.delete_vm.return_value = True
        mock.return_value = mock_instance
        yield mock


@pytest.fixture
def mock_azure_cli_success():
    """Mock successful Azure CLI commands."""
    with patch("subprocess.run") as mock:
        mock.return_value = Mock(
            returncode=0,
            stdout='{"id": "/subscriptions/test", "name": "test-vm"}',
            stderr=""
        )
        yield mock


@pytest.fixture
def mock_azure_cli_failure():
    """Mock failed Azure CLI commands."""
    with patch("subprocess.run") as mock:
        mock.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error: Resource not found"
        )
        yield mock


@pytest.fixture
def sample_vm_list():
    """Sample VM list for testing list/status commands."""
    return [
        {
            "name": "test-vm-1",
            "status": "Running",
            "resource_group": "test-rg",
            "location": "eastus",
            "size": "Standard_D2s_v3",
            "public_ip": "20.123.45.67"
        },
        {
            "name": "test-vm-2",
            "status": "Stopped",
            "resource_group": "test-rg",
            "location": "westus",
            "size": "Standard_B2s",
            "public_ip": None
        }
    ]


@pytest.fixture
def invalid_option_values():
    """Common invalid option values for testing validation."""
    return {
        "empty_string": "",
        "whitespace_only": "   ",
        "invalid_url": "not-a-url",
        "invalid_region": "mars-central-1",
        "invalid_vm_size": "NotARealVMSize",
        "negative_number": "-5",
        "non_integer": "abc123",
        "special_chars": "test@#$%^&*()"
    }
```

### 7.2 Helper Functions

```python
def assert_cli_error(result, expected_message_fragment):
    """Assert that CLI invocation failed with expected error message."""
    assert result.exit_code != 0
    assert expected_message_fragment.lower() in result.output.lower()


def assert_cli_success(result):
    """Assert that CLI invocation succeeded."""
    assert result.exit_code == 0
    assert "error" not in result.output.lower()


def assert_help_text_complete(result, expected_options):
    """Assert that help text documents all expected options."""
    assert result.exit_code == 0
    assert "Usage:" in result.output
    for option in expected_options:
        assert option in result.output, f"Option {option} not in help text"


def invoke_with_mock(runner, command_args, mock_target, mock_return_value=None):
    """Invoke CLI with mock for testing."""
    with patch(mock_target) as mock:
        if mock_return_value:
            mock.return_value = mock_return_value
        result = runner.invoke(main, command_args)
        return result, mock
```

## 8. Implementation Guidelines

### 8.1 Development Process

1. **Phase 1**: Set up test infrastructure
   - Create directory structure
   - Add CLI-specific fixtures to conftest.py
   - Create helper utilities

2. **Phase 2**: Implement Priority 1 commands (core)
   - Write tests for each command following template
   - Aim for 100% pass rate before moving on
   - Target: ~60 tests

3. **Phase 3**: Implement Priority 2 commands (common)
   - Focus on most-used commands
   - Target: ~90 additional tests

4. **Phase 4**: Implement Priority 3 commands (advanced)
   - Command groups with subcommands
   - Target: ~120 additional tests

5. **Phase 5**: Implement Priority 4 commands (specialized)
   - Less common but still important
   - Target: ~60 additional tests

6. **Phase 6**: Integration tests
   - Complex option combinations across commands
   - Command chaining scenarios
   - Target: ~20 additional tests

### 8.2 Testing Best Practices

1. **Use CliRunner consistently**: All CLI tests should use Click's CliRunner
2. **Mock external dependencies**: Never make real Azure API calls
3. **Test in isolation**: Each test should be independent
4. **Use descriptive names**: Test names should clearly state what is tested
5. **Keep tests focused**: One assertion concept per test
6. **Document expected behavior**: Clear docstrings for each test
7. **Avoid test duplication**: Use fixtures and helper functions
8. **Test error messages**: Verify exact error message content
9. **Test exit codes**: Verify correct exit code for success/failure
10. **Test stdout/stderr**: Verify output goes to correct stream

### 8.3 CI/CD Integration

```yaml
# Add to .github/workflows/test.yml
- name: Run CLI syntax tests
  run: |
    pytest tests/unit/cli/ \
      --cov=src/azlin/cli.py \
      --cov-report=term-missing \
      --cov-fail-under=95 \
      -v

- name: Generate CLI test report
  run: |
    pytest tests/unit/cli/ \
      --junitxml=reports/cli-tests.xml \
      --html=reports/cli-tests.html
```

## 9. Example Test Files

### 9.1 test_new_command.py (Full Example)

```python
"""Unit tests for 'azlin new' command syntax and behavior."""

from unittest.mock import patch, Mock
import pytest
from click.testing import CliRunner
from azlin.cli import main


class TestNewCommandSyntax:
    """Test basic syntax validation for 'azlin new' command."""

    def test_no_arguments_shows_help(self):
        """Test that 'azlin new' with no arguments shows help text."""
        runner = CliRunner()
        result = runner.invoke(main, ["new"])

        assert result.exit_code == 0
        assert "Usage:" in result.output or "Options:" in result.output

    def test_with_repo_only_is_valid(self):
        """Test that --repo alone is valid minimal syntax."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            result = runner.invoke(main, ["new", "--repo", "https://github.com/user/repo"])

            assert mock_create.called
            assert "Error: Missing" not in result.output

    def test_empty_string_repo_shows_error(self):
        """Test that empty --repo value shows validation error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", ""])

        assert result.exit_code != 0
        assert "empty" in result.output.lower() or "invalid" in result.output.lower()

    def test_whitespace_only_repo_shows_error(self):
        """Test that whitespace-only --repo value shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "   "])

        assert result.exit_code != 0

    def test_with_all_valid_options(self):
        """Test command with all valid options specified."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm"):
            result = runner.invoke(main, [
                "new",
                "--repo", "https://github.com/user/repo",
                "--vm-size", "Standard_D2s_v3",
                "--region", "eastus",
                "--resource-group", "test-rg",
                "--name", "custom-vm",
                "--config", "/path/to/config.yaml",
                "--template", "python-dev",
                "--nfs-storage", "my-storage",
                "--no-auto-connect"
            ])

            assert result.exit_code == 0


class TestNewCommandOptions:
    """Test option combinations for 'azlin new' command."""

    def test_pool_and_name_are_mutually_exclusive(self):
        """Test that --pool and --name cannot be used together."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "new",
            "--repo", "https://github.com/user/repo",
            "--pool", "3",
            "--name", "custom-vm"
        ])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or "cannot" in result.output.lower()

    def test_resource_group_short_and_long_form_equivalent(self):
        """Test that -rg and --resource-group are equivalent."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            # Long form
            runner.invoke(main, ["new", "--repo", "https://...", "--resource-group", "test-rg"])
            long_form_call = mock_create.call_args

            mock_create.reset_mock()

            # Short form
            runner.invoke(main, ["new", "--repo", "https://...", "-rg", "test-rg"])
            short_form_call = mock_create.call_args

            # Both should pass same resource_group
            assert long_form_call == short_form_call

    def test_pool_with_positive_integer_succeeds(self):
        """Test that --pool accepts positive integers."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm"):
            result = runner.invoke(main, ["new", "--repo", "https://...", "--pool", "5"])

            assert result.exit_code == 0

    def test_pool_with_zero_shows_error(self):
        """Test that --pool 0 shows validation error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "https://...", "--pool", "0"])

        assert result.exit_code != 0

    def test_pool_with_negative_shows_error(self):
        """Test that --pool with negative number shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "https://...", "--pool", "-1"])

        assert result.exit_code != 0

    def test_pool_with_non_integer_shows_error(self):
        """Test that --pool with non-integer shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "https://...", "--pool", "abc"])

        assert result.exit_code != 0
        assert "integer" in result.output.lower() or "invalid" in result.output.lower()

    def test_config_file_path_validation(self):
        """Test that --config validates file path format."""
        runner = CliRunner()

        with patch("azlin.config_manager.ConfigManager.load_config"):
            result = runner.invoke(main, ["new", "--repo", "https://...", "--config", "/valid/path.yaml"])

            # Should not fail on path format
            assert "invalid path" not in result.output.lower()

    def test_no_auto_connect_flag(self):
        """Test that --no-auto-connect flag works."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            result = runner.invoke(main, ["new", "--repo", "https://...", "--no-auto-connect"])

            assert mock_create.called
            # Verify no_auto_connect was passed
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs.get("no_auto_connect") is True


class TestNewCommandErrors:
    """Test error handling for 'azlin new' command."""

    def test_unknown_option_shows_error(self):
        """Test that unknown options show helpful error message."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--unknown-option", "value"])

        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_invalid_vm_size_shows_error(self):
        """Test that invalid VM size shows clear error."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm", side_effect=ValueError("Invalid VM size")):
            result = runner.invoke(main, ["new", "--repo", "https://...", "--vm-size", "InvalidSize"])

            assert result.exit_code != 0
            assert "invalid" in result.output.lower()

    def test_invalid_region_shows_error(self):
        """Test that invalid region shows clear error."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm", side_effect=ValueError("Invalid region")):
            result = runner.invoke(main, ["new", "--repo", "https://...", "--region", "invalid-region"])

            assert result.exit_code != 0
            assert "region" in result.output.lower()

    def test_invalid_repo_url_shows_error(self):
        """Test that invalid repository URL shows error."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--repo", "not-a-valid-url"])

        # May fail at validation or during execution
        # Just ensure error is shown
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_missing_azure_credentials_shows_helpful_message(self):
        """Test that missing Azure credentials shows helpful error."""
        runner = CliRunner()

        with patch("azure.identity.DefaultAzureCredential", side_effect=Exception("No credentials found")):
            result = runner.invoke(main, ["new", "--repo", "https://..."])

            assert result.exit_code != 0
            assert "credential" in result.output.lower() or "auth" in result.output.lower()

    def test_azure_quota_exceeded_shows_clear_error(self):
        """Test that Azure quota errors show clear message."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm", side_effect=Exception("QuotaExceeded")):
            result = runner.invoke(main, ["new", "--repo", "https://..."])

            assert result.exit_code != 0
            assert "quota" in result.output.lower()

    def test_network_timeout_shows_error(self):
        """Test that network timeouts show appropriate error."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm", side_effect=TimeoutError("Connection timeout")):
            result = runner.invoke(main, ["new", "--repo", "https://..."])

            assert result.exit_code != 0
            assert "timeout" in result.output.lower() or "connection" in result.output.lower()


class TestNewCommandHelp:
    """Test help text for 'azlin new' command."""

    def test_help_flag_shows_complete_usage(self):
        """Test that --help shows complete usage information."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Options:" in result.output

    def test_help_documents_all_options(self):
        """Test that help text includes all available options."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        expected_options = [
            "--repo",
            "--vm-size",
            "--region",
            "--resource-group",
            "--name",
            "--pool",
            "--no-auto-connect",
            "--config",
            "--template",
            "--nfs-storage"
        ]

        for option in expected_options:
            assert option in result.output, f"Option {option} not documented"

    def test_help_includes_usage_examples(self):
        """Test that help text includes usage examples."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "--help"])

        # Check for example patterns
        assert "example" in result.output.lower() or "azlin new" in result.output

    def test_short_help_flag_works(self):
        """Test that -h is alias for --help."""
        runner = CliRunner()
        result = runner.invoke(main, ["new", "-h"])

        assert result.exit_code == 0
        assert "Usage:" in result.output


class TestNewCommandAliases:
    """Test aliases for 'azlin new' command (vm, create)."""

    def test_new_and_vm_are_equivalent(self):
        """Test that 'azlin new' and 'azlin vm' produce same result."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            result_new = runner.invoke(main, ["new", "--repo", "https://..."])
            new_exit_code = result_new.exit_code

            mock_create.reset_mock()

            result_vm = runner.invoke(main, ["vm", "--repo", "https://..."])
            vm_exit_code = result_vm.exit_code

            assert new_exit_code == vm_exit_code

    def test_new_and_create_are_equivalent(self):
        """Test that 'azlin new' and 'azlin create' produce same result."""
        runner = CliRunner()

        with patch("azlin.vm_manager.VMManager.create_vm") as mock_create:
            result_new = runner.invoke(main, ["new", "--repo", "https://..."])
            result_create = runner.invoke(main, ["create", "--repo", "https://..."])

            assert result_new.exit_code == result_create.exit_code
```

## 10. Validation and Reporting

### 10.1 Test Metrics Dashboard

Track these metrics:
- Total tests written vs target (300+)
- Tests passing vs failing
- Coverage percentage per command
- Average tests per command
- Distribution across categories

### 10.2 Coverage Report Format

```
CLI Command Syntax Test Coverage Report
========================================

Overall Statistics:
  Total Commands: 33
  Commands with tests: 33 (100%)
  Total tests: 342
  Tests passing: 342 (100%)
  Average tests per command: 10.4

Coverage by Command:
  azlin new:           25 tests (18 passing, 95% coverage)
  azlin list:          12 tests (12 passing, 98% coverage)
  azlin connect:       15 tests (15 passing, 96% coverage)
  ...

Coverage by Category:
  Syntax validation:   102 tests (30%)
  Option combinations: 118 tests (35%)
  Error handling:      85 tests (25%)
  Help text:           37 tests (11%)
  Aliases:             10 tests (3%)

Priority 1 (Core):     60 tests (100% complete)
Priority 2 (Common):   90 tests (100% complete)
Priority 3 (Advanced): 120 tests (100% complete)
Priority 4 (Specialized): 72 tests (100% complete)
```

## 11. Maintenance and Updates

### 11.1 When to Update Tests

- New CLI command added: Add full test suite for command
- Command option added: Add tests for new option and combinations
- Command behavior changed: Update existing tests
- Bug fixed: Add regression test
- Error message improved: Update error assertion tests

### 11.2 Test Review Checklist

Before marking test suite complete:
- [ ] All 33 commands have test files
- [ ] Each command has minimum required tests
- [ ] All test categories represented
- [ ] 95%+ code coverage achieved
- [ ] All tests pass consistently
- [ ] No flaky tests detected
- [ ] Tests follow naming conventions
- [ ] All tests have docstrings
- [ ] Fixtures properly shared in conftest.py
- [ ] CI/CD integration configured
- [ ] Coverage reports generated
- [ ] Documentation updated

---

## Summary

This specification provides a complete blueprint for creating 300+ exhaustive tests covering all 33 CLI commands. The structured approach ensures:

1. **Comprehensive coverage**: Every command, option, and error condition tested
2. **Consistent patterns**: Reusable templates and fixtures
3. **Maintainability**: Clear organization and naming conventions
4. **Quality assurance**: Success criteria and validation metrics
5. **Prioritization**: Phased implementation plan

By following this specification, the test suite will provide confidence that all CLI commands work correctly across all syntax variations and error conditions.
