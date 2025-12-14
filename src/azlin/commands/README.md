# CLI Commands Module

This directory contains the decomposed CLI commands from `cli.py`.

## Structure (Post-Decomposition)

```
commands/
├── __init__.py              # Command exports for easy imports
├── cli_helpers.py           # Shared helper functions (~200-300 lines)
├── monitoring.py            # Monitoring commands (~859 lines, 6 commands)
├── lifecycle.py             # VM lifecycle commands (~454 lines, 6 commands)
├── connectivity.py          # Connectivity commands (~572 lines, 4 commands)
├── admin.py                 # Administrative commands (~412 lines, 4 commands)
├── provisioning.py          # VM provisioning commands (~199 lines, 3 commands)
├── special.py               # Special commands (~122 lines, 2 commands)
├── ask.py                   # Natural language queries (existing)
├── auth.py                  # Authentication (existing)
├── autopilot.py             # Autopilot mode (existing)
├── bastion.py               # Bastion management (existing)
├── compose.py               # Multi-VM compositions (existing)
├── context.py               # Context switching (existing)
├── costs.py                 # Cost analysis (existing)
├── doit.py                  # AI-powered task execution (existing)
├── fleet.py                 # Fleet management (existing)
├── github_runner.py         # GitHub Actions runners (existing)
├── storage.py               # Storage management (existing)
└── tag.py                   # Tag management (existing)
```

## Module Responsibilities

### `cli_helpers.py`
Shared utility functions used across multiple commands:
- VM selection and interaction
- Configuration loading and resolution
- Common validation logic
- SSH execution helpers
- Display/formatting utilities

### `monitoring.py`
Commands for observing VM state and activity:
- `list` - List VMs with quota/tmux info
- `status` - Show detailed VM status
- `session` - Manage session names
- `w` - Run 'w' command on all VMs
- `top` - Live distributed metrics dashboard
- `ps` - Process listing across VMs

### `lifecycle.py`
Commands for VM lifecycle management:
- `start` - Start stopped VM
- `stop` - Stop running VM
- `kill` - Force stop VM
- `destroy` - Delete VM with confirmation
- `killall` - Batch VM deletion
- `clone` - Create VM copy

### `connectivity.py`
Commands for connecting to and transferring files:
- `connect` - Interactive SSH connection
- `code` - Launch VS Code Remote-SSH
- `cp` - File copy operations
- `sync` - Home directory synchronization

### `admin.py`
Administrative and maintenance commands:
- `prune` - Remove old/unused VMs
- `update` - Update azlin on VM
- `os-update` - Update OS packages
- `cost` - Track and display costs

### `provisioning.py`
Commands for creating new VMs:
- `new` - Provision new VM (primary interface)
- `vm` - Alias for `new`
- `create` - Alias for `new`

Includes provisioning helpers:
- Template loading
- Configuration resolution
- Pool provisioning
- Bastion auto-detection

### `special.py`
Special-purpose commands:
- `do` - Natural language command execution
- `help` - Enhanced help system

## Design Principles

### 1. Single Responsibility
Each module focuses on a cohesive set of related commands.

### 2. Minimal Dependencies
Modules should minimize dependencies on each other.
- Shared logic → `cli_helpers.py`
- Module-specific logic → stays in module
- Avoid circular imports

### 3. Clear Interfaces
Each command function should:
- Use Click decorators for CLI interface
- Accept explicit parameters (no hidden globals)
- Return consistent types (int exit codes or None)
- Handle errors appropriately

### 4. Testability
Modules should be independently testable:
- Extract business logic from Click decorators
- Use dependency injection where practical
- Mock external dependencies
- Test helper functions separately

### 5. Documentation
Every module and function should have:
- Clear docstring
- Parameter descriptions
- Return value documentation
- Usage examples where helpful

## Import Pattern

Commands are exported from each module and registered in `cli.py`:

```python
# In monitoring.py
@click.command(name="list")
@click.option(...)
def list_command(...):
    """List VMs in resource group."""
    pass

# In cli.py
from azlin.commands.monitoring import list_command

main.add_command(list_command)
```

## Testing Strategy

Each command module has corresponding tests:

```
tests/commands/
├── test_monitoring.py
├── test_lifecycle.py
├── test_connectivity.py
├── test_admin.py
├── test_provisioning.py
└── test_special.py
```

Tests should cover:
- Happy path scenarios
- Error conditions
- Edge cases
- Integration with external services (mocked)

## Migration Notes

This structure was created as part of Issue #423 to decompose the 9,126-line
`cli.py` into focused, maintainable modules.

**Before**: 1 monolithic file with 26 inline commands
**After**: 6 command modules + 1 helpers module + existing command groups

**Benefits**:
- 94% reduction in cli.py size (9,126 → <500 lines)
- Parallel development (no merge conflicts)
- Easier testing and maintenance
- Clear module boundaries
- Faster IDE performance
- Better code organization

## Adding New Commands

To add a new command to an existing module:

1. Define command function with Click decorators
2. Add to module's command exports
3. Import and register in `cli.py`
4. Add tests to corresponding test file
5. Update this README if adding new module

Example:

```python
# In monitoring.py
@click.command(name="metrics")
@click.option("--vm", required=True)
def metrics_command(vm: str):
    \"\"\"Show detailed VM metrics.\"\"\"
    # Implementation
    pass

# In cli.py
from azlin.commands.monitoring import metrics_command
main.add_command(metrics_command)

# In tests/commands/test_monitoring.py
def test_metrics_command():
    # Test implementation
    pass
```

## Maintenance Guidelines

1. **Keep modules focused**: Don't let modules grow beyond ~1000 lines
2. **Extract helpers early**: Move shared code to `cli_helpers.py` promptly
3. **Update tests**: Every change should update corresponding tests
4. **Document changes**: Update docstrings and this README
5. **Run full suite**: Test entire CLI after module changes

## References

- Issue #423: CLI.py Decomposition
- DEFAULT_WORKFLOW.md: Development process
- DECOMPOSITION_PLAN.md: Extraction strategy
- IMPLEMENTATION_GUIDE.md: Phase-by-phase guide
