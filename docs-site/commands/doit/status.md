# azlin doit status

Check status of a deployment session.

## Synopsis

```bash
azlin doit status [OPTIONS]
```

## Description

Checks the status of an ongoing or completed doit deployment session.

## Options

| Option | Description |
|--------|-------------|
| `-s, --session TEXT` | Session ID to check |
| `-h, --help` | Show help |

## Examples

### Check current session
```bash
azlin doit status
```

### Check specific session
```bash
azlin doit status --session abc123
```

## Output

Shows:
- Session ID
- Request
- Status (in progress, completed, failed)
- Resources created
- Errors (if any)

## Related Commands

- [azlin doit deploy](deploy.md) - Start deployment
- [azlin doit list](list.md) - List resources
