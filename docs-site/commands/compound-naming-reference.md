# Compound Naming CLI Reference

This reference details how compound `hostname:session_name` format works across all azlin commands.

## Format Specification

**Compound Format:** `hostname:session_name`

- **hostname** - Azure VM hostname (e.g., `myvm`, `azlin-vm-12345`)
- **session_name** - Tmux session name (e.g., `main`, `dev`, `feature-xyz`)
- **Separator** - Colon (`:`) character

**Examples:**
- `myvm:main` - "main" session on "myvm"
- `prod-vm:api` - "api" session on "prod-vm"
- `azlin-vm-12345:dev` - "dev" session on VM with full Azure name

## Commands Supporting Compound Naming

All commands that accept a VM identifier support compound naming:

### Connection Commands

#### `azlin connect`

```bash
# Basic usage
azlin connect hostname:session

# Examples
azlin connect myvm:main
azlin connect prod-vm:api --use-bastion
azlin connect dev-vm:test --no-tmux
```

**Fallback behavior:**
- `azlin connect main` - Searches all VMs for session named "main"
- Error if multiple VMs have "main" session
- Success if only one VM has "main" session

#### `azlin ssh`

```bash
# Create new session using compound name
azlin ssh myvm --tmux-session feature-auth
# Creates session accessible as: myvm:feature-auth
```

### Execution Commands

#### `azlin exec`

```bash
# Execute on specific session
azlin exec hostname:session "command"

# Examples
azlin exec myvm:dev "docker ps -a"
azlin exec prod-vm:main "systemctl status nginx"
azlin exec test-vm:ci "pytest tests/"
```

#### `azlin command`

```bash
# Batch execution with compound names
azlin command hostname:session "git status"

# Multiple targets
for target in myvm:dev myvm:staging myvm:prod; do
    azlin command "$target" "uptime"
done
```

### Management Commands

#### `azlin session`

```bash
# Set session name (creates compound reference)
azlin session myvm main

# View as compound name
azlin list  # Shows: myvm:main

# Clear session
azlin session myvm --clear
```

#### `azlin list`

```bash
# Shows all sessions in compound format
azlin list

# Example output:
# HOSTNAME      SESSION       STATUS     IP
# myvm          main          Running    20.12.34.56
# myvm          dev           Running    20.12.34.56
# prod-vm       api           Running    20.45.67.89
```

## Resolution Algorithm

When azlin receives an identifier, it follows this resolution order:

### 1. Compound Format Detection

```bash
azlin connect myvm:main
# Pattern: Contains ':'
# Action: Split on ':' → hostname='myvm', session='main'
# Lookup: Find VM 'myvm', check for session 'main'
```

### 2. Session-Only Format

```bash
azlin connect main
# Pattern: No ':'
# Action: Search all VMs for session named 'main'
# Success: If exactly one VM has session 'main'
# Error: If 0 or 2+ VMs have session 'main'
```

### 3. Hostname-Only Format

```bash
azlin connect myvm
# Pattern: No ':', matches VM hostname
# Action: Use default session on 'myvm' (typically 'azlin')
```

## Error Messages

### Ambiguous Session Name

```
Error: Ambiguous session name 'main'

Found on multiple VMs:
  - myvm:main (20.12.34.56) in eastus
  - prodvm:main (20.45.67.89) in westus2

Solution: Use compound format to specify which VM:
  azlin connect myvm:main
  azlin connect prodvm:main
```

### Session Not Found

```
Error: Session 'myvm:dev' not found

Available sessions on myvm:
  - myvm:main
  - myvm:staging

Available sessions on all VMs:
  - myvm:main
  - myvm:staging
  - prodvm:api
  - prodvm:main

Use `azlin list` to see available sessions.
```

### Invalid Format

```
Error: Invalid compound name format: 'myvm:dev:test'

Expected format: hostname:session_name
Examples:
  - myvm:dev
  - prod-vm:main
  - azlin-vm-12345:test
```

### VM Not Found

```
Error: VM 'nonexistent' not found

Provided identifier: nonexistent:main

The hostname 'nonexistent' doesn't match any VM in:
  - Resource group: azlin-rg-1234567890
  - Region: eastus

Available VMs:
  - myvm (20.12.34.56)
  - prodvm (20.45.67.89)
```

## Examples by Use Case

### Development Workflow

```bash
# Setup: Create sessions for different features
azlin ssh myvm --tmux-session feature-a
azlin ssh myvm --tmux-session feature-b

# Work: Switch between features
azlin connect myvm:feature-a  # Work on feature A
azlin connect myvm:feature-b  # Switch to feature B

# Execute: Run commands on specific features
azlin exec myvm:feature-a "git status"
azlin exec myvm:feature-b "npm test"
```

### Multi-Environment Testing

```bash
# Test endpoint across environments
for env in dev staging prod; do
    azlin exec "${env}-vm:api" "curl localhost:8080/health"
done

# Compare versions
azlin exec dev-vm:api "cat version.txt"
azlin exec staging-vm:api "cat version.txt"
azlin exec prod-vm:api "cat version.txt"
```

### Team Collaboration

```bash
# Team members have personal sessions on shared VM
azlin connect shared-vm:alice    # Alice's workspace
azlin connect shared-vm:bob      # Bob's workspace
azlin connect shared-vm:charlie  # Charlie's workspace

# Check who's working
azlin list | grep shared-vm
```

### Automated Deployments

```bash
#!/bin/bash
# deploy.sh - Deploy to multiple targets

TARGETS=(
    "web1:prod"
    "web2:prod"
    "api:prod"
)

for target in "${TARGETS[@]}"; do
    echo "Deploying to $target..."
    azlin exec "$target" <<'EOF'
        cd /app
        git pull origin main
        docker-compose down
        docker-compose up -d
EOF
done
```

## Configuration Storage

Session mappings are stored in `~/.azlin/config.toml`:

```toml
[sessions]
"myvm:main" = "20.12.34.56"
"myvm:dev" = "20.12.34.56"
"myvm:staging" = "20.12.34.56"
"prodvm:api" = "20.45.67.89"
"prodvm:web" = "20.45.67.89"
```

This allows:
- Fast lookups by compound name
- Multiple sessions per VM
- Persistent session tracking

## Special Cases

### Colons in Session Names

**Not supported.** Session names cannot contain colons:

```bash
# Invalid:
azlin ssh myvm --tmux-session "feature:auth"  # ❌

# Valid:
azlin ssh myvm --tmux-session "feature-auth"  # ✅
```

### Case Sensitivity

Both hostname and session name are case-sensitive:

```bash
azlin connect MyVM:Main  # Different from myvm:main
```

### Whitespace

Whitespace not allowed in compound names:

```bash
# Invalid:
azlin connect "my vm:main"  # ❌

# Valid:
azlin connect my-vm:main   # ✅
```

## Implementation Notes

The compound naming feature is implemented in a single module (`~100 lines`) with no changes to existing session resolution logic. It adds:

1. **Compound name parser** - Splits `hostname:session` format
2. **Enhanced resolver** - Tries compound format before fallback
3. **Error messages** - Clear guidance when ambiguous
4. **Backward compatibility** - Session-only format still works

## See Also

- [Compound Naming Guide](../getting-started/compound-naming.md) - User guide
- [Session Management](../advanced/session-management.md) - Advanced session usage
- [azlin connect](./connect.md) - Connection command reference
- [azlin exec](./command.md) - Command execution reference
