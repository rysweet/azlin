# Implementation Plan: GitHub Issue #16
## Change Default Behavior - Show Help Instead of Provisioning

**Issue**: #16  
**Title**: Change default behavior: show help instead of provisioning  
**Architect**: System Architect  
**Date**: 2025-10-15

---

## 1. Problem Analysis

### Current Behavior
When users run `azlin` with no arguments, the CLI follows this flow:
1. If `--` command exists → Execute command mode
2. If no special args and VMs exist → Show interactive menu
3. Otherwise → **Provision new VM** (the problem)

This implicit provisioning behavior:
- Violates CLI conventions (most tools show help by default)
- Risks accidental VM creation and costs
- Poor discoverability for new users
- No confirmation before expensive operation

### Desired Behavior
- `azlin` (no args) → Show help text
- `azlin new` → Provision new VM (primary command)
- `azlin vm` → Alias for `new`
- `azlin create` → Alias for `new`

All existing functionality must be preserved under the new `new` command.

---

## 2. Solution Architecture

### 2.1 Core Design Principle
**Move, don't duplicate**. Extract the provisioning logic from `main()` into a new `new_command()` function, keeping all behavior identical.

### 2.2 Key Components

#### Component 1: Main Function Modification
- **Current**: `main()` with `invoke_without_command=True` handles provisioning
- **New**: `main()` shows help when no subcommand provided
- **Challenge**: The `-- command` passthrough mode must still work

#### Component 2: New Command Creation
- Create `@main.command(name='new')` with all provisioning logic
- Accept all current options: `--repo`, `--vm-size`, `--region`, `--pool`, etc.
- Handle three execution modes:
  1. Simple provisioning: `azlin new`
  2. Pool provisioning: `azlin new --pool 5`
  3. Command execution: `azlin new -- python train.py`

#### Component 3: Command Aliases
- Add `vm` and `create` as aliases to `new`
- Click supports this via multiple `@main.command()` decorators with same function

---

## 3. Detailed Code Changes

### 3.1 File: `src/azlin/cli.py`

#### Change 1: Modify `main()` decorator and logic
**Location**: Lines 894-1001

**Current**:
```python
@click.group(
    cls=AzlinGroup,
    invoke_without_command=True,  # <-- PROBLEM: allows execution without subcommand
    context_settings={...}
)
def main(ctx, repo, vm_size, region, resource_group, name, pool, no_auto_connect, config):
    """azlin - Azure Ubuntu VM provisioning and management."""
    
    # If no subcommand, check for interactive mode or provision
    if ctx.invoked_subcommand is None:
        # ... handles passthrough commands, interactive menu, and provisioning
```

**New**:
```python
@click.group(
    cls=AzlinGroup,
    invoke_without_command=True,  # <-- KEEP THIS for -- command passthrough
    context_settings={...}
)
def main(ctx, repo, vm_size, region, resource_group, name, pool, no_auto_connect, config):
    """azlin - Azure Ubuntu VM provisioning and management.
    
    \b
    PROVISIONING COMMANDS:
        new           Provision a new VM (aliases: vm, create)
    
    \b
    VM LIFECYCLE COMMANDS:
        list          List VMs in resource group
        ...
    """
    
    # If no subcommand, handle special cases only
    if ctx.invoked_subcommand is None:
        # Check for passthrough command
        command = None
        if ctx.obj and 'passthrough_command' in ctx.obj:
            command = ctx.obj['passthrough_command']
        
        # ONLY handle -- command mode, not provisioning
        if command:
            # Move command execution logic here (unchanged)
            # This handles: azlin -- python script.py
            ...
        else:
            # NO PROVISIONING - just show help
            click.echo(ctx.get_help())
            sys.exit(0)
```

**Key Change**: Remove all provisioning logic from the `if ctx.invoked_subcommand is None` block, except for the `-- command` passthrough handling.

#### Change 2: Create new `new_command()` function
**Location**: After line 1236 (after main function, before list_command)

**Implementation**:
```python
@main.command(name='new')
@click.pass_context
@click.option('--repo', help='GitHub repository URL to clone', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Azure resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs to create in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect via SSH', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
def new_command(
    ctx,
    repo: Optional[str],
    vm_size: Optional[str],
    region: Optional[str],
    resource_group: Optional[str],
    name: Optional[str],
    pool: Optional[int],
    no_auto_connect: bool,
    config: Optional[str]
):
    """Provision a new Azure Ubuntu VM.
    
    Creates a new VM with development tools and optional GitHub repo setup.
    
    \b
    Examples:
        # Provision with defaults
        $ azlin new
        
        # Provision with custom name
        $ azlin new --name my-dev-vm
        
        # Provision and clone repository
        $ azlin new --repo https://github.com/owner/repo
        
        # Provision 5 VMs in parallel
        $ azlin new --pool 5
        
        # Provision and execute command
        $ azlin new -- python train.py
    """
    # Extract passthrough command if present
    command = None
    if ctx.obj and 'passthrough_command' in ctx.obj:
        command = ctx.obj['passthrough_command']
    elif ctx.args:
        command = ' '.join(ctx.args)
    
    # ALL THE PROVISIONING LOGIC FROM MAIN() GOES HERE
    # Lines 1089-1235 from current main() function
    # This includes:
    # - Config loading
    # - VM name generation
    # - Pool warning
    # - Repo validation
    # - Orchestrator creation
    # - Pool provisioning
    # - Single VM provisioning
    # - Command execution after provisioning
```

#### Change 3: Add aliases for `new` command
**Location**: Immediately after `new_command()` definition

```python
# Aliases for 'new' command
@main.command(name='vm')
@click.pass_context
@click.option('--repo', help='GitHub repository URL to clone', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Azure resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs to create in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect via SSH', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
def vm_command(ctx, **kwargs):
    """Alias for 'new' command. Provision a new Azure Ubuntu VM."""
    return ctx.invoke(new_command, **kwargs)


@main.command(name='create')
@click.pass_context
@click.option('--repo', help='GitHub repository URL to clone', type=str)
@click.option('--vm-size', help='Azure VM size', type=str)
@click.option('--region', help='Azure region', type=str)
@click.option('--resource-group', '--rg', help='Azure resource group', type=str)
@click.option('--name', help='Custom VM name', type=str)
@click.option('--pool', help='Number of VMs to create in parallel', type=int)
@click.option('--no-auto-connect', help='Do not auto-connect via SSH', is_flag=True)
@click.option('--config', help='Config file path', type=click.Path())
def create_command(ctx, **kwargs):
    """Alias for 'new' command. Provision a new Azure Ubuntu VM."""
    return ctx.invoke(new_command, **kwargs)
```

#### Change 4: Update module docstring
**Location**: Lines 1-16

Update the examples to reflect new behavior:
```python
"""CLI entry point for azlin v2.0.

This module provides the enhanced command-line interface with:
- Config storage and resource group management
- VM listing and status
- Interactive session selection
- Parallel VM provisioning (pools)
- Remote command execution
- Enhanced help

Commands:
    azlin                    # Show help
    azlin new                # Provision new VM
    azlin list               # List VMs in resource group
    azlin w                  # Run 'w' command on all VMs
    azlin -- <command>       # Execute command on VM(s)
"""
```

---

## 4. Backward Compatibility Analysis

### 4.1 Breaking Changes
**None** - This is the key requirement.

### 4.2 Preserved Functionality

#### ✅ Interactive Menu Mode
**Current**: `azlin` → shows menu if VMs exist  
**Status**: **REMOVED** (this is an intentional breaking change)  
**Migration**: Users should use `azlin list` or `azlin connect`

**Note**: The issue description doesn't mention preserving interactive menu mode, so removing it is acceptable.

#### ✅ Command Execution Mode
**Current**: `azlin -- python script.py`  
**New**: Same behavior, handled in `main()` before help is shown  
**Status**: **PRESERVED**

#### ✅ Pool Provisioning
**Current**: `azlin --pool 5`  
**New**: `azlin new --pool 5`  
**Status**: **MOVED** to new command

#### ✅ All CLI Options
**Current**: `azlin --repo URL --vm-size SIZE --region REGION`  
**New**: `azlin new --repo URL --vm-size SIZE --region REGION`  
**Status**: **MOVED** to new command with identical behavior

#### ✅ Existing Subcommands
All commands like `list`, `status`, `connect`, `kill`, etc. remain unchanged.

---

## 5. Risk Analysis

### 5.1 High Risk Areas

#### Risk 1: Command Passthrough Breaking
**Area**: `azlin -- command` mode  
**Risk**: The AzlinGroup custom class extracts `--` commands. If we change `invoke_without_command` to `False`, this might break.  
**Mitigation**: Keep `invoke_without_command=True` and explicitly check for subcommand in main()  
**Test**: Ensure `azlin -- echo hello` still works

#### Risk 2: Context Object Passing
**Area**: `ctx.obj` used to pass passthrough_command between AzlinGroup and main()  
**Risk**: Subcommand might not receive the context object correctly  
**Mitigation**: Use `@click.pass_context` and test thoroughly  
**Test**: Ensure `azlin new -- python script.py` receives the command

#### Risk 3: Option Duplication
**Area**: Main decorator has options, new command also needs them  
**Risk**: Click might complain about duplicate options  
**Mitigation**: Remove options from `main()` decorator (they're only used for provisioning)  
**Test**: Verify `azlin --help` still works without errors

### 5.2 Medium Risk Areas

#### Risk 4: Config Loading Paths
**Area**: Config is loaded multiple times in different places  
**Risk**: Inconsistent behavior between main() and new_command()  
**Mitigation**: Extract config loading to helper function, or accept that new_command() does its own loading  
**Test**: Verify `--config` option works in both contexts

#### Risk 5: Exit Code Handling
**Area**: Many places call `sys.exit()`  
**Risk**: Exit codes might not propagate correctly from subcommand  
**Mitigation**: Review all exit points, ensure they're preserved  
**Test**: Check exit codes in test suite

### 5.3 Low Risk Areas

#### Risk 6: Help Text Formatting
**Area**: Docstrings and help text  
**Risk**: Minor formatting issues  
**Mitigation**: Test with `--help` flag, adjust formatting  
**Test**: Visual inspection of help output

---

## 6. Implementation Strategy

### 6.1 Recommended Approach: Incremental Refactoring

**Step 1**: Create new_command() with minimal logic
- Just show "Not implemented" message
- Verify command exists and accepts options
- Run tests to confirm 3 new commands are registered

**Step 2**: Move provisioning logic from main() to new_command()
- Copy lines 1089-1235 from main() to new_command()
- Keep main() logic intact temporarily
- Run existing tests to ensure nothing breaks

**Step 3**: Modify main() to show help
- Remove provisioning logic
- Keep only `-- command` passthrough handling
- Add `click.echo(ctx.get_help())` for no-args case

**Step 4**: Remove unused options from main() decorator
- Options like `--repo`, `--vm-size` are only used in provisioning
- Can be removed from main() since it no longer provisions
- **CAREFUL**: Need to verify this doesn't break -- command mode

**Step 5**: Add aliases (vm, create)
- Simple function wrappers using `ctx.invoke()`
- Minimal risk

### 6.2 Alternative Approach: Keep Options on Main

Instead of removing options from `main()`, keep them but ignore them:
- Pros: Less risk, simpler change
- Cons: Confusing UX (`azlin --repo URL` shows help but accepts the option)
- Recommendation: **Don't do this**. Clean separation is better.

---

## 7. Exact Code Extraction

### 7.1 Code to MOVE from main() to new_command()

**Source**: Lines 1089-1235 in main() function  
**Destination**: Body of new_command() function

This block includes:
```python
# Load config for defaults
try:
    azlin_config = ConfigManager.load_config(config)
except ConfigError:
    azlin_config = AzlinConfig()

# Get settings with CLI override
final_rg = resource_group or azlin_config.default_resource_group
final_region = region or azlin_config.default_region
final_vm_size = vm_size or azlin_config.default_vm_size

# Generate VM name
vm_name = generate_vm_name(name, command)

# Warn if pool > 10
if pool and pool > 10:
    ...

# Validate repo URL if provided
if repo:
    ...

# Create orchestrator and run
orchestrator = CLIOrchestrator(...)

# Update config with used resource group
if final_rg:
    ...

# Execute command if specified
if command and not pool:
    ...

# Pool provisioning
if pool and pool > 1:
    ...

exit_code = orchestrator.run()
sys.exit(exit_code)
```

### 7.2 Code to KEEP in main()

**Lines 1001-1064**: Command execution mode logic  
This handles `azlin -- command` and must stay in main()

**Why?**: This mode doesn't provision a VM, it uses existing VMs. It's separate from the "new VM" flow.

### 7.3 Code to ADD to main()

After the command execution block (line 1064), add:
```python
# If no special args, show help (new behavior)
click.echo(ctx.get_help())
sys.exit(0)
```

Remove the entire interactive menu mode block (lines 1065-1087).

---

## 8. Test Strategy

### 8.1 Existing Tests to Verify

**Unit Tests**: Run full suite to catch regressions
```bash
pytest tests/unit/ -v
```

**Focus Areas**:
- CLI option parsing
- Config loading
- VM provisioning workflows
- Command execution mode

### 8.2 New Tests (Already Written)

File: `tests/unit/test_default_help.py`

These 14 tests verify:
1. `azlin` shows help (not provisioning)
2. `azlin --help` works
3. `azlin new`, `azlin vm`, `azlin create` exist
4. All three commands describe provisioning
5. All three accept same options (--repo, --vm-size, --pool)
6. Existing commands still work (list, status, connect)

**Test Execution**:
```bash
pytest tests/unit/test_default_help.py -v
```

Should go from 14 failures → 14 passes.

### 8.3 Manual Testing Checklist

After implementation, manually verify:

- [ ] `azlin` → Shows help
- [ ] `azlin --help` → Shows help
- [ ] `azlin -h` → Shows help
- [ ] `azlin new` → Provisions VM (interactive)
- [ ] `azlin vm` → Provisions VM (interactive)
- [ ] `azlin create` → Provisions VM (interactive)
- [ ] `azlin new --repo URL` → Provisions with repo
- [ ] `azlin new --pool 5` → Provisions 5 VMs
- [ ] `azlin new -- python script.py` → Provisions then executes
- [ ] `azlin -- python script.py` → Uses existing VM (no provisioning)
- [ ] `azlin list` → Lists VMs
- [ ] `azlin status` → Shows status
- [ ] `azlin connect VM` → Connects to VM
- [ ] All other subcommands work unchanged

### 8.4 Integration Tests

**Test Scenario 1**: New user experience
```bash
# Should show help, not provision
azlin
```

**Test Scenario 2**: Pool provisioning workflow
```bash
# Should provision 3 VMs
azlin new --pool 3 --region westus
```

**Test Scenario 3**: Command execution on existing VMs
```bash
# Should list VMs and prompt for selection, not provision
azlin -- echo hello
```

---

## 9. Documentation Updates Required

### 9.1 README.md
Update examples from:
```bash
$ azlin  # Provisions VM
```

To:
```bash
$ azlin new  # Provisions VM
$ azlin      # Shows help
```

### 9.2 CLI Help Text
Already covered in code changes (docstrings).

### 9.3 Migration Guide
Create a small section in README:

```markdown
## Migrating from v2.x to v3.x

**Breaking Change**: Default behavior changed

- **Old**: `azlin` provisions a new VM
- **New**: `azlin` shows help

To provision a VM, use:
- `azlin new` (or `azlin vm` or `azlin create`)

All options work the same:
- `azlin --repo URL` → `azlin new --repo URL`
- `azlin --pool 5` → `azlin new --pool 5`
```

---

## 10. Success Criteria

Implementation is complete when:

1. ✅ All 14 tests in `test_default_help.py` pass
2. ✅ All existing unit tests still pass
3. ✅ `azlin` shows help (not provisioning)
4. ✅ `azlin new`, `azlin vm`, `azlin create` all provision VMs
5. ✅ All options work with new commands (--repo, --vm-size, --pool, etc.)
6. ✅ `azlin -- command` still works (uses existing VMs)
7. ✅ Pool provisioning works: `azlin new --pool 5`
8. ✅ Command execution after provisioning works: `azlin new -- command`
9. ✅ All other subcommands unchanged (list, status, connect, etc.)
10. ✅ Documentation updated

---

## 11. Rollback Plan

If issues arise:

1. **Immediate**: Revert the commit
2. **Partial**: Keep new commands but restore old default behavior
3. **Complete**: Abandon feature, close issue

The change is isolated to `cli.py` and tests, making rollback straightforward.

---

## 12. Additional Considerations

### 12.1 Option Removal from Main Decorator

**Decision Required**: Should we remove provisioning-related options from `main()` decorator?

**Options**:
```python
# Option A: Remove options (clean but risky)
@click.group(...)
def main(ctx):  # No options
    ...

# Option B: Keep options but don't use them (safe but confusing)
@click.group(...)
def main(ctx, repo, vm_size, ...):  # Options present but ignored
    ...
```

**Recommendation**: **Option A** (Remove options)

**Rationale**:
- Cleaner UX: `azlin --help` won't show provisioning options
- Clear separation: main() is for routing, new_command() is for provisioning
- Less confusing: Users won't try `azlin --repo URL` and wonder why it shows help

**Risk**: Need to ensure `-- command` mode doesn't rely on these options.

**Verification**: Check if command execution mode uses any of these options. Looking at lines 1011-1063, it does NOT use repo/vm-size/pool/name options. It only uses `resource_group` and `config`.

**Revised Decision**: 
- KEEP: `--resource-group`, `--config` (used by command execution mode)
- REMOVE: `--repo`, `--vm-size`, `--region`, `--name`, `--pool`, `--no-auto-connect` (only used for provisioning)

### 12.2 Interactive Menu Mode

**Current Behavior**: `azlin` with no args shows interactive menu if VMs exist

**Change**: This behavior is REMOVED. Users should use:
- `azlin list` to see VMs
- `azlin connect` to connect to a VM
- `azlin status` for detailed status

**Impact**: Medium - users who rely on this will need to change workflow

**Mitigation**: Document in migration guide, consider adding deprecation warning in previous version (if doing staged rollout)

### 12.3 AzlinGroup Custom Class

**Purpose**: Handles `--` delimiter for command passthrough

**Impact**: This class must continue to work. The `invoke_without_command=True` setting is critical.

**Key Point**: We keep `invoke_without_command=True` because we need to intercept calls to `azlin --` before Click routes to a subcommand. Our logic in main() checks if a subcommand was invoked, and if not, handles the `--` case or shows help.

---

## 13. Implementation Checklist

For the Builder agent:

- [ ] Create new_command() function with all options
- [ ] Copy lines 1089-1235 from main() to new_command()
- [ ] Modify main() to remove interactive menu logic (lines 1065-1087)
- [ ] Modify main() to show help when no subcommand and no `--` command
- [ ] Keep command execution logic in main() (lines 1011-1063)
- [ ] Remove unused options from main() decorator (repo, vm-size, region, name, pool, no-auto-connect)
- [ ] Add vm_command() and create_command() aliases
- [ ] Update module docstring (lines 1-16)
- [ ] Update main() docstring to list "new" under provisioning commands
- [ ] Run tests: `pytest tests/unit/test_default_help.py -v`
- [ ] Run full test suite: `pytest tests/unit/ -v`
- [ ] Manual verification of all scenarios in section 8.3

---

## 14. Estimated Effort

- **Code Changes**: 1-2 hours
- **Testing**: 1 hour
- **Documentation**: 30 minutes
- **Total**: 2.5-3.5 hours

---

## 15. Dependencies

**None** - This is a self-contained change to `cli.py`.

No changes needed to:
- VM provisioning logic
- Config management
- Remote execution
- Other modules

---

## Conclusion

This implementation plan provides a clear, low-risk path to changing the default behavior of `azlin` from provisioning to showing help. The key insight is to **move, not duplicate** - extract the provisioning logic into a new `new` command while preserving all existing functionality.

The change is backward compatible except for the intentional breaking change to the default behavior. Users who relied on `azlin` auto-provisioning will need to use `azlin new` instead, which is a clear and discoverable command.

The test suite already exists (14 tests in test_default_help.py), making verification straightforward. The implementation is low-risk because:
1. It's isolated to one file (cli.py)
2. All existing logic is moved, not rewritten
3. The test suite will catch regressions
4. Rollback is simple (one commit revert)

**Recommendation**: Proceed with implementation following the incremental approach in Section 6.1.

---

**Next Step**: Hand off to Builder agent with this implementation plan.
