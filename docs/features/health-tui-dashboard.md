# Health TUI Dashboard

Interactive terminal dashboard for real-time VM fleet monitoring with sparkline
trend visualization and one-key VM actions.

## Usage

```bash
# Launch interactive TUI dashboard
azlin health --tui

# Custom refresh interval (default: 5 seconds)
azlin health --tui --interval 10

# Single VM dashboard
azlin health --tui --vm my-vm
```

## Keyboard Shortcuts

| Key       | Action                              |
|-----------|-------------------------------------|
| `j` / Down  | Select next VM                   |
| `k` / Up    | Select previous VM               |
| `g`       | Jump to first VM                    |
| `G`       | Jump to last VM                     |
| `Enter`   | SSH connect to selected VM          |
| `s`       | Start selected VM                   |
| `x`       | Stop (deallocate) selected VM       |
| `r`       | Force immediate refresh             |
| `q` / Esc | Quit dashboard                      |
| `Ctrl+C`  | Quit dashboard                      |

## Dashboard Layout

```
+-- azlin fleet dashboard | 14:30:05 | refresh #3 every 5s --+
|                                                              |
+-- Fleet Status ----------------------------------------------|
| >> vm-1    Running   eastus   10.0.0.1   OK    0   45.2 ... |
|    vm-2    Running   westus   10.0.0.2   OK    0   12.1 ... |
|    vm-3    Stopped   eastus   -          -     0    0.0 ... |
+--------------------------------------------------------------|
+-- Trends: vm-1 ---------------------------------------------|
|  CPU 45.2%              |  Mem 67.3%                         |
|  ▂▃▅▇▅▃▂▃▅▇            |  ▅▅▆▆▇▇▇▆▅▅                       |
+--------------------------------------------------------------|
| q:quit j/k:nav Enter:connect s:start x:stop r:refresh       |
+--------------------------------------------------------------+
```

### Sections

1. **Header**: Shows current time, refresh count, and interval
2. **Fleet Status**: Color-coded VM table with health metrics
3. **Sparkline Trends**: CPU and memory history for the selected VM
4. **Footer**: Keyboard shortcut reference and status messages

## Color Coding

- **Green**: Metric below 50% / VM running / Agent OK
- **Yellow**: Metric 50-80% / VM transitioning
- **Red**: Metric above 80% / VM stopped / Agent down

## Columns

| Column   | Description                                |
|----------|--------------------------------------------|
| VM Name  | Azure VM name                              |
| State    | Power state (Running, Stopped, etc.)       |
| Region   | Azure region                               |
| IP       | Public or private IP address               |
| Agent    | Azure Linux agent status                   |
| Errors   | Error count from journalctl (last hour)    |
| CPU %    | Current CPU utilization                    |
| Mem %    | Current memory utilization                 |
| Disk %   | Root filesystem usage                      |
| Sessions | Active tmux sessions (when available)      |

## Sparklines

The bottom panel shows rolling CPU and memory sparkline graphs for the currently
selected VM. Each refresh cycle adds a new data point (up to 60 samples). The
sparkline color matches the current metric threshold.

## VM Actions

When you press `Enter`, `s`, or `x`, the dashboard temporarily exits to execute
the action, then returns to the TUI:

- **Connect** (`Enter`): Opens an interactive SSH session to the selected VM
- **Start** (`s`): Starts the VM via `az vm start`
- **Stop** (`x`): Deallocates the VM via `az vm deallocate` (saves costs)

## Fallback

When stdout is not a TTY (e.g., piped output), use the static table output:

```bash
azlin health  # Static table output (no --tui flag)
```
