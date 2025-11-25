# azlin w

Run the `w` command on all VMs to see who's logged in and what they're doing.

## Usage

```bash
azlin w [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Resource group |
| `-h, --help` | Show help message |

## Examples

### Check All VMs

```bash
azlin w
```

**Output:**
```
[alice-vm]
 15:30:22 up 2 days,  3:45,  1 user,  load average: 0.15, 0.20, 0.18
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0    192.168.1.100    14:22    0.00s  0.04s  0.00s python app.py

[bob-vm]
 15:30:23 up 5 days,  1:12,  0 users,  load average: 0.05, 0.10, 0.08

[carol-vm]
 15:30:24 up 1 day,   6:33,  2 users,  load average: 1.20, 0.95, 0.87
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0    192.168.1.101    13:00    1:15   0.50s  0.50s vim code.py
azureuser pts/1    192.168.1.101    15:20    0.00s  0.02s  0.00s w
```

## Common Use Cases

### Check Who's Working

```bash
# See who's logged into which VMs
azlin w | grep "user"
```

### Monitor Load Averages

```bash
# Check system load across fleet
azlin w | grep "load average"
```

### Find Idle VMs

```bash
# Find VMs with no users (candidates for stopping)
azlin w | grep "0 users"
```

## What It Shows

- **Uptime**: How long VM has been running
- **Users**: Who's currently logged in
- **Load Average**: System load (1min, 5min, 15min)
- **Activity**: What each user is doing

## Related Commands

- [azlin ps](ps.md) - View running processes
- [azlin top](top.md) - Live system monitoring
- [azlin cost](cost.md) - Check VM costs
