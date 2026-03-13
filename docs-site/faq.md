# Frequently Asked Questions

## General

### What is azlin?

azlin is a CLI tool for provisioning and managing Azure Ubuntu VMs for development. It automates VM creation, tool installation, SSH setup, and session management.

### What language is azlin written in?

azlin is written in Rust (current version 2.6.17), providing 75-85x faster startup than the original Python implementation. A Python bridge (`azlin-py`) is still available for backward compatibility.

### How much does it cost?

azlin itself is free and open source (MIT license). You pay only for Azure resources (VMs, storage, networking). azlin includes cost tracking (`azlin cost`) and auto-stop for idle VMs to minimize costs.

### What Azure VM sizes are supported?

Any Azure VM size available in your subscription. Common choices for development:

- `Standard_B2s` - Budget-friendly, burstable (2 vCPUs, 4 GB RAM)
- `Standard_D2s_v3` - General purpose (2 vCPUs, 8 GB RAM)
- `Standard_D4s_v3` - Power user (4 vCPUs, 16 GB RAM)
- `Standard_D8s_v3` - Heavy workloads (8 vCPUs, 32 GB RAM)

## Installation

### Do I need Python installed?

No. The recommended installation is a pre-built binary download which has no dependencies other than Azure CLI. Python is only needed if you use `uvx` or `pip` installation methods.

### How do I update azlin?

```bash
azlin self-update
```

This downloads the latest binary from GitHub Releases and replaces the current one.

### Does azlin work on Windows?

azlin works on Windows via WSL2. The binary runs natively on Linux, and WSL2 provides a Linux environment. Native Windows support is available for basic commands but WSL2 is recommended for the full experience (SSH, tmux, X11 forwarding).

## VM Management

### How long does it take to create a VM?

Typically 4-7 minutes. The breakdown:

- VM provisioning: 4-5 minutes (Azure API)
- Tool installation via cloud-init: 2-3 minutes
- SSH setup: a few seconds

### What tools are pre-installed on VMs?

Every VM gets: Docker, Azure CLI, GitHub CLI, Git, Node.js, Python 3.13+, Rust, Go, .NET, GitHub Copilot CLI, OpenAI Codex CLI, and Claude Code CLI.

### Can I customize what gets installed?

Yes, through templates (`azlin template create`) and custom cloud-init scripts. You can also install additional tools after VM creation.

### How do I access a GUI on the VM?

azlin supports two approaches:

- **X11 forwarding** for lightweight apps: `azlin connect --x11 myvm`
- **VNC desktop** for full desktop sessions: `azlin gui myvm`

See the [GUI Forwarding guide](advanced/gui-forwarding.md) for details.

### Can I share storage between VMs?

Yes. Use Azure Files NFS storage:

```bash
azlin storage create
azlin storage mount --vm myvm1
azlin storage mount --vm myvm2
```

## Networking

### Does my VM need a public IP?

No. azlin supports Azure Bastion for secure access to VMs without public IPs. All features including GUI forwarding work through Bastion tunnels.

### How is SSH secured?

azlin uses Ed25519 key-based authentication only (no passwords). Keys are stored at `~/.ssh/azlin_key` with strict permissions. You can rotate keys with `azlin keys rotate`.

## Troubleshooting

### `azlin list` is slow

The first call queries Azure APIs. Subsequent calls use a local cache. Force a refresh with `azlin list --refresh`.

### VM creation fails with quota error

You've hit your Azure vCPU quota for the region. Options:

- Try a different region: `azlin new --name myvm --region westus2`
- Request a quota increase in the Azure portal
- Use a smaller VM size: `azlin new --name myvm --vm-size Standard_B2s`

Check your quota with `az vm list-usage --location <region>`.

### I can't connect to my VM

Common causes:

- VM is stopped (`azlin start myvm`)
- NSG rules blocking SSH (port 22)
- SSH key mismatch

---

Have a question not covered here? [Open a discussion](https://github.com/rysweet/azlin/discussions).
