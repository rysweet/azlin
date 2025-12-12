# azlin github-runner

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


## Description

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

## Usage

```bash
azlin github-runner
```

## Subcommands

### disable

Disable GitHub Actions runner fleet.

Stops auto-scaling and optionally destroys all runners in the fleet.


Examples:
  $ azlin github-runner disable --pool ci-workers
  $ azlin github-runner disable --pool ci-workers --keep-vms


**Usage:**
```bash
azlin github-runner disable [OPTIONS]
```

**Options:**
- `--pool` - VM pool name
- `--keep-vms` - Keep VMs running (don't delete)

### enable

Enable GitHub Actions runner fleet on VM pool.

Configures a VM pool to act as auto-scaling GitHub Actions runners.
Runners are ephemeral (destroyed after each job) for security.


REPO format: owner/repo (e.g., microsoft/vscode)
POOL: Unique name for this runner fleet


GitHub Token:
Set GITHUB_TOKEN environment variable with a PAT that has:
  - repo scope (for repository runners)
  - admin:org scope (for organization runners)


Examples:
  $ export GITHUB_TOKEN=ghp_your_token_here
  $ azlin github-runner enable --repo myorg/myrepo --pool ci-workers
  $ azlin github-runner enable --repo myorg/myrepo --pool gpu-runners \
      --min-runners 1 --max-runners 5 --labels gpu,cuda --vm-size Standard_NC6


**Usage:**
```bash
azlin github-runner enable [OPTIONS]
```

**Options:**
- `--repo` - GitHub repository (format: owner/repo)
- `--pool` - VM pool name for runners
- `--labels` - Comma-separated runner labels (default: self-hosted,linux)
- `--min-runners` - Minimum number of runners (default: 0)
- `--max-runners` - Maximum number of runners (default: 10)
- `--resource-group`, `--rg` - Azure resource group
- `--region` - Azure region
- `--vm-size` - Azure VM size (default: Standard_D2s_v3)

### scale

Manually scale runner fleet to target count.

Provisions or destroys runners to reach the target count.
Respects min/max constraints from fleet configuration.


Examples:
  $ azlin github-runner scale --pool ci-workers --count 5
  $ azlin github-runner scale --pool ci-workers --count 0


**Usage:**
```bash
azlin github-runner scale [OPTIONS]
```

**Options:**
- `--pool` - VM pool name
- `--count` - Target runner count

### status

Show GitHub Actions runner fleet status.

Displays current status of runners in the fleet including:
- Active runners
- Queue depth
- Recent scaling actions


Examples:
  $ azlin github-runner status --pool ci-workers


**Usage:**
```bash
azlin github-runner status [OPTIONS]
```

**Options:**
- `--pool` - VM pool name
