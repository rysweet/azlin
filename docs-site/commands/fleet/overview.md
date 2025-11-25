# Fleet Commands

Distributed command orchestration across VM fleets.

## Overview

Execute commands across multiple VMs in parallel with intelligent routing and error handling.

## Available Commands

- `azlin fleet exec` - Execute command on fleet
- `azlin batch exec` - Batch command execution

## Quick Start

```bash
# Execute on all VMs
azlin fleet exec "*" "docker ps"

# Execute on pattern
azlin fleet exec "api-*" "systemctl status nginx"

# Execute with specific VMs
azlin fleet exec "vm1,vm2,vm3" "uptime"
```

## Features

- **Parallel Execution**: Run commands simultaneously
- **Pattern Matching**: Target VMs with wildcards
- **Error Handling**: Continue on failures
- **Output Aggregation**: Collect and format results

## Related Commands

- [azlin batch command](../batch/command.md) - Batch operations
- [azlin w](../util/w.md) - Distributed monitoring
- [azlin ps](../util/ps.md) - Distributed process listing
