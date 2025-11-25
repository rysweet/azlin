# GitHub Runner Commands

Manage GitHub Actions self-hosted runner fleets on azlin VMs.

## Overview

Transform azlin VMs into auto-scaling GitHub Actions runners for massive CI/CD parallelism improvements.

## Features

- **Ephemeral runners**: Per-job lifecycle
- **Auto-scaling**: Based on job queue
- **Secure**: Runner rotation per job
- **Cost tracking**: Per-job cost monitoring

## Commands

- [enable](enable.md) - Enable runner fleet on VM pool
- [disable](disable.md) - Disable runner fleet
- [status](status.md) - Show runner fleet status
- [scale](scale.md) - Manually scale runner fleet

## Quick Start

```bash
# Enable fleet
azlin github-runner enable --repo myorg/myrepo --pool ci-workers

# Check status
azlin github-runner status --pool ci-workers

# Scale manually
azlin github-runner scale --pool ci-workers --count 10

# Disable
azlin github-runner disable --pool ci-workers
```

## Related Commands

- [azlin new](../vm/new.md) - Create VMs for runners
- [azlin tag](../vm/tag.md) - Tag VMs for pool organization
