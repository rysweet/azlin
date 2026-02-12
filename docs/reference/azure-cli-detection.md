# Technical Reference: Azure CLI Detection

**Audience**: Developers
**Type**: API Reference

## Overview

The Azure CLI detection system consists of three core modules that work together to detect WSL2 + Windows CLI issues and fix them automatically.

## Module: `cli_detector.py`

### Purpose

Detects the runtime environment (WSL2, native Linux, Windows) and identifies Azure CLI installation type (Windows or Linux).

### Public API

#### `EnvironmentInfo`

Data class containing detection results:

```python
@dataclass
class EnvironmentInfo:
    environment: Environment        # WSL2, LINUX_NATIVE, WINDOWS, UNKNOWN
    cli_type: CLIType              # WINDOWS, LINUX, NONE
    cli_path: Optional[Path]       # Path to az command
    has_problem: bool              # True if WSL2 + Windows CLI
    problem_description: Optional[str]  # Human-readable problem description
```

#### `CLIDetector`

Main detection class:

```python
class CLIDetector:
    def detect() -> EnvironmentInfo:
        """
        Perform complete detection of environment and CLI.

        Returns:
            EnvironmentInfo with all detection results
        """

    def get_linux_cli_path() -> Optional[Path]:
        """
        Get explicit path to Linux Azure CLI if installed.

        Returns:
            Path to Linux CLI binary, or None if not found
        """
```

### Detection Logic

**Environment Detection**:

1. Check `platform.system()` for OS type
2. If Linux, check for WSL2 indicators:
   - `/proc/version` contains "microsoft" or "wsl2"
   - `/run/WSL` directory exists
   - `WSL_DISTRO_NAME` or `WSL_INTEROP` environment variables present

**CLI Detection**:

1. Use `shutil.which("az")` to find az command
2. Check if path indicates Windows installation:
   - Starts with `/mnt/c/` or `/mnt/d/`
   - Contains "Program Files" (case-insensitive)
   - Has `.exe` extension

**Problem Detection**:

- Problem exists if: `environment == WSL2` AND `cli_type == WINDOWS`

### Usage Example

```python
from azlin.modules.cli_detector import CLIDetector

# Detect environment and CLI
detector = CLIDetector()
env_info = detector.detect()

if env_info.has_problem:
    print(f"Problem detected: {env_info.problem_description}")
    print(f"Windows CLI at: {env_info.cli_path}")

    # Check if Linux CLI is available
    linux_cli = detector.get_linux_cli_path()
    if linux_cli:
        print(f"Linux CLI available at: {linux_cli}")
    else:
        print("Linux CLI not installed")
```

## Module: `cli_installer.py`

### Purpose

Handles interactive installation of Linux Azure CLI in WSL2.

### Public API

#### `InstallResult`

Data class containing installation outcome:

```python
@dataclass
class InstallResult:
    status: InstallStatus          # SUCCESS, CANCELLED, FAILED, ALREADY_INSTALLED
    cli_path: Optional[Path]       # Path to installed CLI (if successful)
    error_message: Optional[str]   # Error details (if failed)
```

#### `CLIInstaller`

Installation orchestrator:

```python
class CLIInstaller:
    def prompt_install() -> bool:
        """
        Prompt user for installation consent.

        Returns:
            True if user consents, False otherwise
        """

    def install() -> InstallResult:
        """
        Execute Linux Azure CLI installation.

        Returns:
            InstallResult with installation outcome
        """
```

### Installation Flow

1. **Check Existing Installation**:
   - Query `CLIDetector.get_linux_cli_path()`
   - If found, return `ALREADY_INSTALLED`

2. **Prompt User**:
   - Display problem explanation
   - Show installation details (URL, requirements, time)
   - Get user consent (y/N)

3. **Download Script**:
   - `curl -sL https://aka.ms/InstallAzureCLIDeb`
   - Timeout: 300 seconds (5 minutes)

4. **Execute Installation**:
   - `sudo bash -c <script>`
   - User prompted for sudo password
   - Timeout: 300 seconds

5. **Verify Installation**:
   - Check `get_linux_cli_path()` again
   - Return `SUCCESS` or `FAILED`

### Usage Example

```python
from azlin.modules.cli_installer import CLIInstaller

installer = CLIInstaller()

# Execute installation (prompts user)
result = installer.install()

if result.status.value == "success":
    print(f"Installed at: {result.cli_path}")
elif result.status.value == "cancelled":
    print("User cancelled installation")
else:
    print(f"Installation failed: {result.error_message}")
```

## Module: `subprocess_helper.py`

### Purpose

Executes subprocesses with deadlock prevention through pipe draining.

### Public API

#### `SubprocessResult`

Data class containing execution result:

```python
@dataclass
class SubprocessResult:
    returncode: int         # Process exit code
    stdout: str            # Captured stdout
    stderr: str            # Captured stderr
    timed_out: bool        # True if timeout occurred
```

#### `safe_run()`

Execute subprocess safely:

```python
def safe_run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    timeout: Optional[int] = 30,
    env: Optional[dict] = None
) -> SubprocessResult:
    """
    Execute subprocess with pipe deadlock prevention.

    Uses background threads to drain stdout/stderr pipes,
    preventing buffer overflow that causes deadlocks.

    Args:
        cmd: Command and arguments
        cwd: Working directory
        timeout: Timeout in seconds (None = no timeout)
        env: Environment variables

    Returns:
        SubprocessResult with output and exit code
    """
```

### Deadlock Prevention

**Problem**: Azure CLI commands write continuous output. If stdout/stderr pipes aren't drained, the 64KB buffer fills up and the process blocks.

**Solution**:

1. **Spawn Process**: Create `subprocess.Popen` with `PIPE` for stdout/stderr
2. **Start Drain Threads**: Background threads continuously read from pipes
3. **Wait for Process**: Call `process.wait(timeout=timeout)`
4. **Collect Output**: Gather drained output from queues
5. **Return Result**: Exit code + captured output

### Usage Example

```python
from azlin.modules.subprocess_helper import safe_run

# Execute Azure CLI command
result = safe_run(
    cmd=["az", "network", "bastion", "tunnel", "--name", "my-bastion"],
    timeout=None  # No timeout for long-running tunnel
)

if result.timed_out:
    print("Command timed out")
elif result.returncode != 0:
    print(f"Command failed: {result.stderr}")
else:
    print("Command succeeded")
    # Tunnel is running, result.stdout has output
```

## Integration Points

### Startup Hook (`cli.py`)

```python
def startup_checks():
    """Perform startup environment checks."""
    from .modules.cli_detector import CLIDetector
    from .modules.cli_installer import CLIInstaller

    detector = CLIDetector()
    env_info = detector.detect()

    if env_info.has_problem:
        print(f"\n⚠️  {env_info.problem_description}\n")

        installer = CLIInstaller()
        result = installer.install()

        if result.status.value == "success":
            print("\n✓ Azure CLI fixed! Continuing...\n")
        elif result.status.value == "cancelled":
            print("\n⚠️  Installation cancelled.\n")
        else:
            print(f"\n❌ Installation failed: {result.error_message}\n")

def main():
    """Main CLI entry point."""
    startup_checks()  # Add before argument parsing
    # ... rest of CLI logic ...
```

### Bastion Manager (`bastion_manager.py`)

```python
from ..modules.subprocess_helper import safe_run
from ..modules.cli_detector import CLIDetector

class BastionManager:
    def __init__(self):
        self._cli_path = self._get_cli_path()

    def _get_cli_path(self) -> str:
        """Get explicit path to Azure CLI."""
        detector = CLIDetector()
        env_info = detector.detect()

        if env_info.environment.value == "wsl2":
            linux_cli = detector.get_linux_cli_path()
            if linux_cli:
                return str(linux_cli)

        return "az"  # Fallback to PATH

    def create_tunnel(self, ...):
        """Create bastion tunnel using safe subprocess execution."""
        cmd = [self._cli_path, "network", "bastion", "tunnel", ...]

        result = safe_run(cmd, timeout=None)

        if result.timed_out or result.returncode != 0:
            return False

        return True
```

## Error Codes

### CLI Detector

- No exceptions raised, always returns `EnvironmentInfo`

### CLI Installer

Returns `InstallResult` with status:

- `SUCCESS`: Installation completed successfully
- `CANCELLED`: User chose not to install
- `FAILED`: Installation failed (see `error_message`)
- `ALREADY_INSTALLED`: Linux CLI already present

### Subprocess Helper

Returns `SubprocessResult` with:

- `returncode == 0`: Success
- `returncode == 127`: Command not found
- `returncode == -1`: Timeout occurred
- `returncode > 0`: Command failed
- `timed_out == True`: Timeout flag

## Testing

See test files in `tests/` directory:

- `test_cli_detector.py`: Unit tests for detection logic
- `test_cli_installer.py`: Integration tests for installation
- `test_subprocess_helper.py`: Unit tests for subprocess execution

## Related Documentation

- [Feature Overview](../features/azure-cli-wsl2-detection.md)
- [How-To Guide](../how-to/azure-cli-wsl2-setup.md)
- [Troubleshooting](../troubleshooting/azure-cli-wsl2-issues.md)
