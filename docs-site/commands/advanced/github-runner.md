# azlin github-runner

Deploy self-hosted GitHub Actions runners on azlin VMs for CI/CD pipelines.

## Description

Provision and manage self-hosted GitHub Actions runners on azlin VMs. Scale CI/CD capacity, use custom VM sizes (including GPU), and reduce GitHub Actions costs.

## Usage

```bash
azlin github-runner [COMMAND] [OPTIONS]
```

## Commands

| Command | Description |
|---------|-------------|
| `create` | Create runner on VM |
| `list` | List all runners |
| `delete` | Remove runner |
| `logs` | View runner logs |

## Examples

### Create GitHub Runner

```bash
# Create runner on new VM
azlin github-runner create \
  --repo owner/repo \
  --name my-runner \
  --vm-size Standard_D4s_v3
```

**Output:**
```
Creating GitHub Actions runner...
  Repository: owner/repo
  Runner name: my-runner
  VM: azlin-runner-001

Provisioning VM...
✓ VM created: azlin-runner-001

Installing GitHub Runner...
✓ Runner installed and configured

Registering with GitHub...
✓ Runner registered: my-runner

Runner is ready!
  Status: Online
  VM: azlin-runner-001
  URL: https://github.com/owner/repo/settings/actions/runners

Use in workflow:
  runs-on: self-hosted
```

### Create GPU Runner

```bash
# ML/AI workflows with GPU
azlin github-runner create \
  --repo owner/ml-project \
  --name gpu-runner \
  --vm-size Standard_NC6 \
  --labels gpu,ml,cuda
```

### List All Runners

```bash
azlin github-runner list
```

**Output:**
```
GitHub Actions Runners:

NAME         VM               STATUS   LABELS           REPO
my-runner    azlin-runner-001 Online   self-hosted      owner/repo
gpu-runner   azlin-runner-002 Online   gpu,ml,cuda      owner/ml-project
ci-runner    azlin-runner-003 Idle     self-hosted,ci   owner/webapp
```

### Scale Runner Fleet

```bash
# Create multiple runners for parallel jobs
for i in {1..5}; do
  azlin github-runner create \
    --repo owner/repo \
    --name ci-runner-$i \
    --labels ci,parallel
done
```

### Delete Runner

```bash
# Remove runner and VM
azlin github-runner delete my-runner
```

## Common Workflows

### CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI Pipeline
on: [push]

jobs:
  test:
    runs-on: self-hosted  # Uses azlin runner
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: pytest
```

### GPU-Accelerated Builds

```yaml
# .github/workflows/ml-training.yml
name: ML Training
on: [push]

jobs:
  train:
    runs-on: [self-hosted, gpu, ml]
    steps:
      - uses: actions/checkout@v3
      - name: Train model
        run: python train.py --gpu
```

### Cost Optimization

```bash
# Use spot instances for cost savings
azlin github-runner create \
  --repo owner/repo \
  --name spot-runner \
  --vm-size Standard_D4s_v3 \
  --spot-instance

# Auto-stop idle runners
azlin github-runner auto-stop --idle-minutes 30
```

## Security

Runners are isolated:
- Dedicated VM per runner
- Secure token registration
- Network isolation
- Automatic cleanup

## Pricing

GitHub-hosted vs. self-hosted comparison:

| Runner Type | Cost (per minute) | Notes |
|-------------|-------------------|-------|
| GitHub-hosted | $0.008 | 2-core, 7GB RAM |
| azlin Standard_D2s_v3 | $0.0016 | 2-core, 8GB RAM (5x cheaper) |
| azlin Standard_NC6 (GPU) | $0.015 | 1x K80 GPU (not available on GitHub) |

## Related Commands

- [`azlin new`](../vm/new.md) - Provision runner VM
- [`azlin kill`](../vm/kill.md) - Delete runner VM
- [`azlin list`](../vm/list.md) - List runner VMs

## Deep Links

- [GitHub runner implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/github_runner.py)
- [Runner specification](https://github.com/rysweet/azlin/blob/main/docs/GITHUB_RUNNER_SPECIFICATION.md)

## See Also

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Runners](../../advanced/github-runners.md)
