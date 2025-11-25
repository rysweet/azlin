# Command Reference

Complete reference for all azlin commands organized by category.

## Command Groups

### Core Commands
- [VM Commands](vm/index.md) - VM lifecycle management
- [Auth Commands](auth/index.md) - Authentication profiles
- [Context Commands](context/index.md) - Multi-tenant context management
- [Storage Commands](storage/index.md) - Azure Files NFS storage

### Operations & Monitoring
- [Batch Commands](batch/index.md) - Batch operations across VMs
- [Fleet Commands](fleet/overview.md) - Distributed command orchestration
- [Util Commands](util/index.md) - Utilities (cp, sync, logs, ps, w, top, cost, update)

### Environment & Configuration
- [Env Commands](env/index.md) - Environment variable management
- [Snapshot Commands](snapshot/index.md) - VM snapshots and backups
- [Template Commands](template/index.md) - VM configuration templates
- [Keys Commands](keys/index.md) - SSH key management

### Security & Networking
- [Bastion Commands](bastion/index.md) - Azure Bastion for secure access
- [IP Commands](ip/index.md) - IP diagnostics and troubleshooting

### AI & Automation
- [Do Command](ai/do.md) - Natural language VM management
- [Doit Commands](doit/index.md) - Autonomous infrastructure deployment
- [Autopilot Commands](autopilot/index.md) - Cost optimization and lifecycle management

### Advanced Features
- [Compose Commands](compose/index.md) - Multi-VM docker-compose orchestration
- [GitHub Runner Commands](github-runner/index.md) - GitHub Actions runner fleets


## Quick Reference

### VM Lifecycle
- `azlin new` - Create a new VM
- `azlin clone` - Clone a VM with contents
- `azlin list` - List all VMs
- `azlin connect` - Connect to a VM
- `azlin start` - Start a stopped VM
- `azlin stop` - Stop a running VM
- `azlin status` - Show VM status
- `azlin session` - Manage session names
- `azlin tag` - Manage VM tags
- `azlin update` - Update development tools
- `azlin destroy` - Delete a VM
- `azlin kill` - Delete VM and resources
- `azlin killall` - Delete all VMs
- `azlin prune` - Delete idle VMs

### AI-Powered Features
- `azlin do "<request>"` - Natural language commands
- `azlin doit deploy "<infrastructure>"` - Deploy infrastructure
- `azlin autopilot enable` - Enable cost optimization

### Storage & Files
- `azlin storage create` - Create NFS storage
- `azlin storage mount` - Mount storage on VMs
- `azlin storage mount local` - Mount on macOS
- `azlin storage list` - List storage accounts
- `azlin cp` - Copy files to/from VMs
- `azlin sync` - Sync home directory

### Monitoring & Operations
- `azlin status` - Show VM status
- `azlin w` - Show who is logged in
- `azlin ps` - Show running processes
- `azlin top` - Distributed resource monitoring
- `azlin cost` - Show cost estimates
- `azlin logs` - View VM logs

### Batch Operations
- `azlin batch exec` - Execute on multiple VMs
- `azlin batch sync` - Sync multiple VMs
- `azlin batch start` - Start multiple VMs
- `azlin batch stop` - Stop multiple VMs
- `azlin batch update` - Update multiple VMs

### Environment & Snapshots
- `azlin env set` - Set environment variables
- `azlin env list` - List environment variables
- `azlin snapshot create` - Create VM snapshot
- `azlin snapshot restore` - Restore from snapshot

### Authentication & Context
- `azlin auth setup` - Setup service principal
- `azlin auth list` - List auth profiles
- `azlin context create` - Create context
- `azlin context use` - Switch context

### Advanced Features
- `azlin compose up` - Deploy multi-VM compose
- `azlin github-runner enable` - Enable runner fleet
- `azlin bastion setup` - Setup Azure Bastion
- `azlin ip check` - Check IP configuration
