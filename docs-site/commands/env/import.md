# azlin env import

Import environment variables from a file to a VM.

## Usage

```bash
azlin env import <vm-name> --input <file>
```

## Examples

```bash
azlin env import myvm --input env.json
azlin env import myvm --input .env --format dotenv
```

## See Also

- [env export](export.md)
- [env set](set.md)
