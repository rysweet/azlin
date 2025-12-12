# azlin azdoit-main

Execute natural language Azure commands using AI (standalone CLI).

azdoit v2.0 uses amplihack's autonomous goal-seeking engine to iteratively
pursue Azure infrastructure objectives and generate example scripts.


Quick Start:
    1. Set API key: export ANTHROPIC_API_KEY=your-key-here
    2. Get key from: https://console.anthropic.com/
    3. Try: azdoit "create 3 VMs called test-vm-{1,2,3}"


Examples:
    azdoit "create a VM called dev-box"
    azdoit "provision an AKS cluster with monitoring"
    azdoit "set up a storage account with blob containers"
    azdoit --max-turns 30 "set up a complete dev environment"


How It Works:
    - azdoit constructs a prompt template from your request
    - Delegates to amplihack auto mode for iterative execution
    - Auto mode researches Azure docs and generates example scripts
    - Output includes reusable infrastructure-as-code


Requirements:
    - ANTHROPIC_API_KEY environment variable (get from console.anthropic.com)
    - amplihack CLI installed (pip install amplihack)
    - Azure CLI authenticated (az login)


For More Information:
    See docs/AZDOIT_REQUIREMENTS_V2.md for architecture details


## Description

Execute natural language Azure commands using AI (standalone CLI).
azdoit v2.0 uses amplihack's autonomous goal-seeking engine to iteratively
pursue Azure infrastructure objectives and generate example scripts.

Quick Start:
1. Set API key: export ANTHROPIC_API_KEY=your-key-here
2. Get key from: https://console.anthropic.com/
3. Try: azdoit "create 3 VMs called test-vm-{1,2,3}"

Examples:
azdoit "create a VM called dev-box"
azdoit "provision an AKS cluster with monitoring"
azdoit "set up a storage account with blob containers"
azdoit --max-turns 30 "set up a complete dev environment"

How It Works:
- azdoit constructs a prompt template from your request
- Delegates to amplihack auto mode for iterative execution
- Auto mode researches Azure docs and generates example scripts
- Output includes reusable infrastructure-as-code

Requirements:
- ANTHROPIC_API_KEY environment variable (get from console.anthropic.com)
- amplihack CLI installed (pip install amplihack)
- Azure CLI authenticated (az login)

For More Information:
See docs/AZDOIT_REQUIREMENTS_V2.md for architecture details

## Usage

```bash
azlin azdoit-main REQUEST [OPTIONS]
```

## Arguments

- `REQUEST` - No description available

## Options

- `--dry-run` - Show execution plan without running commands
- `--yes`, `-y` - Skip confirmation prompts
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--verbose`, `-v` - Show detailed execution information
