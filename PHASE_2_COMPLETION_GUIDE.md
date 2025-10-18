# Phase 2 Completion Guide

## Current Status

✅ **Phase 1 Complete - Foundation Established**

### Completed Modules (4/12)
- ✅ `commands/help.py` (50 lines) - Help command
- ✅ `commands/cost.py` (110 lines) - Cost tracking
- ✅ `commands/prune.py` (150 lines) - Prune operations
- ✅ `commands/env.py` (340 lines) - Environment variable management
- ✅ `commands/storage.py` (existing) - Storage management

### Pattern Established

All new modules follow this structure:

```python
"""Module description.

This module provides commands related to [functionality].
"""

import sys  # if needed
import click

from azlin.module_name import ClassName
# ... other imports


def register_MODULE_commands(main: click.Group) -> None:
    """Register MODULE commands with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """

    @main.command()  # or @main.group()
    @click.option(...)
    def command_name(...):
        """Command docstring."""
        # Implementation
```

## Remaining Work

### Phase 2: Create Remaining 7 Modules (Estimated: 6-8 hours)

#### 1. commands/monitoring.py (~500 lines)

**Extract from cli.py:**
- Lines 895-940: `execute_command_on_vm()`, `select_vm_for_command()`
- Lines 1680-1745: `w` command
- Lines 1745-1846: `top` command
- Lines 1846-1903: `os_update` command
- Lines 2359-2434: `ps` command

**Imports needed:**
```python
import subprocess
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigManager
from azlin.distributed_top import DistributedTopExecutor, DistributedTopError
from azlin.modules.ssh_connector import SSHConfig, SSHConnector
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import (
    OSUpdateExecutor,
    PSCommandExecutor,
    RemoteExecError,
    RemoteExecutor,
    WCommandExecutor,
)
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
```

**Function signature:**
```python
def register_monitoring_commands(main: click.Group) -> None:
```

#### 2. commands/keys.py (~400 lines)

**Extract from cli.py:**
- Lines 3843-3850: `keys_group` group definition
- Lines 4092-4165: `keys_rotate` command
- Lines 4232-4280: `keys_list` command
- Lines 4617-4650: `keys_export` command
- Lines 4650-4682: `keys_backup` command

**Imports needed:**
```python
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigManager
from azlin.key_rotator import KeyRotationError, SSHKeyRotator
from azlin.modules.ssh_keys import SSHKeyError, SSHKeyManager
from azlin.vm_manager import VMManager, VMManagerError
```

**Function signature:**
```python
def register_keys_commands(main: click.Group) -> None:
```

#### 3. commands/templates.py (~400 lines)

**Extract from cli.py:**
- Lines 3852-3890: `template` group definition
- Lines 4165-4232: `template_create` command
- Lines 4682-4722: `template_list` command
- Lines 4722-4764: `template_delete` command
- Lines 4764-4798: `template_export` command
- Lines 4798-4828: `template_import` command

**Imports needed:**
```python
import sys

import click

from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig
```

**Function signature:**
```python
def register_templates_commands(main: click.Group) -> None:
```

#### 4. commands/snapshots.py (~600 lines)

**Extract from cli.py:**
- Lines 3890-3934: `snapshot` group definition
- Lines 3934-3976: `snapshot_enable` command
- Lines 3976-4008: `snapshot_disable` command
- Lines 4008-4049: `snapshot_sync` command
- Lines 4049-4092: `snapshot_status` command
- Lines 4828-4884: `snapshot_create` command
- Lines 4884-4955: `snapshot_list` command
- Lines 4955-5028: `snapshot_restore` command
- Lines 5028-5085: `snapshot_delete` command

**Imports needed:**
```python
import sys

import click

from azlin.config_manager import ConfigManager
from azlin.modules.snapshot_manager import SnapshotError, SnapshotManager
from azlin.vm_manager import VMManager, VMManagerError
```

**Function signature:**
```python
def register_snapshots_commands(main: click.Group) -> None:
```

#### 5. commands/batch.py (~400 lines)

**Extract from cli.py:**
- Lines 3791-3806: `batch` group definition
- Lines 3808-3842: `batch_stop` command
- Lines 4280-4340: `_validate_batch_selection`, `_select_vms_by_criteria`, `_confirm_batch_operation`, `_display_batch_summary` helpers
- Lines 4340-4431: `batch_start` command
- Lines 4431-4533: `batch command` command
- Lines 4533-4617: `batch_sync` command

**Imports needed:**
```python
import sys

import click

from azlin.batch_executor import BatchExecutor, BatchExecutorError, BatchResult, BatchSelector
from azlin.config_manager import ConfigManager
from azlin.modules.home_sync import HomeSyncManager
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import RemoteExecutor
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
```

**Function signature:**
```python
def register_batch_commands(main: click.Group) -> None:
```

#### 6. commands/vm_lifecycle.py (~800 lines)

**Extract from cli.py:**
- Lines 873-895: `generate_vm_name()` helper
- Lines 1215-1296: `_load_config_and_template`, `_resolve_vm_settings`, `_validate_inputs`, `_update_config_state`, `_execute_command_mode` helpers
- Lines 1296-1400: `_provision_pool`, `_display_pool_results` helpers
- Lines 1388-1520: `new_command`, `vm_command`, `create_command` commands
- Lines 1525-1605: `list_command` command
- Lines 2917-2966: `stop` command
- Lines 2966-3006: `start` command
- Lines 1903-2076: `kill` command
- Lines 2076-2178: `destroy` command (with helpers)
- Lines 2178-2251: `killall` command (with helpers)

**Imports needed:**
```python
import sys
import time
from pathlib import Path

import click

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.modules.progress import ProgressDisplay
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.tag_manager import TagManager
from azlin.template_manager import TemplateManager, VMTemplateConfig
from azlin.vm_lifecycle import DeletionSummary, VMLifecycleError, VMLifecycleManager
from azlin.vm_lifecycle_control import VMLifecycleControlError, VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import (
    PoolProvisioningResult,
    ProvisioningError,
    VMConfig,
    VMProvisioner,
)
```

**Function signature:**
```python
def register_vm_lifecycle_commands(main: click.Group) -> None:
```

#### 7. commands/vm_operations.py (~600 lines)

**Extract from cli.py:**
- Lines 1605-1680: `session_command` command
- Lines 2516-2633: `_interactive_vm_selection`, `_resolve_vm_identifier`, `_verify_vm_exists`, `_resolve_tmux_session` helpers
- Lines 2633-2783: `connect` command
- Lines 2783-2917: `update` command
- Lines 3720-3791: `status` command

**Imports needed:**
```python
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigManager
from azlin.modules.ssh_connector import SSHConfig, SSHConnectionError, SSHConnector
from azlin.modules.ssh_keys import SSHKeyManager
from azlin.remote_exec import OSUpdateExecutor, RemoteExecError
from azlin.vm_connector import VMConnector, VMConnectorError
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
```

**Function signature:**
```python
def register_vm_operations_commands(main: click.Group) -> None:
```

#### 8. commands/vm_advanced.py (~700 lines)

**Extract from cli.py:**
- Lines 3006-3090: `_get_sync_vm_by_name`, `_select_sync_vm_interactive`, `_execute_sync` helpers
- Lines 3090-3151: `sync` command
- Lines 3151-3280: `cp` command
- Lines 3280-3720: `clone` command (with all helpers: `_validate_and_resolve_source_vm`, `_ensure_source_vm_running`, `_provision_clone_vms`, `_display_clone_results`, `_resolve_source_vm`, `_generate_clone_configs`, `_copy_home_directories`, `_set_clone_session_names`)

**Imports needed:**
```python
import sys
from pathlib import Path

import click

from azlin.config_manager import ConfigManager
from azlin.modules.file_transfer import (
    FileTransfer,
    FileTransferError,
    PathParser,
    SessionManager,
    TransferEndpoint,
)
from azlin.modules.home_sync import (
    HomeSyncError,
    HomeSyncManager,
    RsyncError,
    SecurityValidationError,
)
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyPair
from azlin.vm_lifecycle_control import VMLifecycleController
from azlin.vm_manager import VMInfo, VMManager, VMManagerError
from azlin.vm_provisioning import PoolProvisioningResult, VMConfig, VMProvisioner
```

**Function signature:**
```python
def register_vm_advanced_commands(main: click.Group) -> None:
```

### Phase 3: Update cli.py (Estimated: 2 hours)

Once all modules are created:

1. **Remove extracted code** from cli.py

2. **Keep in cli.py:**
   - CLIOrchestrator class (lines 96-770)
   - Helper functions: `_auto_sync_home_directory`, `show_interactive_menu` (if used by orchestrator)
   - AzlinGroup class (lines 980-1014)
   - Main group definition (lines 1017-1184)

3. **Add imports** at top of cli.py:
```python
from azlin.commands.batch import register_batch_commands
from azlin.commands.cost import register_cost_command
from azlin.commands.env import register_env_commands
from azlin.commands.help import register_help_command
from azlin.commands.keys import register_keys_commands
from azlin.commands.monitoring import register_monitoring_commands
from azlin.commands.prune import register_prune_command
from azlin.commands.snapshots import register_snapshots_commands
from azlin.commands.storage import storage_group
from azlin.commands.templates import register_templates_commands
from azlin.commands.vm_advanced import register_vm_advanced_commands
from azlin.commands.vm_lifecycle import register_vm_lifecycle_commands
from azlin.commands.vm_operations import register_vm_operations_commands
```

4. **After main group definition**, add registration calls:
```python
# Register all command groups
register_help_command(main)
register_cost_command(main)
register_prune_command(main)
register_monitoring_commands(main)
register_env_commands(main)
register_keys_commands(main)
register_templates_commands(main)
register_snapshots_commands(main)
register_batch_commands(main)
register_vm_lifecycle_commands(main)
register_vm_operations_commands(main)
register_vm_advanced_commands(main)
main.add_command(storage_group)
```

5. **Final cli.py structure** (~300 lines):
```python
# Imports (50 lines)
# CLIOrchestrator class (670 lines - keep as-is)
# AzlinGroup class (35 lines - keep as-is)
# Main group definition (170 lines - keep as-is)
# Command registrations (15 lines - new)
# if __name__ == "__main__" (5 lines)
```

### Phase 4: Update commands/__init__.py

Create `/src/azlin/commands/__init__.py`:
```python
"""CLI command groups for azlin.

This package contains modularized command groups for the azlin CLI.
Each module is responsible for one category of commands.
"""

from azlin.commands.batch import register_batch_commands
from azlin.commands.cost import register_cost_command
from azlin.commands.env import register_env_commands
from azlin.commands.help import register_help_command
from azlin.commands.keys import register_keys_commands
from azlin.commands.monitoring import register_monitoring_commands
from azlin.commands.prune import register_prune_command
from azlin.commands.snapshots import register_snapshots_commands
from azlin.commands.storage import storage_group
from azlin.commands.templates import register_templates_commands
from azlin.commands.vm_advanced import register_vm_advanced_commands
from azlin.commands.vm_lifecycle import register_vm_lifecycle_commands
from azlin.commands.vm_operations import register_vm_operations_commands

__all__ = [
    "register_batch_commands",
    "register_cost_command",
    "register_env_commands",
    "register_help_command",
    "register_keys_commands",
    "register_monitoring_commands",
    "register_prune_command",
    "register_snapshots_commands",
    "register_templates_commands",
    "register_vm_advanced_commands",
    "register_vm_lifecycle_commands",
    "register_vm_operations_commands",
    "storage_group",
]
```

### Phase 5: Testing (Estimated: 2 hours)

1. **Run tests:**
```bash
pytest tests/
```

2. **Run pre-commit:**
```bash
pre-commit run --all-files
```

3. **Test each command manually:**
```bash
azlin help
azlin cost --help
azlin prune --help
# ... test all commands
```

4. **Verify no regressions:**
- All commands work as before
- No import errors
- All functionality preserved

## Tools and Scripts

### Automated Extraction Script

Use the `automate_decomposition.py` script to help extract modules:

```bash
python3 automate_decomposition.py
```

### Manual Extraction Steps

For each module:

1. **Read the section** from cli.py
2. **Copy function definitions** including decorators
3. **Identify imports** needed (look for references to classes/modules)
4. **Create register function** wrapper
5. **Indent content** properly (4 spaces inside register function)
6. **Test imports** - make sure all referenced symbols are imported

### Quick Reference: Finding Line Ranges

```bash
# Find a specific function
grep -n "^def function_name" src/azlin/cli.py

# Find where a function ends (next def at same indent)
# Manually inspect or use Python to parse

# Extract lines X to Y
sed -n 'X,Yp' src/azlin/cli.py
```

## Expected Final Structure

```
src/azlin/
├── cli.py                      (~300 lines)
├── commands/
│   ├── __init__.py             (30 lines)
│   ├── batch.py                (400 lines)
│   ├── cost.py                 (110 lines) ✅
│   ├── env.py                  (340 lines) ✅
│   ├── help.py                 (50 lines) ✅
│   ├── keys.py                 (400 lines)
│   ├── monitoring.py           (500 lines)
│   ├── prune.py                (150 lines) ✅
│   ├── snapshots.py            (600 lines)
│   ├── storage.py              (300 lines) ✅ (existing)
│   ├── templates.py            (400 lines)
│   ├── vm_advanced.py          (700 lines)
│   ├── vm_lifecycle.py         (800 lines)
│   └── vm_operations.py        (600 lines)
```

**Total Lines:**
- Before: 5419 lines in cli.py
- After: ~300 lines in cli.py + ~5100 lines across 12 command modules

## Success Criteria

- [ ] All 12 command modules created
- [ ] cli.py reduced to <500 lines
- [ ] All CLI commands work identically
- [ ] All tests pass
- [ ] Pre-commit hooks pass
- [ ] No functionality lost
- [ ] Clear module boundaries
- [ ] Zero regressions

## Estimated Time

- **Remaining module creation**: 6-8 hours
- **CLI update**: 2 hours
- **Testing**: 2 hours
- **Total Phase 2**: 10-12 hours

## Notes

- Take breaks between modules
- Test each module after creation
- Use the pattern from completed modules
- Don't rush - quality matters
- Run tests frequently
- Commit progress incrementally
