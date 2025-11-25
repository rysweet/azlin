# Getting Started with azlin

Welcome to azlin! This guide will help you set up and create your first Azure development VM in minutes.

## What You'll Learn

In this section, you'll learn how to:

1. **[Install azlin](installation.md)** - Get azlin set up on your system
2. **[Quick Start](quickstart.md)** - Create your first VM in 5 minutes
3. **[First VM](first-vm.md)** - Detailed walkthrough of VM creation
4. **[Basic Concepts](concepts.md)** - Understand azlin's core concepts

## Prerequisites

Before you start, make sure you have:

- **Azure Account** - [Create a free account](https://azure.microsoft.com/free/)
- **Python 3.12+** - [Download Python](https://www.python.org/downloads/)
- **Azure CLI** - [Install Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- **SSH Client** - Pre-installed on macOS/Linux, [Download for Windows](https://www.openssh.com/)

## Quick Start

If you just want to dive in:

```bash
# Install azlin
uvx --from git+https://github.com/rysweet/azlin azlin new

# Login to Azure
az login

# Create your first VM
azlin new --name myproject
```

That's it! azlin will guide you through the rest.

## Learning Path

### 1. New to Azure?
Start with [Installation](installation.md) to set up Azure CLI and authentication.

### 2. Experienced Azure User?
Jump to [Quick Start](quickstart.md) to create your first VM immediately.

### 3. Want to Understand More?
Read [Basic Concepts](concepts.md) to understand how azlin works.

### 4. Ready to Explore?
Check out [Authentication](../authentication/index.md) for advanced auth setups.

## What's Next?

After creating your first VM:

- **[Connect to VMs](../vm-lifecycle/connecting.md)** - SSH into your VMs
- **[Manage Storage](../storage/index.md)** - Set up shared NFS storage
- **[Transfer Files](../file-transfer/index.md)** - Copy files to/from VMs
- **[Monitor VMs](../monitoring/index.md)** - Track resource usage

## Need Help?

- **In-app help**: Run `azlin --help` or `azlin <command> --help`
- **Troubleshooting**: Check [Common Issues](../troubleshooting/common-issues.md)
- **GitHub Issues**: [Report bugs](https://github.com/rysweet/azlin/issues)
- **Discussions**: [Ask questions](https://github.com/rysweet/azlin/discussions)

---

*Ready to begin?* Start with [Installation →](installation.md)
