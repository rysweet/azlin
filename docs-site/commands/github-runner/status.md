# azlin github-runner status

Show GitHub Actions runner fleet status.

## Synopsis

```bash
azlin github-runner status --pool <pool-name>
```

## Examples

```bash
azlin github-runner status --pool ci-workers
```

## Output

```
GitHub Runner Fleet Status

Pool: ci-workers
Repository: myorg/myrepo
Status: Active

Runners:
  ci-worker-1: Online (running job #1234)
  ci-worker-2: Online (idle)
  ci-worker-3: Online (idle)

Scaling:
  Current: 3 runners
  Min: 2 runners
  Max: 20 runners
  Queue: 5 jobs waiting

Statistics (Last 24h):
  Jobs completed: 145
  Average job time: 8m 32s
  Total cost: $24.50
```

## Related Commands

- [azlin github-runner enable](enable.md) - Enable fleet
- [azlin github-runner scale](scale.md) - Scale fleet
