# azlin do

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


## Description

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

## Usage

```bash
azlin do REQUEST [OPTIONS]
```

## Arguments

- `REQUEST` - No description available

## Options

- `--dry-run` - Show execution plan without running commands
- `--yes`, `-y` - Skip confirmation prompts
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--verbose`, `-v` - Show detailed execution information
