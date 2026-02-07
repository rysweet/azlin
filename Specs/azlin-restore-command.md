# Module Specification: azlin restore Command

## Purpose

Restore ALL active azlin sessions from `azlin list` by launching new terminal windows with SSH connections. Smart terminal detection provides platform-specific defaults (macOS Terminal, WSL Windows Terminal, Windows wt.exe) with user configuration support.

## Philosophy

- **Single Responsibility**: Restore sessions, nothing else
- **Standard Library**: Use existing modules (terminal_launcher, vm_manager, config_manager)
- **Self-Contained**: All restore logic in one module with clear public API
- **Zero-BS**: Every function works or doesn't exist - no stubs or placeholders

## EXPLICIT User Requirements (MUST PRESERVE)

1. ✅ **ALL sessions from azlin list** - Restore every session, not a subset
2. ✅ **Smart terminal defaults** - macOS=Terminal, WSL=/mnt/c/Users/$USER/.../wt.exe, Windows=wt.exe
3. ✅ **User configurable via ~/.azlin/config.toml** - Must allow customization
4. ✅ **Multi-tab Windows Terminal support** - Windows Terminal can open multiple tabs in single window
5. ✅ **Integration with existing connect** - Use `azlin connect -y <hostname> --tmux-session <name>` pattern

## Module: `azlin/commands/restore.py`

### Public API (the "studs")

```python
"""azlin restore command - Restore ALL active sessions.

Philosophy:
- Single responsibility (restore sessions)
- Standard library + existing azlin modules
- Self-contained and regeneratable
- Zero-BS implementation (no stubs/placeholders)

Public API:
    restore_command: Click command for CLI
    RestoreSessionConfig: Configuration dataclass
    PlatformDetector: Platform detection utility
    TerminalLauncher: Terminal launcher abstraction
"""

__all__ = [
    "restore_command",
    "RestoreSessionConfig",
    "PlatformDetector",
    "TerminalLauncher"
]
```

### Contract

**Inputs:**
- `resource_group` (optional str): Filter to specific resource group
- `config_path` (optional str): Custom config file path
- `terminal` (optional str): Override terminal launcher
- `dry_run` (bool): Show what would happen without executing

**Outputs:**
- Success: Print summary of restored sessions
- Failure: Print error messages with actionable guidance
- Exit code: 0 on success, 1 on partial failure, 2 on total failure

**Side Effects:**
- Reads from `~/.azlin/config.toml`
- Calls `azlin list` to get running VMs
- Launches terminal windows via `terminal_launcher`
- Creates SSH connections to VMs

### Dependencies

**Required Modules:**
- `azlin.vm_manager.VMManager` - List VMs and get VM details
- `azlin.config_manager.ConfigManager` - Load config and session names
- `azlin.terminal_launcher.TerminalLauncher` - Launch terminal windows
- Standard library: `pathlib`, `subprocess`, `platform`, `sys`, `dataclasses`

**External Tools:**
- Platform-specific terminals (Terminal.app, wt.exe, etc.)
- SSH client
- Azure CLI (via vm_manager)

## Design

### 1. New Command Module Structure

```
azlin/commands/
├── __init__.py
└── restore.py    # New module for restore command
```

### 2. Platform Detection System

```python
from dataclasses import dataclass
from enum import Enum
import platform
import subprocess
from pathlib import Path

class TerminalType(Enum):
    """Terminal application types."""
    MACOS_TERMINAL = "macos_terminal"      # Terminal.app
    WINDOWS_TERMINAL = "windows_terminal"  # wt.exe
    LINUX_GNOME = "linux_gnome"           # gnome-terminal
    LINUX_XTERM = "linux_xterm"            # xterm
    UNKNOWN = "unknown"

class PlatformDetector:
    """Detect platform and available terminals."""

    @classmethod
    def detect_platform(cls) -> str:
        """Detect operating platform.

        Returns:
            "macos", "wsl", "windows", or "linux"
        """
        system = platform.system()

        if system == "Darwin":
            return "macos"
        elif system == "Windows":
            return "windows"
        elif system == "Linux":
            # Check if WSL
            if cls._is_wsl():
                return "wsl"
            return "linux"
        return "unknown"

    @classmethod
    def _is_wsl(cls) -> bool:
        """Check if running in WSL."""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except Exception:
            return False

    @classmethod
    def get_default_terminal(cls) -> TerminalType:
        """Get default terminal for current platform.

        Returns:
            TerminalType enum value
        """
        platform_name = cls.detect_platform()

        if platform_name == "macos":
            return TerminalType.MACOS_TERMINAL
        elif platform_name in ("wsl", "windows"):
            return TerminalType.WINDOWS_TERMINAL
        elif platform_name == "linux":
            # Prefer gnome-terminal, fallback to xterm
            if cls._has_command("gnome-terminal"):
                return TerminalType.LINUX_GNOME
            elif cls._has_command("xterm"):
                return TerminalType.LINUX_XTERM

        return TerminalType.UNKNOWN

    @classmethod
    def get_windows_terminal_path(cls) -> Path | None:
        """Get Windows Terminal path for WSL.

        Returns:
            Path to wt.exe or None if not found
        """
        if cls.detect_platform() != "wsl":
            return None

        # Try common paths
        windows_user = cls._get_windows_username()
        if windows_user:
            paths = [
                Path(f"/mnt/c/Users/{windows_user}/AppData/Local/Microsoft/WindowsApps/wt.exe"),
                Path(f"/mnt/c/Program Files/WindowsApps/Microsoft.WindowsTerminal*/wt.exe"),
            ]

            for path_pattern in paths:
                # Handle wildcards
                if "*" in str(path_pattern):
                    # Use glob to find matching paths
                    import glob
                    matches = glob.glob(str(path_pattern))
                    if matches:
                        return Path(matches[0])
                elif path_pattern.exists():
                    return path_pattern

        return None

    @classmethod
    def _get_windows_username(cls) -> str | None:
        """Get Windows username in WSL."""
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "echo", "%USERNAME%"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @classmethod
    def _has_command(cls, command: str) -> bool:
        """Check if command is available."""
        try:
            subprocess.run(
                ["which", command],
                capture_output=True,
                timeout=5,
                check=True
            )
            return True
        except Exception:
            return False
```

### 3. Terminal Launcher Abstraction

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class RestoreSessionConfig:
    """Configuration for restoring a session."""
    vm_name: str
    hostname: str
    username: str
    ssh_key_path: Path
    tmux_session: str = "azlin"
    terminal_type: TerminalType = TerminalType.UNKNOWN

class TerminalLauncher:
    """Launch terminals for session restoration."""

    @classmethod
    def launch_session(cls, config: RestoreSessionConfig) -> bool:
        """Launch terminal window for session.

        Args:
            config: Session configuration

        Returns:
            True if successful, False otherwise
        """
        if config.terminal_type == TerminalType.MACOS_TERMINAL:
            return cls._launch_macos_terminal(config)
        elif config.terminal_type == TerminalType.WINDOWS_TERMINAL:
            return cls._launch_windows_terminal(config)
        elif config.terminal_type == TerminalType.LINUX_GNOME:
            return cls._launch_gnome_terminal(config)
        elif config.terminal_type == TerminalType.LINUX_XTERM:
            return cls._launch_xterm(config)
        else:
            print(f"Unsupported terminal type: {config.terminal_type}")
            return False

    @classmethod
    def launch_all_sessions(
        cls,
        sessions: list[RestoreSessionConfig],
        multi_tab: bool = False
    ) -> tuple[int, int]:
        """Launch multiple sessions.

        Args:
            sessions: List of session configurations
            multi_tab: Use multi-tab mode if supported (Windows Terminal)

        Returns:
            Tuple of (successful_count, failed_count)
        """
        if not sessions:
            return 0, 0

        # Windows Terminal multi-tab support
        if multi_tab and sessions[0].terminal_type == TerminalType.WINDOWS_TERMINAL:
            return cls._launch_windows_terminal_multi_tab(sessions)

        # Launch individual windows
        success_count = 0
        failed_count = 0

        for session_config in sessions:
            if cls.launch_session(session_config):
                success_count += 1
            else:
                failed_count += 1

        return success_count, failed_count

    @classmethod
    def _launch_macos_terminal(cls, config: RestoreSessionConfig) -> bool:
        """Launch macOS Terminal.app."""
        from azlin.terminal_launcher import TerminalLauncher as AzlinTerminalLauncher
        from azlin.terminal_launcher import TerminalConfig

        terminal_config = TerminalConfig(
            ssh_host=config.hostname,
            ssh_user=config.username,
            ssh_key_path=config.ssh_key_path,
            tmux_session=config.tmux_session,
            title=f"azlin - {config.vm_name}"
        )

        return AzlinTerminalLauncher.launch(terminal_config, fallback_inline=False)

    @classmethod
    def _launch_windows_terminal(cls, config: RestoreSessionConfig) -> bool:
        """Launch Windows Terminal (single window)."""
        wt_path = PlatformDetector.get_windows_terminal_path()
        if not wt_path:
            print("Windows Terminal (wt.exe) not found")
            return False

        # Build SSH command
        ssh_cmd = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-i {config.ssh_key_path} "
            f"-t {config.username}@{config.hostname} "
            f"'tmux attach-session -t {config.tmux_session} || "
            f"tmux new-session -s {config.tmux_session}'"
        )

        try:
            subprocess.Popen(
                [str(wt_path), "--title", f"azlin - {config.vm_name}", "wsl", "-e", "bash", "-c", ssh_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception as e:
            print(f"Failed to launch Windows Terminal: {e}")
            return False

    @classmethod
    def _launch_windows_terminal_multi_tab(
        cls,
        sessions: list[RestoreSessionConfig]
    ) -> tuple[int, int]:
        """Launch Windows Terminal with multiple tabs."""
        wt_path = PlatformDetector.get_windows_terminal_path()
        if not wt_path:
            print("Windows Terminal (wt.exe) not found")
            return 0, len(sessions)

        # Build multi-tab command
        # wt -w 0 new-tab --title "Tab1" cmd1 ; new-tab --title "Tab2" cmd2
        wt_args = [str(wt_path), "-w", "0"]  # -w 0 = use existing window or create new

        for i, config in enumerate(sessions):
            ssh_cmd = (
                f"ssh -o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"-i {config.ssh_key_path} "
                f"-t {config.username}@{config.hostname} "
                f"'tmux attach-session -t {config.tmux_session} || "
                f"tmux new-session -s {config.tmux_session}'"
            )

            if i == 0:
                # First tab
                wt_args.extend(["new-tab", "--title", f"azlin - {config.vm_name}"])
            else:
                # Subsequent tabs
                wt_args.extend([";", "new-tab", "--title", f"azlin - {config.vm_name}"])

            wt_args.extend(["wsl", "-e", "bash", "-c", ssh_cmd])

        try:
            subprocess.Popen(
                wt_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return len(sessions), 0
        except Exception as e:
            print(f"Failed to launch Windows Terminal multi-tab: {e}")
            return 0, len(sessions)

    @classmethod
    def _launch_gnome_terminal(cls, config: RestoreSessionConfig) -> bool:
        """Launch gnome-terminal."""
        from azlin.terminal_launcher import TerminalLauncher as AzlinTerminalLauncher
        from azlin.terminal_launcher import TerminalConfig

        terminal_config = TerminalConfig(
            ssh_host=config.hostname,
            ssh_user=config.username,
            ssh_key_path=config.ssh_key_path,
            tmux_session=config.tmux_session,
            title=f"azlin - {config.vm_name}"
        )

        return AzlinTerminalLauncher.launch(terminal_config, fallback_inline=False)

    @classmethod
    def _launch_xterm(cls, config: RestoreSessionConfig) -> bool:
        """Launch xterm."""
        from azlin.terminal_launcher import TerminalLauncher as AzlinTerminalLauncher
        from azlin.terminal_launcher import TerminalConfig

        terminal_config = TerminalConfig(
            ssh_host=config.hostname,
            ssh_user=config.username,
            ssh_key_path=config.ssh_key_path,
            tmux_session=config.tmux_session,
            title=f"azlin - {config.vm_name}"
        )

        return AzlinTerminalLauncher.launch(terminal_config, fallback_inline=False)
```

### 4. Config Schema Extension

Add to `azlin/config_manager.py`:

```python
@dataclass
class AzlinConfig:
    """Azlin configuration data."""

    # ... existing fields ...

    # Terminal restore settings
    terminal_launcher: str | None = None  # Override terminal launcher
    terminal_multi_tab: bool = True       # Use multi-tab mode (Windows Terminal)
    restore_timeout: int = 30             # Timeout per session (seconds)
```

### 5. Integration Points with Existing Code

**With `vm_manager.py`:**
```python
# Get running VMs
vms = VMManager.list_vms(resource_group, include_stopped=False)

# Get VM details
vm_info = VMManager.get_vm(vm_name, resource_group)
```

**With `config_manager.py`:**
```python
# Load config
config = ConfigManager.load_config()

# Get session name
session_name = ConfigManager.get_session_name(vm_name)

# Get terminal launcher override
terminal_launcher = config.terminal_launcher
```

**With `terminal_launcher.py`:**
```python
# Use existing TerminalConfig and TerminalLauncher
from azlin.terminal_launcher import TerminalConfig, TerminalLauncher

terminal_config = TerminalConfig(
    ssh_host=vm_info.public_ip,
    ssh_user="azureuser",
    ssh_key_path=Path("~/.ssh/id_rsa").expanduser(),
    tmux_session=session_name or "azlin"
)

success = TerminalLauncher.launch(terminal_config)
```

### 6. Error Handling Strategy

```python
class RestoreError(Exception):
    """Base exception for restore command."""
    pass

class NoVMsFoundError(RestoreError):
    """No running VMs found."""
    pass

class TerminalLaunchError(RestoreError):
    """Terminal launch failed."""
    pass

class ConfigError(RestoreError):
    """Configuration error."""
    pass

# Error handling pattern
def restore_sessions():
    try:
        # Get VMs
        vms = VMManager.list_vms(resource_group, include_stopped=False)
        if not vms:
            raise NoVMsFoundError("No running VMs found in resource group")

        # Launch sessions
        success_count, failed_count = TerminalLauncher.launch_all_sessions(sessions)

        if failed_count > 0:
            print(f"Warning: {failed_count} sessions failed to launch")
            return 1  # Partial failure

        print(f"Successfully restored {success_count} sessions")
        return 0  # Success

    except NoVMsFoundError as e:
        print(f"Error: {e}")
        print("Run 'azlin list' to see available VMs")
        return 2  # Total failure

    except TerminalLaunchError as e:
        print(f"Error launching terminals: {e}")
        print("Check terminal configuration in ~/.azlin/config.toml")
        return 2

    except Exception as e:
        print(f"Unexpected error: {e}")
        return 2
```

### 7. Testing Approach

**Test Strategy (60% unit, 30% integration, 10% E2E):**

```python
# Unit Tests (60%)
def test_platform_detection_macos():
    """Test macOS platform detection."""
    with patch("platform.system", return_value="Darwin"):
        assert PlatformDetector.detect_platform() == "macos"

def test_platform_detection_wsl():
    """Test WSL detection."""
    with patch("platform.system", return_value="Linux"):
        with patch("builtins.open", mock_open(read_data="microsoft")):
            assert PlatformDetector.detect_platform() == "wsl"

def test_default_terminal_macos():
    """Test default terminal for macOS."""
    with patch.object(PlatformDetector, "detect_platform", return_value="macos"):
        assert PlatformDetector.get_default_terminal() == TerminalType.MACOS_TERMINAL

# Integration Tests (30%)
def test_restore_session_config_creation():
    """Test creating restore session config."""
    config = RestoreSessionConfig(
        vm_name="test-vm",
        hostname="192.168.1.1",
        username="azureuser",
        ssh_key_path=Path("/tmp/key"),
        tmux_session="test"
    )
    assert config.vm_name == "test-vm"
    assert config.tmux_session == "test"

def test_terminal_launcher_with_mock():
    """Test terminal launcher with mocked subprocess."""
    with patch("subprocess.Popen") as mock_popen:
        config = RestoreSessionConfig(
            vm_name="test-vm",
            hostname="192.168.1.1",
            username="azureuser",
            ssh_key_path=Path("/tmp/key"),
            terminal_type=TerminalType.MACOS_TERMINAL
        )

        # Mock success
        mock_popen.return_value.returncode = 0
        result = TerminalLauncher.launch_session(config)
        assert result is True

# E2E Tests (10%)
def test_restore_command_dry_run(tmp_path):
    """Test restore command in dry-run mode."""
    # Create test config
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
default_resource_group = "test-rg"
""")

    # Run restore with dry-run
    with patch.object(VMManager, "list_vms") as mock_list:
        mock_list.return_value = [
            VMInfo(
                name="test-vm",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
                public_ip="192.168.1.1"
            )
        ]

        # Test dry-run mode
        result = restore_command_impl(
            resource_group="test-rg",
            config_path=str(config_file),
            dry_run=True
        )

        assert result == 0
        # Verify no terminals were launched
```

## Implementation Notes

### Key Design Decisions

1. **Platform Detection**: Auto-detect platform at runtime rather than install-time to support portability
2. **Terminal Abstraction**: Use existing `terminal_launcher` module as foundation, extend for multi-tab support
3. **Config Extension**: Add terminal-specific settings to existing `AzlinConfig` dataclass
4. **Error Handling**: Use exception hierarchy for different failure modes with actionable error messages
5. **Multi-tab Support**: Windows Terminal gets special multi-tab mode for efficiency

### Trade-offs

**Chosen: Extend existing `terminal_launcher` module**
- Pro: Reuses existing code, maintains consistency
- Pro: Leverages existing security validation and error handling
- Con: Module grows slightly in scope

**Alternative: Create new `session_restore` module**
- Pro: Clear separation of concerns
- Con: Duplicates terminal launch logic
- Con: More complexity to maintain

**Decision**: Extend existing module - aligns with "Zero-BS" principle (don't create duplicates).

### Windows Terminal Multi-Tab Implementation

Windows Terminal supports multi-tab via command-line arguments:
```bash
wt -w 0 new-tab --title "Tab1" cmd1 ; new-tab --title "Tab2" cmd2
```

This creates all tabs in a single window, which is more efficient than multiple windows.

### SSH Key Path Resolution

Assumptions:
1. SSH key path is consistent across all VMs (typically `~/.ssh/id_rsa`)
2. If custom key path needed, user can set in config
3. Fallback to default if not specified

### Session Name Resolution

Follow existing pattern:
1. Check config for session name mapping (vm_name -> session_name)
2. Fallback to "azlin" default
3. Use session name for tmux attachment

## Test Requirements

### Unit Tests (60%)
- Platform detection (macOS, WSL, Windows, Linux)
- Default terminal selection
- Windows Terminal path resolution
- Session config creation
- Error handling for each exception type

### Integration Tests (30%)
- Terminal launcher with mocked subprocess
- Config loading and session name resolution
- VM listing integration
- Multi-tab command building

### E2E Tests (10%)
- Dry-run mode end-to-end
- Single session restore (mocked terminal)
- Multi-session restore with failure handling
- Config file integration

### Test Coverage Goals
- Line coverage: >80%
- Branch coverage: >70%
- All error paths tested
- Platform-specific code paths tested via mocking

## CLI Interface

```bash
# Restore all sessions
azlin restore

# Restore sessions from specific resource group
azlin restore --resource-group my-rg

# Dry-run mode (show what would happen)
azlin restore --dry-run

# Override terminal launcher
azlin restore --terminal windows_terminal

# Disable multi-tab mode
azlin restore --no-multi-tab

# Custom config path
azlin restore --config ~/.azlin/custom-config.toml
```

## Configuration Examples

### ~/.azlin/config.toml

```toml
# Default settings
default_resource_group = "azlin-dev"

# Terminal restore settings
terminal_launcher = "macos_terminal"  # Override auto-detection
terminal_multi_tab = true              # Use multi-tab mode (Windows Terminal)
restore_timeout = 30                   # Timeout per session (seconds)

# Session name mappings
[session_names]
"azlin-vm-1" = "dev"
"azlin-vm-2" = "test"
"azlin-vm-3" = "prod"
```

## Success Criteria

1. ✅ Command restores ALL active sessions from `azlin list`
2. ✅ Smart terminal defaults work on macOS, WSL, and Windows
3. ✅ User can override terminal via config
4. ✅ Multi-tab mode works for Windows Terminal
5. ✅ Integration with existing `azlin connect` pattern
6. ✅ Clear error messages for all failure modes
7. ✅ Dry-run mode shows what would happen
8. ✅ >80% test coverage with unit/integration/E2E split

## Implementation Order

1. Platform detection system
2. Terminal launcher abstraction
3. Config schema extension
4. Integration with vm_manager
5. CLI command implementation
6. Error handling
7. Tests (unit → integration → E2E)
8. Documentation

## Module Regeneration

This module can be rebuilt from this specification because:
1. Clear input/output contract
2. Explicit dependencies on existing modules
3. Platform detection algorithm specified
4. Terminal launch patterns defined
5. Error handling strategy documented
6. Test requirements enumerated

Any AI agent given this spec should be able to regenerate functionally equivalent code.
