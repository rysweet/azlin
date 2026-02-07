# Configuration Reference - azlin restore

Complete reference fer configurin' terminal preferences and restore behavior.

## Configuration File Location

`~/.azlin/config.toml`

## Terminal Settings

### terminal_launcher

Override the automatic terminal detection.

**Type**: `string` (optional)
**Default**: Auto-detected based on platform
**Valid Values**:
- `"macos_terminal"` - macOS Terminal.app
- `"windows_terminal"` - Windows Terminal (wt.exe)
- `"linux_gnome"` - gnome-terminal
- `"linux_xterm"` - xterm

**Example**:
```toml
terminal_launcher = "macos_terminal"
```

**When to Use**:
- Override auto-detection if wrong terminal selected
- Force specific terminal when multiple installed
- Testing different terminal applications

### terminal_multi_tab

Enable or disable multi-tab mode fer Windows Terminal.

**Type**: `boolean`
**Default**: `true`
**Platform**: Windows Terminal only

**Example**:
```toml
terminal_multi_tab = true  # Open all sessions in one window (default)
```

```toml
terminal_multi_tab = false  # Open separate windows fer each session
```

**Behavior**:
- `true`: All sessions open as tabs in one Windows Terminal window
- `false`: Each session opens in separate Windows Terminal window

**Performance**:
- Multi-tab mode is faster fer 3+ sessions (single window launch)
- Separate windows useful fer multi-monitor setups

### restore_timeout

Timeout fer each session launch (in seconds).

**Type**: `integer`
**Default**: `30`
**Range**: 5-300 seconds

**Example**:
```toml
restore_timeout = 60  # 1 minute timeout per session
```

**When to Adjust**:
- Increase fer slow network connections
- Increase fer VMs with long boot times
- Decrease fer fast local networks

## Session Name Mappings

Map VM names to custom tmux session names.

**Section**: `[session_names]`
**Type**: `table`
**Default**: All sessions named "azlin"

**Example**:
```toml
[session_names]
"dev-vm-1" = "development"
"test-vm-2" = "testing"
"prod-vm-3" = "production"
```

**Usage**:
- The `azlin restore` command attaches to the mapped session name
- If session doesn't exist, it creates one with that name
- Useful fer organizing work contexts

## SSH Key Configuration

Configure SSH key paths fer authentication.

**Section**: Main config
**Type**: `string` (path)
**Default**: `~/.ssh/id_rsa`

**Example**:
```toml
ssh_key_path = "~/.ssh/azlin_key"
```

**Multiple Keys** (per-VM):
```toml
[vm_ssh_keys]
"dev-vm-1" = "~/.ssh/dev_key"
"prod-vm-3" = "~/.ssh/prod_key"
```

## Resource Group Settings

Default resource group fer restore operations.

**Setting**: `default_resource_group`
**Type**: `string`
**Default**: None (queries all resource groups)

**Example**:
```toml
default_resource_group = "azlin-dev"
```

**When Set**:
- `azlin restore` only restores VMs from this resource group
- Override with `--resource-group` flag

## Complete Configuration Example

```toml
# ~/.azlin/config.toml

# Default resource group
default_resource_group = "azlin-development"

# Terminal settings
terminal_launcher = "windows_terminal"  # Override auto-detection
terminal_multi_tab = true                # Use tabs (Windows Terminal)
restore_timeout = 45                     # 45 second timeout

# SSH configuration
ssh_key_path = "~/.ssh/azlin_key"

# Session name mappings
[session_names]
"azlin-dev-vm-1" = "backend-dev"
"azlin-dev-vm-2" = "frontend-dev"
"azlin-test-vm-1" = "integration-tests"
"azlin-prod-vm-1" = "production"

# Per-VM SSH keys (optional)
[vm_ssh_keys]
"azlin-prod-vm-1" = "~/.ssh/production_key"
```

## Platform-Specific Examples

### macOS Configuration

```toml
# macOS with custom session names
default_resource_group = "dev-team"
terminal_launcher = "macos_terminal"
restore_timeout = 30

[session_names]
"backend-vm" = "backend"
"frontend-vm" = "frontend"
"database-vm" = "postgres"
```

### WSL Configuration

```toml
# WSL with Windows Terminal
default_resource_group = "azlin-wsl"
terminal_launcher = "windows_terminal"
terminal_multi_tab = true  # Open all in one window
restore_timeout = 60       # Longer timeout fer WSL

[session_names]
"dev-vm" = "development"
"test-vm" = "testing"
```

### Linux Configuration

```toml
# Linux with gnome-terminal
default_resource_group = "linux-vms"
terminal_launcher = "linux_gnome"
restore_timeout = 30

[session_names]
"dev-vm" = "dev-session"
"build-vm" = "build-server"
```

## Configuration Validation

Validate yer configuration:

```bash
# Dry-run shows what configuration will be used
azlin restore --dry-run
```

Output shows:
```
Configuration loaded from: ~/.azlin/config.toml
Platform: macOS
Terminal: macos_terminal
Multi-tab: disabled
Timeout: 30s
Default resource group: azlin-dev

Session mappings:
  dev-vm-1 → backend-dev
  test-vm-2 → frontend-test
```

## Configuration Priority

Settings are applied in this order (highest to lowest):

1. **Command-line flags** (e.g., `--terminal windows_terminal`)
2. **Environment variables** (e.g., `AZLIN_TERMINAL_LAUNCHER`)
3. **Config file** (`~/.azlin/config.toml`)
4. **Auto-detection** (platform defaults)

## Environment Variable Overrides

Override config file settings temporarily:

```bash
# Override terminal launcher
export AZLIN_TERMINAL_LAUNCHER=windows_terminal
azlin restore

# Override timeout
export AZLIN_RESTORE_TIMEOUT=60
azlin restore

# Override multi-tab mode
export AZLIN_MULTI_TAB=false
azlin restore
```

## Troubleshooting Configuration

### Check Current Configuration

```bash
azlin config show
```

### Test Terminal Detection

```bash
azlin restore --dry-run
```

### Validate Config File

```bash
azlin config validate
```

## See Also

- [How to restore sessions](../how-to/restore-sessions.md)
- [Platform setup guide](../tutorials/platform-setup-restore.md)
- [Troubleshooting restore issues](../troubleshooting/restore-issues.md)
