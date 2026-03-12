# azlin env export

Export environment variables from a VM to a file.

## Usage

```bash
azlin env export <vm-name> --output <file>
```

## Examples

```bash
azlin env export myvm --output env.json
azlin env export myvm --output env.env --format dotenv
```

## See Also

- [env import](import.md)
- [env list](list.md)
