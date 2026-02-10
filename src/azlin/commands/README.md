# CLI Commands Module

Reference documentation for the azlin modular CLI architecture.

## Contents

- [Architecture Overview](#architecture-overview)
- [Module Reference](#module-reference)
  - [Core Command Modules](#core-command-modules)
  - [Command Group Modules](#command-group-modules)
  - [Shared Utilities](#shared-utilities)
- [Public APIs](#public-apis)
- [Import Patterns](#import-patterns)
- [Adding New Commands](#adding-new-commands)
- [Testing Guide](#testing-guide)

## Architecture Overview

The CLI is organized as a modular system where `cli.py` acts as a thin router (~400 lines) that imports and registers commands from specialized modules. Each module is a self-contained "brick" with a clear public interface.

```
src/azlin/
├── cli.py                    # Router only (~400 lines)
└── commands/
    ├── __init__.py           # Public exports
    ├── cli_helpers.py        # Shared utilities
    │
    │   # Core command modules (single commands)
    ├── monitoring.py         # status
    ├── lifecycle.py          # start, stop, kill, destroy, killall, clone
    ├── connectivity.py       # connect, code, cp, sync
    ├── admin.py              # prune, update, os-update, cost
    ├── provisioning.py       # new, vm, create
    ├── special.py            # do, help
    ├── list_cmd.py           # list
    ├── session_cmd.py        # session
    ├── w_cmd.py              # w
    ├── top_cmd.py            # top
    ├── ps_cmd.py             # ps
    ├── restore.py            # restore
    │
    │   # Command group modules (subcommand hierarchies)
    ├── ask.py                # ask group: ask, ask session, ask clear
    ├── auth.py               # auth group: setup, test, list, show, remove
    ├── autopilot.py          # autopilot group: start, stop, status
    ├── bastion.py            # bastion group: create, delete, status, connect
    ├── compose.py            # compose group: up, down, status, list
    ├── context.py            # context group: show, set, list, clear
    ├── costs.py              # costs group: summary, detail, export
    ├── doit.py               # doit: AI-powered task execution
    ├── fleet.py              # fleet group: run, workflow
    ├── github_runner.py      # runner group: setup, status, remove
    ├── storage.py            # storage group: mount, unmount, status
    └── tag.py                # tag group: add, remove, list, filter
```

## Module Reference

### Core Command Modules

These modules export individual commands (not command groups).

#### `monitoring.py`

Observability and status commands.

| Command  | Purpose                      | Key Options                    |
|----------|------------------------------|--------------------------------|
| `status` | Show detailed VM status      | `--rg`, `--config`, `--vm`     |

```python
# Public API
from azlin.commands.monitoring import status

# Usage
azlin status --vm my-vm
```

#### `lifecycle.py`

VM lifecycle management commands.

| Command   | Purpose              | Key Options                        |
|-----------|----------------------|------------------------------------|
| `start`   | Start stopped VM     | `--vm`, `--rg`, `--wait`           |
| `stop`    | Stop running VM      | `--vm`, `--rg`, `--deallocate`     |
| `kill`    | Force stop VM        | `--vm`, `--rg`                     |
| `destroy` | Delete VM            | `--vm`, `--rg`, `--force`          |
| `killall` | Batch delete VMs     | `--rg`, `--pattern`, `--force`     |
| `clone`   | Create VM copy       | `--vm`, `--name`, `--rg`           |

```python
# Public API
from azlin.commands.lifecycle import (
    start_command,
    stop_command,
    kill_command,
    destroy_command,
    killall_command,
    clone_command,
)

# Usage
azlin start --vm my-vm --wait
azlin destroy --vm old-vm --force
```

#### `connectivity.py`

Commands for connecting to VMs and file transfers.

| Command   | Purpose                   | Key Options                      |
|-----------|---------------------------|----------------------------------|
| `connect` | Interactive SSH           | `--vm`, `--rg`, `--user`         |
| `code`    | Launch VS Code Remote-SSH | `--vm`, `--rg`, `--folder`       |
| `cp`      | Copy files to/from VM     | `SRC`, `DEST`, `--recursive`     |
| `sync`    | Sync home directory       | `--vm`, `--rg`, `--dry-run`      |

```python
# Public API
from azlin.commands.connectivity import (
    connect_command,
    code_command,
    cp_command,
    sync_command,
)

# Usage
azlin connect --vm my-vm
azlin code --vm my-vm --folder /home/user/project
azlin cp local-file.txt my-vm:/home/user/
```

#### `admin.py`

Administrative and maintenance commands.

| Command     | Purpose                | Key Options                    |
|-------------|------------------------|--------------------------------|
| `prune`     | Remove old/unused VMs  | `--rg`, `--days`, `--dry-run`  |
| `update`    | Update azlin on VM     | `--vm`, `--rg`, `--all`        |
| `os-update` | Update OS packages     | `--vm`, `--rg`, `--reboot`     |
| `cost`      | Display cost info      | `--rg`, `--period`, `--format` |

```python
# Public API
from azlin.commands.admin import (
    prune_command,
    update_command,
    os_update_command,
    cost_command,
)

# Usage
azlin prune --days 30 --dry-run
azlin update --all
```

#### `provisioning.py`

VM creation and provisioning commands.

| Command  | Purpose               | Key Options                              |
|----------|-----------------------|------------------------------------------|
| `new`    | Create new VM         | `--name`, `--size`, `--image`, `--rg`    |
| `vm`     | Alias for `new`       | Same as `new`                            |
| `create` | Alias for `new`       | Same as `new`                            |

```python
# Public API
from azlin.commands.provisioning import (
    new_command,
    vm_command,
    create_command,
)

# Usage
azlin new --name dev-vm --size Standard_D4s_v3
azlin vm --name test-vm --image Ubuntu2204
```

#### `special.py`

Special-purpose commands.

| Command | Purpose                          | Key Options          |
|---------|----------------------------------|----------------------|
| `do`    | Natural language command exec    | `PROMPT`, `--vm`     |
| `help`  | Enhanced help system             | `--command`          |

```python
# Public API
from azlin.commands.special import do_command, help_command

# Usage
azlin do "install docker and run nginx"
azlin help --command fleet
```

#### `list_cmd.py`

VM listing command.

| Command | Purpose                    | Key Options                         |
|---------|----------------------------|-------------------------------------|
| `list`  | List VMs with details      | `--rg`, `--all`, `--format`, `--tag`|

```python
# Public API
from azlin.commands.list_cmd import list_command

# Usage
azlin list --format json
azlin list --tag env=production
```

#### `session_cmd.py`

Session name management.

| Command   | Purpose                   | Key Options              |
|-----------|---------------------------|--------------------------|
| `session` | Manage session names      | `--vm`, `--set`, `--get` |

```python
# Public API
from azlin.commands.session_cmd import session_command

# Usage
azlin session --vm my-vm --set "feature-work"
```

#### `w_cmd.py`

Run 'w' command across VMs.

| Command | Purpose                    | Key Options       |
|---------|----------------------------|-------------------|
| `w`     | Show logged-in users       | `--rg`, `--all`   |

```python
# Public API
from azlin.commands.w_cmd import w_command

# Usage
azlin w --all
```

#### `top_cmd.py`

Distributed metrics dashboard.

| Command | Purpose                      | Key Options                   |
|---------|------------------------------|-------------------------------|
| `top`   | Live metrics across VMs      | `--rg`, `--interval`, `--vm`  |

```python
# Public API
from azlin.commands.top_cmd import top_command

# Usage
azlin top --interval 5
```

#### `ps_cmd.py`

Process listing across VMs.

| Command | Purpose                    | Key Options                |
|---------|----------------------------|----------------------------|
| `ps`    | Show processes across VMs  | `--rg`, `--user`, `--all`  |

```python
# Public API
from azlin.commands.ps_cmd import ps_command

# Usage
azlin ps --user azureuser
```

#### `restore.py`

VM restore from snapshots.

| Command   | Purpose                   | Key Options                    |
|-----------|---------------------------|--------------------------------|
| `restore` | Restore VM from snapshot  | `--vm`, `--snapshot`, `--rg`   |

```python
# Public API
from azlin.commands.restore import restore_command

# Usage
azlin restore --vm my-vm --snapshot snap-20240101
```

### Command Group Modules

These modules export Click command groups with subcommands.

#### `ask.py`

Natural language query interface.

| Subcommand      | Purpose                    |
|-----------------|----------------------------|
| `ask`           | Query with natural language|
| `ask session`   | Manage conversation session|
| `ask clear`     | Clear conversation history |

```python
# Public API
from azlin.commands.ask import ask_group

# Usage
azlin ask "how much did I spend this month?"
azlin ask session --new
azlin ask clear
```

#### `auth.py`

Service principal authentication management.

| Subcommand     | Purpose                       |
|----------------|-------------------------------|
| `auth setup`   | Interactive profile setup     |
| `auth test`    | Test authentication           |
| `auth list`    | List available profiles       |
| `auth show`    | Show profile details          |
| `auth remove`  | Remove authentication profile |

```python
# Public API
from azlin.commands.auth import auth

# Usage
azlin auth setup --profile production
azlin auth test --profile production
azlin auth list
```

#### `autopilot.py`

Autonomous VM management.

| Subcommand        | Purpose                    |
|-------------------|----------------------------|
| `autopilot start` | Start autonomous mode      |
| `autopilot stop`  | Stop autonomous mode       |
| `autopilot status`| Show autopilot status      |

```python
# Public API
from azlin.commands.autopilot import autopilot_group

# Usage
azlin autopilot start --policy cost-optimize
azlin autopilot status
```

#### `bastion.py`

Azure Bastion management.

| Subcommand        | Purpose                   |
|-------------------|---------------------------|
| `bastion create`  | Create bastion host       |
| `bastion delete`  | Delete bastion host       |
| `bastion status`  | Show bastion status       |
| `bastion connect` | Connect via bastion       |

```python
# Public API
from azlin.commands.bastion import bastion_group

# Usage
azlin bastion create --rg my-rg
azlin bastion connect --vm private-vm
```

#### `compose.py`

Multi-VM composition management.

| Subcommand       | Purpose                    |
|------------------|----------------------------|
| `compose up`     | Deploy composition         |
| `compose down`   | Tear down composition      |
| `compose status` | Show composition status    |
| `compose list`   | List compositions          |

```python
# Public API
from azlin.commands.compose import compose_group

# Usage
azlin compose up ./cluster.yaml
azlin compose status --name my-cluster
```

#### `context.py`

Azure context switching.

| Subcommand      | Purpose                    |
|-----------------|----------------------------|
| `context show`  | Show current context       |
| `context set`   | Set active context         |
| `context list`  | List available contexts    |
| `context clear` | Clear context              |

```python
# Public API
from azlin.commands.context import context_group

# Usage
azlin context list
azlin context set --subscription prod-sub --rg prod-rg
```

#### `costs.py`

Cost tracking and analysis.

| Subcommand      | Purpose                    |
|-----------------|----------------------------|
| `costs summary` | Cost summary by period     |
| `costs detail`  | Detailed cost breakdown    |
| `costs export`  | Export cost data           |

```python
# Public API
from azlin.commands.costs import costs_group

# Usage
azlin costs summary --period month
azlin costs export --format csv --output costs.csv
```

#### `doit.py`

AI-powered task execution.

| Command | Purpose                              |
|---------|--------------------------------------|
| `doit`  | Execute tasks with AI assistance     |

```python
# Public API
from azlin.commands.doit import doit_command

# Usage
azlin doit "set up a kubernetes cluster with 3 nodes"
```

#### `fleet.py`

Distributed fleet operations.

| Subcommand       | Purpose                      |
|------------------|------------------------------|
| `fleet run`      | Execute across fleet         |
| `fleet workflow` | Run YAML workflow            |

```python
# Public API
from azlin.commands.fleet import fleet_group

# Usage
azlin fleet run "npm test" --if-idle --parallel 5
azlin fleet workflow deploy.yaml --tag env=staging
```

#### `github_runner.py`

GitHub Actions self-hosted runners.

| Subcommand       | Purpose                    |
|------------------|----------------------------|
| `runner setup`   | Set up runner on VM        |
| `runner status`  | Show runner status         |
| `runner remove`  | Remove runner              |

```python
# Public API
from azlin.commands.github_runner import runner_group

# Usage
azlin runner setup --vm build-vm --repo myorg/myrepo
azlin runner status --vm build-vm
```

#### `storage.py`

Storage account management.

| Subcommand        | Purpose                   |
|-------------------|---------------------------|
| `storage mount`   | Mount storage to VM       |
| `storage unmount` | Unmount storage           |
| `storage status`  | Show mount status         |

```python
# Public API
from azlin.commands.storage import storage_group

# Usage
azlin storage mount --vm my-vm --account mystorageaccount
azlin storage status
```

#### `tag.py`

VM tag management.

| Subcommand    | Purpose                    |
|---------------|----------------------------|
| `tag add`     | Add tags to VM             |
| `tag remove`  | Remove tags from VM        |
| `tag list`    | List VM tags               |
| `tag filter`  | Filter VMs by tag          |

```python
# Public API
from azlin.commands.tag import tag_group

# Usage
azlin tag add --vm my-vm env=production team=platform
azlin tag filter --tag env=production
```

### Shared Utilities

#### `cli_helpers.py`

Common functions used across multiple commands.

| Function                  | Purpose                              |
|---------------------------|--------------------------------------|
| `generate_vm_name`        | Generate VM name from timestamp      |
| `select_vm_for_command`   | Interactive VM selection             |
| `format_vm_table`         | Format VM list as table              |
| `resolve_resource_group`  | Get RG from config or args           |
| `execute_ssh_command`     | Run command via SSH                  |
| `wait_for_vm_state`       | Poll until VM reaches state          |
| `display_progress`        | Show progress indicator              |
| `confirm_destructive`     | Confirm destructive operations       |

```python
# Public API
from azlin.commands.cli_helpers import (
    generate_vm_name,
    select_vm_for_command,
    format_vm_table,
    resolve_resource_group,
    execute_ssh_command,
    wait_for_vm_state,
    display_progress,
    confirm_destructive,
)

# Usage
vm_name = generate_vm_name(custom_name="my-vm")
selected_vm = select_vm_for_command(vms, "connect")
```

## Public APIs

Each module defines its public API via `__all__`:

```python
# monitoring.py
__all__ = ["status"]

# lifecycle.py
__all__ = [
    "start_command",
    "stop_command",
    "kill_command",
    "destroy_command",
    "killall_command",
    "clone_command",
]

# cli_helpers.py
__all__ = [
    "generate_vm_name",
    "select_vm_for_command",
    "format_vm_table",
    "resolve_resource_group",
    "execute_ssh_command",
    "wait_for_vm_state",
    "display_progress",
    "confirm_destructive",
]
```

## Import Patterns

### Router Pattern (cli.py)

The main CLI file acts as a thin router:

```python
# cli.py (~400 lines)
import click
from azlin.click_group import AzlinGroup

# Import commands
from azlin.commands.monitoring import status
from azlin.commands.lifecycle import start_command, stop_command
from azlin.commands.connectivity import connect_command, code_command
from azlin.commands.auth import auth
from azlin.commands.fleet import fleet_group
# ... etc

@click.group(cls=AzlinGroup)
def main():
    """Azure Linux VM management made simple."""
    pass

# Register individual commands
main.add_command(status)
main.add_command(start_command, name="start")
main.add_command(stop_command, name="stop")
main.add_command(connect_command, name="connect")
main.add_command(code_command, name="code")

# Register command groups
main.add_command(auth)
main.add_command(fleet_group, name="fleet")
# ... etc
```

### Module Internal Imports

Commands import from azlin core modules:

```python
# In any command module
from azlin.config_manager import ConfigManager
from azlin.vm_manager import VMManager, VMInfo
from azlin.context_manager import ContextManager
from azlin.commands.cli_helpers import select_vm_for_command
```

### Avoiding Circular Imports

Follow these rules to prevent circular imports:

1. `cli_helpers.py` imports only from azlin core (not from commands)
2. Command modules import from `cli_helpers.py`, not from each other
3. `cli.py` imports from command modules (one-way dependency)

```
cli.py
   │
   └─→ commands/*.py
          │
          └─→ cli_helpers.py
                  │
                  └─→ azlin core modules
```

## Adding New Commands

### Step 1: Choose Module Location

| Command Type                   | Location            |
|--------------------------------|---------------------|
| New standalone command         | New `*_cmd.py` file |
| Related to existing module     | Add to that module  |
| New command group              | New `*.py` file     |
| Shared utility function        | `cli_helpers.py`    |

### Step 2: Implement the Command

```python
# new_feature_cmd.py
"""New feature command.

This module provides the new-feature command for azlin.
"""

import click
from azlin.config_manager import ConfigManager
from azlin.commands.cli_helpers import resolve_resource_group

__all__ = ["new_feature_command"]


@click.command(name="new-feature")
@click.option("--vm", help="Target VM name", required=True)
@click.option("--rg", "--resource-group", help="Resource group")
@click.option("--config", help="Config file path", type=click.Path())
def new_feature_command(vm: str, rg: str | None, config: str | None):
    """Execute the new feature operation.

    This command does something useful with the specified VM.

    \b
    Examples:
        azlin new-feature --vm my-vm
        azlin new-feature --vm my-vm --rg my-rg
    """
    resource_group = resolve_resource_group(rg, config)
    # Implementation here
    click.echo(f"Executing new feature on {vm}")
```

### Step 3: Register in cli.py

```python
# In cli.py
from azlin.commands.new_feature_cmd import new_feature_command

main.add_command(new_feature_command)
```

### Step 4: Add Tests

```python
# tests/commands/test_new_feature_cmd.py
"""Tests for new_feature_cmd module."""

import pytest
from click.testing import CliRunner
from azlin.commands.new_feature_cmd import new_feature_command


class TestNewFeatureCommand:
    """Tests for new-feature command."""

    def test_requires_vm_option(self):
        """Command requires --vm option."""
        runner = CliRunner()
        result = runner.invoke(new_feature_command, [])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_executes_with_valid_args(self, mocker):
        """Command executes with valid arguments."""
        mocker.patch("azlin.commands.new_feature_cmd.resolve_resource_group")
        runner = CliRunner()
        result = runner.invoke(new_feature_command, ["--vm", "test-vm"])
        assert result.exit_code == 0
        assert "test-vm" in result.output
```

### Step 5: Update Documentation

Add the command to this README in the appropriate section.

## Testing Guide

### Test Structure

```
tests/commands/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_monitoring.py
├── test_lifecycle.py
├── test_connectivity.py
├── test_admin.py
├── test_provisioning.py
├── test_special.py
├── test_list_cmd.py
├── test_session_cmd.py
├── test_w_cmd.py
├── test_top_cmd.py
├── test_ps_cmd.py
├── test_restore.py
├── test_ask.py
├── test_auth.py
├── test_autopilot.py
├── test_bastion.py
├── test_compose.py
├── test_context.py
├── test_costs.py
├── test_doit.py
├── test_fleet.py
├── test_github_runner.py
├── test_storage.py
├── test_tag.py
└── test_cli_helpers.py
```

### Testing Pyramid

Follow the 60/30/10 testing pyramid:

```
60% Unit Tests
├── Test individual functions
├── Mock external dependencies
└── Fast execution (<1s per test)

30% Integration Tests
├── Test command with mocked Azure APIs
├── Test option combinations
└── Test error handling paths

10% E2E Tests
├── Test full command execution
├── Use real (or realistic) fixtures
└── Validate user-facing output
```

### Running Tests

```bash
# Run all command tests
pytest tests/commands/ -v

# Run specific module tests
pytest tests/commands/test_lifecycle.py -v

# Run with coverage
pytest tests/commands/ --cov=azlin.commands --cov-report=html

# Run only unit tests (fast)
pytest tests/commands/ -v -m "not integration and not e2e"
```

### Common Test Fixtures

```python
# conftest.py
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock

@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()

@pytest.fixture
def mock_vm_info():
    """Mock VMInfo object."""
    vm = MagicMock()
    vm.name = "test-vm"
    vm.resource_group = "test-rg"
    vm.power_state = "VM running"
    vm.public_ip = "1.2.3.4"
    vm.is_running.return_value = True
    return vm

@pytest.fixture
def mock_config(mocker):
    """Mock ConfigManager."""
    return mocker.patch("azlin.config_manager.ConfigManager")
```

### Test Example

```python
# test_lifecycle.py
"""Tests for lifecycle commands."""

import pytest
from click.testing import CliRunner
from azlin.commands.lifecycle import start_command, stop_command


class TestStartCommand:
    """Tests for start command."""

    def test_start_running_vm_warns(self, cli_runner, mocker, mock_vm_info):
        """Starting an already running VM shows warning."""
        mock_vm_info.is_running.return_value = True
        mocker.patch(
            "azlin.commands.lifecycle.VMManager.get_vm",
            return_value=mock_vm_info
        )

        result = cli_runner.invoke(start_command, ["--vm", "test-vm"])

        assert "already running" in result.output.lower()

    def test_start_stopped_vm_succeeds(self, cli_runner, mocker, mock_vm_info):
        """Starting a stopped VM succeeds."""
        mock_vm_info.is_running.return_value = False
        mock_vm_info.power_state = "VM deallocated"
        mocker.patch(
            "azlin.commands.lifecycle.VMManager.get_vm",
            return_value=mock_vm_info
        )
        mocker.patch("azlin.commands.lifecycle.VMManager.start_vm")

        result = cli_runner.invoke(start_command, ["--vm", "test-vm"])

        assert result.exit_code == 0
```

## Design Principles

### Single Responsibility

Each module handles one cohesive set of commands. If a module exceeds 500 lines, consider splitting it.

### Minimal Dependencies

- Command modules depend on `cli_helpers.py` and azlin core
- Command modules do not depend on each other
- `cli_helpers.py` depends only on azlin core

### Clear Interfaces

Every command function:
- Uses Click decorators for CLI interface
- Accepts explicit parameters (no hidden globals)
- Returns None or raises exceptions (Click handles exit codes)
- Has clear docstrings with examples

### Testability

- Extract business logic from Click decorators when complex
- Use dependency injection via parameters
- Mock external Azure API calls
- Test at module boundaries

## Maintenance Guidelines

1. **Keep modules focused**: Split if exceeding 500 lines
2. **Update `__all__`**: Always export new public functions
3. **Add tests first**: TDD approach for new commands
4. **Update this README**: Document new commands immediately
5. **Run full test suite**: Verify no regressions after changes

## References

- [Issue #423](https://github.com/rysweet/azlin/issues/423): CLI.py Decomposition
- [Click Documentation](https://click.palletsprojects.com/): CLI framework reference
- [azlin Architecture](../../docs/architecture.md): System architecture overview
