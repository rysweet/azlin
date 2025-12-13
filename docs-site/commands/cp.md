# azlin cp

Copy files between local machine and VMs.

Supports bidirectional file transfer with security-hardened path validation.

Arguments support session:path notation:
- Local path: myfile.txt
- Remote path: vm1:~/myfile.txt


Examples:
    azlin cp myfile.txt vm1:~/          # Local to remote
    azlin cp vm1:~/data.txt ./          # Remote to local
    azlin cp vm1:~/src vm2:~/dest       # Remote to remote (not supported)
    azlin cp --dry-run test.txt vm1:~/  # Show transfer plan


## Description

Copy files between local machine and VMs.
Supports bidirectional file transfer with security-hardened path validation.
Arguments support session:path notation:
- Local path: myfile.txt
- Remote path: vm1:~/myfile.txt

Examples:
azlin cp myfile.txt vm1:~/          # Local to remote
azlin cp vm1:~/data.txt ./          # Remote to local
azlin cp vm1:~/src vm2:~/dest       # Remote to remote (not supported)
azlin cp --dry-run test.txt vm1:~/  # Show transfer plan

## Usage

```bash
azlin cp SOURCE DESTINATION [OPTIONS]
```

## Arguments

- `SOURCE` - No description available
- `DESTINATION` - No description available

## Options

- `--dry-run` - Show what would be transferred
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
