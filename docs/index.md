# azlin Documentation

## Quick Start

- [Quick Reference](./QUICK_REFERENCE.md) — Common commands at a glance
- [README](../README.md) — Installation, setup, and feature overview

## Reference

- [API Reference](./API_REFERENCE.md) — Programmatic API for automation
- [CLI Command Reference](./reference/cli-python-parity.md) — All CLI flags, defaults, and migration notes
- [Logs Command](./reference/logs-command.md) — View and stream VM log files
- [Restore Command](./reference/cli-help-restore.md) — Restore terminal sessions
- [Destroy Command](./reference/destroy-command.md) — Autonomous resource cleanup
- [Configuration: Default Behaviors](./reference/config-default-behaviors.md) — Auto-sync, auto-detect, log viewer defaults
- [Configuration: Terminal/Restore](./reference/configuration-reference.md) — Terminal launcher and restore settings
- [Azure CLI Detection](./reference/azure-cli-detection.md) — WSL2 az CLI detection logic

## How-To Guides

- [View VM Logs](./how-to/view-vm-logs.md) — View and stream log files from VMs
- [Restore Sessions](./how-to/restore-sessions.md) — Reconnect to all active sessions
- [Separate Home Disk](./how-to/separate-home-disk.md) — Add a dedicated /home disk
- [Azure CLI WSL2 Setup](./how-to/azure-cli-wsl2-setup.md) — Configure az CLI under WSL2
- [Network Security](./how-to/network-security-enhancements.md) — NSG and bastion setup
- [Troubleshoot Connections](./how-to/troubleshoot-connection-issues.md) — Diagnose SSH and bastion issues

## Tutorials

- [Quick Start Restore](./tutorials/quick-start-restore.md) — First-time session restore walkthrough
- [Platform Setup](./tutorials/platform-setup-restore.md) — Platform-specific terminal setup
- [WSL2 Setup](./tutorials/wsl2-setup-walkthrough.md) — Full WSL2 environment walkthrough

## Architecture & Design

- [Architecture](./ARCHITECTURE.md) — System architecture overview
- [Design](./DESIGN.md) — Design decisions and rationale
- [Code Atlas](./atlas/index.md) — Auto-generated architecture diagrams

## Features

- [Auto-Sync SSH Keys](./features/auto-sync-keys.md)
- [Auto-Detect Resource Group](./features/auto-detect-rg.md)
- [Health TUI Dashboard](./features/health-tui-dashboard.md)
- [Session Restore](./features/session-restore.md)
- [Tmux Session Status](./features/tmux-session-status.md)
- [VM Lifecycle Automation](./features/vm-lifecycle-automation.md)

## Monitoring

- [Monitoring Quick Reference](./monitoring-quick-reference.md) — Dashboard, alerts, metrics
- [Monitoring Overview](./monitoring.md) — Full monitoring guide
