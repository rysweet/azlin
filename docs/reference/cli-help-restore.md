# CLI Help Output - azlin restore

This document specifies the exact help output fer `azlin restore --help`.

## Command Help Output

```
Usage: azlin restore [OPTIONS]

  Restore ALL active azlin sessions by launching new terminal windows.

  This command finds all running VMs and launches terminal windows with SSH
  connections to each. Terminal detection is automatic based on your platform:
    - macOS: Terminal.app
    - Windows/WSL: Windows Terminal (wt.exe) with multi-tab support
    - Linux: gnome-terminal (fallback to xterm)

  Each terminal connects via SSH and attaches to the tmux session (or creates
  a new one if it doesn't exist).

Examples:
  # Restore all sessions
  azlin restore

  # Restore sessions from specific resource group
  azlin restore --resource-group my-rg

  # Preview what would happen without launching terminals
  azlin restore --dry-run

  # Override terminal launcher
  azlin restore --terminal windows_terminal

  # Disable multi-tab mode (Windows Terminal only)
  azlin restore --no-multi-tab

Options:
  -g, --resource-group TEXT  Filter to specific resource group
  -c, --config PATH          Custom config file path [default: ~/.azlin/config.toml]
  -t, --terminal TEXT        Override terminal launcher
                             [macos_terminal|windows_terminal|linux_gnome|linux_xterm]
  --dry-run                  Show what would happen without launching terminals
  --no-multi-tab             Disable multi-tab mode (Windows Terminal only)
  --timeout INTEGER          Timeout per session in seconds [default: 30]
  -v, --verbose              Enable verbose output
  -h, --help                 Show this message and exit

Terminal Launchers:
  macos_terminal      macOS Terminal.app (default on macOS)
  windows_terminal    Windows Terminal wt.exe (default on Windows/WSL)
  linux_gnome         gnome-terminal (default on Linux)
  linux_xterm         xterm (fallback on Linux)

Configuration:
  Settings can be configured in ~/.azlin/config.toml:
    terminal_launcher     Override auto-detected terminal
    terminal_multi_tab    Enable multi-tab mode (Windows Terminal)
    restore_timeout       Timeout per session (seconds)
    [session_names]       Map VM names to tmux session names

Exit Codes:
  0    All sessions restored successfully
  1    Partial failure (some sessions failed to launch)
  2    Total failure (no sessions restored)

See also:
  azlin list       - Show running VMs
  azlin connect    - Connect to single VM
  azlin config     - View configuration

Documentation:
  https://rysweet.github.io/azlin/how-to/restore-sessions/
```

## Short Help Output

When user runs `azlin --help`, the restore command appears in the commands list:

```
Commands:
  ...
  restore   Restore all active sessions with new terminal windows
  ...
```

## Error Messages

### No VMs Found

```
Error: No running VMs found in resource group 'my-rg'

Run 'azlin list' to see available VMs or start VMs with 'azlin start'
```

### Terminal Launch Failed

```
Error: Terminal launch failed for 2 out of 3 VMs

Failed VMs:
  - dev-vm-1: Terminal.app not found
  - test-vm-2: SSH connection timeout

Check terminal configuration in ~/.azlin/config.toml
See troubleshooting guide: https://rysweet.github.io/azlin/troubleshooting/restore-issues/
```

### Configuration Error

```
Error: Invalid configuration in ~/.azlin/config.toml

Line 5: Unknown terminal launcher 'invalid_terminal'
Valid options: macos_terminal, windows_terminal, linux_gnome, linux_xterm

Run 'azlin config validate' to check configuration
```

### Platform Detection Failed

```
Warning: Could not auto-detect platform terminal

Using fallback: manual terminal launcher required
Specify terminal with --terminal option or in config file

Example:
  azlin restore --terminal macos_terminal

Supported terminals:
  macos_terminal      - macOS Terminal.app
  windows_terminal    - Windows Terminal (wt.exe)
  linux_gnome         - gnome-terminal
  linux_xterm         - xterm
```

## Success Messages

### Full Success

```
Detecting platform: macOS
Found 3 running VMs in resource group 'azlin-dev'

Launching terminals for:
  ✓ dev-vm-1 (10.0.1.4) → session: development
  ✓ test-vm-2 (10.0.1.5) → session: testing
  ✓ prod-vm-3 (10.0.1.6) → session: production

Successfully restored 3 sessions
```

### Partial Success

```
Detecting platform: WSL
Found 4 running VMs in resource group 'azlin-dev'

Launching terminals for:
  ✓ dev-vm-1 (10.0.1.4) → session: development
  ✓ test-vm-2 (10.0.1.5) → session: testing
  ✗ build-vm-3 (10.0.1.6) → connection timeout
  ✓ prod-vm-4 (10.0.1.7) → session: production

Warning: 1 out of 4 sessions failed to launch
Successfully restored 3 sessions

Check failed VM connectivity with:
  azlin status build-vm-3
  ssh -v -i ~/.ssh/id_rsa azureuser@10.0.1.6
```

### Dry-Run Output

```
[DRY RUN] Session restore preview:

Platform: macOS
Terminal: Terminal.app (auto-detected)
Multi-tab: disabled (not supported on macOS)
Timeout: 30 seconds
Resource group: azlin-dev

Running VMs found: 3

Would restore sessions:
  1. dev-vm-1
     VM: dev-vm-1 (10.0.1.4)
     User: azureuser
     SSH Key: ~/.ssh/id_rsa
     Tmux Session: development
     Command: Terminal.app → ssh -i ~/.ssh/id_rsa -t azureuser@10.0.1.4 \
              'tmux attach-session -t development || tmux new-session -s development'

  2. test-vm-2
     VM: test-vm-2 (10.0.1.5)
     User: azureuser
     SSH Key: ~/.ssh/id_rsa
     Tmux Session: testing
     Command: Terminal.app → ssh -i ~/.ssh/id_rsa -t azureuser@10.0.1.5 \
              'tmux attach-session -t testing || tmux new-session -s testing'

  3. prod-vm-3
     VM: prod-vm-3 (10.0.1.6)
     User: azureuser
     SSH Key: ~/.ssh/prod_key
     Tmux Session: production
     Command: Terminal.app → ssh -i ~/.ssh/prod_key -t azureuser@10.0.1.6 \
              'tmux attach-session -t production || tmux new-session -s production'

No terminals will be launched in dry-run mode.
Run without --dry-run to restore sessions.
```

## Verbose Output Example

```bash
azlin restore --verbose
```

Output:
```
[DEBUG] Loading configuration from ~/.azlin/config.toml
[DEBUG] Configuration loaded successfully
[DEBUG] Platform detection: macOS
[DEBUG] Default terminal: macos_terminal
[DEBUG] Resource group: azlin-dev (from config)
[DEBUG] Querying Azure for running VMs...
[DEBUG] Azure query: az vm list --resource-group azlin-dev --show-details --query "[?powerState=='VM running']"
[INFO]  Found 3 running VMs

[DEBUG] Building session configurations...
[DEBUG] VM: dev-vm-1
[DEBUG]   IP: 10.0.1.4
[DEBUG]   SSH Key: ~/.ssh/id_rsa
[DEBUG]   Session name: development (from config mapping)
[DEBUG] VM: test-vm-2
[DEBUG]   IP: 10.0.1.5
[DEBUG]   SSH Key: ~/.ssh/id_rsa
[DEBUG]   Session name: azlin (default)
[DEBUG] VM: prod-vm-3
[DEBUG]   IP: 10.0.1.6
[DEBUG]   SSH Key: ~/.ssh/prod_key (VM-specific)
[DEBUG]   Session name: production (from config mapping)

[INFO]  Launching 3 terminal windows...

[DEBUG] Launching terminal for dev-vm-1
[DEBUG]   Command: osascript -e 'tell application "Terminal" to do script "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/id_rsa -t azureuser@10.0.1.4 \"tmux attach-session -t development || tmux new-session -s development\""'
[DEBUG]   Terminal launched successfully
[INFO]  ✓ dev-vm-1 terminal launched

[DEBUG] Launching terminal for test-vm-2
[DEBUG]   Command: osascript -e 'tell application "Terminal" to do script "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/id_rsa -t azureuser@10.0.1.5 \"tmux attach-session -t azlin || tmux new-session -s azlin\""'
[DEBUG]   Terminal launched successfully
[INFO]  ✓ test-vm-2 terminal launched

[DEBUG] Launching terminal for prod-vm-3
[DEBUG]   Command: osascript -e 'tell application "Terminal" to do script "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/prod_key -t azureuser@10.0.1.6 \"tmux attach-session -t production || tmux new-session -s production\""'
[DEBUG]   Terminal launched successfully
[INFO]  ✓ prod-vm-3 terminal launched

[INFO]  Successfully restored 3 out of 3 sessions (100%)
[DEBUG] Exit code: 0
```

## See Also

- [How to Restore Sessions](../how-to/restore-sessions.md)
- [Configuration Reference](../reference/configuration-reference.md)
- [Troubleshooting Guide](../troubleshooting/restore-issues.md)
