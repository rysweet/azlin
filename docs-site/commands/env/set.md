# azlin env set

Set an environment variable on a VM.

## Usage

```bash
azlin env set <vm-name> <KEY>=<VALUE>
```

## Examples

```bash
azlin env set myvm DATABASE_URL="postgres://localhost/mydb"
azlin env set myvm NODE_ENV=production
azlin env set myvm API_KEY="sk-..."
```

## Options

| Option | Description |
|--------|-------------|
| `--persist` | Make the variable persist across VM restarts |

## See Also

- [env list](list.md)
- [env delete](delete.md)
