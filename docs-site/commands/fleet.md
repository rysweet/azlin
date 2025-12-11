# azlin fleet

Distributed command orchestration across VM fleets.

Execute commands across multiple VMs with advanced features:
- Conditional execution based on VM state
- Smart routing to least-loaded VMs
- Sequential dependency chains
- YAML workflow definitions
- Result diff reports


COMMANDS:
    run        Execute command across fleet
    workflow   Execute YAML workflow definition


EXAMPLES:
    # Run tests on idle VMs only
    $ azlin fleet run "npm test" --if-idle --parallel 5

    # Deploy to web servers with retry
    $ azlin fleet run "deploy.sh" --tag role=web --retry-failed

    # Execute on least-loaded VMs
    $ azlin fleet run "backup.sh" --smart-route --count 3

    # Run workflow from YAML
    $ azlin fleet workflow deploy.yaml --tag env=staging


## Description

Distributed command orchestration across VM fleets.
Execute commands across multiple VMs with advanced features:
- Conditional execution based on VM state
- Smart routing to least-loaded VMs
- Sequential dependency chains
- YAML workflow definitions
- Result diff reports

COMMANDS:
run        Execute command across fleet
workflow   Execute YAML workflow definition

EXAMPLES:
# Run tests on idle VMs only
$ azlin fleet run "npm test" --if-idle --parallel 5
# Deploy to web servers with retry
$ azlin fleet run "deploy.sh" --tag role=web --retry-failed
# Execute on least-loaded VMs
$ azlin fleet run "backup.sh" --smart-route --count 3
# Run workflow from YAML
$ azlin fleet workflow deploy.yaml --tag env=staging

## Usage

```bash
azlin fleet
```

## Subcommands

### run

Execute command across fleet of VMs.

Runs the specified command on selected VMs with optional conditions,
smart routing, and result aggregation.


COMMAND is the shell command to execute remotely.


Selection Options:
  --tag          Filter by tag (e.g., role=web)
  --pattern      Filter by name pattern (e.g., 'web-*')
  --all          Run on all VMs


Condition Options:
  --if-idle          Only run on idle VMs (no active users)
  --if-cpu-below N   Only run if CPU usage below N%
  --if-mem-below N   Only run if memory usage below N%


Routing Options:
  --smart-route  Route to least-loaded VMs first
  --count N      Limit to N VMs


Execution Options:
  --parallel N     Max parallel workers (default: 10)
  --retry-failed   Retry failed VMs once
  --timeout N      Command timeout in seconds (default: 300)
  --dry-run        Show what would be executed


Output Options:
  --show-diff    Show diff of command outputs across VMs


Examples:
  # Run tests on all idle web servers
  $ azlin fleet run "npm test" --tag role=web --if-idle

  # Deploy to 3 least-loaded staging VMs
  $ azlin fleet run "deploy.sh" --tag env=staging --smart-route --count 3

  # Backup with retry on failure
  $ azlin fleet run "backup.sh" --pattern 'db-*' --retry-failed

  # Check versions with diff report
  $ azlin fleet run "node --version" --all --show-diff


**Usage:**
```bash
azlin fleet run COMMAND [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group
- `--tag` - Filter VMs by tag (format: key=value)
- `--pattern` - Filter VMs by name pattern (glob)
- `--all` - Run on all VMs
- `--parallel` - Max parallel workers (default: 10)
- `--if-idle` - Only run on idle VMs
- `--if-cpu-below` - Only run if CPU below threshold
- `--if-mem-below` - Only run if memory below threshold
- `--smart-route` - Route to least-loaded VMs first
- `--count` - Limit execution to N VMs
- `--retry-failed` - Retry failed VMs once
- `--show-diff` - Show diff of command outputs
- `--timeout` - Command timeout in seconds
- `--dry-run` - Show what would be executed

### workflow

Execute YAML workflow definition.

Loads and executes a multi-step workflow defined in YAML format.
Supports dependency chains, conditions, and parallel execution.


WORKFLOW_FILE is the path to YAML workflow definition.


Workflow YAML Format:
  steps:
    - name: step1
      command: "echo hello"
      condition: idle           # Optional
      depends_on: []            # Optional
      parallel: true            # Optional (default: true)
      retry_on_failure: false   # Optional (default: false)
      continue_on_error: false  # Optional (default: false)


Examples:
  # Run deploy workflow on staging
  $ azlin fleet workflow deploy.yaml --tag env=staging

  # Dry run to see workflow steps
  $ azlin fleet workflow deploy.yaml --all --dry-run

  # Run with diff on final step
  $ azlin fleet workflow test.yaml --pattern 'web-*' --show-diff


**Usage:**
```bash
azlin fleet workflow WORKFLOW_FILE [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group
- `--tag` - Filter VMs by tag (format: key=value)
- `--pattern` - Filter VMs by name pattern (glob)
- `--all` - Run on all VMs
- `--parallel` - Max parallel workers (default: 10)
- `--show-diff` - Show diff of final step outputs
- `--dry-run` - Show workflow without executing
