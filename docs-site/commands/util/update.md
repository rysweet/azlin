# azlin update

Update all development tools and AI CLI packages on azlin VMs.

## Description

The `azlin update` command updates programming languages, build tools, and AI CLI assistants installed during VM provisioning. Keep development environments current with latest versions, security patches, and features.

**Default timeout:** 300 seconds per tool

## Usage

```bash
azlin update VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - VM to update (name, session, or IP)

## Options

| Option | Description |
|--------|-------------|
| `--timeout SECONDS` | Command timeout (default: 300) |
| `--tools TEXT` | Specific tools to update (comma-separated) |
| `--skip-ai` | Skip AI CLI tools (GitHub Copilot, OpenAI Codex, Claude Code) |
| `--resource-group, --rg TEXT` | Azure resource group |
| `-h, --help` | Show help message |

## Examples

### Update All Tools (Default)

```bash
azlin update my-dev-vm
```

**Output:**
```
Updating development tools on 'my-dev-vm'...

Connecting to VM...
✓ Connected

Updating Node.js packages...
  npm: 10.2.3 -> 10.2.4
  ✓ Updated

Updating AI CLI tools...
  @github/copilot: 1.5.0 -> 1.6.0
  @openai/codex: 2.1.0 -> 2.1.2
  @anthropic-ai/claude-code: 3.2.0 -> 3.2.1
  ✓ Updated

Updating Python packages...
  pip: 23.3.1 -> 23.3.2
  uv: 0.1.5 -> 0.1.6
  ✓ Updated

Updating Rust toolchain...
  rustc: 1.74.0 -> 1.74.1
  cargo: 1.74.0 -> 1.74.1
  ✓ Updated

Updating Go toolchain...
  go: 1.21.4 -> 1.21.5
  ✓ Updated

Updating Docker...
  docker: 24.0.7 -> 24.0.8
  ✓ Updated

Updating GitHub CLI...
  gh: 2.40.0 -> 2.40.1
  ✓ Updated

Updating Azure CLI...
  az: 2.54.0 -> 2.55.0
  ✓ Updated

✓ Update complete!
  Tools updated: 8
  Time: 4m 32s
```

### Update Specific Tools

```bash
# Update only Python and Node.js
azlin update my-vm --tools python,node
```

### Skip AI Tools

```bash
# Update everything except AI CLI tools
azlin update my-vm --skip-ai
```

### Update with Custom Timeout

```bash
# Allow more time for slow connections
azlin update my-vm --timeout 600
```

### Update by Session Name

```bash
azlin update my-project
```

## What Gets Updated

### Programming Languages & Runtimes

- **Node.js**: npm packages, global npm tools
- **Python**: pip, uv, astral-uv
- **Rust**: rustc, cargo via rustup
- **Go**: go toolchain
- **.NET**: dotnet SDK and runtime

### AI CLI Tools

- **GitHub Copilot CLI**: `@github/copilot`
- **OpenAI Codex CLI**: `@openai/codex`
- **Claude Code CLI**: `@anthropic-ai/claude-code`

### Development Tools

- **Docker**: docker engine and CLI
- **GitHub CLI**: gh command
- **Azure CLI**: az command
- **Git**: git version control

### NOT Updated

These require `azlin os-update`:
- Ubuntu system packages
- Linux kernel
- System libraries

## Common Workflows

### Monthly Tool Updates

```bash
# Update all development VMs
for vm in $(azlin list --tag team=engineering --format json | jq -r '.[].name'); do
  echo "Updating $vm..."
  azlin update $vm --timeout 600
done
```

### Synchronized Team Updates

```bash
# Ensure all team members have same tool versions
azlin update alice-dev
azlin update bob-dev
azlin update carol-dev

# Verify versions
azlin connect alice-dev
node --version && python3 --version && rustc --version
```

### Pre-Project Updates

```bash
# Update tools before starting new project
azlin update my-vm

# Then start work
azlin connect my-vm
cd ~/projects/new-project
```

### Selective Updates

```bash
# Update only languages used in project
azlin update backend-vm --tools python,rust,docker
azlin update frontend-vm --tools node,docker
```

## Update Strategies

### All-at-Once (Default)

```bash
# Update everything
azlin update my-vm
```

**Pros:** Simple, complete
**Cons:** Takes longer (2-5 minutes)

### Tool-Specific

```bash
# Update only what's needed
azlin update my-vm --tools node,python
```

**Pros:** Faster, focused
**Cons:** Other tools may become outdated

### Skip AI Tools

```bash
# Skip AI CLI to save time
azlin update my-vm --skip-ai
```

**Pros:** Faster (save 30-60s)
**Cons:** AI tools may be outdated

## Performance

| Tools Updated | Update Time |
|---------------|-------------|
| All (8 tools) | 2-5 minutes |
| Core (no AI) | 1-3 minutes |
| Specific (2-3 tools) | 30-90 seconds |
| AI tools only | 30-60 seconds |

*Times vary by network speed and available updates*

## Best Practices

### Update Schedule

- **Active development VMs**: Weekly
- **Staging VMs**: Bi-weekly
- **Production VMs**: Monthly (with testing)

### Version Synchronization

Keep team VMs in sync:

```bash
# Create update script
cat > ~/sync-team-tools.sh << 'EOF'
#!/bin/bash
for vm in alice-dev bob-dev carol-dev; do
  echo "Updating $vm..."
  azlin update $vm --timeout 600
done
echo "All team VMs updated!"
EOF

chmod +x ~/sync-team-tools.sh
./sync-team-tools.sh
```

### Test After Updates

```bash
# Update
azlin update my-vm

# Test
azlin connect my-vm
node --version
python3 --version
rustc --version
docker --version
```

## Troubleshooting

### Update Timeout

**Problem:** Update times out.

**Solution:**
```bash
# Increase timeout
azlin update my-vm --timeout 900

# Or update manually
azlin connect my-vm
# Update tools individually
```

### Tool Update Fails

**Problem:** Specific tool fails to update.

**Solution:**
```bash
# SSH and investigate
azlin connect my-vm

# Check tool-specific update
npm update -g  # Node.js
rustup update  # Rust
pip install --upgrade pip  # Python
```

### AI CLI Tools Fail

**Problem:** AI CLI tools won't update.

**Solution:**
```bash
# Skip AI tools for now
azlin update my-vm --skip-ai

# Update AI tools manually
azlin connect my-vm
npm update -g @github/copilot @openai/codex @anthropic-ai/claude-code
```

### Version Conflicts

**Problem:** Tool versions incompatible.

**Solution:**
```bash
# Update OS packages first
azlin os-update my-vm

# Then update tools
azlin update my-vm
```

## Version Verification

After updates, verify versions:

```bash
azlin connect my-vm

# Check key versions
echo "Node.js: $(node --version)"
echo "Python: $(python3 --version)"
echo "Rust: $(rustc --version)"
echo "Go: $(go version)"
echo "Docker: $(docker --version)"
echo "GitHub CLI: $(gh --version)"
echo "Azure CLI: $(az --version | head -1)"

# Check AI CLIs
npm list -g @github/copilot @openai/codex @anthropic-ai/claude-code
```

## Related Commands

- [`azlin os-update`](os-update.md) - Update Ubuntu system packages
- [`azlin connect`](../vm/connect.md) - SSH to VM
- [`azlin new`](../vm/new.md) - Provision VM with latest tools

## Deep Links

- [Update implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L3400-L3500)

## See Also

- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Development](../../development/index.md)
