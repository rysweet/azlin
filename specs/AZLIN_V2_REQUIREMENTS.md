# azlin v2.0 - Requirements Specification

**Document Version**: 1.0
**Date**: 2025-10-09
**Status**: Draft for Review
**Author**: Architect Agent

---

## Executive Summary

This document provides a comprehensive analysis of the azlin v2.0 feature requests, breaking them down into clear requirements with acceptance criteria, technical approaches, complexity estimates, and a recommended implementation order. The v2.0 features transform azlin from a single-use VM provisioner into a session manager with multi-VM support.

### Philosophy Alignment

All features are evaluated against azlin's core philosophy:
- **Ruthless simplicity**: Minimal abstractions, clear purpose
- **Security-first**: No credentials in code, proper permission handling
- **Brick architecture**: Self-contained, regeneratable modules
- **Standard library preference**: Minimize dependencies

---

## Table of Contents

1. [Feature Analysis](#feature-analysis)
2. [Dependency Matrix](#dependency-matrix)
3. [Implementation Order](#implementation-order)
4. [Risk Assessment](#risk-assessment)
5. [Technical Architecture](#technical-architecture)
6. [Additional Recommendations](#additional-recommendations)

---

## Feature Analysis

### Feature 1: Shared Resource Group with Config Storage

**Status**: CLARIFIED

#### Requirements

1. All VMs created by azlin should be placed in a shared resource group
2. Resource group name should be configurable via `--resource-group` (or `--rg`) CLI argument
3. Store configuration in `~/.azlin/config.json`
4. Default to saved resource group on subsequent runs

#### Ambiguities Identified

1. **Initial default**: What happens on first run when no config exists?
   - Recommended: Use `azlin-vms` as default, auto-create if doesn't exist
2. **Multiple users**: How to handle shared Azure subscriptions?
   - Recommended: Include username in default: `azlin-{username}-vms`
3. **Config scope**: What else should be stored in config?
   - Recommended: Resource group, default region, default VM size
4. **Overrides**: Should CLI args override saved config?
   - Recommended: Yes, CLI args always override saved values

#### Acceptance Criteria

- [ ] `~/.azlin/config.json` is created on first run
- [ ] `azlin --rg my-group` saves `my-group` as default for future runs
- [ ] `azlin` (no args) uses saved resource group from config
- [ ] Config file has proper permissions (0600)
- [ ] Missing config directory is auto-created with proper permissions (0700)
- [ ] Invalid/corrupted config falls back to defaults with warning
- [ ] Multiple VMs can coexist in the same resource group

#### Technical Approach

**Module**: `config_manager.py` (New Brick 10)

```python
class ConfigManager:
    """Manages ~/.azlin/config.json configuration."""

    def __init__(self, config_path: Path = Path.home() / ".azlin" / "config.json"):
        self.config_path = config_path

    def load() -> AzlinConfig:
        """Load config from disk, return defaults if not found."""

    def save(config: AzlinConfig) -> None:
        """Save config to disk with proper permissions."""

    def get_resource_group() -> str:
        """Get resource group, falling back to default."""

    def set_resource_group(rg: str) -> None:
        """Update resource group in config."""
```

**Config Schema**:
```json
{
  "version": "2.0",
  "resource_group": "azlin-vms",
  "default_region": "eastus",
  "default_vm_size": "Standard_B2s",
  "sessions": []
}
```

**Security Considerations**:
- Config directory: `0700` (drwx------)
- Config file: `0600` (-rw-------)
- No credentials stored in config (only resource names)

#### Complexity: LOW

- Simple JSON read/write
- Standard library (json, pathlib)
- Clear contracts
- ~100 lines of code

#### Dependencies

- None (foundation for other features)

---

### Feature 2: azlin list Command

**Status**: CLARIFIED

#### Requirements

1. List all VMs in the configured resource group
2. Show VM status (running, stopped, deallocated)
3. Show VM name
4. Show public IP address
5. Show additional useful metadata (size, region, uptime)

#### Ambiguities Identified

1. **Scope**: List only azlin-created VMs or all VMs in resource group?
   - Recommended: All VMs (simpler), optionally filter by tag
2. **Formatting**: Table, JSON, or both?
   - Recommended: Default to table, add `--json` flag for scripting
3. **Offline VMs**: How to handle VMs without public IPs?
   - Recommended: Show "N/A" or "-" for missing values
4. **Empty list**: What to show when no VMs exist?
   - Recommended: "No VMs found in resource group 'X'"

#### Acceptance Criteria

- [ ] `azlin list` shows all VMs in configured resource group
- [ ] Output includes: name, status, IP, size, region, uptime
- [ ] Table is properly aligned and formatted
- [ ] `azlin list --json` outputs valid JSON
- [ ] Handles missing resource group gracefully
- [ ] Handles empty VM list gracefully
- [ ] Shows VMs created by other tools (not just azlin)

#### Technical Approach

**Module**: `vm_manager.py` (New Brick 11)

```python
class VMManager:
    """Manages VM lifecycle and queries."""

    def list_vms(resource_group: str, format: str = "table") -> List[VMInfo]:
        """List all VMs in resource group."""
        # Uses: az vm list --resource-group X
        # Returns: List of VMInfo objects

    def get_vm_details(vm_name: str, resource_group: str) -> VMInfo:
        """Get detailed info for a specific VM."""

    def format_table(vms: List[VMInfo]) -> str:
        """Format VMs as ASCII table."""

    def format_json(vms: List[VMInfo]) -> str:
        """Format VMs as JSON."""
```

**Output Example**:
```
NAME              STATUS    IP              SIZE           REGION    UPTIME
azlin-2025-10-09  Running   20.10.30.40     Standard_B2s   eastus    2h 15m
azlin-dev         Stopped   -               Standard_B2s   eastus    -
azlin-test        Running   20.10.30.41     Standard_B4s   westus    5d 3h
```

**Implementation Notes**:
- Use `az vm list` with `--query` for efficient filtering
- Cache results for 30 seconds to avoid repeated API calls
- Use `tabulate` or simple string formatting (prefer stdlib)

#### Complexity: LOW

- Straightforward Azure CLI wrapper
- Simple formatting logic
- ~150 lines of code

#### Dependencies

- Feature 1 (Config Manager) for resource group
- Azure CLI

---

### Feature 3: Interactive Session Selection

**Status**: CLARIFIED

#### Requirements

1. When user runs `azlin` with no arguments and VMs exist, show interactive menu
2. List existing sessions/VMs with metadata
3. Allow user to select a session to reconnect
4. Provide option to create new VM
5. Handle keyboard navigation (arrow keys, enter)

#### Ambiguities Identified

1. **Menu library**: Which terminal UI library?
   - Recommended: `questionary` (simple, CLI-focused) or `prompt_toolkit`
   - Alternative: Simple numbered menu with stdlib (stays dependency-free)
2. **Session state**: How to detect if SSH session is active?
   - Recommended: Track in config, but verify with actual SSH check
3. **Stale sessions**: How to handle VMs that are stopped?
   - Recommended: Show status, warn user before attempting connection
4. **Empty state**: What if no VMs exist?
   - Recommended: Skip menu, go straight to creation flow

#### Acceptance Criteria

- [ ] `azlin` shows interactive menu when VMs exist
- [ ] Menu displays VM name, status, IP, last connected time
- [ ] Arrow keys navigate menu
- [ ] Enter selects VM and connects
- [ ] "Create new VM" option is always available
- [ ] ESC or Ctrl+C cancels and exits
- [ ] Selecting stopped VM shows warning
- [ ] Selecting running VM attempts SSH connection
- [ ] Menu skipped if only one VM exists (optional optimization)

#### Technical Approach

**Option A: External Dependency (Recommended)**

```python
import questionary

def select_session(vms: List[VMInfo]) -> VMInfo | CreateNew:
    """Show interactive menu for session selection."""
    choices = [
        f"{vm.name} ({vm.status}) - {vm.ip}"
        for vm in vms
    ]
    choices.append("Create new VM")

    selection = questionary.select(
        "Select a session:",
        choices=choices
    ).ask()

    if selection == "Create new VM":
        return CreateNew()
    return vms[choices.index(selection)]
```

**Option B: Standard Library Only**

```python
def select_session(vms: List[VMInfo]) -> VMInfo | CreateNew:
    """Show numbered menu for session selection."""
    print("\nAvailable sessions:")
    for i, vm in enumerate(vms, 1):
        print(f"  {i}. {vm.name} ({vm.status}) - {vm.ip}")
    print(f"  {len(vms) + 1}. Create new VM")

    while True:
        try:
            choice = int(input("\nSelect (1-{}): ".format(len(vms) + 1)))
            if 1 <= choice <= len(vms):
                return vms[choice - 1]
            elif choice == len(vms) + 1:
                return CreateNew()
        except (ValueError, KeyboardInterrupt):
            sys.exit(0)
```

**Recommendation**: Start with Option B (stdlib only), add Option A if users request it.

#### Complexity: MEDIUM

- Interaction logic requires careful UX design
- State management (connecting vs reconnecting)
- Error handling for failed connections
- ~200 lines of code

#### Dependencies

- Feature 1 (Config Manager)
- Feature 2 (VM Manager for listing VMs)

---

### Feature 4: --name Flag with Smart Defaults

**Status**: REQUIRES CLARIFICATION

#### Requirements

1. User can specify VM name via `--name` flag
2. If not specified, auto-generate from datetime
3. Optionally include "running commands" in auto-generated name
4. Track command activity on remote shell

#### Ambiguities Identified - HIGH PRIORITY

1. **"Running commands" definition**: What does this mean?
   - Option A: Commands passed via `azlin -- <cmd>` syntax (Feature 7)
   - Option B: Commands currently executing in the tmux session
   - Option C: Commands in shell history on the VM
   - **NEEDS USER CLARIFICATION**

2. **Tracking mechanism**: How to track commands?
   - Option A: Only for commands passed at creation time
   - Option B: Monitor tmux session actively (complex, fragile)
   - Option C: Parse shell history file periodically (intrusive)
   - **NEEDS USER CLARIFICATION**

3. **Name format**: What's the actual format?
   - Current v1.0: `azlin-{timestamp}` (e.g., `azlin-20251009-143020`)
   - Proposed: `azlin-{timestamp}-{command}` (e.g., `azlin-20251009-143020-pytest`)
   - Concern: Command names may contain invalid chars for Azure VM names

4. **Name sanitization**: How to handle special characters?
   - Azure VM names: alphanumeric and hyphens only, 1-64 chars
   - Command: `python -m pytest tests/` → Sanitized: `python-pytest`

#### Acceptance Criteria (PROVISIONAL)

- [ ] `azlin --name my-vm` creates VM with exact name "my-vm"
- [ ] `azlin` (no --name) creates VM with format: `azlin-YYYYMMDD-HHMMSS`
- [ ] `azlin -- pytest` creates VM with format: `azlin-YYYYMMDD-HHMMSS-pytest`
- [ ] Names are validated against Azure VM naming rules
- [ ] Invalid characters are sanitized (replaced with hyphens)
- [ ] Names > 64 chars are truncated intelligently
- [ ] Name collision detection with auto-increment suffix

#### Technical Approach (PROVISIONAL)

**Module**: Extend `vm_provisioner.py`

```python
def generate_vm_name(user_name: str | None, command: str | None) -> str:
    """Generate or validate VM name.

    Priority:
    1. Use user_name if provided
    2. Generate from timestamp + command if command provided
    3. Generate from timestamp only
    """
    if user_name:
        return sanitize_vm_name(user_name)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"azlin-{timestamp}"

    if command:
        cmd_slug = sanitize_command_slug(command)
        return f"{base}-{cmd_slug}"

    return base

def sanitize_vm_name(name: str) -> str:
    """Ensure name meets Azure VM requirements."""
    # Replace invalid chars with hyphens
    name = re.sub(r'[^a-zA-Z0-9-]', '-', name)
    # Remove consecutive hyphens
    name = re.sub(r'-+', '-', name)
    # Trim to 64 chars
    return name[:64].strip('-')

def sanitize_command_slug(command: str) -> str:
    """Extract meaningful slug from command."""
    # Take first word of command
    first_word = command.split()[0]
    # Remove path components
    slug = os.path.basename(first_word)
    # Remove file extensions
    slug = os.path.splitext(slug)[0]
    return sanitize_vm_name(slug)[:20]  # Limit to 20 chars
```

**Command Tracking** (if interpretation B or C):
- **Not recommended**: Overly complex for marginal benefit
- **Alternative**: Store command in VM tags for reference

#### Complexity: LOW to HIGH (depending on clarification)

- **Without command tracking**: LOW (50 lines)
- **With command tracking**: HIGH (200+ lines, ongoing complexity)

#### Dependencies

- Potentially Feature 7 (Remote Command Execution)

#### RECOMMENDATION

**Request clarification from user before implementing**. Suggest the simplified interpretation:
- Auto-name format: `azlin-YYYYMMDD-HHMMSS`
- If `azlin -- <cmd>` used: `azlin-YYYYMMDD-HHMMSS-{cmd-slug}`
- No active command tracking (too complex)

---

### Feature 5: azlin w Command

**Status**: CLARIFIED

#### Requirements

1. Run `w` command on all VMs in resource group
2. Aggregate results from all VMs
3. Prefix each output line with VM name for clarity

#### Ambiguities Identified

1. **Parallelization**: Sequential or parallel execution?
   - Recommended: Parallel (faster for multiple VMs)
2. **Offline VMs**: How to handle stopped VMs?
   - Recommended: Skip with warning message
3. **Errors**: What if SSH fails for a VM?
   - Recommended: Show error, continue to next VM
4. **Output format**: Raw output or structured?
   - Recommended: Raw with clear VM separators

#### Acceptance Criteria

- [ ] `azlin w` executes `w` command on all running VMs
- [ ] Each line prefixed with VM name: `[vm-name] output-line`
- [ ] VMs are processed in parallel for speed
- [ ] Stopped VMs are skipped with message: `[vm-name] SKIPPED (not running)`
- [ ] SSH errors shown: `[vm-name] ERROR: Connection failed`
- [ ] Summary shown at end: "Ran on 3/5 VMs (2 offline)"
- [ ] Works with 0 VMs (shows "No VMs found")

#### Technical Approach

**Module**: `remote_commands.py` (New Brick 12)

```python
class RemoteCommandRunner:
    """Execute commands on remote VMs via SSH."""

    def run_on_all(
        command: str,
        vms: List[VMInfo],
        parallel: bool = True
    ) -> List[CommandResult]:
        """Run command on all VMs, return results."""

    def run_on_vm(command: str, vm: VMInfo) -> CommandResult:
        """Run command on single VM via SSH."""

    def format_results(results: List[CommandResult]) -> str:
        """Format results with VM name prefixes."""
```

**Implementation**:
```python
import concurrent.futures

def run_w_command(vms: List[VMInfo]) -> None:
    """Run 'w' on all VMs concurrently."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_vm = {
            executor.submit(run_ssh_command, vm, "w"): vm
            for vm in vms if vm.status == "Running"
        }

        for future in concurrent.futures.as_completed(future_to_vm):
            vm = future_to_vm[future]
            try:
                result = future.result()
                for line in result.stdout.splitlines():
                    print(f"[{vm.name}] {line}")
            except Exception as e:
                print(f"[{vm.name}] ERROR: {e}")
```

**Output Example**:
```
[azlin-dev] 14:32:01 up 2 days,  3:15,  1 user,  load average: 0.52, 0.58, 0.59
[azlin-dev] USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
[azlin-dev] ryan     pts/0    203.0.113.42     14:00    0.00s  0.04s  0.00s w
[azlin-test] 14:32:02 up  5:23,  1 user,  load average: 0.12, 0.15, 0.18
[azlin-test] USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
[azlin-test] ryan     pts/0    203.0.113.42     09:15    0.00s  0.02s  0.00s w

Summary: Ran on 2/3 VMs (1 offline)
```

#### Complexity: MEDIUM

- Parallel execution adds complexity
- SSH error handling
- Output aggregation and formatting
- ~200 lines of code

#### Dependencies

- Feature 1 (Config Manager)
- Feature 2 (VM Manager)
- SSH keys from v1.0

---

### Feature 6: --pool Flag

**Status**: CLARIFIED

#### Requirements

1. `azlin --pool N` creates N VMs in parallel
2. Accept any positive integer
3. Efficient parallel provisioning

#### Ambiguities Identified

1. **Naming**: How to name VMs in a pool?
   - Recommended: `azlin-YYYYMMDD-HHMMSS-1`, `azlin-YYYYMMDD-HHMMSS-2`, etc.
   - Alternative: `azlin-pool-YYYYMMDD-HHMMSS-1`
2. **Connection behavior**: After creation, which VM to connect to?
   - Option A: Connect to first VM
   - Option B: Don't connect, show list of created VMs
   - Option C: Ask user which to connect to
   - **Recommended: Option B (don't auto-connect)**
3. **Failure handling**: What if 2/5 VMs fail to provision?
   - Recommended: Continue creating others, report failures at end
4. **Resource limits**: Should there be a max pool size?
   - Recommended: Yes, cap at 20 to prevent accidents (overridable)
5. **Cost warning**: Should we warn about costs?
   - Recommended: Yes, show estimated cost before proceeding

#### Acceptance Criteria

- [ ] `azlin --pool 5` creates 5 VMs in parallel
- [ ] VMs named with sequential suffixes: `-1`, `-2`, `-3`, etc.
- [ ] All VMs share the same configuration (size, region, tools)
- [ ] Progress shown for each VM independently
- [ ] Failures don't block other VMs
- [ ] Summary shows: "Created 4/5 VMs successfully"
- [ ] No auto-connect (user must use `azlin list` then connect)
- [ ] Pool size validated (1-20, error if > 20 without --force)
- [ ] Cost estimate shown before proceeding (if possible)

#### Technical Approach

**Module**: Extend `vm_provisioner.py`

```python
def provision_pool(
    count: int,
    config: VMConfig,
    max_workers: int = 10
) -> List[VMInfo]:
    """Provision multiple VMs in parallel.

    Args:
        count: Number of VMs to create
        config: Base configuration for all VMs
        max_workers: Max parallel provisioning tasks

    Returns:
        List of successfully provisioned VMs
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(1, count + 1):
            vm_config = config.copy()
            vm_config.name = f"{config.name_prefix}-{timestamp}-{i}"
            futures.append(executor.submit(provision_vm, vm_config))

        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                vm_info = future.result()
                results.append(vm_info)
                print(f"✓ {vm_info.name} created")
            except Exception as e:
                print(f"✗ VM creation failed: {e}")

        return results
```

**Azure Considerations**:
- Azure has subscription-level quotas (cores, IPs, etc.)
- Parallel provisioning may hit rate limits
- Use exponential backoff for retries
- Consider using Azure Batch for > 10 VMs

#### Complexity: HIGH

- Parallel provisioning is complex
- Error handling for partial failures
- Resource quota management
- Progress display for multiple operations
- ~300 lines of code

#### Dependencies

- Feature 1 (Config Manager)
- v1.0 VM Provisioner (extend it)
- Azure quota checking (new)

---

### Feature 7: Remote Command Execution

**Status**: CLARIFIED

#### Requirements

1. `azlin -- <command>` syntax for remote execution
2. Execute command via SSH on VM
3. Open results in new terminal window

#### Ambiguities Identified - HIGH PRIORITY

1. **VM selection**: Which VM to run command on?
   - Option A: Use interactive menu (Feature 3)
   - Option B: Require `--name` flag
   - Option C: Run on all VMs (like Feature 5)
   - **Recommended: Option A (interactive) with Option B as override**

2. **New terminal window**: What does this mean?
   - Option A: Open new terminal tab/window and run command there
   - Option B: SSH in background, stream output to new terminal
   - Option C: Just execute via SSH and show output inline
   - **Platform differences**: macOS Terminal vs iTerm2 vs Linux Terminal
   - **NEEDS USER CLARIFICATION**

3. **Session persistence**: Should command run in tmux?
   - Recommended: Yes, for consistency with main workflow

4. **Output handling**: Stream output or wait for completion?
   - Recommended: Stream output in real-time

#### Acceptance Criteria (PROVISIONAL)

- [ ] `azlin -- ls -la` prompts for VM selection if multiple exist
- [ ] `azlin --name my-vm -- ls -la` runs on specific VM
- [ ] Command executes in tmux session on remote VM
- [ ] Output is streamed in real-time
- [ ] Exit code is preserved and returned
- [ ] SSH authentication uses existing azlin keys
- [ ] Command is properly escaped/quoted
- [ ] Works with complex commands: `azlin -- 'cd /app && npm test'`

#### Technical Approach

**Module**: Extend `remote_commands.py`

```python
def execute_remote_command(
    command: str,
    vm: VMInfo,
    in_tmux: bool = True
) -> CommandResult:
    """Execute command on remote VM via SSH.

    Args:
        command: Shell command to execute
        vm: Target VM information
        in_tmux: Whether to run in tmux session

    Returns:
        CommandResult with stdout, stderr, exit_code
    """
    ssh_cmd = [
        "ssh",
        "-i", str(SSH_KEY_PATH),
        "-o", "StrictHostKeyChecking=accept-new",
        f"azureuser@{vm.ip}",
    ]

    if in_tmux:
        # Run in tmux session, attach to see output
        remote_cmd = f"tmux send-keys '{command}' C-m"
        ssh_cmd.append(remote_cmd)
    else:
        # Run directly, get output
        ssh_cmd.append(command)

    result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.returncode
    )
```

**New Terminal Window** (if required):
```python
def open_in_new_terminal(command: str) -> None:
    """Open command in new terminal window (macOS)."""
    if sys.platform == "darwin":
        # macOS Terminal.app
        applescript = f'''
        tell application "Terminal"
            do script "{command}"
            activate
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript])
    elif sys.platform == "linux":
        # Linux - try common terminals
        for term in ["gnome-terminal", "konsole", "xterm"]:
            if shutil.which(term):
                subprocess.run([term, "--", "bash", "-c", command])
                break
    else:
        # Fallback: run inline
        subprocess.run(["bash", "-c", command])
```

#### Complexity: MEDIUM to HIGH

- **Without new terminal**: MEDIUM (~150 lines)
- **With new terminal**: HIGH (~300 lines, platform-specific code)

#### Dependencies

- Feature 2 (VM Manager) for VM selection
- Feature 3 (Interactive Selection) if multi-VM
- SSH keys from v1.0

#### RECOMMENDATION

**Request clarification on "new terminal window" requirement**. Suggest:
- **Phase 1**: Implement inline execution (simpler, cross-platform)
- **Phase 2**: Add terminal window support as optional enhancement

---

### Feature 8: Enhanced --help

**Status**: CLARIFIED

#### Requirements

1. Comprehensive help documentation
2. Examples for all commands
3. Clear usage patterns

#### Ambiguities Identified

None. This is straightforward.

#### Acceptance Criteria

- [ ] `azlin --help` shows all commands and flags
- [ ] Each command has a clear description
- [ ] At least 3 usage examples included
- [ ] Examples cover common workflows
- [ ] Help text is < 50 lines (readable on one screen)
- [ ] Subcommands have their own help: `azlin list --help`

#### Technical Approach

**Module**: Extend `cli.py` (Click framework handles this)

```python
@click.command()
@click.option('--name', help='Custom VM name (default: auto-generated)')
@click.option('--rg', '--resource-group', help='Azure resource group')
@click.option('--pool', type=int, help='Create N VMs in parallel')
@click.option('--repo', help='GitHub repository to clone')
@click.argument('command', nargs=-1, type=click.UNPROCESSED)
def main(name, rg, pool, repo, command):
    """azlin - One command to create Azure dev VMs.

    Examples:
        azlin                          # Create single VM, connect via SSH
        azlin --name my-dev-vm         # Create VM with custom name
        azlin --pool 5                 # Create 5 VMs in parallel
        azlin list                     # List all VMs
        azlin -- pytest                # Run command on remote VM
        azlin w                        # Run 'w' on all VMs
        azlin --rg my-group            # Use custom resource group

    For detailed help: azlin COMMAND --help
    """
    pass
```

**Subcommands**:
```python
@main.command()
@click.option('--json', is_flag=True, help='Output as JSON')
def list(json):
    """List all VMs in resource group."""
    pass

@main.command()
def w():
    """Run 'w' command on all VMs."""
    pass
```

#### Complexity: LOW

- Click framework does heavy lifting
- Just write good docstrings
- ~50 lines of documentation

#### Dependencies

- None (documentation task)

---

### Feature 9: Additional Feature Suggestions

**Status**: BRAINSTORMING

Based on the v2.0 features and azlin's philosophy, here are recommended additions:

#### 9.1: azlin stop [NAME]

**Purpose**: Stop VM(s) to save costs without deleting

**Rationale**: Users may want to pause work without losing VM state

**Acceptance Criteria**:
- `azlin stop` (interactive selection if multiple VMs)
- `azlin stop my-vm` (stop specific VM)
- `azlin stop --all` (stop all VMs)

**Complexity**: LOW (Azure CLI wrapper)

---

#### 9.2: azlin start [NAME]

**Purpose**: Restart a stopped VM

**Rationale**: Complement to `stop` command

**Acceptance Criteria**:
- `azlin start` (interactive selection)
- `azlin start my-vm` (start specific VM)
- Automatically reconnect via SSH after start

**Complexity**: LOW

---

#### 9.3: azlin destroy [NAME]

**Purpose**: Delete VM and associated resources

**Rationale**: Clean up is currently manual

**Acceptance Criteria**:
- `azlin destroy` (interactive selection with confirmation)
- `azlin destroy my-vm` (destroy specific VM with confirmation)
- `azlin destroy --all` (destroy all with confirmation)
- Show cost savings after deletion

**Complexity**: MEDIUM (must handle associated resources: NICs, disks, IPs)

---

#### 9.4: azlin connect [NAME]

**Purpose**: SSH into an existing VM

**Rationale**: Currently requires manual SSH

**Acceptance Criteria**:
- `azlin connect` (interactive selection)
- `azlin connect my-vm` (connect to specific VM)
- Use existing tmux session if present
- Handle stopped VMs (auto-start with prompt)

**Complexity**: LOW

---

#### 9.5: azlin status

**Purpose**: Show resource group summary and cost estimates

**Rationale**: Users need visibility into their Azure usage

**Acceptance Criteria**:
- Show total VMs (running, stopped)
- Show total cores/memory in use
- Estimate monthly cost
- Show Azure quota usage

**Complexity**: MEDIUM (requires Azure Cost Management API)

---

#### 9.6: azlin logs [NAME]

**Purpose**: View cloud-init logs and VM diagnostics

**Rationale**: Troubleshooting VM setup issues

**Acceptance Criteria**:
- `azlin logs` (interactive selection)
- `azlin logs my-vm` (specific VM)
- Show cloud-init status and logs
- Show recent syslog entries

**Complexity**: MEDIUM

---

#### 9.7: azlin ssh-config

**Purpose**: Generate SSH config entries for all VMs

**Rationale**: Integration with other SSH tools

**Acceptance Criteria**:
- `azlin ssh-config` outputs SSH config format
- `azlin ssh-config >> ~/.ssh/config` for easy integration
- Includes HostName, User, IdentityFile

**Complexity**: LOW

---

#### 9.8: azlin clone REPO [--to NAME]

**Purpose**: Clone a repo to existing VM

**Rationale**: User may want to add repos after creation

**Acceptance Criteria**:
- `azlin clone https://github.com/user/repo` (interactive VM selection)
- `azlin clone https://github.com/user/repo --to my-vm`
- Uses existing GitHub auth on VM

**Complexity**: LOW

---

## Dependency Matrix

```
Feature                     Depends On
------------------------------------------------------------
1. Config Storage           -
2. azlin list              1
3. Interactive Selection   1, 2
4. --name with Smart       (potentially 7)
5. azlin w                 1, 2
6. --pool                  1
7. Remote Command Exec     2, 3 (optional)
8. Enhanced --help         -
9.1. azlin stop            1, 2
9.2. azlin start           1, 2
9.3. azlin destroy         1, 2
9.4. azlin connect         1, 2, 3
9.5. azlin status          1, 2
9.6. azlin logs            1, 2
9.7. azlin ssh-config      1, 2
9.8. azlin clone           1, 2
```

**Critical Path**:
1. Config Storage (Foundation)
2. VM Manager (Foundation)
3. All other features

---

## Implementation Order

Based on dependencies, complexity, and user value, here's the recommended implementation order:

### Phase 1: Foundation (Week 1)

**Goal**: Enable multi-VM management

1. **Feature 1: Config Storage** (2 days)
   - Create config_manager.py
   - Write tests
   - Update CLI to use config

2. **Feature 2: azlin list** (2 days)
   - Create vm_manager.py
   - Implement list functionality
   - Write tests

3. **Feature 8: Enhanced --help** (1 day)
   - Update CLI docstrings
   - Add examples
   - Test help output

### Phase 2: User Experience (Week 2)

**Goal**: Improve UX for existing users

4. **Feature 3: Interactive Selection** (3 days)
   - Implement simple numbered menu (stdlib)
   - Integrate with list command
   - Write tests

5. **Feature 9.4: azlin connect** (1 day)
   - Reuse SSH connector
   - Add interactive selection
   - Write tests

6. **Feature 4: --name Flag** (1 day)
   - AFTER getting user clarification
   - Implement name generation
   - Add sanitization

### Phase 3: Advanced Features (Week 3)

**Goal**: Power user features

7. **Feature 9.1 & 9.2: stop/start** (2 days)
   - Simple Azure CLI wrappers
   - Add to vm_manager.py
   - Write tests

8. **Feature 9.3: azlin destroy** (2 days)
   - Careful implementation (destructive!)
   - Add confirmation prompts
   - Cleanup associated resources
   - Write tests

9. **Feature 5: azlin w** (1 day)
   - Create remote_commands.py
   - Implement parallel execution
   - Write tests

### Phase 4: Scaling Features (Week 4)

**Goal**: Handle multiple VMs efficiently

10. **Feature 7: Remote Command Execution** (3 days)
    - AFTER getting user clarification on terminal window
    - Extend remote_commands.py
    - Integrate with interactive selection
    - Write tests

11. **Feature 6: --pool Flag** (2 days)
    - Extend vm_provisioner.py
    - Add parallel provisioning
    - Add quota checking
    - Write tests

### Phase 5: Polish (Week 5)

**Goal**: Production-ready v2.0

12. **Feature 9.5-9.8: Additional commands** (3 days)
    - Implement based on user feedback
    - Prioritize most requested

13. **Integration Testing** (1 day)
    - Test all features together
    - Test failure modes
    - Test edge cases

14. **Documentation** (1 day)
    - Update README
    - Create USAGE_V2.md
    - Update ARCHITECTURE.md

---

## Risk Assessment

### High-Risk Items

#### 1. Feature 6: --pool Flag

**Risk**: Azure quota limits, rate limiting, cost overruns

**Mitigation**:
- Check quotas before provisioning
- Add cost warnings
- Cap at 20 VMs by default
- Implement exponential backoff for rate limits

**Contingency**:
- Provide clear error messages with resolution steps
- Fallback to sequential provisioning if parallel fails

---

#### 2. Feature 4: Command Tracking

**Risk**: Unclear requirements, potential over-engineering

**Mitigation**:
- Get explicit clarification before implementing
- Start with simplest interpretation
- Make command tracking optional/additive

**Contingency**:
- Implement basic auto-naming only
- Defer command tracking to v2.1

---

#### 3. Feature 7: New Terminal Window

**Risk**: Platform-specific code, maintenance burden

**Mitigation**:
- Clarify if actually needed
- Start with inline execution
- Add terminal window as optional enhancement

**Contingency**:
- Document platform limitations
- Provide manual workarounds

---

### Medium-Risk Items

#### 4. Config File Corruption

**Risk**: Users manually edit config, breaking functionality

**Mitigation**:
- Validate config on load
- Provide clear error messages
- Auto-repair common issues
- Fallback to defaults

---

#### 5. Concurrent Modifications

**Risk**: Multiple azlin instances modifying same config

**Mitigation**:
- Use file locking (fcntl on Unix)
- Atomic writes with temp file + rename
- Read config fresh each time

---

### Low-Risk Items

Most other features are low-risk because they:
- Use proven patterns from v1.0
- Leverage existing Azure CLI
- Have clear requirements
- Are easily testable

---

## Technical Architecture

### New Modules (Bricks)

```
src/azlin/modules/
    config_manager.py       # Brick 10 - Config storage
    vm_manager.py           # Brick 11 - VM lifecycle
    remote_commands.py      # Brick 12 - Remote execution
```

### Updated Modules

```
src/azlin/
    cli.py                  # Update orchestrator for new commands
    vm_provisioner.py       # Add pool support, name generation
```

### Configuration Schema

```json
{
  "version": "2.0",
  "resource_group": "azlin-vms",
  "default_region": "eastus",
  "default_vm_size": "Standard_B2s",
  "sessions": [
    {
      "vm_name": "azlin-20251009-143020",
      "ip": "20.10.30.40",
      "created": "2025-10-09T14:30:20Z",
      "last_connected": "2025-10-09T15:45:10Z",
      "status": "running"
    }
  ]
}
```

### CLI Command Structure

```
azlin                           # Create VM or show interactive menu
azlin --name NAME               # Create VM with custom name
azlin --pool N                  # Create N VMs
azlin --rg NAME                 # Use custom resource group
azlin -- COMMAND                # Execute command on VM

azlin list                      # List all VMs
azlin list --json               # List as JSON

azlin connect [NAME]            # Connect to VM
azlin stop [NAME]               # Stop VM
azlin start [NAME]              # Start VM
azlin destroy [NAME]            # Delete VM

azlin w                         # Run 'w' on all VMs
azlin status                    # Show resource group status
azlin logs [NAME]               # View VM logs
azlin ssh-config                # Generate SSH config
azlin clone REPO [--to NAME]    # Clone repo to VM

azlin --help                    # Show help
azlin COMMAND --help            # Command-specific help
```

---

## Security Considerations

### Config File Security

- **Location**: `~/.azlin/config.json`
- **Permissions**:
  - Directory: 0700 (drwx------)
  - File: 0600 (-rw-------)
- **Content**: No credentials, only resource names and metadata

### Remote Command Execution

- **Input sanitization**: Validate commands before execution
- **SSH key reuse**: Use existing azlin_key from v1.0
- **No credential passing**: All auth delegated to SSH agent

### Pool Provisioning

- **Quota checking**: Verify before creating multiple VMs
- **Cost warnings**: Show estimated costs
- **Failure isolation**: One VM failure doesn't expose credentials

---

## Testing Strategy

### Unit Tests (60%)

- Config manager: load, save, validation, permissions
- VM manager: list, filter, format
- Remote commands: execution, error handling, output formatting
- Name generation: sanitization, collision detection

### Integration Tests (30%)

- Config + VM manager integration
- Interactive selection + connect
- Pool provisioning coordination
- Remote command + VM selection

### E2E Tests (10%)

- Full workflow with real Azure VMs
- Pool creation and management
- Multi-VM command execution
- Cost: ~$5 per test run

---

## Questions for User

Before proceeding with implementation, please clarify:

### High Priority

1. **Feature 4 - Command Tracking**:
   - What does "running commands" mean in the context of auto-generated names?
   - Should we track commands actively or just at creation time?
   - Suggested default: Only include commands passed via `azlin -- <cmd>` syntax

2. **Feature 7 - New Terminal Window**:
   - Is opening a new terminal window actually required?
   - Which platforms must be supported? (macOS/Linux/Windows)
   - Suggested default: Execute inline with real-time output

### Medium Priority

3. **Feature 6 - Pool Size Limit**:
   - What's an acceptable default max pool size? (Suggested: 20)
   - Should we show cost estimates before creating pools?

4. **Feature 3 - Auto-connect**:
   - If only one VM exists, should we skip the menu and auto-connect?
   - Or always show menu for consistency?

### Low Priority

5. **Additional Features**:
   - Which of the suggested features (9.1-9.8) are highest priority?
   - Any other features to consider?

---

## Estimated Timeline

**Total Duration**: 5 weeks (one developer, full-time)

- **Week 1**: Foundation (Config, List, Help)
- **Week 2**: UX (Interactive, Connect, Names)
- **Week 3**: Advanced (Stop/Start, Destroy, W command)
- **Week 4**: Scaling (Remote commands, Pool)
- **Week 5**: Polish (Additional features, testing, docs)

**Parallel Development**: With 2 developers, could complete in 3 weeks

**Minimal Viable v2.0**: Features 1, 2, 3, 8 could ship in 1 week

---

## Recommendation

### Immediate Next Steps

1. **Get clarifications** on Features 4 and 7
2. **Implement Phase 1** (Config Storage + List command)
3. **User testing** after Phase 2 (Interactive Selection)
4. **Iterate** based on feedback before Phase 3

### Philosophy Check

All proposed features align with azlin's philosophy:
- Simple, clear purpose
- Security-first (no credentials in code)
- Standard library where possible
- Fail fast with clear errors

The v2.0 features transform azlin from a **VM creator** into a **VM session manager** while maintaining ruthless simplicity.

---

## Appendix A: Module Specifications

See individual module specs for detailed implementation guidance:
- `specs/MODULE_SPEC_CONFIG_MANAGER.md`
- `specs/MODULE_SPEC_VM_MANAGER.md`
- `specs/MODULE_SPEC_REMOTE_COMMANDS.md`

(To be created after this requirements doc is approved)

---

**Document Status**: Ready for Review
**Next Action**: User clarification on ambiguities
**Approval Required**: Product Owner / User
