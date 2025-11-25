# Fleet Management

Advanced distributed command orchestration with conditional execution, smart routing, and workflow definitions.

## Overview

Fleet management extends batch operations with intelligent VM selection, dependency chains, and YAML-based workflows for complex multi-step processes.

## Commands

### `azlin fleet run`

Execute commands with advanced features:

```bash
# Run on idle VMs only
azlin fleet run "npm test" --if-idle --parallel 5

# Smart route to least-loaded VMs
azlin fleet run "backup.sh" --smart-route --count 3

# Retry failed operations
azlin fleet run "deploy.sh" --tag role=web --retry-failed
```

### `azlin fleet workflow`

Execute YAML workflows:

```bash
azlin fleet workflow deploy.yaml --tag env=staging
```

## Features

- **Conditional execution**: Run based on VM state (idle, load, etc.)
- **Smart routing**: Automatically select least-loaded VMs
- **Dependency chains**: Sequential multi-step workflows
- **Retry logic**: Automatic retry on failures
- **Result diffing**: Compare outputs across VMs

## Example Workflow

```yaml
# deploy.yaml
name: Application Deployment
steps:
  - name: Pull latest code
    command: git pull origin main

  - name: Install dependencies
    command: npm install
    requires: Pull latest code

  - name: Restart service
    command: sudo systemctl restart app
    requires: Install dependencies
```

Run it:

```bash
azlin fleet workflow deploy.yaml --tag role=app
```

## See Also

- [Batch Operations](index.md)
- [Batch Command](command.md)

---

*Documentation last updated: 2025-11-24*
