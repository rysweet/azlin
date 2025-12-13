# azlin main

azlin - Azure Ubuntu VM provisioning and management.

Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
and executes commands remotely.

Use --auth-profile to specify a service principal authentication profile
(configured via 'azlin auth setup').


NATURAL LANGUAGE COMMANDS (AI-POWERED):
    do            Execute commands using natural language
                  Example: azlin do "create a new vm called Sam"
                  Example: azlin do "sync all my vms"
                  Example: azlin do "show me the cost over the last week"
                  Requires: ANTHROPIC_API_KEY environment variable


VM LIFECYCLE COMMANDS:
    new           Provision a new VM (aliases: vm, create)
    clone         Clone a VM with its home directory contents
    list          List VMs in resource group
    session       Set or view session name for a VM
    status        Show detailed status of VMs
    start         Start a stopped VM
    stop          Stop/deallocate a VM to save costs
    connect       Connect to existing VM via SSH
    update        Update all development tools on a VM
    tag           Manage VM tags (add, remove, list)


ENVIRONMENT MANAGEMENT:
    env set       Set environment variable on VM
    env list      List environment variables on VM
    env delete    Delete environment variable from VM
    env export    Export variables to .env file
    env import    Import variables from .env file
    env clear     Clear all environment variables


SNAPSHOT COMMANDS:
    snapshot create <vm>              Create snapshot of VM disk
    snapshot list <vm>                List snapshots for VM
    snapshot restore <vm> <snapshot>  Restore VM from snapshot
    snapshot delete <snapshot>        Delete a snapshot


STORAGE COMMANDS:
    storage create    Create NFS storage for shared home directories
    storage list      List NFS storage accounts
    storage status    Show storage usage and connected VMs
    storage mount     Mount storage on VM
    storage unmount   Unmount storage from VM
    storage delete    Delete storage account


MONITORING COMMANDS:
    w             Run 'w' command on all VMs
    ps            Run 'ps aux' on all VMs
    cost          Show cost estimates for VMs
    logs          View VM logs without SSH connection


DELETION COMMANDS:
    kill          Delete a VM and all resources
    destroy       Delete VM with dry-run and RG options
    killall       Delete all VMs in resource group
    cleanup       Find and remove orphaned resources


SSH KEY MANAGEMENT:
    keys rotate   Rotate SSH keys across all VMs
    keys list     List VMs and their SSH keys
    keys export   Export public key to file
    keys backup   Backup current SSH keys


AUTHENTICATION:
    auth setup    Set up service principal authentication profile
    auth test     Test authentication with a profile
    auth list     List available authentication profiles
    auth show     Show profile details
    auth remove   Remove authentication profile


EXAMPLES:
    # Show help
    $ azlin

    # Natural language commands (AI-powered)
    $ azlin do "create a new vm called Sam"
    $ azlin do "sync all my vms"
    $ azlin do "show me the cost over the last week"
    $ azlin do "delete vms older than 30 days" --dry-run

    # Provision a new VM
    $ azlin new

    # Provision with custom session name
    $ azlin new --name my-project

    # List VMs and show status
    $ azlin list
    $ azlin list --tag env=dev
    $ azlin status

    # Manage session names
    $ azlin session azlin-vm-12345 my-project
    $ azlin session azlin-vm-12345 --clear

    # Environment variables
    $ azlin env set my-vm DATABASE_URL="postgres://localhost/db"
    $ azlin env list my-vm
    $ azlin env export my-vm prod.env

    # Manage tags
    $ azlin tag my-vm --add env=dev
    $ azlin tag my-vm --list
    $ azlin tag my-vm --remove env

    # Start/stop VMs
    $ azlin start my-vm
    $ azlin stop my-vm

    # Update VM tools
    $ azlin update my-vm
    $ azlin update my-project

    # Manage snapshots
    $ azlin snapshot create my-vm
    $ azlin snapshot list my-vm
    $ azlin snapshot restore my-vm my-vm-snapshot-20251015-053000

    # Shared NFS storage for home directories
    $ azlin storage create team-shared --size 100 --tier Premium
    $ azlin new --nfs-storage team-shared --name worker-1
    $ azlin new --nfs-storage team-shared --name worker-2
    $ azlin storage status team-shared

    # View costs
    $ azlin cost --by-vm
    $ azlin cost --from 2025-01-01 --to 2025-01-31

    # View VM logs
    $ azlin logs my-vm
    $ azlin logs my-vm --boot
    $ azlin logs my-vm --follow

    # Run 'w' and 'ps' on all VMs
    $ azlin w
    $ azlin ps

    # Delete VMs
    $ azlin kill azlin-vm-12345
    $ azlin destroy my-vm --dry-run
    $ azlin destroy my-vm --delete-rg --force

    # Provision VM with custom name
    $ azlin new --name my-dev-vm

    # Provision VM and clone repository
    $ azlin new --repo https://github.com/owner/repo

    # Provision 5 VMs in parallel
    $ azlin new --pool 5


CONFIGURATION:
    Config file: ~/.azlin/config.toml
    Set defaults: default_resource_group, default_region, default_vm_size

For help on any command: azlin <command> --help


## Description

azlin - Azure Ubuntu VM provisioning and management.
Provisions Azure Ubuntu VMs with development tools, manages existing VMs,
and executes commands remotely.
Use --auth-profile to specify a service principal authentication profile
(configured via 'azlin auth setup').

NATURAL LANGUAGE COMMANDS (AI-POWERED):
do            Execute commands using natural language

## Usage

```bash
azlin main [OPTIONS]
```

## Options

- `--auth-profile` TEXT - Service principal authentication profile to use
- `--version` - Show the version and exit.

## Subcommands

### auth

Manage service principal authentication profiles.

Service principals enable automated Azure authentication without
interactive login. Use these commands to set up and manage
authentication profiles.


EXAMPLES:
    # Set up a new profile
    $ azlin auth setup --profile production

    # Test authentication
    $ azlin auth test --profile production

    # List all profiles
    $ azlin auth list

    # Show profile details
    $ azlin auth show production

    # Remove a profile
    $ azlin auth remove production


### autopilot

AI-powered cost optimization and VM lifecycle management.

Autopilot learns your VM usage patterns and automatically manages
VM lifecycle to stay within budget.

Features:
- Learns work hours and idle patterns
- Auto-stops idle VMs
- Downsizes underutilized VMs
- Enforces budget constraints
- Transparent notifications

Example:
    azlin autopilot enable --budget 500 --strategy balanced


### bastion

Manage Azure Bastion hosts for secure VM connections.

Azure Bastion provides secure RDP/SSH connectivity to VMs
without exposing public IPs. These commands help you list,
configure, and use Bastion hosts with azlin.


COMMANDS:
    list         List Bastion hosts
    status       Show Bastion host status
    configure    Configure Bastion for a VM


EXAMPLES:
    # List all Bastion hosts
    $ azlin bastion list

    # List Bastion hosts in a resource group
    $ azlin bastion list --resource-group my-rg

    # Check status of a specific Bastion
    $ azlin bastion status my-bastion --resource-group my-rg

    # Configure VM to use Bastion
    $ azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg


### batch

Batch operations on multiple VMs.

Execute operations on multiple VMs simultaneously using
tag-based selection, pattern matching, or all VMs.


Examples:
    azlin batch stop --tag 'env=dev'
    azlin batch start --vm-pattern 'test-*'
    azlin batch command 'git pull' --all
    azlin batch sync --tag 'env=dev'


### clone

Clone a VM with its home directory contents.

Creates new VM(s) and copies the entire home directory from the source VM.
Useful for creating development environments, parallel testing, or team onboarding.


Examples:
    # Clone single VM
    azlin clone amplihack

    # Clone with custom session name
    azlin clone amplihack --session-prefix dev-env

    # Clone multiple replicas
    azlin clone amplihack --num-replicas 3 --session-prefix worker
    # Creates: worker-1, worker-2, worker-3

    # Clone with specific VM size
    azlin clone my-vm --vm-size Standard_D4s_v3

The source VM can be specified by VM name or session name.
Home directory security filters are applied (no SSH keys, credentials, etc.).


**Usage:**
```bash
azlin main clone SOURCE_VM [OPTIONS]
```

**Options:**
- `--num-replicas` - Number of clones to create (default: 1)
- `--session-prefix` - Session name prefix for clones
- `--resource-group`, `--rg` - Resource group
- `--vm-size` - VM size for clones (default: same as source)
- `--region` - Azure region (default: same as source)
- `--config` - Config file path

### code

Launch VS Code with Remote-SSH for a VM.

One-click VS Code launch that automatically:
- Configures SSH connection in ~/.ssh/config
- Installs configured extensions from ~/.azlin/vscode/extensions.json
- Sets up port forwarding from ~/.azlin/vscode/ports.json
- Launches VS Code Remote-SSH

VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Configuration:
Create ~/.azlin/vscode/ directory with optional files:
- extensions.json: {"extensions": ["ms-python.python", ...]}
- ports.json: {"forwards": [{"local": 3000, "remote": 3000}, ...]}
- settings.json: VS Code workspace settings


Examples:
    # Launch VS Code for VM
    azlin code my-dev-vm

    # Launch with explicit resource group
    azlin code my-vm --rg my-resource-group

    # Launch by session name
    azlin code my-project

    # Launch by IP address
    azlin code 20.1.2.3

    # Skip extension installation (faster)
    azlin code my-vm --no-extensions

    # Open specific remote directory
    azlin code my-vm --workspace /home/azureuser/projects

    # Custom SSH user
    azlin code my-vm --user myuser

    # Custom SSH key
    azlin code my-vm --key ~/.ssh/custom_key


**Usage:**
```bash
azlin main code VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group (required for VM name)
- `--config` - Config file path
- `--user` - SSH username (default: azureuser)
- `--key` - SSH private key path
- `--no-extensions` - Skip extension installation (faster launch)
- `--workspace` - Remote workspace path (default: /home/user)

### compose

Multi-VM docker-compose orchestration commands.

Deploy and manage multi-container applications across multiple VMs
using extended docker-compose syntax.

Example docker-compose.azlin.yml:


version: '3.8'
services:
  web:
    image: nginx:latest
    vm: web-server-1
    ports:
      - "80:80"
  api:
    image: myapi:latest
    vm: api-server-*
    replicas: 3


### connect

Connect to existing VM via SSH.

If VM_IDENTIFIER is not provided, displays an interactive list of available
VMs to choose from, or option to create a new VM.

VM_IDENTIFIER can be either:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Use -- to separate remote command from options.

By default, auto-reconnect is ENABLED. If your SSH session disconnects,
you will be prompted to reconnect. Use --no-reconnect to disable this.


Examples:
    # Interactive selection
    azlin connect

    # Connect to VM by name
    azlin connect my-vm

    # Connect to VM by session name
    azlin connect my-project

    # Connect to VM by name with explicit resource group
    azlin connect my-vm --rg my-resource-group

    # Connect by IP address
    azlin connect 20.1.2.3

    # Connect without tmux
    azlin connect my-vm --no-tmux

    # Connect with custom tmux session name
    azlin connect my-vm --tmux-session dev

    # Connect and run command
    azlin connect my-vm -- ls -la

    # Connect with custom SSH user
    azlin connect my-vm --user myuser

    # Connect with custom SSH key
    azlin connect my-vm --key ~/.ssh/custom_key

    # Disable auto-reconnect
    azlin connect my-vm --no-reconnect

    # Set maximum reconnection attempts
    azlin connect my-vm --max-retries 5


**Usage:**
```bash
azlin main connect VM_IDENTIFIER REMOTE_COMMAND [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group (required for VM name)
- `--config` - Config file path
- `--no-tmux` - Skip tmux session
- `--tmux-session` - Tmux session name (default: azlin)
- `--user` - SSH username (default: azureuser)
- `--key` - SSH private key path
- `--no-reconnect` - Disable auto-reconnect on disconnect
- `--max-retries` - Maximum reconnection attempts (default: 3)
- `--yes`, `-y` - Skip all confirmation prompts (e.g., Bastion)

### context

Manage kubectl-style contexts for multi-tenant Azure access.

Contexts allow you to switch between different Azure subscriptions
and tenants without changing environment variables or config files.

Each context contains:
- subscription_id: Azure subscription ID
- tenant_id: Azure tenant ID
- auth_profile: Optional service principal profile


EXAMPLES:
    # List all contexts
    $ azlin context list

    # Show current context
    $ azlin context current

    # Switch to a context
    $ azlin context use production

    # Create new context
    $ azlin context create staging \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

    # Create context with auth profile
    $ azlin context create prod \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
        --auth-profile prod-sp

    # Rename context
    $ azlin context rename old-name new-name

    # Delete context
    $ azlin context delete staging

    # Migrate from legacy config
    $ azlin context migrate


### cost

Show cost estimates for VMs.

Displays cost estimates based on VM size and uptime.
Costs are approximate based on Azure pay-as-you-go pricing.


Examples:
    azlin cost
    azlin cost --by-vm
    azlin cost --from 2025-01-01 --to 2025-01-31
    azlin cost --estimate
    azlin cost --rg my-resource-group --by-vm


**Usage:**
```bash
azlin main cost [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--by-vm` - Show per-VM breakdown
- `--from` - Start date (YYYY-MM-DD)
- `--to` - End date (YYYY-MM-DD)
- `--estimate` - Show monthly cost estimate

### costs

Cost intelligence and optimization.

Analyze spending, set budgets, get recommendations, and automate
cost-saving actions for your Azure resources.


COMMANDS:
    dashboard      View current costs and spending trends
    history        Analyze historical cost data
    budget         Manage budgets and alerts
    recommend      Get cost optimization recommendations
    actions        Execute cost-saving actions


EXAMPLES:
    # View current costs
    $ azlin costs dashboard --resource-group my-rg

    # Analyze last 30 days
    $ azlin costs history --resource-group my-rg --days 30

    # Set monthly budget with alert
    $ azlin costs budget set --resource-group my-rg --amount 1000 --threshold 80

    # Get optimization recommendations
    $ azlin costs recommend --resource-group my-rg

    # Execute high-priority actions
    $ azlin costs actions execute --priority high


### cp

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


**Usage:**
```bash
azlin main cp SOURCE DESTINATION [OPTIONS]
```

**Options:**
- `--dry-run` - Show what would be transferred
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### create

Alias for 'new' command. Provision a new Azure VM.

**Usage:**
```bash
azlin main create [OPTIONS]
```

**Options:**
- `--repo` - GitHub repository URL to clone
- `--vm-size` - Azure VM size
- `--region` - Azure region
- `--resource-group`, `--rg` - Azure resource group
- `--name` - Custom VM name
- `--pool` - Number of VMs to create in parallel
- `--no-auto-connect` - Do not auto-connect via SSH
- `--config` - Config file path
- `--template` - Template name to use for VM configuration
- `--nfs-storage` - NFS storage account name to mount as home directory
- `--no-bastion` - Skip bastion auto-detection and always create public IP
- `--bastion-name` - Explicit bastion host name to use for private VM

### destroy

Destroy a VM and optionally the entire resource group.

This is an alias for the 'kill' command with additional options.
Deletes the VM, NICs, disks, and public IPs.


Examples:
    azlin destroy azlin-vm-12345
    azlin destroy my-vm --dry-run
    azlin destroy my-vm --delete-rg --force
    azlin destroy my-vm --rg my-resource-group


**Usage:**
```bash
azlin main destroy VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--force` - Skip confirmation prompt
- `--dry-run` - Show what would be deleted without actually deleting
- `--delete-rg` - Delete the entire resource group (use with caution)

### do

Execute natural language azlin commands using AI.

The 'do' command understands natural language and automatically translates
your requests into the appropriate azlin commands. Just describe what you
want in plain English.


Quick Start:
    1. Set API key: export ANTHROPIC_API_KEY=your-key-here
    2. Get key from: https://console.anthropic.com/
    3. Try: azlin do "list all my vms"


VM Management Examples:
    azlin do "create a new vm called Sam"
    azlin do "show me all my vms"
    azlin do "what is the status of my vms"
    azlin do "start my development vm"
    azlin do "stop all test vms"


Cost & Monitoring:
    azlin do "what are my azure costs"
    azlin do "show me costs by vm"
    azlin do "what's my spending this month"


File Operations:
    azlin do "sync all my vms"
    azlin do "sync my home directory to vm Sam"
    azlin do "copy myproject to the vm"


Resource Cleanup:
    azlin do "delete vm called test-123" --dry-run  # Preview first
    azlin do "delete all test vms"                   # Then execute
    azlin do "stop idle vms to save costs"


Complex Operations:
    azlin do "create 5 test vms and sync them all"
    azlin do "set up a new development environment"
    azlin do "show costs and stop any idle vms"


Options:
    --dry-run      Preview actions without executing anything
    --yes, -y      Skip confirmation prompts (for automation)
    --verbose, -v  Show detailed parsing and confidence scores
    --rg NAME      Specify Azure resource group


Safety Features:
    - Shows plan and asks for confirmation (unless --yes)
    - High accuracy: 95-100% confidence on VM operations
    - Graceful error handling for invalid requests
    - Dry-run mode to preview without executing


Error Handling:
    - Invalid requests (0% confidence): No commands executed
    - Ambiguous requests (low confidence): Asks for confirmation
    - Always shows what will be executed before running


Requirements:
    - ANTHROPIC_API_KEY environment variable (get from console.anthropic.com)
    - Azure CLI authenticated (az login)
    - Active Azure subscription


For More Examples:
    See docs/AZDOIT.md for 50+ examples and comprehensive guide
    Integration tested: 7/7 tests passing with real Azure resources


**Usage:**
```bash
azlin main do REQUEST [OPTIONS]
```

**Options:**
- `--dry-run` - Show execution plan without running commands
- `--yes`, `-y` - Skip confirmation prompts
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--verbose`, `-v` - Show detailed execution information

### doit

Autonomous Azure infrastructure deployment.

Use natural language to describe your infrastructure needs,
and doit will autonomously deploy it using Azure CLI.


### env

Manage environment variables on VMs.

Commands to set, list, delete, and export environment variables
stored in ~/.bashrc on remote VMs.


Examples:
    azlin env set my-vm DATABASE_URL="postgres://localhost/db"
    azlin env list my-vm
    azlin env delete my-vm API_KEY
    azlin env export my-vm prod.env


### fleet

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


### github-runner

Manage GitHub Actions self-hosted runner fleets.

Transform azlin VMs into auto-scaling GitHub Actions runners for
substantial CI/CD parallelism improvements.


COMMANDS:
    enable     Enable runner fleet on VM pool
    disable    Disable runner fleet
    status     Show runner fleet status
    scale      Manually scale runner fleet


FEATURES:
    - Ephemeral runners (per-job lifecycle)
    - Auto-scaling based on job queue
    - Secure runner rotation
    - Cost tracking per job


EXAMPLES:
    # Enable fleet for repository
    $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers

    # Enable with custom scaling
    $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers \
        --min-runners 2 --max-runners 20 --labels linux,docker

    # Show fleet status
    $ azlin github-runner status --pool ci-workers

    # Scale fleet manually
    $ azlin github-runner scale --pool ci-workers --count 5

    # Disable fleet
    $ azlin github-runner disable --pool ci-workers


### help

Show help for commands.

Display general help or help for a specific command.


Examples:
    azlin help              # Show general help
    azlin help connect      # Show help for connect command
    azlin help list         # Show help for list command


**Usage:**
```bash
azlin main help COMMAND_NAME
```

### ip

IP diagnostics and network troubleshooting commands.

Commands to diagnose IP address classification and connectivity issues.


Examples:
    azlin ip check my-vm
    azlin ip check --all


### keys

SSH key management and rotation.

Manage SSH keys across Azure VMs with rotation, backup, and export functionality.


### kill

Delete a VM and all associated resources.

Deletes the VM, NICs, disks, and public IPs.


Examples:
    azlin kill azlin-vm-12345
    azlin kill my-vm --rg my-resource-group
    azlin kill my-vm --force


**Usage:**
```bash
azlin main kill VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--force` - Skip confirmation prompt

### killall

Delete all VMs in resource group.

Deletes all VMs matching the prefix and their associated resources.


Examples:
    azlin killall
    azlin killall --rg my-resource-group
    azlin killall --prefix test-vm
    azlin killall --force


**Usage:**
```bash
azlin main killall [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--force` - Skip confirmation prompt
- `--prefix` - Only delete VMs with this prefix

### list

List VMs in a resource group.

By default, lists azlin-managed VMs in the configured resource group.
Use --show-all-vms (-a) to scan all VMs across all resource groups (expensive).

Shows VM name, status, IP address, region, size, vCPUs, and optionally quota/tmux info.


Examples:
    azlin list                    # VMs in default RG with quota & tmux
    azlin list --rg my-rg         # VMs in specific RG
    azlin list --all              # Include stopped VMs
    azlin list --tag env=dev      # Filter by tag
    azlin list --show-all-vms     # All VMs across all RGs (expensive)
    azlin list -a                 # Same as --show-all-vms
    azlin list --no-quota         # Skip quota information
    azlin list --no-tmux          # Skip tmux session info
    azlin list --all-contexts     # VMs across all configured contexts
    azlin list --contexts "prod*" # VMs from production contexts
    azlin list --contexts "*-dev" --all  # All VMs (including stopped) in dev contexts


**Usage:**
```bash
azlin main list [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group to list VMs from
- `--config` - Config file path
- `--all` - Show all VMs (including stopped)
- `--tag` - Filter VMs by tag (format: key or key=value)
- `--show-quota` - Show Azure vCPU quota information
- `--show-tmux` - Show active tmux sessions
- `--show-all-vms`, `-a` - List all VMs across all resource groups (expensive operation)
- `--all-contexts` - List VMs across all configured contexts (requires context configuration)
- `--contexts` - List VMs from contexts matching glob pattern (e.g., 'prod*', 'dev-*')
- `--wide`, `-w` - Prevent VM name truncation in table output

### new

Provision a new Azure VM with development tools.

SSH keys are automatically stored in Azure Key Vault for cross-system access.

Creates a new Ubuntu VM in Azure with all development tools pre-installed.
Optionally connects via SSH and clones a GitHub repository.


EXAMPLES:
    # Provision basic VM (uses size 'l' = 128GB RAM)
    $ azlin new

    # Provision with size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
    $ azlin new --size m     # Medium: 64GB RAM
    $ azlin new --size s     # Small: 8GB RAM (original default)
    $ azlin new --size xl    # Extra-large: 256GB RAM

    # Provision with exact VM size (overrides --size)
    $ azlin new --vm-size Standard_E8as_v5

    # Provision with custom name
    $ azlin new --name my-dev-vm --size m

    # Provision and clone repository
    $ azlin new --repo https://github.com/owner/repo

    # Provision 5 VMs in parallel
    $ azlin new --pool 5 --size l

    # Provision from template
    $ azlin new --template dev-vm

    # Provision with NFS storage for shared home directory
    $ azlin new --nfs-storage myteam-shared --name worker-1

    # Provision and execute command
    $ azlin new --size xl -- python train.py


**Usage:**
```bash
azlin main new [OPTIONS]
```

**Options:**
- `--repo` - GitHub repository URL to clone
- `--size` - VM size tier: s(mall), m(edium), l(arge), xl (default: l)
- `--vm-size` - Azure VM size (overrides --size)
- `--region` - Azure region
- `--resource-group`, `--rg` - Azure resource group
- `--name` - Custom VM name
- `--pool` - Number of VMs to create in parallel
- `--no-auto-connect` - Do not auto-connect via SSH
- `--config` - Config file path
- `--template` - Template name to use for VM configuration
- `--nfs-storage` - NFS storage account name to mount as home directory
- `--no-nfs` - Skip NFS storage mounting (use local home directory only)
- `--no-bastion` - Skip bastion auto-detection and always create public IP
- `--bastion-name` - Explicit bastion host name to use for private VM
- `--yes`, `-y` - Accept all defaults and confirmations (non-interactive mode)

### os-update

Update OS packages on a VM.

Runs 'apt update && apt upgrade -y' on Ubuntu VMs to update all packages.

VM_IDENTIFIER can be:
- Session name (resolved to VM)
- VM name (requires --resource-group or default config)
- IP address (direct connection)


Examples:
    azlin os-update my-session
    azlin os-update azlin-myvm --rg my-resource-group
    azlin os-update 20.1.2.3
    azlin os-update my-vm --timeout 600  # 10 minute timeout


**Usage:**
```bash
azlin main os-update VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--timeout` - Timeout in seconds (default 300)

### prune

Prune inactive VMs based on age and idle time.

Identifies and optionally deletes VMs that are:
- Older than --age-days (default: 1)
- Idle for longer than --idle-days (default: 1)
- Stopped/deallocated (unless --include-running)
- Without named sessions (unless --include-named)


Examples:
    azlin prune --dry-run                    # Preview what would be deleted
    azlin prune                              # Delete VMs idle for 1+ days (default)
    azlin prune --age-days 7 --idle-days 3   # Custom thresholds
    azlin prune --force                      # Skip confirmation
    azlin prune --include-running            # Include running VMs


**Usage:**
```bash
azlin main prune [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--age-days` - Age threshold in days (default: 1)
- `--idle-days` - Idle threshold in days (default: 1)
- `--dry-run` - Preview without deleting
- `--force` - Skip confirmation prompt
- `--include-running` - Include running VMs
- `--include-named` - Include named sessions

### ps

Run 'ps aux' command on all VMs.

Shows running processes on each VM. Output is prefixed with [vm-name].
SSH processes are automatically filtered out.


Examples:
    azlin ps
    azlin ps --rg my-resource-group
    azlin ps --grouped


**Usage:**
```bash
azlin main ps [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--grouped` - Group output by VM instead of prefixing

### session

Set or view session name for a VM.

Session names are labels that help you identify what you're working on.
They appear in the 'azlin list' output alongside the VM name.


Examples:
    # Set session name
    azlin session azlin-vm-12345 my-project

    # View current session name
    azlin session azlin-vm-12345

    # Clear session name
    azlin session azlin-vm-12345 --clear


**Usage:**
```bash
azlin main session VM_NAME SESSION_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--clear` - Clear session name

### snapshot

Manage VM snapshots and scheduled backups.

Enable scheduled snapshots, sync snapshots manually, or manage snapshot schedules.


EXAMPLES:
    # Enable scheduled snapshots (every 24 hours, keep 2)
    $ azlin snapshot enable my-vm --every 24

    # Enable with custom retention (every 12 hours, keep 5)
    $ azlin snapshot enable my-vm --every 12 --keep 5

    # Sync snapshots now (checks all VMs with schedules)
    $ azlin snapshot sync

    # Sync specific VM
    $ azlin snapshot sync --vm my-vm

    # Disable scheduled snapshots
    $ azlin snapshot disable my-vm

    # Show snapshot schedule
    $ azlin snapshot status my-vm


### start

Start a stopped or deallocated VM.


Examples:
    azlin start my-vm
    azlin start my-vm --rg my-resource-group


**Usage:**
```bash
azlin main start VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### status

Show status of VMs in resource group.

Displays detailed status information including power state and IP addresses.


Examples:
    azlin status
    azlin status --rg my-resource-group
    azlin status --vm my-vm


**Usage:**
```bash
azlin main status [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--vm` - Show status for specific VM only

### stop

Stop or deallocate a VM.

Stopping a VM with --deallocate (default) fully releases compute resources
and stops billing for the VM (storage charges still apply).


Examples:
    azlin stop my-vm
    azlin stop my-vm --rg my-resource-group
    azlin stop my-vm --no-deallocate


**Usage:**
```bash
azlin main stop VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--deallocate` - Deallocate to save costs (default: yes)

### storage

Manage Azure Files NFS shared storage.

Create and manage Azure Files NFS storage accounts for sharing
home directories across multiple VMs.


COMMANDS:
    create     Create new NFS storage account
    list       List storage accounts
    status     Show storage status and usage
    delete     Delete storage account
    mount      Mount storage (group with vm/local subcommands)
    unmount    Unmount storage from VM


EXAMPLES:
    # Create 100GB Premium storage
    $ azlin storage create myteam-shared --size 100 --tier Premium

    # List all storage accounts
    $ azlin storage list

    # Mount storage on VM (new syntax)
    $ azlin storage mount vm myteam-shared --vm my-dev-vm

    # Mount storage locally
    $ azlin storage mount local --mount-point ~/azure/

    # Mount storage on VM (backward compatible)
    $ azlin storage mount myteam-shared --vm my-dev-vm

    # Check storage status
    $ azlin storage status myteam-shared

    # Unmount from VM
    $ azlin storage unmount --vm my-dev-vm

    # Delete storage
    $ azlin storage delete myteam-shared


### sync

Sync ~/.azlin/home/ to VM home directory.

Syncs local configuration files to remote VM for consistent
development environment.


Examples:
    azlin sync                    # Interactive VM selection
    azlin sync --vm-name myvm     # Sync to specific VM
    azlin sync --dry-run          # Show what would be synced


**Usage:**
```bash
azlin main sync [OPTIONS]
```

**Options:**
- `--vm-name` - VM name to sync to
- `--dry-run` - Show what would be synced
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path

### tag

Manage Azure VM tags.

Add, remove, and list tags on Azure VMs. Tags help organize
and categorize VMs for easier management and cost tracking.


COMMANDS:
    add        Add tags to a VM
    remove     Remove tags from a VM
    list       List VM tags


EXAMPLES:
    # Add single tag
    $ azlin tag add my-vm environment=production

    # Add multiple tags
    $ azlin tag add my-vm project=web team=backend

    # List VM tags
    $ azlin tag list my-vm

    # Remove tags
    $ azlin tag remove my-vm environment project


### template

Manage VM configuration templates.

Templates allow you to save and reuse VM configurations.
Stored in ~/.azlin/templates/ as YAML files.


SUBCOMMANDS:
    create   Create a new template
    list     List all templates
    delete   Delete a template
    export   Export template to file
    import   Import template from file


EXAMPLES:
    # Create a template interactively
    azlin template create dev-vm

    # List all templates
    azlin template list

    # Delete a template
    azlin template delete dev-vm

    # Export a template
    azlin template export dev-vm my-template.yaml

    # Import a template
    azlin template import my-template.yaml

    # Use a template when creating VM
    azlin new --template dev-vm


### top

Run distributed top command on all VMs.

Shows real-time CPU, memory, load, and top processes across all VMs
in a unified dashboard that updates every N seconds.


Examples:
    azlin top                    # Default: 10s refresh
    azlin top -i 5               # 5 second refresh
    azlin top --rg my-rg         # Specific resource group
    azlin top -i 15 -t 10        # 15s refresh, 10s timeout


Press Ctrl+C to exit the dashboard.


**Usage:**
```bash
azlin main top [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--interval`, `-i` - Refresh interval in seconds (default 10)
- `--timeout`, `-t` - SSH timeout per VM in seconds (default 5)

### update

Update all development tools on a VM.

Updates system packages, programming languages, CLIs, and other dev tools
that were installed during VM provisioning.

VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Tools updated:
- System packages (apt)
- Azure CLI
- GitHub CLI
- npm and npm packages (Copilot, Codex, Claude Code)
- Rust toolchain
- astral-uv


Examples:
    # Update VM by name
    azlin update my-vm

    # Update VM by session name
    azlin update my-project

    # Update VM by IP
    azlin update 20.1.2.3

    # Update with custom timeout (default 300s per tool)
    azlin update my-vm --timeout 600

    # Update with explicit resource group
    azlin update my-vm --rg my-resource-group


**Usage:**
```bash
azlin main update VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--timeout` - Timeout per update in seconds

### vm

Alias for 'new' command. Provision a new Azure VM.

**Usage:**
```bash
azlin main vm [OPTIONS]
```

**Options:**
- `--repo` - GitHub repository URL to clone
- `--vm-size` - Azure VM size
- `--region` - Azure region
- `--resource-group`, `--rg` - Azure resource group
- `--name` - Custom VM name
- `--pool` - Number of VMs to create in parallel
- `--no-auto-connect` - Do not auto-connect via SSH
- `--config` - Config file path
- `--template` - Template name to use for VM configuration
- `--nfs-storage` - NFS storage account name to mount as home directory
- `--no-bastion` - Skip bastion auto-detection and always create public IP
- `--bastion-name` - Explicit bastion host name to use for private VM

### w

Run 'w' command on all VMs.

Shows who is logged in and what they are doing on each VM.


Examples:
    azlin w
    azlin w --rg my-resource-group


**Usage:**
```bash
azlin main w [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
