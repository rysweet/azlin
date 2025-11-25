# azlin ps

Run `ps aux` on all VMs to see running processes.

## Usage

```bash
azlin ps [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--grouped` | Group output by VM instead of prefixing |
| `--resource-group, --rg TEXT` | Resource group |
| `-h, --help` | Show help message |

## Examples

### View All Processes

```bash
azlin ps
```

**Output:**
```
[alice-vm] root     1  0.0  0.1  init
[alice-vm] root     100  0.2  1.5  python app.py
[bob-vm]  root     1  0.0  0.1  init
[bob-vm]  www      250  1.5  3.2  node server.js
[carol-vm] root    1  0.0  0.1  init
[carol-vm] azure   180  0.8  2.1  python train.py
```

### Grouped Output

```bash
azlin ps --grouped
```

**Output:**
```
=== alice-vm ===
USER  PID  %CPU %MEM COMMAND
root  1    0.0  0.1  init
root  100  0.2  1.5  python app.py

=== bob-vm ===
USER  PID  %CPU %MEM COMMAND
root  1    0.0  0.1  init
www   250  1.5  3.2  node server.js

=== carol-vm ===
USER  PID  %CPU %MEM COMMAND
root  1    0.0  0.1  init
azure 180  0.8  2.1  python train.py
```

## Common Use Cases

### Find Python Processes

```bash
azlin ps | grep python
```

### Check Resource Usage

```bash
# Find high CPU processes
azlin ps --grouped | grep -E "[5-9]\.[0-9]" | head -10
```

### Monitor Specific App

```bash
azlin ps | grep "app.py"
```

## Notes

- SSH processes are automatically filtered out
- Output prefixed with `[vm-name]` by default
- Use `--grouped` for easier reading

## Related Commands

- [azlin w](w.md) - See who's logged in
- [azlin top](top.md) - Live monitoring dashboard
- [azlin cost](cost.md) - Check VM costs
