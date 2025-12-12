# azlin costs

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


## Description

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

## Usage

```bash
azlin costs
```

## Subcommands

### actions

Execute cost-saving actions.


Examples:
    azlin costs actions list --rg my-rg
    azlin costs actions execute --rg my-rg --dry-run
    azlin costs actions execute --rg my-rg --priority high


**Usage:**
```bash
azlin costs actions ACTION [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--priority` - Execute only high-priority actions
- `--dry-run` - Show what would be done without executing

### budget

Manage budgets and alerts.


Examples:
    azlin costs budget set --rg my-rg --amount 1000 --threshold 80
    azlin costs budget show --rg my-rg
    azlin costs budget alerts --rg my-rg


**Usage:**
```bash
azlin costs budget ACTION [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--amount` - Budget amount in USD
- `--threshold` - Alert threshold percentage (e.g., 80)

### dashboard

View current costs and spending dashboard.

Shows current month costs, daily spending, and resource breakdown.


Examples:
    azlin costs dashboard --resource-group my-rg
    azlin costs dashboard --rg my-rg --refresh


**Usage:**
```bash
azlin costs dashboard [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--refresh` - Force refresh (ignore cache)

### history

Analyze historical cost data and trends.


Examples:
    azlin costs history --resource-group my-rg
    azlin costs history --rg my-rg --days 90


**Usage:**
```bash
azlin costs history [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--days` - Number of days to analyze

### recommend

Get cost optimization recommendations.


Examples:
    azlin costs recommend --resource-group my-rg
    azlin costs recommend --rg my-rg --priority high


**Usage:**
```bash
azlin costs recommend [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group name
- `--priority` - Filter by priority (low, medium, high)
