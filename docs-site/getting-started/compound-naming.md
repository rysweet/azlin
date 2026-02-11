# Compound VM:Session Naming

**Available since:** v2.3.0

Compound naming lets ye reference VMs usin' a `hostname:session_name` format, makin' it easy to work with multiple sessions on the same VM or distinguish between VMs with similar session names across different hosts.

## Quick Start

```bash
# Connect using compound naming
azlin connect myvm:main

# List sessions showing compound format
azlin list
# Output shows: myvm:main, myvm:dev, othervm:main

# Execute commands on specific sessions
azlin exec myvm:dev "git status"
```

## When to Use Compound Naming

Use compound naming when ye need to:

1. **Disambiguate session names** - Multiple VMs have sessions with the same name
2. **Target specific VM** - Explicitly specify which VM's session to use
3. **Scripting workflows** - Precisely control which VM:session combination to access
4. **Team environments** - Work with shared VMs where session names alone aren't unique

## Basic Usage

### Connecting to Sessions

```bash
# Connect to "main" session on "myvm"
azlin connect myvm:main

# Connect to "dev" session on same VM
azlin connect myvm:dev

# Still works: session-only format (if unambiguous)
azlin connect main
```

### Listing Sessions

```bash
# List all sessions (shows compound names)
azlin list

# Output example:
# HOSTNAME    SESSION     STATUS    IP            REGION
# myvm        main        Running   20.12.34.56   eastus
# myvm        dev         Running   20.12.34.56   eastus
# othervm     main        Running   20.45.67.89   westus2
```

### Executing Commands

```bash
# Run command on specific session
azlin exec myvm:main "docker ps"

# Works across different VMs
azlin exec vm1:test "npm test"
azlin exec vm2:test "npm test"
```

## How It Works

### Name Resolution Order

When ye provide an identifier, azlin resolves it in this order:

1. **Compound format** (`hostname:session`) - Exact match takes priority
2. **Session name only** - Searches for unique session name across all VMs
3. **Hostname only** - Uses default session on that VM (typically "azlin")

### Ambiguity Handling

If ye provide just a session name and multiple VMs have that session:

```bash
azlin connect main

# Error: Ambiguous session name 'main'
# Found on multiple VMs:
#   - myvm:main (20.12.34.56)
#   - othervm:main (20.45.67.89)
#
# Use compound format: azlin connect hostname:main
```

## Common Patterns

### Development Workflow

```bash
# Create multiple dev environments on same VM
azlin ssh myvm --tmux-session feature-auth
azlin ssh myvm --tmux-session feature-api

# Later, connect to specific feature
azlin connect myvm:feature-auth
azlin connect myvm:feature-api
```

### Team Collaboration

```bash
# Team shares VM with personal sessions
azlin connect shared-vm:alice
azlin connect shared-vm:bob
azlin connect shared-vm:charlie
```

### Multi-Environment Testing

```bash
# Test across environments
azlin exec prod-vm:app "curl localhost:8080/health"
azlin exec staging-vm:app "curl localhost:8080/health"
azlin exec dev-vm:app "curl localhost:8080/health"
```

## Configuration

Compound naming works automatically with no configuration required. Session names are stored in `~/.azlin/config.toml`:

```toml
[sessions]
"myvm:main" = "20.12.34.56"
"myvm:dev" = "20.12.34.56"
"othervm:main" = "20.45.67.89"
```

## Troubleshooting

### Error: "Ambiguous session name"

**Problem:** Multiple VMs have the same session name.

**Solution:** Use compound format to specify exactly which VM:session ye want:

```bash
# Instead of:
azlin connect main  # ❌ Ambiguous

# Use:
azlin connect myvm:main  # ✅ Explicit
```

### Error: "Session not found"

**Problem:** The specified compound name doesn't exist.

**Solution:** Check available sessions with `azlin list`:

```bash
azlin list
# Verify hostname and session name are correct
```

### Hostname vs Session Name Confusion

**Problem:** Not sure if identifier is hostname or session.

**Solution:** Hostnames typically match Azure VM names. Sessions are what ye specify with `--tmux-session` or `azlin session` command:

```bash
# Hostname: VM name in Azure (e.g., azlin-vm-12345 or myvm)
# Session: tmux session name (e.g., main, dev, feature-xyz)

# Check both:
azlin list  # Shows both hostnames and sessions
```

## Advanced Usage

### Scripting with Compound Names

```bash
#!/bin/bash
# Deploy to multiple environments

ENVIRONMENTS=(
    "prod-vm:app"
    "staging-vm:app"
    "dev-vm:app"
)

for env in "${ENVIRONMENTS[@]}"; do
    echo "Deploying to $env..."
    azlin exec "$env" "cd ~/app && git pull && docker-compose up -d"
done
```

### Integration with CI/CD

```yaml
# GitHub Actions example
jobs:
  deploy:
    steps:
      - name: Deploy to production
        run: |
          azlin exec prod-vm:app "cd /app && ./deploy.sh"

      - name: Verify deployment
        run: |
          azlin exec prod-vm:app "curl -f localhost:8080/health"
```

## Best Practices

1. **Use descriptive session names** - `feature-auth` beats `dev1`
2. **Consistent naming across VMs** - Same session names for same purposes
3. **Document team conventions** - Agree on naming patterns with yer crew
4. **Use compound format in scripts** - Avoid ambiguity in automation

## Related Commands

- [`azlin session`](../commands/session.md) - Manage session names
- [`azlin connect`](../commands/connect.md) - Connect to sessions
- [`azlin list`](../commands/list.md) - List all sessions
- [`azlin exec`](../commands/command.md) - Execute commands on sessions

## See Also

- [Session Management Guide](../advanced/session-management.md)
- [Multi-VM Workflows](../advanced/multi-vm-workflows.md)
- [Team Collaboration](../advanced/team-collaboration.md)
