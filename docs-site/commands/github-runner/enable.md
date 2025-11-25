# azlin github-runner enable

Enable GitHub Actions runner fleet on VM pool.

## Synopsis

```bash
azlin github-runner enable --repo <org/repo> --pool <pool-name> [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--repo TEXT` | GitHub repository (org/repo) **[required]** |
| `--pool TEXT` | VM pool name **[required]** |
| `--min-runners INTEGER` | Minimum runners (default: 1) |
| `--max-runners INTEGER` | Maximum runners (default: 10) |
| `--labels TEXT` | Runner labels (comma-separated) |
| `-h, --help` | Show help |

## Examples

```bash
# Basic fleet
azlin github-runner enable --repo myorg/myrepo --pool ci-workers

# With scaling limits
azlin github-runner enable --repo myorg/myrepo --pool ci-workers \
  --min-runners 2 --max-runners 20

# With custom labels
azlin github-runner enable --repo myorg/myrepo --pool ci-workers \
  --labels linux,docker,gpu
```

## Related Commands

- [azlin github-runner status](status.md) - View status
- [azlin github-runner disable](disable.md) - Disable fleet
