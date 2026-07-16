# Advanced Session Management

This guide covers advanced patterns fer workin' with VM sessions, includin' compound namin', multi-session workflows, and team collaboration strategies.

## Overview

Azure Linux CLI (azlin) supports multiple tmux sessions per VM, each accessible through **compound naming** (`hostname:session_name`). This enables complex workflows like:

- Multiple workspaces per VM
- Team collaboration on shared VMs
- Environment-specific sessions (dev, staging, prod)
- Feature branch isolation

## Session Basics

### Creating Sessions

```bash
# Default session (named "azlin")
azlin connect myvm

# Named session
azlin connect myvm --tmux-session feature-auth
# Accessible as: myvm:feature-auth

# Multiple sessions on same VM
azlin connect myvm --tmux-session dev
azlin connect myvm --tmux-session staging
azlin connect myvm --tmux-session prod
```

### Session Lifecycle

```bash
# Create session
azlin connect vm --tmux-session newsession

# Connect to existing session
azlin connect vm:newsession

# List all sessions
azlin list

# Session persists even after disconnect
# Reconnect anytime with same command
```

## Compound Naming Deep Dive

### Format Specification

**Compound Name:** `hostname:session_name`

Components:
- **hostname** - Azure VM hostname (matches VM name or custom name)
- **session_name** - tmux session identifier
- **separator** - Single colon (`:`)

### Resolution Strategy

When ye provide an identifier, azlin uses this algorithm:

```python
def resolve_identifier(identifier: str):
    if ':' in identifier:
        # Compound format: exact match
        hostname, session = identifier.split(':', 1)
        return lookup_exact(hostname, session)

    # Try as unique session name
    matches = find_sessions_by_name(identifier)
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise AmbiguousSessionError(identifier, matches)

    # Try as hostname with default session
    return lookup_hostname(identifier, default_session="azlin")
```

**Example Resolution:**

```bash
# Given VMs:
# - myvm with sessions: main, dev, staging
# - prodvm with sessions: main, api

azlin connect myvm:main      # → Exact match
azlin connect dev            # → Unique session (only on myvm)
azlin connect main           # → Error: ambiguous (on myvm AND prodvm)
azlin connect myvm           # → myvm:azlin (default session)
```

## Multi-Session Workflows

### Feature Branch Development

Isolate work on different features using separate sessions:

```bash
# Setup feature sessions
azlin connect devvm --tmux-session feature-auth
azlin connect devvm --tmux-session feature-api
azlin connect devvm --tmux-session feature-ui

# Work on feature-auth
azlin connect devvm:feature-auth
# Inside session:
cd ~/project
git checkout feature/authentication
npm run dev

# Switch to feature-api (feature-auth keeps running)
azlin connect devvm:feature-api
cd ~/project
git checkout feature/api-redesign
npm run dev
```

### Environment Isolation

Maintain separate sessions for different environments:

```bash
# Single VM, multiple environments
azlin connect myvm --tmux-session dev
azlin connect myvm --tmux-session staging
azlin connect myvm --tmux-session prod

# Deploy to dev
azlin connect myvm:dev -- bash <<'EOF'
    cd /app
    git pull origin develop
    docker-compose -f docker-compose.dev.yml up -d
EOF

# Deploy to staging
azlin connect myvm:staging -- bash <<'EOF'
    cd /app
    git pull origin staging
    docker-compose -f docker-compose.staging.yml up -d
EOF
```

### Parallel Testing

Run tests in parallel sessions:

```bash
# Create test sessions
for i in {1..5}; do
    azlin connect testvm --tmux-session "test-$i"
done

# Execute tests in parallel
for i in {1..5}; do
    azlin connect testvm:test-$i -- "pytest tests/suite-$i" &
done
wait
```

## Team Collaboration

### Shared VM Strategy

When multiple team members share a VM:

```bash
# Each team member gets personal session
azlin connect shared-vm --tmux-session alice
azlin connect shared-vm --tmux-session bob
azlin connect shared-vm --tmux-session charlie

# Team members connect to their sessions
# Alice:
azlin connect shared-vm:alice

# Bob:
azlin connect shared-vm:bob
```

### Session Naming Conventions

Establish team standards:

```bash
# Convention: {username}-{purpose}
azlin connect teamvm --tmux-session alice-frontend
azlin connect teamvm --tmux-session alice-backend
azlin connect teamvm --tmux-session bob-testing
azlin connect teamvm --tmux-session bob-debugging

# Or: {project}-{component}
azlin connect projectvm --tmux-session webapp-api
azlin connect projectvm --tmux-session webapp-ui
azlin connect projectvm --tmux-session mobile-ios
```

### Collaboration Patterns

**Pattern 1: Shared Workspace**
```bash
# Multiple people working on same codebase
# Each has their own session for isolation
azlin connect shared-vm:alice  # Alice's workspace
azlin connect shared-vm:bob    # Bob's workspace
# Both can access shared /workspace/ directory
```

**Pattern 2: Handoff Sessions**
```bash
# Create session for specific task
azlin connect vm --tmux-session bugfix-1234

# Work on it
azlin connect vm:bugfix-1234
# ... fix bug, commit, push ...

# Teammate takes over
azlin connect vm:bugfix-1234  # Continues from same state
```

## Session Management Commands

### azlin session

Manage session names and metadata:

```bash
# Set friendly name for session
azlin session myvm:dev production-deployment

# List sessions with names
azlin list
# Shows friendly names in SESSION NAME column

# Clear session name
azlin session myvm:dev --clear
```

### azlin list

View all sessions:

```bash
# Standard listing
azlin list
# HOSTNAME    SESSION     STATUS     IP
# myvm        main        Running    20.12.34.56
# myvm        dev         Running    20.12.34.56

# Wide format (no truncation)
azlin list --wide

# Include stopped VMs
azlin list --all
```

### Session Operations

```bash
# Connect to session
azlin connect hostname:session

# Execute in session
azlin connect hostname:session -- "command"

# Detach from a session without destroying tmux
# Inside tmux: Ctrl+b, then d (detach) — or simply close the SSH session

# Destroy session entirely
azlin connect hostname --tmux-session session
# Inside tmux: Ctrl+b, then type :kill-session
```

## Advanced Patterns

### Dynamic Session Creation

```bash
#!/bin/bash
# create-test-environments.sh

BRANCH=$1
SESSION_NAME="test-${BRANCH}"

# Create dedicated session for branch testing
azlin connect testvm --tmux-session "$SESSION_NAME"

# Setup environment
azlin connect "testvm:${SESSION_NAME}" -- bash <<EOF
    cd /app
    git fetch origin
    git checkout "$BRANCH"
    npm install
    npm run build
    npm test
EOF

echo "Test environment ready: testvm:${SESSION_NAME}"
```

### Session Monitoring

```bash
#!/bin/bash
# monitor-sessions.sh

# List all sessions and their status
azlin list | grep -E "^(HOSTNAME|[a-z])" > sessions.txt

# Check each session's processes
while IFS= read -r line; do
    if [[ $line =~ ^([a-z][a-z-]+[0-9]*)[[:space:]]+([a-z][a-z-]+) ]]; then
        hostname="${BASH_REMATCH[1]}"
        session="${BASH_REMATCH[2]}"

        echo "=== $hostname:$session ==="
        azlin connect "$hostname:$session" -- "ps aux | grep -v grep | grep -E 'node|python|docker'"
    fi
done < sessions.txt
```

### Automated Session Cleanup

```bash
#!/bin/bash
# cleanup-idle-sessions.sh

# Find idle sessions (no processes for 1+ hours)
azlin list | tail -n +2 | while read hostname session status ip; do
    idle_time=$(azlin connect "$hostname:$session" -- "tmux display-message -p '#{session_activity}'")
    current_time=$(date +%s)
    idle_seconds=$((current_time - idle_time))

    if [ $idle_seconds -gt 3600 ]; then
        echo "Idle session: $hostname:$session (${idle_seconds}s)"
        # Optionally destroy: azlin connect "$hostname:$session" -- "tmux kill-session"
    fi
done
```

## Session Persistence

### Tmux Configuration

Customize tmux behavior for azlin sessions:

```bash
# ~/.tmux.conf on VM
# Increase history
set-option -g history-limit 10000

# Better status bar
set -g status-right "#H #(date +'%Y-%m-%d %H:%M')"

# Mouse support
set -g mouse on

# Vim-like pane navigation
bind h select-pane -L
bind j select-pane -D
bind k select-pane -U
bind l select-pane -R
```

### Session Recovery

Sessions persist across disconnections:

```bash
# Start session and run long task
azlin connect myvm:main
# In session: start-long-running-task.sh

# Disconnect (network drop, accidental close)
# Session keeps running on VM

# Reconnect anytime
azlin connect myvm:main
# Task still running!
```

## Best Practices

### Naming Conventions

1. **Descriptive Names**
   ```bash
   # Good
   azlin connect vm --tmux-session feature-oauth
   azlin connect vm --tmux-session debug-memory-leak

   # Bad
   azlin connect vm --tmux-session dev1
   azlin connect vm --tmux-session temp
   ```

2. **Consistent Format**
   ```bash
   # Team convention: {component}-{environment}
   azlin connect vm --tmux-session api-dev
   azlin connect vm --tmux-session api-staging
   azlin connect vm --tmux-session api-prod
   ```

3. **Avoid Special Characters**
   ```bash
   # Use hyphens or underscores
   azlin connect vm --tmux-session feature-auth  # ✅
   azlin connect vm --tmux-session feature_auth  # ✅
   azlin connect vm --tmux-session feature:auth  # ❌ (colon conflicts)
   ```

### Session Organization

1. **Limit Sessions Per VM**
   - Keep to 5-10 active sessions maximum
   - Too many sessions = confusion and resource waste

2. **Document Purpose**
   - Use `azlin session` to add descriptive names
   - Document in team wiki or README

3. **Regular Cleanup**
   - Review sessions weekly
   - Delete unused sessions
   - Kill zombie processes

### Security Considerations

1. **Personal Sessions on Shared VMs**
   ```bash
   # Each user works in their own session
   # But all can see each other's processes
   ps aux | grep -v grep  # Shows ALL users' processes
   ```

2. **Sensitive Work**
   - Use dedicated VMs for sensitive tasks
   - Don't share sessions with credentials
   - Clear sensitive files when done

3. **Session Naming**
   - Avoid including sensitive info in session names
   - Session names visible to all users on VM

## Integration Examples

### CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy to VM

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production session
        run: |
          azlin connect prod-vm:main -- bash <<'EOF'
            cd /app
            git pull origin main
            npm install
            npm run build
            pm2 restart app
          EOF

      - name: Verify deployment
        run: |
          azlin connect prod-vm:main -- "curl -f http://localhost:8080/health"
```

### Monitoring Integration

```python
# monitor_sessions.py
import subprocess
import json

def get_sessions():
    """Get all active sessions"""
    result = subprocess.run(
        ['azlin', 'list', '--format', 'json'],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def check_session_health(hostname, session):
    """Check if session is responsive"""
    result = subprocess.run(
        ['azlin', 'connect', f'{hostname}:{session}', '--', 'echo ok'],
        capture_output=True,
        text=True,
        timeout=5
    )
    return result.returncode == 0

# Monitor all sessions
for session_info in get_sessions():
    hostname = session_info['hostname']
    session = session_info['session']
    healthy = check_session_health(hostname, session)
    print(f"{hostname}:{session} - {'✅' if healthy else '❌'}")
```

## Troubleshooting

See [Compound Naming Troubleshooting](../troubleshooting/compound-naming.md) fer common issues and solutions.

## See Also

- [Compound Naming Guide](../getting-started/compound-naming.md) - Basic usage
- [CLI Reference](../getting-started/compound-naming.md) - Command details
- Multi-VM Workflows - Working with multiple VMs
- Team Collaboration - Team best practices
