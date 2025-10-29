# azdo it - Natural Language Azure Management

> "Just tell it what you want, and it figures out how to do it."

**azdoit** brings natural language understanding to Azure infrastructure management. Instead of remembering complex CLI commands, just describe what you want in plain English.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Advanced Features](#advanced-features)
- [Examples](#examples)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Install
```bash
# Via uvx (recommended - always latest)
uvx --from git+https://github.com/rysweet/azlin azlin do "list my vms"

# Or install locally
pip install git+https://github.com/rysweet/azlin
```

### 2. Configure API Key
```bash
# Get your key from: https://console.anthropic.com/
export ANTHROPIC_API_KEY=sk-ant-xxxxx...

# Make it permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export ANTHROPIC_API_KEY=sk-ant-xxxxx...' >> ~/.bashrc
```

### 3. Authenticate with Azure
```bash
az login
```

### 4. Try It!
```bash
azlin do "list all my vms"
azlin do "show me my azure costs"
azlin do "create a new vm called dev-box"
```

---

## Installation

### Option 1: uvx (Recommended)

Run without installing:
```bash
uvx --from git+https://github.com/rysweet/azlin azlin do "your request here"
```

### Option 2: pip install

Install for repeated use:
```bash
pip install git+https://github.com/rysweet/azlin
```

### Option 3: Development Install

Clone and install in editable mode:
```bash
git clone https://github.com/rysweet/azlin
cd azlin
pip install -e .
```

---

## Basic Usage

### Natural Language Flexibility

The AI understands multiple phrasings. All of these work:

**VM Creation:**
- "create a vm called test"
- "provision a new vm named test"
- "make me a vm called test"
- "set up a Standard_D4s_v3 vm"

**Listing:**
- "show me all my vms"
- "list my vms"
- "what vms do I have"

**Be as natural as you'd speak - the AI adapts to your style.**

### The Two Commands

**`azlin do`** - Simple natural language execution
```bash
# Basic command
azlin do "create a vm called test-vm"

# With options
azlin do "list vms" --dry-run --verbose

# Skip confirmation prompts (for automation)
azlin do "delete vm test-vm" --yes
```

**`azlin doit`** - Enhanced with state tracking (Phase 1+)
```bash
# Advanced objective management
azlin doit "provision an AKS cluster with 3 nodes"

# With state persistence and audit logging
azlin doit "create a complete dev environment" --verbose
```

### Command Options

| Option | Short | Description |
|--------|-------|-------------|
| `--dry-run` | | Show what would be executed without running |
| `--yes` | `-y` | Skip confirmation prompts (automation) |
| `--verbose` | `-v` | Show detailed execution information |
| `--resource-group` | `--rg` | Specify Azure resource group |
| `--config` | | Path to config file |
| `--help` | `-h` | Show help message |

---

## Advanced Features

### Dry-Run Mode

Preview commands before execution:
```bash
azlin do "delete all test vms" --dry-run

# Output:
# Commands to execute:
#   1. azlin kill test-vm-1
#   2. azlin kill test-vm-2
#   3. azlin kill test-vm-3
# [DRY RUN] Would execute the above commands.
```

### Automation Mode

Skip all prompts for CI/CD:
```bash
#!/bin/bash
export ANTHROPIC_API_KEY=...

# Create resources
azlin do "create vm ci-test-001" --yes

# Run tests
./run-tests.sh

# Cleanup
azlin do "delete vm ci-test-001" --yes
```

### Verbose Output

See what's happening under the hood:
```bash
azlin do "list vms" --verbose

# Shows:
# - Intent parsing details
# - Confidence scores
# - Generated commands
# - Execution results
# - API interactions
```

### State Persistence (doit only)

Track objectives across sessions:
```bash
# Create objective
azlin doit "provision 5 test vms"

# State saved to: ~/.azlin/objectives/<uuid>.json
# Audit log: ~/.azlin/audit.log

# List objectives
ls ~/.azlin/objectives/

# View audit trail
tail -f ~/.azlin/audit.log
```

---

## Examples

### VM Management

#### Create a VM
```bash
# Basic VM
azlin do "create a new vm called dev-box"

# VM with specific size
azlin do "create a Standard_D4s_v3 vm called ml-training"

# Multiple VMs
azlin do "create 3 test vms"

# GPU-enabled VM
azlin do "provision a vm with GPU support for machine learning"
```

#### List and Status
```bash
# List all VMs
azlin do "show me all my vms"

# Check specific VM
azlin do "what's the status of dev-box"

# Show VM details
azlin do "give me details about all running vms"
```

#### VM Lifecycle
```bash
# Start VM
azlin do "start the vm called dev-box"

# Stop VM
azlin do "stop all test vms"

# Update tools
azlin do "update dev-box"

# Delete VM
azlin do "delete the vm called old-test-vm"
```

### File Operations

#### Sync Files
```bash
# Sync to one VM
azlin do "sync my home directory to dev-box"

# Sync to all VMs
azlin do "sync all my vms"

# Sync specific files
azlin do "copy myproject.tar.gz to dev-box"
```

#### File Transfer
```bash
# Upload
azlin do "copy local-file.txt to vm dev-box"

# Download
azlin do "get results.csv from dev-box"
```

### Cost Management

#### Check Costs
```bash
# Current costs
azlin do "what are my azure costs"

# Historical costs
azlin do "show me costs for the last week"

# Costs by VM
azlin do "how much is dev-box costing me"

# Cost optimization
azlin do "show me my costs and stop any idle vms"
```

### Storage Operations

#### Create Storage
```bash
# Create NFS storage
azlin do "create 100GB shared storage called team-data"

# List storage
azlin do "show all my storage accounts"

# Check usage
azlin do "how much space is left on team-data"
```

### Multi-Step Operations

#### Development Environment
```bash
# Full setup
azlin do "set up a new development environment called devenv"

# With repository
azlin do "create a vm with my dotfiles repo"

# Complete stack
azlin do "provision a vm, mount storage, and sync my files"
```

#### Fleet Management
```bash
# Provision fleet
azlin do "create 5 test vms and sync them all"

# Update fleet
azlin do "update all my vms"

# Stop fleet
azlin do "stop all test vms"

# Cleanup fleet
azlin do "delete all vms older than 7 days"
```

### Resource Cleanup

#### Individual Resources
```bash
# Delete specific VM
azlin do "delete vm test-001"

# With confirmation skip
azlin do "delete vm test-001" --yes
```

#### Bulk Cleanup
```bash
# By pattern
azlin do "delete all test vms"

# By age
azlin do "delete vms older than 30 days"

# All resources in group
azlin do "delete everything in resource group test-rg"
```

#### Safe Cleanup Workflow
```bash
# 1. List what will be deleted
azlin do "show me all test vms" --verbose

# 2. Preview deletion
azlin do "delete all test vms" --dry-run

# 3. Confirm and execute
azlin do "delete all test vms"
# (asks for confirmation)

# 4. Verify cleanup
azlin do "list all vms"
```

### Error Handling

#### Invalid Requests
```bash
# Out of scope
azlin do "make me coffee"
# Recognized as invalid, 0% confidence, no execution

# Ambiguous request
azlin do "do something with my vm"
# Low confidence warning, asks for clarification
```

#### Recovery from Failures
```bash
# If command fails
azlin do "create vm test" --verbose
# Shows detailed error from Azure
# Suggests fixes

# Retry with --dry-run first
azlin do "create vm test" --dry-run
# Verify command looks correct

# Then execute
azlin do "create vm test"
```

---

## Configuration

### API Key Setup

#### Method 1: Environment Variable (Recommended)
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx...

# Make permanent
echo 'export ANTHROPIC_API_KEY=sk-ant-xxxxx...' >> ~/.bashrc
source ~/.bashrc
```

#### Method 2: Secure File
```bash
# Create secure key file
echo 'sk-ant-xxxxx...' > ~/.anthropic_api_key
chmod 600 ~/.anthropic_api_key

# Load in shell startup
echo 'export ANTHROPIC_API_KEY=$(cat ~/.anthropic_api_key)' >> ~/.bashrc
```

#### Method 3: Azure Key Vault (Production)
```bash
# Store in Key Vault
az keyvault secret set \
  --vault-name my-vault \
  --name anthropic-api-key \
  --value sk-ant-xxxxx...

# Retrieve and use
export ANTHROPIC_API_KEY=$(az keyvault secret show \
  --vault-name my-vault \
  --name anthropic-api-key \
  --query value -o tsv)
```

### Azure Configuration

#### Set Default Resource Group
```bash
azlin config set default_resource_group=my-rg

# Or use --rg flag
azlin do "list vms" --rg my-rg
```

#### Set Default Region
```bash
azlin config set default_region=eastus
```

#### View Config
```bash
cat ~/.azlin/config.toml
```

---

## Troubleshooting

### Common Issues

#### 1. "ANTHROPIC_API_KEY not set"
```bash
# Solution: Set the API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx...

# Verify
echo $ANTHROPIC_API_KEY
```

#### 2. "Not authenticated with Azure"
```bash
# Solution: Login to Azure
az login

# Verify
az account show
```

#### 3. "No resource group specified"
```bash
# Solution 1: Set default
azlin config set default_resource_group=my-rg

# Solution 2: Use --rg flag
azlin do "list vms" --rg my-rg
```

#### 4. "Command timed out"
```bash
# VM creation can take 10+ minutes
# Workaround: Use native command for long operations
azlin new --name my-vm

# Or increase timeout (future enhancement)
```

#### 5. "Low confidence warning"
```bash
# Your request is ambiguous
# Solution: Be more specific
❌ azlin do "do something with my vm"
✅ azlin do "start the vm called dev-box"
```

### Debugging

#### Enable Verbose Mode
```bash
azlin do "your command" --verbose

# Shows:
# - Parsed intent
# - Confidence score
# - Generated commands
# - Execution details
# - API responses
```

#### Check Logs
```bash
# Audit log (doit only)
tail -f ~/.azlin/audit.log

# Recent commands
history | grep "azlin do"

# Test output logs
ls /tmp/azlin-*.log
```

#### Test Without Execution
```bash
# Dry-run mode
azlin do "risky command" --dry-run

# Verify parsing
azlin do "your command" --dry-run --verbose
```

---

## Integration Testing

Run the comprehensive test suite:

```bash
# Set API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx...

# Run safe tests (no VM creation)
SKIP_VM_CREATION=1 ./scripts/test_agentic_integration.sh

# Run all tests (creates real VM, costs money)
./scripts/test_agentic_integration.sh
```

See [REAL_AZURE_TESTING.md](REAL_AZURE_TESTING.md) for detailed testing procedures.

---

## Best Practices

### 1. Always Use Dry-Run First
```bash
# Preview before executing
azlin do "delete all vms" --dry-run

# Verify output looks correct
# Then run for real
azlin do "delete all vms"
```

### 2. Be Specific in Requests
```bash
❌ "do something"
✅ "create a Standard_B2s vm called web-server in eastus"

❌ "fix my vm"
✅ "restart the vm called dev-box"
```

### 3. Use --yes for Automation
```bash
# In scripts/CI
azlin do "create vm ci-test" --yes
```

### 4. Monitor Costs
```bash
# Check before creating resources
azlin do "what are my current costs"

# After major operations
azlin do "show me costs for today"
```

### 5. Clean Up Regularly
```bash
# Weekly cleanup script
#!/bin/bash
azlin do "delete vms older than 7 days" --yes
azlin do "show me current costs"
```

---

## Security

### API Key Protection

**DO:**
- ✅ Store in environment variable
- ✅ Use chmod 600 on key files
- ✅ Rotate keys regularly
- ✅ Use Azure Key Vault in production

**DON'T:**
- ❌ Commit keys to git
- ❌ Share keys in chat/email
- ❌ Use same key across environments
- ❌ Log API keys

### Azure Permissions

Requires:
- Azure subscription access
- VM creation permissions
- Storage account access
- Cost management read access

### Audit Trail

All `azlin doit` commands are logged:
```bash
# View audit log
tail -f ~/.azlin/audit.log

# Entries include:
# - Timestamp
# - Command executed
# - User
# - Result
# - Resources created/modified
```

---

## Performance

### Response Times

| Operation | Time |
|-----------|------|
| Intent parsing | 1-2 seconds |
| List VMs | 2-3 seconds |
| Cost query | 3-5 seconds |
| VM creation | 10-15 minutes |
| File sync | Varies by size |

### Optimization Tips

1. **Use native commands for long operations:**
   ```bash
   # Faster
   azlin new --name my-vm

   # Slower (2 extra seconds for parsing)
   azlin do "create vm my-vm"
   ```

2. **Cache context when possible:**
   ```bash
   # Lists VMs once for context
   azlin do "show vm status"
   ```

3. **Batch operations:**
   ```bash
   # Single request
   azlin do "create 5 vms and sync them"

   # vs 6 separate requests
   azlin do "create vm-1"
   azlin do "create vm-2"
   ...
   ```

---

## Roadmap

### Phase 1: Core Infrastructure ✅ (Current)
- Natural language parsing
- Command execution
- State persistence
- Audit logging

### Phase 2: Strategy Selection (Next)
- Multi-strategy execution
- Azure CLI strategy
- Automatic fallback

### Phase 3: Cost Management
- Real-time cost estimation
- Budget alerts
- Cost optimization suggestions

### Phase 4: Terraform Integration
- Generate Terraform code
- State management
- Plan/apply workflow

### Phase 5: Failure Recovery
- Automatic retry logic
- MS Learn documentation research
- Intelligent error handling

### Phase 6: MCP Server
- Tool discovery
- Dynamic capability expansion
- Third-party integrations

### Phase 7: Advanced Features
- Multi-cloud support
- Team collaboration
- Auto-scaling policies

---

## Support

### Documentation
- [README.md](../README.md) - Getting started
- [AZLIN.md](AZLIN.md) - Traditional command reference
- [REAL_AZURE_TESTING.md](REAL_AZURE_TESTING.md) - Testing procedures
- [PHASE1_COMPLETE.md](PHASE1_COMPLETE.md) - Implementation details

### Getting Help
- GitHub Issues: [rysweet/azlin/issues](https://github.com/rysweet/azlin/issues)
- Command help: `azlin do --help`
- Verbose mode: `azlin do "command" --verbose`

### Contributing
- Follow the [brick philosophy](../README.md#philosophy)
- Write tests for new features
- Update documentation
- Run pre-commit hooks

---

## License

See [LICENSE](../LICENSE) for details.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Last Updated:** 2025-10-21
**Version:** 2.0.0 (Phase 1 Complete)
