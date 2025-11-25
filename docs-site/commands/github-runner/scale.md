# azlin github-runner scale

Manually scale runner fleet to target count.

## Synopsis

```bash
azlin github-runner scale --pool <pool-name> --count <number>
```

## Options

| Option | Description |
|--------|-------------|
| `--pool TEXT` | VM pool name **[required]** |
| `--count INTEGER` | Target runner count **[required]** |
| `-h, --help` | Show help |

## Examples

```bash
# Scale to 10 runners
azlin github-runner scale --pool ci-workers --count 10

# Scale down to 2
azlin github-runner scale --pool ci-workers --count 2
```

## Related Commands

- [azlin github-runner status](status.md) - View current count
- [azlin github-runner enable](enable.md) - Enable with auto-scaling
