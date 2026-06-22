# CLI Help Output - azlin restore

This document captures the exact help output for `azlin restore --help`.

## Command Help Output

```
Restore sessions across terminal tabs

Usage: azlin restore [OPTIONS]

Options:
      --resource-group <RESOURCE_GROUP>  Resource group
      --config <CONFIG>                  Config file path
      --skip-health-check                Skip VM health checks
      --force                            Force restore even if VMs are stopped
      --terminal <TERMINAL>              Use specific terminal
      --exclude <EXCLUDE>                Exclude VMs by name pattern
      --dry-run                          Show what would be restored without actually restoring
      --no-multi-tab                     Restore in single tab instead of multiple tabs
      --verbose                          Enable verbose output for restore
  -o, --output <OUTPUT>                  Output format [default: table] [possible values: table, json, csv]
      --auth-profile <AUTH_PROFILE>      Service principal authentication profile to use
      --startup-time                     Show startup time diagnostic and exit
  -h, --help                             Print help
```

## Short Help Output

When user runs `azlin --help`, the restore command appears in the commands list:

```
Commands:
  ...
  restore   Restore sessions across terminal tabs
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
```

## Success Messages

### Full Success

```
Found 3 running VMs in resource group 'azlin-dev'

Launching terminals for:
  ✓ dev-vm-1 (10.0.1.4) → session: development
  ✓ test-vm-2 (10.0.1.5) → session: testing
  ✓ prod-vm-3 (10.0.1.6) → session: production

Successfully restored 3 sessions
```

### Dry-Run Output

```
[DRY RUN] Session restore preview:

Platform: macOS
Terminal: Terminal.app (auto-detected)
Multi-tab: disabled (not supported on macOS)

Running VMs found: 3

Would restore sessions:
  1. dev-vm-1 (10.0.1.4) → session: development
  2. test-vm-2 (10.0.1.5) → session: testing
  3. prod-vm-3 (10.0.1.6) → session: production

No terminals will be launched in dry-run mode.
Run without --dry-run to restore sessions.
```

## See Also

- [Configuration Reference](configuration-reference.md)
- [CLI Python Parity](cli-python-parity.md)
