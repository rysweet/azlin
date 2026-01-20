# Azlin PWA Feature Roadmap

**Analysis Date**: 2026-01-19
**Current Version**: 1.0.0
**Status**: Production-Ready MVP with 10 High-Value Features Identified

---

## Executive Summary

Based on comprehensive analysis of the current PWA and research into mobile VM management best practices, we've identified 10 high-value features to transform the Azlin PWA from an MVP into a comprehensive mobile VM management platform.

**Current State**: Functional core (auth, VM list/start/stop, basic tmux)
**Opportunity**: 10 features that address critical gaps and user pain points

---

## 🎯 **Top 10 Features to Implement**

### Priority Tier 1: Critical Features (Implement First)

These features address the most significant gaps and provide immediate high value to users.

---

#### **1. Real-Time Cost Tracking Dashboard** 🏴‍☠️

**Why This Feature**: Most documented but completely missing. Users are flying blind on spending.

**User Problem Solved**:
- "How much am I spending on VMs this month?"
- "Which VMs are costing me the most?"
- "Am I on track to exceed my budget?"

**Features**:
- Month-to-date (MTD) spending by VM
- Daily cost trend graph (last 30 days)
- Cost breakdown by resource group
- Budget progress indicator
- "Estimated today" with 24-hour lag disclaimer
- Cost per VM with recommendations to stop expensive idle VMs

**Technical Implementation**:
```typescript
// Files to create:
src/api/cost-client.ts          // Azure Cost Management API
src/store/cost-store.ts         // Redux state (already exists as placeholder)
src/pages/CostDashboardPage.tsx // Main UI
src/components/CostChart.tsx    // Trend visualization
src/utils/cost-calculator.ts    // Estimation logic

// Azure API:
POST /providers/Microsoft.CostManagement/query
{
  "type": "Usage",
  "timeframe": "MonthToDate",
  "dataset": {
    "granularity": "Daily",
    "aggregation": { "totalCost": { "name": "Cost", "function": "Sum" }}
  }
}
```

**Complexity**: Medium (3-5 days)
**Value**: Critical (prevents budget overruns)
**Dependencies**: None

---

#### **2. Budget Alerts & Push Notifications** 🔔

**Why This Feature**: Proactive cost control prevents surprises at month-end.

**User Problem Solved**:
- "Alert me when I hit 80% of my monthly budget"
- "Notify me immediately if a VM becomes expensive"
- "Warn me before I exceed my threshold"

**Features**:
- Set budget threshold (e.g., $500/month)
- Push notifications at 50%, 80%, 100% of budget
- Daily spending summaries
- High-cost VM alerts (e.g., VM running >24 hours)
- Automatic email alerts (via Azure Monitor Action Groups)

**Technical Implementation**:
```typescript
// Files to create:
src/api/budget-client.ts        // Azure Consumption Budgets API
src/utils/notification-manager.ts // Web Push API
src/components/BudgetConfig.tsx  // Budget settings UI
src/store/budget-store.ts       // Redux state

// Azure API:
PUT /subscriptions/{id}/providers/Microsoft.Consumption/budgets/{name}
{
  "properties": {
    "amount": 500,
    "timeGrain": "Monthly",
    "notifications": { "threshold": 80, "enabled": true }
  }
}

// Web Push API for PWA notifications:
navigator.serviceWorker.ready.then(reg => {
  reg.showNotification('Budget Alert', {
    body: 'You've reached 80% of your monthly budget',
    icon: '/pwa-192x192.png'
  });
});
```

**Complexity**: Medium (3-4 days)
**Value**: High (prevents cost overruns)
**Dependencies**: Feature #1 (Cost Tracking)

---

#### **3. One-Tap VM Quick Actions** ⚡

**Why This Feature**: Every tap matters on mobile. Reduce friction for common operations.

**User Problem Solved**:
- "I need to start my dev VM NOW while on the bus"
- "Quick! Stop all VMs before the weekend"
- "Restart this VM that's acting weird"

**Features**:
- Swipe gestures: Swipe right = Start, Swipe left = Stop
- Quick action buttons on VM cards
- Batch operations: "Stop All", "Start Group"
- Confirmation shortcuts (long-press = skip confirm)
- Recent VMs widget (last 5 accessed)
- Favorites/pinning (star icon to pin to top)

**Technical Implementation**:
```typescript
// Files to modify:
src/pages/VMListPage.tsx        // Add swipe handlers
src/components/VMCard.tsx       // Extract card component with gestures
src/utils/gesture-handler.ts   // Swipe detection
src/store/favorites-store.ts   // Favorites persistence

// React-swipeable library:
<SwipeableVMCard
  onSwipeLeft={() => dispatch(stopVM(vm))}
  onSwipeRight={() => dispatch(startVM(vm))}
  onLongPress={() => dispatch(toggleFavorite(vm))}
>
```

**Complexity**: Low (2-3 days)
**Value**: High (UX improvement)
**Dependencies**: None

---

### Priority Tier 2: High-Value Features (Implement Second)

---

#### **4. VM Performance Metrics Dashboard** 📊

**Why This Feature**: "Is my VM healthy?" is a critical question when troubleshooting from mobile.

**User Problem Solved**:
- "Why is my app slow? Is the VM maxed out?"
- "Did the VM run out of memory?"
- "Is there a network issue?"

**Features**:
- CPU utilization graph (last 15min/1hr/6hr/24hr)
- Memory usage with swap
- Disk I/O and space usage
- Network bandwidth (in/out)
- "At a glance" health indicators (green/yellow/red)
- Anomaly detection (AI-powered unusual pattern alerts)

**Technical Implementation**:
```typescript
// Files to create:
src/api/monitor-client.ts       // Azure Monitor API
src/pages/VMMetricsPage.tsx     // Metrics UI
src/components/MetricChart.tsx  // Time series graphs
src/utils/metric-aggregator.ts  // Data processing

// Azure Monitor API:
GET /subscriptions/{id}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{vm}/providers/microsoft.insights/metrics
?metricnames=Percentage CPU,Available Memory Bytes,Network In,Network Out
&timespan=PT1H (last 1 hour)
&interval=PT1M (1-minute granularity)
```

**Complexity**: Medium (4-5 days)
**Value**: High (observability)
**Dependencies**: None

**Mobile Optimization**:
- Use lightweight chart library (Recharts or Chart.js)
- Lazy-load historical data
- Cache recent metrics locally
- Show simplified view by default, details on tap

---

#### **5. Enhanced Tmux Watch Mode (Live Updates)** 👀

**Why This Feature**: Already 80% implemented! Just needs UI integration.

**User Problem Solved**:
- "I want to see my long-running command output without refreshing"
- "Monitor deployment progress in real-time"
- "Watch logs as they happen"

**Features**:
- Auto-refresh every 10 seconds (configurable 5-30s)
- Change highlighting (new lines in different color)
- Pause/resume watch mode
- Battery impact warning
- Scroll lock while watching
- Sound/vibration on new output (optional)

**Technical Implementation**:
```typescript
// Files to modify/create:
src/pages/TmuxPage.tsx          // Add watch mode toggle
src/tmux/tmux-watcher.ts        // Already exists! Just integrate
src/components/WatchControls.tsx // Watch UI controls
src/utils/diff-highlighter.ts   // Line change detection

// Already implemented in tmux-api.ts:
const watcher = tmuxApi.watchSession(
  resourceGroup, vmName, sessionName,
  (diff) => {
    if (diff.hasChanges) {
      highlightChangedLines(diff.changedLines);
      if (soundEnabled) playNotification();
    }
  },
  refreshInterval
);
```

**Complexity**: Low (1-2 days) - Infrastructure already exists!
**Value**: Medium-High (convenience)
**Dependencies**: None

---

#### **6. Cost Optimization Recommendations** 💡

**Why This Feature**: Direct cost savings > any other feature. AI-powered insights.

**User Problem Solved**:
- "Which VMs can I safely shut down to save money?"
- "Am I using the right VM size?"
- "What's costing me the most that I'm not using?"

**Features**:
- Idle VM detection (running but <5% CPU for 7+ days)
- Rightsizing analysis ("Your Standard_D4s_v3 runs at 10% CPU - downsize to D2s_v3 and save $120/month")
- Unused disk identification (disks not attached to VMs)
- Stopped-but-not-deallocated warnings ("Deallocate to save 100% on compute")
- Weekly optimization report
- One-tap optimization actions ("Deallocate all idle VMs")

**Technical Implementation**:
```typescript
// Files to create:
src/utils/cost-optimizer.ts     // Optimization logic
src/pages/OptimizationPage.tsx  // Recommendations UI
src/api/metrics-aggregator.ts   // Utilization analysis
src/components/SavingsCard.tsx  // Savings opportunity UI

// Optimization Algorithm:
1. Fetch last 7 days of metrics (CPU, memory, disk)
2. Identify VMs with avg CPU < 10% AND memory < 30%
3. Calculate current monthly cost
4. Recommend smaller size with projected savings
5. Identify stopped (not deallocated) VMs
6. Calculate total potential monthly savings
```

**Complexity**: Medium (4-5 days)
**Value**: Very High (direct $$ savings)
**Dependencies**: Feature #1 (Cost Tracking), Feature #4 (Metrics)

---

### Priority Tier 3: Valuable Enhancements

---

#### **7. VM Creation Wizard** 🆕

**Why This Feature**: Complete mobile independence. Create VMs from anywhere.

**User Problem Solved**:
- "I need a quick test VM while traveling"
- "Spin up a demo environment for a client meeting"
- "Create a new dev VM without waiting to get home"

**Features**:
- Multi-step wizard (size → image → network → SSH → review)
- Smart defaults (auto-select VNet, use saved SSH key)
- Cost preview before creation
- Template support (save common configurations)
- Quick create (1-tap using last settings)
- Progress tracking (Azure async operation polling)

**Technical Implementation**:
```typescript
// Files to create:
src/pages/VMCreateWizardPage.tsx  // Multi-step wizard
src/components/VMSizePicker.tsx   // Size selection
src/components/ImagePicker.tsx    // OS image picker
src/api/network-client.ts         // VNet/Subnet API
src/api/vm-templates.ts           // Template management
src/utils/vm-validator.ts         // Config validation

// Azure VM Creation Flow:
1. Create Network Interface (POST /networkInterfaces)
2. Create VM (PUT /virtualMachines)
3. Poll provisioning state (GET /virtualMachines/{name})
4. Return VM details when succeeded
```

**Complexity**: High (7-10 days)
**Value**: High (complete lifecycle)
**Dependencies**: None (but benefits from Feature #1 for cost preview)

---

#### **8. Smart Command Snippets & Autocomplete** 📝

**Why This Feature**: Typing on mobile keyboards is painful. Inspired by Termius.

**User Problem Solved**:
- "I keep typing the same commands"
- "Can't remember the exact syntax"
- "Fat-finger typos on mobile keyboard"

**Features**:
- Pre-built snippet library:
  - "Restart Docker service"
  - "Check disk space"
  - "Tail application logs"
  - "Update system packages"
- Custom snippet creation
- Command autocomplete (Azure CLI, common Linux commands)
- Command history with search
- Share snippets across VMs
- Template variables ({{vm_name}}, {{date}}, etc.)

**Technical Implementation**:
```typescript
// Files to create:
src/pages/SnippetsPage.tsx      // Snippet management
src/components/CommandInput.tsx  // Autocomplete input
src/utils/snippet-manager.ts    // Snippet CRUD
src/store/snippets-store.ts     // Redux state
src/data/default-snippets.json  // Built-in snippets

// Snippet Data Structure:
interface Snippet {
  id: string;
  name: string;
  command: string;
  description: string;
  category: 'docker' | 'system' | 'network' | 'custom';
  variables?: string[]; // e.g., ['service_name']
}

// Autocomplete using Trie data structure for fast prefix matching
```

**Complexity**: Medium (3-4 days)
**Value**: Medium-High (UX improvement)
**Dependencies**: None

---

#### **9. VM Health Dashboard (Four Golden Signals)** 🩺

**Why This Feature**: Inspired by Google SRE principles and mobile dashboard best practices.

**User Problem Solved**:
- "Is everything OK?" (at-a-glance health check)
- "What needs my attention right now?"
- "Which VM is having issues?"

**Features**:
- **Four Golden Signals** for each VM:
  1. **Latency**: SSH connection time, API response time
  2. **Traffic**: Network throughput (requests/sec if app instrumented)
  3. **Errors**: Failed SSH attempts, disk errors, OOM events
  4. **Saturation**: CPU/Memory/Disk utilization %
- Red/Yellow/Green health indicators
- Anomaly detection (AI-powered pattern recognition)
- Predictive alerts ("CPU trending up, may hit 100% in 2 hours")
- Quick drill-down to problem VMs

**Technical Implementation**:
```typescript
// Files to create:
src/pages/HealthDashboardPage.tsx   // Main dashboard
src/components/HealthIndicator.tsx  // Status badge
src/utils/health-calculator.ts     // Health scoring
src/api/diagnostics-client.ts      // Boot diagnostics API
src/utils/anomaly-detector.ts      // Pattern detection

// Health Score Algorithm:
function calculateHealth(vm: VMInfo, metrics: Metrics): Health {
  const cpuScore = metrics.cpu < 80 ? 'green' : metrics.cpu < 95 ? 'yellow' : 'red';
  const memoryScore = metrics.memory < 80 ? 'green' : metrics.memory < 95 ? 'yellow' : 'red';
  const diskScore = metrics.disk < 85 ? 'green' : metrics.disk < 95 ? 'yellow' : 'red';

  // Worst signal determines overall health
  return worstOf(cpuScore, memoryScore, diskScore);
}
```

**Complexity**: Medium (4-5 days)
**Value**: High (proactive monitoring)
**Dependencies**: Feature #4 (VM Metrics) provides underlying data

---

#### **10. Scheduled VM Auto-Start/Stop** ⏰

**Why This Feature**: Automation = automatic cost savings without manual intervention.

**User Problem Solved**:
- "I always forget to stop my dev VM on Friday"
- "Automatically start my VM at 9am, stop at 6pm on weekdays"
- "Shut down all test VMs on weekends"

**Features**:
- Schedule per-VM or per-resource-group
- Weekday vs weekend schedules
- Timezone-aware (use device timezone)
- One-time schedules (start tomorrow at 8am)
- Recurring schedules (Mon-Fri 9am-6pm)
- Holiday calendar support
- Manual override (start now, ignore schedule today)
- Cost savings projection ("Save $147/month with this schedule")

**Technical Implementation**:
```typescript
// Files to create:
src/pages/SchedulerPage.tsx      // Schedule management UI
src/components/SchedulePicker.tsx // Time picker component
src/utils/scheduler.ts           // Schedule logic
src/store/schedules-store.ts     // Redux state
src/api/automation-client.ts     // Azure Automation API

// Two Implementation Options:

// Option 1: Azure Automation Runbooks (Preferred)
// - Create runbook that runs on schedule
// - Runbook calls Azure REST API to start/stop VMs
// - Pros: Serverless, reliable, native Azure
// - Cons: Requires Azure Automation account setup

// Option 2: Service Worker + Background Sync (PWA Native)
// - Service worker checks schedule every hour
// - Queues start/stop operations
// - Syncs when device is online
// - Pros: No Azure setup needed
// - Cons: Requires device to be powered on, less reliable

// Recommendation: Use Azure Automation for reliability
```

**Complexity**: High (6-8 days for Azure Automation integration)
**Value**: Very High (automatic cost savings, set-it-and-forget-it)
**Dependencies**: Feature #1 (Cost Tracking) for savings projection

---

### Priority Tier 2: High-Value Enhancements

---

#### **5. VM Creation Wizard** 🛠️

**Why This Feature**: Complete the VM lifecycle - create, manage, delete all from mobile.

**User Problem Solved**:
- "I need a VM but I'm not at my desk"
- "Quick test environment for a demo"
- "Clone this VM configuration for a new project"

**Features**:
- 5-step wizard:
  1. Basics (name, resource group, location)
  2. Size selection with cost comparison
  3. OS image (Ubuntu 22.04/24.04, Debian 12, RHEL)
  4. Networking (VNet, subnet, public IP optional)
  5. SSH key (upload from Files app or paste)
- Template saving ("Save as template")
- Cost preview before creating
- Progress tracking with estimated time
- Quick create from template (1-tap)

**Complexity**: High (7-10 days)
**Value**: High (full lifecycle)
**Dependencies**: None (but benefits from #1 for cost preview)

---

#### **6. Batch Operations & VM Grouping** 📦

**Why This Feature**: Managing 20+ VMs individually is tedious on mobile.

**User Problem Solved**:
- "Stop all development VMs for the weekend"
- "Start my entire staging environment"
- "Tag all VMs in this project"

**Features**:
- Multi-select mode (checkboxes on VM cards)
- Batch actions: Start, Stop, Deallocate, Tag
- Smart groups: By tag, by resource group, by power state
- Saved groups ("Dev Environment", "Production", "Test VMs")
- Group operations confirmation with cost impact
- Parallel execution with progress tracking

**Technical Implementation**:
```typescript
// Files to create:
src/pages/BatchOperationsPage.tsx  // Batch UI
src/components/VMSelector.tsx      // Multi-select component
src/utils/batch-executor.ts       // Parallel operation handler
src/store/groups-store.ts          // Group definitions

// Parallel Execution:
async function batchOperation(vms: VMInfo[], action: 'start' | 'stop') {
  const results = await Promise.allSettled(
    vms.map(vm => dispatch(action === 'start' ? startVM(vm) : stopVM(vm)))
  );

  return {
    succeeded: results.filter(r => r.status === 'fulfilled').length,
    failed: results.filter(r => r.status === 'rejected').length,
  };
}
```

**Complexity**: Low-Medium (3-4 days)
**Value**: Medium-High (efficiency for power users)
**Dependencies**: None

---

#### **7. VM Search, Filter & Organization** 🔍

**Why This Feature**: Findability is critical when managing many VMs from mobile.

**User Problem Solved**:
- "Where's my production database VM?"
- "Show me only running VMs"
- "Find VMs with tag 'customer:acme'"

**Features**:
- Search by name (fuzzy matching)
- Filter by: Power state, resource group, location, size, tags
- Sort by: Name, cost, age, last modified
- Favorites/pinned VMs (star icon)
- Recent VMs (last 5 accessed)
- Saved filters ("My Dev VMs", "High Cost VMs")

**Technical Implementation**:
```typescript
// Files to create:
src/components/VMSearchBar.tsx   // Search input with filters
src/components/FilterPanel.tsx   // Advanced filters
src/utils/vm-filter.ts          // Filter logic
src/utils/fuzzy-search.ts       // Fuzzy matching (Fuse.js)
src/store/preferences-store.ts  // Saved filters

// Fuzzy Search Example:
import Fuse from 'fuse.js';

const fuse = new Fuse(vms, {
  keys: ['name', 'tags', 'resourceGroup'],
  threshold: 0.3, // Fuzzy matching tolerance
});

const results = fuse.search(searchQuery);
```

**Complexity**: Low (2-3 days)
**Value**: Medium (usability for >10 VMs)
**Dependencies**: None

---

#### **8. Biometric Quick Auth (Face ID / Touch ID)** 🔐

**Why This Feature**: Every auth prompt kills mobile momentum. Inspired by Azure Mobile App.

**User Problem Solved**:
- "I have to enter my password again?!"
- "Just let me in quickly - I authenticated 5 minutes ago"
- "This is my device, trust it"

**Features**:
- Face ID / Touch ID for app unlock
- Remember device (30-day trusted device token)
- Quick unlock after iOS background
- Fallback to device code if biometric fails
- Security settings (require re-auth after N hours)

**Technical Implementation**:
```typescript
// Files to create:
src/auth/biometric-auth.ts      // Web Authentication API
src/utils/device-trust.ts       // Device token management
src/components/BiometricPrompt.tsx // UI for biometric prompt

// Web Authentication API (WebAuthn):
const credential = await navigator.credentials.create({
  publicKey: {
    challenge: new Uint8Array([/* challenge from server */]),
    rp: { name: "Azlin PWA" },
    user: {
      id: new Uint8Array([/* user ID */]),
      name: userEmail,
      displayName: userName,
    },
    pubKeyCredParams: [{ alg: -7, type: "public-key" }],
    authenticatorSelection: {
      authenticatorAttachment: "platform", // Use device biometrics
      userVerification: "required",
    }
  }
});

// For quick unlock after background:
- Store encrypted short-lived token in memory
- Re-validate with biometric when app resumes
- Full re-auth only after 24 hours or manual logout
```

**Complexity**: Medium (4-5 days)
**Value**: High (UX improvement, security maintained)
**Dependencies**: None

**Note**: Requires Azure AD configuration to support WebAuthn

---

### Priority Tier 3: Nice-to-Have Features

---

#### **9. VM Activity Log & Audit Trail** 📜

**Why This Feature**: Compliance, debugging, and "what did I do?" questions.

**User Problem Solved**:
- "Did I stop this VM or did it crash?"
- "When was the last time this VM was restarted?"
- "Who accessed this VM last week?"

**Features**:
- Activity timeline (last 30 days)
- Filter by: Action type, user, time range
- Event types: Start, stop, restart, deallocate, commands sent
- Export to CSV
- Push notification for unauthorized actions (if RBAC configured)
- "Undo" for recent actions (restart VM stopped 5 min ago)

**Technical Implementation**:
```typescript
// Files to create:
src/pages/ActivityLogPage.tsx    // Activity timeline UI
src/api/activity-log-client.ts   // Azure Activity Log API
src/components/ActivityCard.tsx   // Event display
src/utils/activity-filter.ts     // Filter logic
src/store/activity-store.ts      // Redux state

// Azure Activity Log API:
GET /subscriptions/{id}/providers/Microsoft.Insights/eventtypes/management/values
?$filter=eventTimestamp ge '2026-01-01' and resourceGroupName eq 'azlin-vms'
&$select=eventTimestamp,operationName,status,caller,resourceId

// Returns events like:
{
  "eventTimestamp": "2026-01-19T10:30:00Z",
  "operationName": "Microsoft.Compute/virtualMachines/start/action",
  "status": "Succeeded",
  "caller": "user@example.com",
  "resourceId": "/subscriptions/.../virtualMachines/my-vm"
}
```

**Complexity**: Medium (3-4 days)
**Value**: Medium (compliance, debugging)
**Dependencies**: None

---

#### **10. Dark Mode & Customization** 🌙

**Why This Feature**: Mobile users often work in varied lighting. Accessibility matters.

**User Problem Solved**:
- "Bright white screen at night kills my eyes"
- "I prefer dark mode for battery life"
- "Match my iOS system theme"

**Features**:
- Dark mode toggle
- Auto dark mode (follow iOS system setting)
- Custom theme colors (accent color picker)
- Font size adjustment (accessibility)
- Compact vs comfortable density
- Custom icon colors for power states
- OLED black mode (pure black background saves battery)

**Technical Implementation**:
```typescript
// Files to create/modify:
src/theme/theme-manager.ts      // Theme switching logic
src/store/preferences-store.ts  // Theme preferences
src/App.tsx                     // Apply theme

// Material-UI Theme:
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#0078d4' }, // Azure blue
    background: {
      default: '#000000',  // OLED black
      paper: '#121212',    // Elevated surfaces
    },
  },
});

// Auto theme detection:
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
```

**Complexity**: Low (1-2 days) - Material-UI makes this easy
**Value**: Medium (accessibility, battery life)
**Dependencies**: None

---

## Feature Prioritization Matrix

| # | Feature | Value | Effort | Priority | Dependencies |
|---|---------|-------|--------|----------|--------------|
| 1 | Cost Tracking Dashboard | Critical | Medium | **P0** | None |
| 2 | Budget Alerts & Notifications | High | Medium | **P0** | #1 |
| 3 | One-Tap Quick Actions | High | Low | **P0** | None |
| 4 | VM Performance Metrics | High | Medium | **P1** | None |
| 5 | Enhanced Tmux Watch Mode | Medium-High | Low | **P1** | None |
| 6 | Cost Optimization Recommendations | Very High | Medium | **P1** | #1, #4 |
| 7 | VM Creation Wizard | High | High | **P2** | None |
| 8 | Smart Command Snippets | Medium-High | Medium | **P2** | None |
| 9 | VM Health Dashboard | Medium | Medium | **P2** | #4 |
| 10 | Dark Mode & Customization | Medium | Low | **P3** | None |

---

## Implementation Roadmap

### **Sprint 1: Cost Management** (2-3 weeks)
- Feature #1: Cost Tracking Dashboard
- Feature #2: Budget Alerts & Notifications
- Feature #6: Cost Optimization Recommendations

**Why**: Addresses the biggest gap (fully documented but missing)
**Impact**: Critical for production use
**Total Effort**: ~12-14 days

### **Sprint 2: UX Polish** (1-2 weeks)
- Feature #3: One-Tap Quick Actions
- Feature #5: Enhanced Tmux Watch Mode
- Feature #10: Dark Mode & Customization

**Why**: Quick wins that dramatically improve daily UX
**Impact**: High user satisfaction
**Total Effort**: ~5-7 days

### **Sprint 3: Observability** (2-3 weeks)
- Feature #4: VM Performance Metrics
- Feature #9: VM Health Dashboard
- Feature #8: Smart Command Snippets (Phase 1)

**Why**: Complete the monitoring story
**Impact**: Proactive issue detection
**Total Effort**: ~10-12 days

### **Sprint 4: Full Lifecycle** (2-3 weeks)
- Feature #7: VM Creation Wizard
- Feature #8: Smart Command Snippets (Complete)
- VM Deletion (bonus feature)

**Why**: Complete mobile independence
**Impact**: No longer need desktop for VM management
**Total Effort**: ~12-14 days

---

## Additional Feature Opportunities (Honorable Mentions)

### **Quick Wins** (1-2 day implementations)
- **VM Notes**: Add notes/comments to VMs
- **Connection Shortcuts**: Quick SSH/RDP links
- **VM Status History**: Power state change log
- **Export VM List**: Download as CSV/JSON
- **VM Cloning**: Duplicate VM configuration

### **Power User Features** (3-5 day implementations)
- **Custom Dashboards**: Build your own dashboard
- **VM Comparison**: Side-by-side VM specs/costs
- **Multi-Subscription Support**: Switch between subscriptions
- **Resource Graph Queries**: Advanced Azure queries
- **Azure CLI Integration**: Run az commands directly

### **Integration Features** (4-7 day implementations)
- **GitHub Actions Integration**: Manage self-hosted runners
- **Azure DevOps Pipelines**: Trigger builds from mobile
- **Slack/Teams Webhooks**: Send alerts to channels
- **IFTTT/Zapier Integration**: Custom automation workflows
- **SSH Key Sync**: Import from GitHub/GitLab

---

## Architecture Considerations for New Features

### **Pattern to Follow** (From Existing Code)

```typescript
// 1. Create API client
src/api/{feature}-client.ts     // Azure API integration

// 2. Create Redux store
src/store/{feature}-store.ts    // State management with async thunks

// 3. Create page component
src/pages/{Feature}Page.tsx     // Main UI

// 4. Create reusable components
src/components/{Feature}*.tsx   // Shared components

// 5. Add routing
src/App.tsx                     // Add route

// 6. Write tests (60/30/10 pyramid)
src/{module}/__tests__/*.test.ts
```

### **Constraints to Respect**

1. **No Backend Server**: Direct Azure API only
   - Can't implement features requiring server-side logic
   - Can't do complex aggregations not supported by Azure APIs

2. **90-Second Timeout**: Azure Run Command hard limit
   - Must chunk long operations
   - Use async polling patterns

3. **Mobile Battery**:
   - Minimize background activity
   - Cache aggressively
   - Warn user about battery-intensive features (watch mode)

4. **Offline-First**:
   - Queue operations when offline
   - Show cached data
   - Sync when connected

---

## Success Metrics for New Features

### **Cost Features (#1, #2, #6)**
- **Target**: 80% of users set budgets within first week
- **Metric**: Average monthly cost reduction of 20-30%
- **KPI**: Zero budget overruns without user awareness

### **UX Features (#3, #5, #10)**
- **Target**: 50% reduction in taps for common operations
- **Metric**: Feature adoption rate >60% within 1 month
- **KPI**: User session duration increase (engaged users)

### **Observability Features (#4, #9)**
- **Target**: Users detect issues 50% faster
- **Metric**: Reduced time-to-resolution for incidents
- **KPI**: Proactive issue detection (alerts before user reports)

### **Lifecycle Features (#7, #8)**
- **Target**: 80% of VM creations happen from mobile within 3 months
- **Metric**: Desktop dependency reduction
- **KPI**: Mobile-first user base growth

---

## Competitive Differentiation

### **What Makes Azlin PWA Unique**

**vs. Azure Mobile App**:
- ✅ Specialized for developers (tmux integration)
- ✅ No backend required (pure PWA)
- ✅ Cost optimization focus
- ❌ Missing: Azure Copilot AI integration
- ❌ Missing: Multi-service support (only VMs)

**vs. Termius/SSH Clients**:
- ✅ VM lifecycle management (not just terminal)
- ✅ Cost tracking and optimization
- ✅ Azure-native integration
- ❌ Missing: External keyboard shortcuts
- ❌ Missing: Mosh protocol support

**vs. AWS Console Mobile**:
- ✅ Lighter weight (no heavy SDK)
- ✅ PWA (installable, offline-capable)
- ❌ Missing: AI assistant (Amazon Q equivalent)
- ❌ Missing: Voice commands

**Opportunity**: Position Azlin as the **developer-focused, cost-conscious Azure VM management tool** with AI-powered cost optimization that neither Azure Mobile nor Termius provide.

---

## Conclusion

The Azlin PWA has a solid technical foundation with excellent architecture and security. The 10 features identified represent high-value opportunities that:

1. **Fill Critical Gaps**: Cost tracking (#1, #2, #6) addresses the biggest missing piece
2. **Improve Daily UX**: Quick actions (#3), watch mode (#5), dark mode (#10) reduce friction
3. **Enable Proactive Management**: Metrics (#4), health (#9), scheduling (#10) shift from reactive to proactive
4. **Complete Lifecycle**: Creation (#7) fills the last major gap
5. **Scale Support**: Search/filter (#7), batch ops (#6), snippets (#8) help power users

**Recommended Starting Point**: Sprint 1 (Cost Management) addresses the most significant gap and provides immediate user value.

Arrr! That be the complete feature analysis, Captain. Ready to chart course toward implementation? 🏴‍☠️</output>
<output>agentId: a5e4521 (for resuming to continue this agent's work if needed)</output>
</result>
<result>
<name>Task</name>
<output>## Mobile VM Management Research Summary

Ahoy! After sailin' through the waters of mobile server management tools and best practices, here be the treasure map of insights:

---

## 🔍 Research Findings: What Makes Exceptional Mobile VM Management

### 1. **Leading Mobile SSH Clients - The Blueprint**

**Termius (Industry Leader)**:
- **Core Philosophy**: "One-tap connections" - eliminate friction
- **Key Features**:
  - Snippet library for common commands
  - Cross-device encrypted sync
  - Port forwarding made simple
  - SFTP file transfers
  - Team collaboration (shared credentials)

**Blink Shell (Developer Favorite)**:
- **Core Philosophy**: "Desktop terminal on mobile"
- **Key Features**:
  - Mosh protocol (optimized for unstable networks)
  - External keyboard shortcuts
  - Split view for iPad
  - True color support
  - Open source (community trust)

**Key Insight**: Users want **speed** (one-tap), **persistence** (Mosh), and **desktop parity** (shortcuts, split view).

---

### 2. **Cloud Management Apps - Azure & AWS Standards**

**Azure Mobile App** (Microsoft's Official Solution):
- Resource status dashboard with health indicators
- Start/stop/restart VM operations
- **Azure Copilot integration** (AI-powered Q&A about resources)
- Push notifications for service health events
- Biometric authentication (Face ID/Touch ID)
- CloudWatch metrics and alarms

**AWS Console Mobile App**:
- EC2 instance lifecycle (start, stop, reboot, terminate)
- Browse, filter, search across resources
- Configuration details at a glance
- **Amazon Q integration** (AI assistant with voice input/output)
- Real-time dashboard with account health

**Key Insight**: Leading cloud providers prioritize **AI assistance** (Copilot/Q), **push notifications**, **biometric auth**, and **health dashboards**.

---

### 3. **Critical Mobile DevOps Workflows (2026 Trends)**

Research on 2026 DevOps trends reveals what developers actually do on mobile:

**Top Mobile Use Cases**:
1. **Incident Response**: "Production is down, I'm not at my desk"
   - Need: Quick diagnostics, restart services, view logs
   - Friction: Typing complex commands on mobile keyboard

2. **On-Call Management**: "Alert triggered at 2am"
   - Need: Acknowledge alerts, triage severity, escalate if needed
   - Friction: Multiple apps (Pagerduty → AWS Console → SSH)

3. **Cost Control**: "Monthly bill shock prevention"
   - Need: Budget alerts, idle resource detection, auto-shutdown
   - Friction: Cost data has 24-hour lag, manual analysis needed

4. **Quick Checks**: "Is the deployment done?"
   - Need: Status at a glance, progress tracking
   - Friction: Manual refresh, no real-time updates

**Key Insight**: Mobile is for **urgency** (incidents, alerts) and **prevention** (cost control, monitoring). Not for **deep work** (complex configs, debugging).

---

### 4. **Dashboard Design Best Practices (Research Summary)**

**Google's Four Golden Signals** (SRE Bible):
1. **Latency**: How long requests take
2. **Traffic**: System demand
3. **Errors**: Failure rate
4. **Saturation**: Resource fullness

**Dashboard Design Principles**:
- **Avoid Clutter**: More charts ≠ more insight
- **Progressive Disclosure**: Key metrics first, details on tap
- **Load Time Target**: <30 seconds or users abandon
- **Mobile-First Question**: "What do users need when NOT at their desk?"

**Anti-Patterns to Avoid**:
- Kitchen sink dashboards (too much data)
- Desktop UI crammed onto mobile
- Metrics without context (is 80% CPU good or bad?)
- No prioritization (everything looks equally important)

**Key Insight**: Mobile dashboards must answer **"Is everything OK?"** in <5 seconds. Details come after.

---

### 5. **Server Monitoring Mobile Apps - Feature Analysis**

**Datadog Mobile** provides:
- Customizable dashboards
- Real-time metrics with time range selection
- Incident management and acknowledgment
- Push notifications for alerts
- On-call scheduling
- Collaboration features (comments on incidents)

**New Relic Mobile** adds:
- AI-powered anomaly detection
- Performance comparison (today vs. yesterday)
- Error tracking with stack traces
- Synthetic monitoring
- Business metrics (revenue impact of outages)

**Key Insight**: Modern monitoring apps use **AI for anomaly detection**, **push notifications for alerts**, and **incident management workflows** (not just graphs).

---

## 📊 What Users Actually Need on Mobile (Research Synthesis)

### **Urgent Needs** (Must be fast, <3 taps)
1. Start/stop VMs
2. Check if VMs are running
3. View cost (today, MTD)
4. Restart hung services
5. Acknowledge alerts

### **Important But Not Urgent** (Can be 5-10 taps)
6. Create new VMs
7. View detailed metrics
8. Search through logs
9. Update VM configurations
10. Review activity history

### **Desktop Work** (Don't try to replicate on mobile)
- Complex networking changes
- Security group rule management
- Detailed log analysis with grep/sed
- Multi-region deployments
- Infrastructure-as-code editing

**Key Insight**: Mobile is for **quick operations** and **monitoring**. Save complex configurations for desktop.

---

## 🎯 Feature Opportunity Categories (Based on Research)

### **Category A: Cost Management** (Highest Research Signal)
Every source mentions cost control as critical for cloud mobile:
- Budget alerts
- Idle resource detection
- Rightsizing recommendations
- Automated shutdown schedules

**Market Gap**: Azure Mobile App doesn't have cost optimization - **Azlin can win here!**

### **Category B: AI-Powered Assistance** (2026 Trend)
Azure Copilot and Amazon Q show AI is table stakes:
- Natural language queries ("Which VMs are idle?")
- Automated troubleshooting suggestions
- Anomaly detection with explanations
- Voice commands for hands-free operation

**Market Gap**: Termius/SSH clients don't have AI - **Opportunity for differentiation!**

### **Category C: Incident Response Workflow** (Mobile Core Use Case)
Research shows mobile is primarily for:
- Acknowledging alerts
- Quick diagnostics
- Service restarts
- Escalation
- Status updates to team

**Market Gap**: None of the SSH clients have incident management - **Could integrate Pagerduty/Opsgenie!**

### **Category D: Automation & Scheduling** (Cost Savings)
Research emphasizes automated cost control:
- Scheduled start/stop (work hours only)
- Auto-shutdown idle VMs
- Weekend auto-deallocate
- Tag-based policies

**Market Gap**: Azure Mobile App doesn't do VM scheduling - **Azlin opportunity!**

---

## Competitive Analysis Insights

### **What Azure Mobile App Does Well**
- Biometric auth (Face ID/Touch ID)
- Push notifications for service health
- Azure Copilot integration
- Multi-service support (not just VMs)

**Azlin Advantage**: Specialized for Linux VMs, tmux integration, no backend required

### **What Termius Does Well**
- One-tap connections
- Snippet library
- Mosh protocol (mobile-optimized)
- External keyboard support
- Cross-device sync

**Azlin Advantage**: VM lifecycle management, cost tracking, Azure-native

### **What AWS Console Mobile Does Well**
- Amazon Q AI assistant
- Voice commands
- Comprehensive EC2 lifecycle
- Real-time dashboard

**Azlin Advantage**: PWA (no app store), offline-first, lightweight

---

## 💡 Novel Feature Ideas (From Research)

### **1. AI-Powered Cost Copilot** (Unique to Azlin)
Combine Azure Copilot + Cost Management API:
- "Ask me about your spending" chat interface
- Natural language: "Which VMs can I safely shut down?"
- Automated recommendations: "Stop these 3 VMs to save $200/month"
- Voice input for hands-free operation

**Differentiation**: Neither Azure Mobile nor Termius have this!

### **2. Mosh Protocol Support** (From Blink Shell)
Integrate Mosh for mobile-optimized terminal:
- Handles network switching (WiFi → LTE)
- Local echo for instant feedback
- Predictive typing
- Resume sessions after disconnection

**Challenge**: Requires Mosh server on VMs (could auto-install)

### **3. Incident Response Workflow** (From On-Call Research)
- Integrate with Pagerduty/Opsgenie
- One-tap incident acknowledgment
- Pre-built runbooks for common incidents
- Team status updates
- Escalation automation

**Differentiation**: Only tool combining VM management + incident response!

### **4. Developer Productivity Metrics** (Novel)
Track developer efficiency:
- VM idle time (how much you're paying for unused VMs)
- Session duration (how long you work in tmux)
- Cost per project (tag-based allocation)
- Optimization savings ("You saved $X this month")

**Gamification**: Leaderboard for cost optimization!

---

## Sources

1. [Top 7 Best SSH Clients for Android in 2026](https://theserverhost.com/blog/post/best-ssh-client-for-android)
2. [5 Best Terminals/SSH Apps for iPad and iPhone [2024]](https://shellbean.app/posts/blog/en/2024-top-5-ios-ssh-clients/)
3. [Termius - Modern SSH Client App](https://apps.apple.com/us/app/termius-modern-ssh-client/id549039908)
4. [Blink Shell](https://blink.sh/)
5. [Azure Mobile App | Microsoft Azure](https://azure.microsoft.com/en-us/get-started/azure-portal/mobile-app/)
6. [What is the Azure mobile app?](https://learn.microsoft.com/en-us/azure/azure-portal/mobile-app/overview)
7. [Manage AWS Resources On Mobile - AWS Console Mobile Application](https://aws.amazon.com/console/mobile/)
8. [2026 DevOps Trends: Predictions Every IT Leader Should Know](https://digitalitnews.com/devops-trends-for-2026-predictions-every-it-leader-should-know/)
9. [Essential Guide to Remote Server Monitoring in 2026](https://signoz.io/guides/remote-server-monitoring/)
10. [Dashboard Design UX Patterns Best Practices](https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-dashboards)
11. [10 Best Server Monitoring Tools for 2026](https://betterstack.com/community/comparisons/server-monitoring-tools/)

This research gives ye the competitive intelligence to make Azlin PWA the best-in-class mobile VM management tool! 🏴‍☠️</output>
<output>agentId: ad2179f (for resuming to continue this agent's work if needed)</output>
</result>
</function_calls>

<function_results>
<result>
<name>TodoWrite</name>
<output>Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable</output>
</result>
<result>
<name>Write</name>
<output>File created successfully at: /Users/ryan/src/azlin/pwa/FEATURE_ROADMAP.md</output>
</result>
