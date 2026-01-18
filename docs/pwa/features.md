# Azlin Mobile PWA Features

**Complete reference for all Azlin Mobile PWA capabilities.**

This document describes every feature available in the Azlin Mobile PWA, with examples and screenshots descriptions.

## Contents

- [VM Management](#vm-management)
- [Tmux Integration](#tmux-integration)
- [Cost Tracking](#cost-tracking)
- [Notifications](#notifications)
- [Offline Support](#offline-support)

## VM Management

### List VMs

View all VMs across your subscription.

**Access**: Home screen → VMs list

**Features**:
- Filter by resource group, region, or status
- Sort by name, cost, or creation date
- Search by name or tags
- Pull-to-refresh for latest data

**Screenshot Description**:
The VMs list shows cards for each VM with:
- VM name and status indicator (green = running, gray = stopped)
- Region and size (e.g., "eastus | Standard_D2s_v3")
- Current cost (e.g., "$1.23/day")
- Last snapshot time
- Action buttons (Start/Stop/Connect)

**Example**:
```javascript
// Programmatic access (for automation)
const vms = await azlin.vm.list({
  resourceGroup: 'dev-rg',
  status: 'running'
});

console.log(vms.map(vm => `${vm.name}: ${vm.powerState}`));
// Output:
// dev-vm-01: running
// test-vm-02: stopped
```

### Create VM

Quickly provision new VMs from your iPhone.

**Access**: Home screen → "+" button → "Create VM"

**Parameters**:
- **Name**: VM hostname (must be unique in resource group)
- **Resource Group**: Existing or create new
- **Size**: VM size picker (common sizes suggested)
- **Image**: OS image (Ubuntu 22.04, 24.04, Debian 12)
- **Region**: Azure region selector
- **Disk Size**: OS disk size in GB (default: 30GB)
- **Authentication**: SSH key or password
- **Network**: Existing VNet or create new

**Screenshot Description**:
The create form has collapsible sections:
1. "Basics" (name, resource group, region)
2. "Size & Image" (VM size picker with cost preview)
3. "Networking" (VNet, subnet, public IP toggle)
4. "Authentication" (SSH key upload or password)

Bottom shows estimated cost: "$0.096/hour | $2.30/day"

**Example**:
```bash
# Create via UI (5-minute provisioning time):
1. Tap "+" → "Create VM"
2. Name: "mobile-dev-01"
3. Resource Group: "mobile-rg" (new)
4. Size: Standard_D2s_v3 ($0.096/hour)
5. Image: Ubuntu 22.04
6. Region: eastus
7. Network: Create new VNet with Bastion
8. Authentication: Upload SSH key from iCloud
9. Tap "Create"

# Monitor creation progress in Notifications tab
```

### Start/Stop VM

Control VM power state to manage costs.

**Access**: VM detail page → "Start" or "Stop" button

**Features**:
- Immediate feedback (operation takes 30-60 seconds)
- Cost impact shown ("Stopping will save $2.30/day")
- Confirmation prompt for production VMs

**Screenshot Description**:
Stop button shows confirmation dialog:
- "Stop dev-vm-01?"
- "This will save $2.30/day"
- "Running workloads will be interrupted"
- Cancel | Stop buttons

**Example**:
```javascript
// Stop VM
await azlin.vm.stop('dev-rg', 'dev-vm-01');
// Success message: "dev-vm-01 stopped (saves $2.30/day)"
```

**Note**: Scheduled start/stop functionality is not included in MVP. See Future Features section below.

### Delete VM

Remove VMs and associated resources.

**Access**: VM detail page → "⋮" menu → "Delete"

**Deletion Options**:
- VM only (keeps disks and networking)
- VM + Disks (keeps networking)
- VM + All Resources (complete cleanup)

**Screenshot Description**:
Delete dialog shows:
- "Delete dev-vm-01?"
- Checkbox list of resources to delete:
  - [x] Virtual Machine
  - [x] OS Disk (30 GB)
  - [x] Network Interface
  - [ ] Public IP (keep for reuse)
  - [ ] Virtual Network (shared)
- Cost impact: "Will save $2.30/day"
- Type VM name to confirm
- Cancel | Delete buttons

**Example**:
```javascript
// Delete VM and all resources
await azlin.vm.delete('dev-rg', 'dev-vm-01', {
  deleteDisks: true,
  deleteNetworkInterfaces: true,
  deletePublicIp: false  // Keep for next VM
});
```

### VM Statistics

Monitor resource utilization.

**Access**: VM detail page → "Stats" tab

**Metrics**:
- CPU utilization (percentage over time)
- Memory usage (used/total)
- Network in/out (bytes)
- Disk IOPS and throughput

**Screenshot Description**:
Stats tab shows line graphs:
- CPU: 15-minute graph showing 45% average
- Memory: Gauge showing 2.1GB / 8GB used
- Network: In/Out rates (142 KB/s in, 89 KB/s out)
- Disk: IOPS line graph (avg 145 IOPS)

Time range selector: 15min | 1hr | 6hr | 24hr

**Example**:
```javascript
// Get VM metrics
const stats = await azlin.vm.getMetrics('dev-rg', 'dev-vm-01', {
  timeRange: '1h',
  metrics: ['cpu', 'memory', 'network']
});

console.log(`CPU avg: ${stats.cpu.average}%`);
// Output: CPU avg: 45.2%
```

## Tmux Integration

### View Tmux Sessions

See all active tmux sessions on a VM.

**Access**: VM detail page → "Sessions" tab

**Features**:
- List all tmux sessions with metadata
- Last activity timestamp
- Window count per session
- Snapshot preview (last 10 lines)

**Screenshot Description**:
Sessions tab shows cards:
- Session "dev-session"
  - Last active: 2 minutes ago
  - 3 windows (vim, bash, logs)
  - Preview shows: "$ npm run dev\n> azlin@1.0.0 dev..."
  - Tap to view full snapshot

**Example**:
```javascript
// List sessions
const sessions = await azlin.tmux.list('dev-rg', 'dev-vm-01');

sessions.forEach(s => {
  console.log(`${s.name}: ${s.windows} windows, active ${s.lastActivity}`);
});
// Output:
// dev-session: 3 windows, active 2m ago
// test-runner: 1 window, active 15m ago
```

### Snapshot Tmux Session

Capture current state without keeping connection open.

**Access**: Sessions tab → Tap session name → "Snapshot" button

**Features**:
- Full pane contents (up to 2000 lines scrollback)
- Window list with titles
- Active window indicator
- Syntax highlighting for code

**Screenshot Description**:
Snapshot view shows:
- Top bar: Session name, timestamp, refresh button
- Window tabs: vim | bash* | logs (* = active)
- Terminal output with syntax highlighting
- Bottom: Command input box + Send button

**Example**:
```javascript
// Capture snapshot
const snapshot = await azlin.tmux.snapshot('dev-rg', 'dev-vm-01', 'dev-session');

console.log(snapshot.activeWindow);  // "bash"
console.log(snapshot.panes[0].content.slice(-10));  // Last 10 lines
// Output: ["$ ls", "file1.txt file2.txt", "$ _"]
```

**Performance**:
- Snapshot takes 3-7 seconds
- Uses Azure Run Command API (no persistent connection)
- Works with private IP VMs via Bastion

### Send Commands to Tmux

Execute commands in tmux sessions remotely.

**Access**: Session snapshot view → Command input box

**Features**:
- Send text to active pane
- Send to specific window (use dropdown)
- Special key sequences (Ctrl+C, Enter, etc.)
- Command history (swipe down on input box)

**Screenshot Description**:
Command box shows:
- Text input with placeholder "Type command..."
- Target selector: "Send to: window 1 (bash)"
- Special keys: ^C | ^D | Enter buttons
- Send button (arrow icon)

**Example**:
```javascript
// Send command
await azlin.tmux.sendKeys('dev-rg', 'dev-vm-01', 'dev-session',
  'npm run test\n'  // \n sends Enter key
);

// Wait a moment, then snapshot to see output
setTimeout(async () => {
  const snapshot = await azlin.tmux.snapshot('dev-rg', 'dev-vm-01', 'dev-session');
  console.log(snapshot.panes[0].content.slice(-5));  // Last 5 lines
}, 5000);
```

### Watch for Activity

Monitor sessions for changes without manual refresh.

**Access**: Session snapshot view → "Watch" toggle

**Features**:
- Auto-refresh every 10 seconds
- Visual notification on changes
- Highlight changed lines
- Pause/resume watching

**Screenshot Description**:
Watch mode enabled shows:
- "Watching..." indicator (animated)
- Last checked: "5s ago"
- Changed lines highlighted in yellow
- Pause button replaces Watch toggle

**Example**:
```javascript
// Enable watch mode
const watcher = azlin.tmux.watch('dev-rg', 'dev-vm-01', 'dev-session', {
  interval: 10000,  // 10 seconds
  onChange: (diff) => {
    console.log(`${diff.linesChanged} lines changed`);
    // Show notification
  }
});

// Stop watching
watcher.stop();
```

**Battery Impact**:
- Watching one session: ~2% battery per hour
- Limit to 3 concurrent watchers recommended

## Cost Tracking

### Daily Cost Dashboard

Monitor Azure spending with awareness of data freshness.

**Access**: Home screen → "Costs" tab

**Features**:
- Today's costs (with 24-hour lag noted)
- Month-to-date total
- Cost by resource group
- Cost by VM
- Projected monthly cost

**Data Freshness**:
- Azure Cost Management API has 24-hour data lag
- Today's costs are estimates marked as "Preliminary"
- Historical data (2+ days old) is accurate
- Cost displays show "Data as of [date]" timestamp

**Screenshot Description**:
Costs dashboard shows:
- Big number: "$12.45 today (Preliminary)"
- Month bar: "$342.18 / $500 budget" (68% filled)
- Top spenders list:
  1. prod-vm-cluster: $4.32/day
  2. dev-vm-01: $2.30/day
  3. test-vm-02: $1.15/day
- "Set Budget" button

**Example**:
```javascript
// Get cost summary
const costs = await azlin.cost.getSummary({
  timeRange: 'month-to-date'
});

console.log(`Total: $${costs.total}`);
console.log(`Projected: $${costs.projectedMonthly}`);
// Output:
// Total: $342.18
// Projected: $487.23
```

### Budget Alerts

Get notified when spending exceeds thresholds.

**Access**: Costs tab → "Set Budget" button

**Features**:
- Monthly budget target
- Alert thresholds (50%, 80%, 100%)
- Push notifications on threshold
- Email alerts (optional)

**Screenshot Description**:
Budget configuration shows:
- "Monthly Budget: $500"
- Alert thresholds:
  - [x] 50% ($250) - notify
  - [x] 80% ($400) - notify + email
  - [x] 100% ($500) - urgent notification
- Current: $342.18 (68%)
- Save button

**Example**:
```javascript
// Set budget
await azlin.cost.setBudget({
  amount: 500,
  currency: 'USD',
  alerts: [
    { threshold: 0.5, notification: true },
    { threshold: 0.8, notification: true, email: true },
    { threshold: 1.0, notification: true, email: true }
  ]
});
```

### Cost Optimization Tips

Get suggestions to reduce spending.

**Access**: Costs tab → "Optimize" button

**Features**:
- Idle VM detection (low CPU for 24+ hours)
- Oversized VM recommendations
- Unused disk identification
- Reserved instance opportunities

**Screenshot Description**:
Optimization suggestions show:
- "💡 Save $45.30/month"
- Suggestions list:
  1. Stop test-vm-02 (idle 3 days) - save $2.30/day
  2. Resize prod-vm-01 (10% CPU avg) - save $1.15/day
  3. Delete unattached disk disk-old - save $0.05/day
- "Apply All" | "Review" buttons

**Example**:
```javascript
// Get recommendations
const tips = await azlin.cost.getOptimizations();

tips.forEach(tip => {
  console.log(`${tip.type}: ${tip.description} (save $${tip.savings}/day)`);
});
// Output:
// idle-vm: Stop test-vm-02 (save $2.30/day)
// resize: Downsize prod-vm-01 to D2s (save $1.15/day)
```

## Notifications

### Push Notifications

Receive alerts for important events.

**Access**: Settings → "Notifications" → Enable

**Notification Types**:
- VM state changes (started, stopped)
- Cost threshold alerts
- Tmux activity in watched sessions
- Long-running commands completed
- Error alerts (VM unreachable, auth expired)

**Screenshot Description**:
Notification settings show toggles:
- [x] VM State Changes
- [x] Cost Alerts
- [x] Tmux Activity
- [ ] Command Completion
- [x] Error Alerts

"Test Notification" button at bottom

**Example**:
```javascript
// Register for notifications (done automatically on enable)
await azlin.notifications.register({
  types: ['vm-state', 'cost-alert', 'tmux-activity']
});

// Sample notification:
// Title: "VM Started"
// Body: "dev-vm-01 is now running ($2.30/day)"
// Action: Tap to open VM details
```

### Notification History

View past notifications.

**Access**: Home screen → 🔔 icon → "History"

**Features**:
- Last 30 days of notifications
- Filter by type
- Mark as read
- Action buttons (e.g., "Stop VM" from cost alert)

## Offline Support

### Cached Data

Access VM information without internet connection.

**Features**:
- VM list (last synced state)
- Last tmux snapshots
- Cost data (last 30 days)
- Action queue (sync when online)

**Screenshot Description**:
Offline mode shows:
- Banner: "Offline - Last synced 15 minutes ago"
- VM list with grayed-out Start/Stop buttons
- "Actions will sync when online" message
- Cached snapshots available (read-only)

**Example**:
```javascript
// Check sync status
const status = await azlin.sync.getStatus();

console.log(`Online: ${status.online}`);
console.log(`Last sync: ${status.lastSync}`);
console.log(`Pending actions: ${status.pendingActions}`);
// Output:
// Online: false
// Last sync: 2024-01-15T10:30:00Z
// Pending actions: 2
```

### Action Queue

Queue actions while offline, sync when connected.

**Features**:
- Stop/start VM commands queued
- Tmux commands queued
- Notifications when actions complete
- Conflict resolution (if state changed)

**Example**:
```javascript
// While offline, stop a VM
await azlin.vm.stop('dev-rg', 'dev-vm-01');
// Message: "Queued - will execute when online"

// When connection restored:
// Notification: "dev-vm-01 stopped successfully"
```

### Service Worker Caching

Instant load times with aggressive caching.

**Features**:
- App shell cached (HTML, CSS, JS)
- API responses cached (5-minute TTL)
- Images and icons cached
- Background sync for updates

**Cache Statistics**:
```javascript
// View cache info (Settings → Storage)
const cacheInfo = await azlin.cache.getStats();

console.log(`Cache size: ${cacheInfo.size} MB`);
console.log(`Items cached: ${cacheInfo.count}`);
// Output:
// Cache size: 12.4 MB
// Items cached: 156
```

**Clear Cache**:
```bash
Settings → Storage → "Clear Cache" button
# Confirmation: "This will require re-downloading data"
```

## Keyboard Shortcuts

For external keyboard users (iPad):

| Shortcut | Action |
|----------|--------|
| `⌘N` | Create new VM |
| `⌘R` | Refresh current view |
| `⌘F` | Search VMs |
| `⌘1-9` | Switch tabs |
| `⌘W` | Close detail view |
| `⌘S` | Open settings |

## Accessibility

### VoiceOver Support

Full VoiceOver compatibility for screen reader users.

**Features**:
- Descriptive labels for all buttons
- Status announcements (VM started, cost updated)
- Semantic HTML structure
- Keyboard navigation

**Example Announcements**:
- "dev-vm-01, running, 2 dollars 30 cents per day, button"
- "Snapshot dev-session, last updated 2 minutes ago, button"

### Dynamic Type

Respects iOS text size settings.

**Font Scaling**:
- Minimum: 14pt (for "Smaller" iOS setting)
- Default: 17pt (iOS default)
- Maximum: 28pt (for "Larger" iOS setting)

### Color Modes

- Light mode (default)
- Dark mode (automatic based on iOS setting)
- High contrast mode support

## Feature Limitations

### Tmux Snapshots

**Size Constraints**:
- Maximum 2000 lines of scrollback
- Azure Run Command has 90-second timeout
- Larger snapshots risk timeout failures

**Workarounds**:
```bash
# Configure tmux history limit
set-option -g history-limit 2000
```

### Cost Data

**Freshness Lag**:
- 24-hour delay in cost data
- Today's costs are preliminary estimates
- Budget alerts have 24-hour lag

### Device Code Authentication

**Time Limits**:
- Device code expires after 15 minutes
- Must complete authentication within window
- New code required if expired

## Future Features

The following features are planned but not included in the MVP:

### Scheduled VM Operations
- Auto-start/stop at specified times
- Timezone-aware scheduling
- Weekend vs weekday schedules

**Example (planned)**:
```javascript
// Not yet implemented
await azlin.vm.setSchedule('dev-rg', 'dev-vm-01', {
  stopTime: '18:00',
  timezone: 'America/Los_Angeles'
});
```

### Advanced Cost Tracking
- Real-time cost estimates (without 24-hour lag)
- Cost prediction using ML
- Anomaly detection for unusual spending

### Enhanced Tmux Features
- Multi-pane snapshot support
- Session recording and playback
- Collaborative session sharing

## Next Steps

- **[Architecture](./architecture.md)**: Understand how features are implemented
- **[Deployment](./deployment.md)**: Deploy your own instance
- **[Getting Started](./getting-started.md)**: Return to setup guide
