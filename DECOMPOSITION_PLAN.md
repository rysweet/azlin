# CLI Decomposition Plan

## Status: Phase 1 Complete (Foundation)

### Completed Work (Phase 1)

✅ **GitHub Issue #128 Created**
  - Comprehensive requirements
  - Clear success criteria
  - Detailed module breakdown

✅ **Worktree and Branch Setup**
  - Branch: `feat/issue-128-decompose-cli`
  - Worktree: `/Users/ryan/src/azlin-worktree-128`

✅ **Working Modules Created (4/12 complete)**
  - `commands/help.py` (50 lines) - Help command ✓
  - `commands/cost.py` (110 lines) - Cost tracking ✓
  - `commands/prune.py` (150 lines) - Prune operations ✓
  - `commands/env.py` (340 lines) - Environment management ✓
  - `commands/storage.py` (existing) - Storage management ✓

✅ **Documentation Created**
  - `DECOMPOSITION_PLAN.md` - Overall architecture and plan
  - `PHASE_2_COMPLETION_GUIDE.md` - Detailed completion instructions

✅ **Development Scripts Created**
  - `decompose_cli.py` - Module organization reference
  - `decompose_cli_full.py` - Extraction utilities
  - `automate_decomposition.py` - Full automation framework

### Architecture Design

```
src/azlin/
├── cli.py                          # Main entry point (~300 lines final)
│   ├── CLIOrchestrator class
│   ├── Main group setup
│   ├── Core workflow functions
│   └── Register command groups
├── commands/
│   ├── __init__.py                 # Export registration functions
│   ├── storage.py                  # ✅ Already exists
│   ├── help.py                     # ✅ Created (50 lines)
│   ├── cost.py                     # ✅ Created (110 lines)
│   ├── prune.py                    # ✅ Created (150 lines)
│   ├── monitoring.py               # 📋 TODO (~500 lines)
│   ├── env.py                      # 📋 TODO (~400 lines)
│   ├── keys.py                     # 📋 TODO (~400 lines)
│   ├── templates.py                # 📋 TODO (~400 lines)
│   ├── snapshots.py                # 📋 TODO (~600 lines)
│   ├── batch.py                    # 📋 TODO (~400 lines)
│   ├── vm_lifecycle.py             # 📋 TODO (~800 lines)
│   ├── vm_operations.py            # 📋 TODO (~600 lines)
│   └── vm_advanced.py              # 📋 TODO (~700 lines)
```

### Remaining Work

**Phase 2: Complete Module Extraction** (Estimated: 6-8 hours)

Each module needs:
1. Extract commands and helper functions
2. Identify and add required imports
3. Create `register_*_commands()` function
4. Format with proper indentation
5. Test module independently

**Modules TODO:**

1. **monitoring.py** (~500 lines)
   - Commands: `w`, `top`, `ps`, `os-update`
   - Helpers: `execute_command_on_vm`, `select_vm_for_command`
   - Imports: RemoteExecutor, DistributedTopExecutor, PSCommandExecutor, etc.

2. **env.py** (~400 lines)
   - Group: `env`
   - Commands: `set`, `list`, `delete`, `export`, `import`, `clear`
   - Helper: `_get_ssh_config_for_vm`
   - Imports: EnvManager, SSHConnector

3. **keys.py** (~400 lines)
   - Group: `keys`
   - Commands: `rotate`, `list`, `export`, `backup`
   - Imports: SSHKeyRotator, SSHKeyManager

4. **templates.py** (~400 lines)
   - Group: `template`
   - Commands: `create`, `list`, `delete`, `export`, `import`
   - Imports: TemplateManager, VMTemplateConfig

5. **snapshots.py** (~600 lines)
   - Group: `snapshot`
   - Commands: `enable`, `disable`, `sync`, `status`, `create`, `list`, `restore`, `delete`
   - Imports: SnapshotManager

6. **batch.py** (~400 lines)
   - Group: `batch`
   - Commands: `stop`, `start`, `command`, `sync`
   - Helpers: `_validate_batch_selection`, `_confirm_batch_operation`, etc.
   - Imports: BatchExecutor

7. **vm_lifecycle.py** (~800 lines)
   - Commands: `new`, `vm`, `create`, `list`, `start`, `stop`, `destroy`, `kill`, `killall`
   - Helpers: `generate_vm_name`, `_load_config_and_template`, `_resolve_vm_settings`, etc.
   - Imports: VMProvisioner, VMLifecycleManager, VMLifecycleController

8. **vm_operations.py** (~600 lines)
   - Commands: `connect`, `update`, `status`, `session`
   - Helpers: `_interactive_vm_selection`, `_resolve_vm_identifier`, `_verify_vm_exists`, etc.
   - Imports: VMConnector, SSHConnector, SSHKeyManager

9. **vm_advanced.py** (~700 lines)
   - Commands: `clone`, `sync`, `cp`
   - Helpers: `_resolve_source_vm`, `_generate_clone_configs`, `_copy_home_directories`, etc.
   - Imports: FileTransfer, HomeSyncManager, VMProvisioner

**Phase 3: Update Main CLI** (Estimated: 2 hours)

1. Update `cli.py`:
   - Remove extracted commands
   - Keep CLIOrchestrator class
   - Keep core helper functions used by multiple modules
   - Add imports for new command modules
   - Call registration functions

2. Update `commands/__init__.py`:
   - Export all registration functions
   - Provide single import point

3. Update imports in test files

**Phase 4: Testing** (Estimated: 2 hours)

1. Run full test suite
2. Run pre-commit hooks
3. Test each command locally
4. Verify no regressions

### Command Line Mapping

**Current (cli.py 5419 lines):**
```
@main.command() help_command
@main.command() cost
@main.command() prune
@main.command() w
@main.command() top
@main.command() ps
@main.command() os_update
@main.command() list_command
@main.command() session_command
@main.command() connect
@main.command() update
@main.command() stop
@main.command() start
@main.command() kill
@main.command() destroy
@main.command() killall
@main.command() sync
@main.command() cp
@main.command() clone
@main.command() status
@main.command() new_command / vm_command / create_command
@main.group() batch
  @batch.command() stop
  @batch.command() start
  @batch.command() command
  @batch.command() sync
@main.group() keys
  @keys.command() rotate
  @keys.command() list
  @keys.command() export
  @keys.command() backup
@main.group() template
  @template.command() create
  @template.command() list
  @template.command() delete
  @template.command() export
  @template.command() import
@main.group() snapshot
  @snapshot.command() enable
  @snapshot.command() disable
  @snapshot.command() sync
  @snapshot.command() status
  @snapshot.command() create
  @snapshot.command() list
  @snapshot.command() restore
  @snapshot.command() delete
@main.group() env
  @env.command() set
  @env.command() list
  @env.command() delete
  @env.command() export
  @env.command() import
  @env.command() clear
main.add_command(storage_group)  # from commands/storage.py
```

**After Decomposition:**
```
cli.py (~300 lines):
  - CLIOrchestrator class
  - Main group definition
  - Core workflow helpers
  - Registration calls

commands/help.py: register_help_command()
commands/cost.py: register_cost_command()
commands/prune.py: register_prune_command()
commands/monitoring.py: register_monitoring_commands()
commands/env.py: register_env_commands()
commands/keys.py: register_keys_commands()
commands/templates.py: register_templates_commands()
commands/snapshots.py: register_snapshots_commands()
commands/batch.py: register_batch_commands()
commands/vm_lifecycle.py: register_vm_lifecycle_commands()
commands/vm_operations.py: register_vm_operations_commands()
commands/vm_advanced.py: register_vm_advanced_commands()
commands/storage.py: storage_group (existing pattern, keep as-is)
```

### Import Strategy

Each command module follows this pattern:

```python
"""Module description."""

import sys  # if needed
from pathlib import Path  # if needed
from datetime import datetime  # if needed

import click

# Import only what's needed from azlin modules
from azlin.config_manager import ConfigManager
from azlin.vm_manager import VMManager, VMInfo
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

### Testing Strategy

1. **Unit Tests**: Each module can be tested independently
2. **Integration Tests**: Test command registration
3. **Manual Tests**: Run each command to verify functionality
4. **CI Tests**: All existing tests must pass

### Benefits of This Decomposition

✅ **Maintainability**: Each module is <1000 lines, focused on one responsibility
✅ **Testability**: Modules can be tested independently
✅ **Discoverability**: Clear organization by command category
✅ **Philosophy**: Follows "one brick, one responsibility"
✅ **Scalability**: Easy to add new command groups
✅ **No Breaking Changes**: All CLI commands work exactly as before

### Next Steps

1. **Complete remaining 9 modules** using automation script
2. **Update cli.py** to remove extracted code and add registrations
3. **Update commands/__init__.py** to export all registration functions
4. **Run tests** to verify all functionality preserved
5. **Local testing** of all CLI commands
6. **Pre-commit hooks**
7. **Commit and push**
8. **Open PR**

### Automation Support

The `automate_decomposition.py` script can be extended to:
- Extract function ranges automatically
- Detect required imports
- Generate properly formatted modules
- Update cli.py automatically

This would reduce the remaining 6-8 hours of manual work to 2-3 hours of supervised automation.

### Success Metrics

- [ ] cli.py reduced from 5419 lines to <500 lines
- [ ] 12 new command modules created (<1000 lines each)
- [ ] All CLI commands work identically
- [ ] All tests pass
- [ ] Pre-commit hooks pass
- [ ] No functionality lost
- [ ] Clear module boundaries
- [ ] Proper documentation

### Estimated Total Effort

- Phase 1 (Foundation): ✅ 2 hours (COMPLETE)
- Phase 2 (Module Extraction): 📋 6-8 hours (TODO)
- Phase 3 (CLI Update): 📋 2 hours (TODO)
- Phase 4 (Testing): 📋 2 hours (TODO)

**Total: 12-14 hours**
**Completed: 2 hours**
**Remaining: 10-12 hours**
