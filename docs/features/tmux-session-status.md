# Tmux Session Connection Status

Instantly identify which tmux sessions are connected or disconnected with visual styling in the `azlin list` command.

## What is Tmux Session Connection Status?

The `azlin list` command now displays tmux session connection status using visual text styling:

1. **Connected Sessions**: Appear in **bold text** to stand out
2. **Disconnected Sessions**: Appear in dim text to de-emphasize
3. **Zero Overhead**: Uses existing SSH connection, no additional network calls

This eliminates the need to SSH into each VM and run `tmux list-sessions` manually to find where your active work is located.

## Why Would I Use It?

Tmux session status monitoring solves several workflow challenges:

### Problem 1: Finding Active Work Sessions

You have multiple VMs with tmux sessions and need to find where your active debugging session is running.

**Without connection status**: SSH into each VM and run `tmux list-sessions` to check connection status.

**With connection status**: Run `azlin list` and connected sessions appear in **bold** - your active work jumps out immediately.

### Problem 2: Identifying Orphaned Sessions

You've disconnected from a VM but can't remember which one still has your tmux session running.

**Without connection status**: Try to remember which VM you were using, or check each one manually.

**With connection status**: Disconnected sessions appear in dim text - quickly scan the list to find orphaned sessions that need attention.

### Problem 3: Multi-VM Workflow Management

You're working across multiple VMs with different tasks in tmux and need to see the overall state at a glance.

**Without connection status**: Keep mental notes or a separate document tracking which sessions are active.

**With connection status**: One `azlin list` command shows the complete picture - bold for active, dim for backgrounded.

### Problem 4: Team Collaboration

Multiple team members are using shared VMs with tmux and you need to see which sessions are currently occupied.

**Without connection status**: Coordinate manually or risk attaching to an active session and disrupting someone's work.

**With connection status**: Connected (bold) sessions indicate someone is actively using them - avoid conflicts.

## How Does It Work?

### Connection Detection

Connection status is detected through an enhanced tmux query that includes attachment information:

```
1. SSH to VM (reuses existing connection)
   └─▶ Already connecting for VM status check - zero additional overhead

2. Run enhanced tmux query
   └─▶ tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"

3. Parse attachment status
   ├─▶ session_attached=1: Session is connected → Apply bold markup
   └─▶ session_attached=0: Session is disconnected → Apply dim markup

4. Apply Rich library styling
   ├─▶ Connected: [bold]session-name[/bold]
   └─▶ Disconnected: [dim]session-name[/dim]
```

**Key Features**:
- **Zero overhead**: Uses existing SSH connection from VM status check
- **Graceful fallback**: If enhanced format fails, parser automatically falls back to old format
- **Terminal-agnostic**: Works across all terminals through Rich library
- **Format-aware**: Detects new vs old tmux output format automatically

### Performance Characteristics

| Operation | Overhead | Notes |
|-----------|----------|-------|
| Connection status detection | 0 seconds | Reuses existing SSH connection |
| Tmux query | <50ms per VM | Minimal query overhead |
| Format detection | Automatic | Parser handles both old and new formats |
| Rendering | <1ms | Rich library handles terminal capabilities |

### Graceful Degradation

The feature handles various edge cases elegantly:

1. **Tmux not installed**: No session display (same as before)
2. **Tmux query fails**: Falls back to old parser format
3. **Terminal doesn't support styling**: Falls back to plain text
4. **No tmux sessions**: Clean display with no session data

## Examples

### VM List With Tmux Sessions

Basic VM listing with tmux connection status:

```bash
azlin list
```

**Output**:
```
Listing VMs in resource group: dev-rg

==================================================================================================
NAME                    STATUS    IP              REGION    SIZE              TMUX SESSIONS
==================================================================================================
dev-vm-001              Running   20.123.45.67    eastus    Standard_D4s_v3   main, debug
dev-vm-002              Running   20.123.45.68    westus2   Standard_D2s_v3   training
dev-vm-003              Running   20.123.45.69    eastus    Standard_D2s_v3   (no sessions)
==================================================================================================

Total: 3 VMs | 12 vCPUs | 24 GB memory in use
```

**Visual Styling** (as seen in terminal):
- `dev-vm-001`: **main** appears bold (connected), `debug` appears dim (disconnected)
- `dev-vm-002`: `training` appears dim (disconnected)
- `dev-vm-003`: No sessions, shows "(no sessions)"

### Finding Active Work

You need to find which VM has your active debugging session:

```bash
azlin list
```

**What you see**:
- VM `dev-vm-001` shows session "**debug**" in bold
- Other sessions appear dim
- **Result**: You immediately know `dev-vm-001` has your active session

### Scanning for Disconnected Sessions

You want to clean up orphaned sessions that are no longer needed:

```bash
azlin list
```

**What you see**:
- Multiple VMs with dim session names
- These are all disconnected sessions
- **Result**: Identify cleanup candidates at a glance

### With Latency Measurement

Combine connection status with latency for complete operational view:

```bash
azlin list --with-latency
```

**Output**:
```
Listing VMs in resource group: dev-rg

============================================================================================================
NAME            STATUS    IP              LATENCY    REGION    SIZE              TMUX SESSIONS
============================================================================================================
dev-vm-001      Running   20.123.45.67    45ms       eastus    Standard_D4s_v3   main, debug
dev-vm-002      Running   20.123.45.68    180ms      westus2   Standard_D2s_v3   training
============================================================================================================

Total: 2 VMs | 8 vCPUs | 16 GB memory in use
```

**Visual Styling**:
- Low latency VM (45ms) with **bold** session indicates optimal target for interactive work
- High latency VM (180ms) with dim sessions suggests backgrounded work

## Technical Notes

### Implementation Details

The feature enhances the existing tmux query format:

**Old format** (still supported via fallback):
```
tmux list-sessions
# Output: session_name: 3 windows (created Thu Dec 19 10:30:00 2024)
```

**New enhanced format**:
```
tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"
# Output: main:1:3:1734608200
#         debug:0:5:1734611100
```

The parser automatically detects which format is returned and processes accordingly.

### Styling with Rich Library

Styling uses Rich library markup that's terminal-agnostic:

```python
# Connected session (bold)
rich_text = "[bold]session-name[/bold]"

# Disconnected session (dim)
rich_text = "[dim]session-name[/dim]"
```

Rich library automatically:
- Detects terminal capabilities
- Falls back to plain text for unsupported terminals
- Handles color/no-color environments
- Renders consistently across macOS, Linux, Windows

### Compatibility

**Supported tmux versions**: 1.8+ (most common installations)

**Terminal compatibility**: Any terminal that supports:
- Bold text (most modern terminals)
- Dim/faint text (fallback to normal if unsupported)

**Platforms**:
- macOS (Terminal.app, iTerm2, Alacritty, etc.)
- Linux (GNOME Terminal, Konsole, xterm, etc.)
- Windows (Windows Terminal, WSL terminals)

### Performance Impact

**Zero performance impact** because:
1. Query piggybacks on existing SSH connection
2. Enhanced format query has same execution time as old format
3. Rich markup parsing happens locally (no network overhead)
4. Fallback detection adds <1ms parsing time

## Troubleshooting

### Issue: No Visual Difference Between Sessions

**Symptom**: All sessions appear the same without bold/dim styling.

**Cause**: Terminal doesn't support text styling.

**Solution**:
- Use a modern terminal (iTerm2, Windows Terminal, etc.)
- Check terminal color support: `echo $TERM`
- Expected values: `xterm-256color`, `screen-256color`

**Workaround**: Connection status is still accurate, just not visually styled.

---

### Issue: Sessions Show Wrong Status

**Symptom**: A session appears connected (bold) but you're not attached, or vice versa.

**Cause**: Query format mismatch or stale session data.

**Solution**:
```bash
# SSH to the VM and verify manually
ssh azureuser@<vm-ip>
tmux list-sessions

# Check for zombie sessions
tmux kill-session -t <session-name>
```

**Likely causes**:
- Tmux server restart needed
- Network interruption left stale session
- Multiple users on same VM

---

### Issue: Format Fallback Warning

**Symptom**: Parser falls back to old format and logs warning.

**Cause**: Tmux version doesn't support enhanced format query.

**Solution**: Update tmux on the VM:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install tmux

# RHEL/CentOS
sudo yum update tmux

# macOS
brew upgrade tmux
```

**Impact**: Feature still works but without connection status detection.

---

### Issue: Sessions Not Displayed At All

**Symptom**: Tmux sessions column shows "(no sessions)" even though sessions exist.

**Cause**: SSH connection unable to query tmux.

**Debugging steps**:
```bash
# Verify tmux is installed
ssh azureuser@<vm-ip> which tmux

# Check if tmux server is running
ssh azureuser@<vm-ip> tmux list-sessions

# Check socket permissions
ssh azureuser@<vm-ip> ls -la /tmp/tmux-*
```

**Common fixes**:
- Restart tmux server: `tmux kill-server && tmux`
- Fix socket permissions: `chmod 700 /tmp/tmux-$(id -u)`

---

### Issue: Performance Degradation With Many VMs

**Symptom**: `azlin list` seems slower with 20+ VMs.

**Cause**: SSH connections to many VMs take time (not related to this feature).

**Solution**: Query specific resource groups or regions:
```bash
# Filter by region
azlin list --region eastus

# Filter by resource group
azlin list --rg dev-rg

# Use compact format (faster)
azlin list --compact
```

**Note**: Tmux connection status adds <50ms per VM, negligible compared to SSH connection time (~500ms-2s per VM).

## Related Features

- **[Memory and Latency Monitoring](./memory-latency.md)** - See VM resource allocation and network latency
- **[VM Lifecycle Automation](./vm-lifecycle-automation.md)** - Automatic status checking that enables this feature
- **[Hostname and Session Name in Status Line](../../specs/tmux-status-line-enhancement.md)** - Complementary feature showing VM info in tmux itself

## See Also

- [azlin Quick Reference](../QUICK_REFERENCE.md) - Complete command reference
- [How to Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md) - SSH and tmux debugging
- [API Reference - list command](../API_REFERENCE.md#list-command) - Technical details
