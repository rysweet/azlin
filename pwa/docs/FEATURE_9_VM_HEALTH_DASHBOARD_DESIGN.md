# Feature #9: VM Health Dashboard Design Specification

**Status**: Design Phase
**Priority**: MEDIUM (P2)
**Effort**: 7-9 days total (3-4 days dashboard + 4-5 days metrics API foundation)
**Dependencies**: Feature #4 (VM Performance Metrics) - must implement metrics API client first

---

## Executive Summary

Design an SRE-style health dashboard that answers "Is everything OK?" in <5 seconds on mobile using Google's Four Golden Signals adapted for VM infrastructure.

**Core Question**: "Can I see VM fleet health at a glance and quickly drill down to problems?"

**Key Design Principles**:
1. **Progressive Disclosure**: Summary first, details on demand
2. **Mobile-First**: Optimize for small screens and touch
3. **Ruthlessly Simple**: No clutter, essential metrics only
4. **Fast Load**: <2 seconds to show health status
5. **Actionable**: Every indicator links to fixing the problem

---

## 1. Four Golden Signals Adapted for VMs

Google's Four Golden Signals provide the foundation, adapted for VM infrastructure:

### 1.1 Latency (Response Time)
**What We Measure**:
- SSH connection time via Azure Bastion (good: <2s, warning: 2-5s, critical: >5s)
- API response time for Azure Management API calls (good: <500ms, warning: 500ms-2s, critical: >2s)
- Disk read/write latency from Azure Monitor (good: <10ms, warning: 10-50ms, critical: >50ms)

**Why It Matters**: Slow responses indicate network issues, overloaded VMs, or failing disks

**Data Source**:
- Azure Monitor API: `Disk Read Latency`, `Disk Write Latency` metrics
- Custom timing: Track SSH connection attempts (tmux API integration)
- Azure Management API response headers for API timing

### 1.2 Traffic (Throughput)
**What We Measure**:
- Network bytes in/out per second (good: <80% capacity, warning: 80-95%, critical: >95%)
- Disk IOPS (input/output operations per second)
- Active SSH connections (if instrumentable via Run Command)

**Why It Matters**: High traffic may indicate legitimate load or an attack/runaway process

**Data Source**:
- Azure Monitor API: `Network In Total`, `Network Out Total`, `Disk IOPS` metrics
- Calculate rate of change over 5-minute windows

### 1.3 Errors (Failure Rate)
**What We Measure**:
- Failed SSH attempts (from Azure Activity Log or custom tracking)
- Disk I/O errors (from Azure Monitor)
- Out of Memory (OOM) events (from boot diagnostics if available)
- Application crashes (requires VM instrumentation - Phase 2)

**Why It Matters**: Errors indicate underlying problems that need immediate attention

**Data Source**:
- Azure Activity Log API: Filter for failed `Microsoft.Compute/virtualMachines/runCommand/action`
- Azure Monitor API: Disk error metrics (if available)
- Azure Boot Diagnostics: Parse console logs for OOM killer messages

### 1.4 Saturation (Resource Utilization)
**What We Measure**:
- CPU utilization % (good: <80%, warning: 80-95%, critical: >95%)
- Memory utilization % (good: <80%, warning: 80-90%, critical: >90%)
- Disk space usage % (good: <85%, warning: 85-95%, critical: >95%)
- Network bandwidth usage % (good: <80%, warning: 80-95%, critical: >95%)

**Why It Matters**: Saturation means resources are nearly exhausted, performance degradation imminent

**Data Source**:
- Azure Monitor API: `Percentage CPU`, `Available Memory Bytes`, `Network In Total`, `Network Out Total`
- Calculate memory % from available vs total (requires VM size spec lookup)
- Disk usage requires Run Command execution: `df -h /`

---

## 2. Health Scoring Algorithm

### 2.1 Per-Signal Health Score

Each of the Four Golden Signals gets a color-coded score:

```typescript
enum HealthStatus {
  GREEN = 'healthy',    // All metrics within normal range
  YELLOW = 'warning',   // One or more metrics approaching limits
  RED = 'critical',     // One or more metrics exceeded limits
  GRAY = 'unknown',     // Insufficient data or VM stopped
}

interface SignalThresholds {
  good: number;      // Below this = GREEN
  warning: number;   // Between good and warning = YELLOW
  critical: number;  // Above warning = RED
}

// Example: CPU utilization thresholds
const CPU_THRESHOLDS: SignalThresholds = {
  good: 80,      // <80% CPU = GREEN
  warning: 95,   // 80-95% CPU = YELLOW
  critical: 95,  // >95% CPU = RED
};
```

### 2.2 Overall VM Health Score

**Worst-Signal-Wins Algorithm**:
The overall VM health is determined by the worst of the four signals:

```typescript
function calculateOverallHealth(signals: FourGoldenSignals): HealthStatus {
  const signalStatuses = [
    signals.latency.status,
    signals.traffic.status,
    signals.errors.status,
    signals.saturation.status,
  ];

  // Worst signal determines overall health
  if (signalStatuses.includes(HealthStatus.RED)) return HealthStatus.RED;
  if (signalStatuses.includes(HealthStatus.YELLOW)) return HealthStatus.YELLOW;
  if (signalStatuses.includes(HealthStatus.GRAY)) return HealthStatus.GRAY;
  return HealthStatus.GREEN;
}
```

**Rationale**: A single critical metric (e.g., 98% CPU) makes the entire VM unhealthy, even if other metrics are fine. This aligns with SRE principles: one bottleneck affects the entire system.

### 2.3 Anomaly Detection (Phase 2)

**Simple Threshold-Based (Phase 1)**:
Use static thresholds (80%, 95%) for initial implementation.

**AI-Powered (Phase 2 - Future)**:
- Compare current metrics to 7-day historical baseline
- Flag sudden spikes (e.g., CPU jumped 50% in 5 minutes)
- Detect unusual patterns (e.g., memory leak: steady increase over hours)
- Use Azure Monitor's built-in anomaly detection if available

```typescript
interface AnomalyDetection {
  isAnomaly: boolean;
  anomalyType: 'spike' | 'gradual_increase' | 'pattern_change';
  confidence: number; // 0-1
  explanation: string; // e.g., "CPU increased 60% in last 10 minutes"
}
```

---

## 3. Dashboard UI Architecture

### 3.1 Information Architecture

```
┌─────────────────────────────────────┐
│ VM Health Dashboard                 │
│ ─────────────────────────────────── │
│ Overall Fleet Health: 🟢 3  🟡 1  🔴 0 │
│ ─────────────────────────────────── │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ VM: web-server-prod       🟢    │ │
│ │ ─────────────────────────────── │ │
│ │ [CPU] [Mem] [Disk] [Net]        │ │
│ │  75%   60%   45%    30%          │ │
│ │ ▬▬▬▬  ▬▬▬   ▬▬    ▬             │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ VM: db-server-staging     🟡    │ │
│ │ ─────────────────────────────── │ │
│ │ [CPU] [Mem] [Disk] [Net]        │ │
│ │  82%   88%   55%    40%          │ │
│ │ ▬▬▬▬▬ ▬▬▬▬▬ ▬▬▬   ▬▬           │ │
│ │ ⚠️ Memory approaching limit     │ │
│ └─────────────────────────────────┘ │
│                                     │
│ [Filter: All] [Sort: Health ▼]     │
└─────────────────────────────────────┘
```

### 3.2 VM Health Card Component

**Purpose**: Show at-a-glance health for a single VM

**Layout** (Mobile-Optimized):
```
┌──────────────────────────────────────────┐
│ db-server-prod            🟡 WARNING     │
│ Standard_D4s_v3 · East US                │
│ ──────────────────────────────────────── │
│                                          │
│ [Latency]  [Traffic]  [Errors] [Saturation] │
│    🟢        🟢         🟢        🟡        │
│   <2s      45%        None     CPU 88%    │
│                                          │
│ ⚠️ CPU utilization high (88%) - consider  │
│    scaling or investigating workload      │
│                                          │
│ Last updated: 2 minutes ago              │
│                                          │
│ [View Details] [Quick Actions ⚡]         │
└──────────────────────────────────────────┘
```

**Interaction**:
- **Tap card**: Navigate to detailed VM metrics page
- **Tap signal icon**: Quick popover explaining what's wrong
- **Swipe left**: Reveal quick actions (restart, stop, view logs)
- **Long press**: Add to favorites

### 3.3 Detailed Metrics View (Drill-Down)

**Triggered by**: Tapping a VM health card

**Layout**:
```
┌──────────────────────────────────────────┐
│ < Back     db-server-prod          🟡    │
│ ──────────────────────────────────────── │
│                                          │
│ [15min] [1hr] [6hr] [24hr]  <- Time range │
│           ════                            │
│                                          │
│ CPU Utilization (88%) 🟡                 │
│ ┌────────────────────────────────────┐   │
│ │     /\                             │   │
│ │    /  \      /\                    │   │
│ │ __/    \____/  \___                │   │
│ │                    \_              │   │
│ │ ─────95% Critical ─────────────    │   │
│ │ ─────80% Warning  ─────────────    │   │
│ └────────────────────────────────────┘   │
│                                          │
│ Memory Usage (60%)  🟢                   │
│ ┌────────────────────────────────────┐   │
│ │ ────────────────────────            │   │
│ └────────────────────────────────────┘   │
│                                          │
│ Disk Usage (55%)    🟢                   │
│ Network Traffic     🟢                   │
│                                          │
│ [Historical Comparison]                  │
│ vs. Yesterday:  +12% CPU                 │
│ vs. Last Week:  +5% CPU                  │
│                                          │
│ [Anomaly Detection]                      │
│ ⚠️ CPU spike detected at 14:23           │
│    Investigate process causing load      │
└──────────────────────────────────────────┘
```

### 3.4 Fleet Health Summary (Top Bar)

**Purpose**: Show overall fleet status at a glance

```
┌──────────────────────────────────────────┐
│ VM Health Dashboard                      │
│ ──────────────────────────────────────── │
│ Fleet Status:                            │
│ 🟢 3 Healthy  🟡 1 Warning  🔴 0 Critical │
│                                          │
│ [Filter by Status ▼]                     │
└──────────────────────────────────────────┘
```

**Interactions**:
- **Tap status badge**: Filter to show only VMs in that state
- **Tap "Filter by Status"**: Show dropdown with filters (all, healthy, warning, critical, stopped)

---

## 4. Component Architecture

### 4.1 Module Structure (Following Brick Pattern)

```
src/
├── api/
│   └── monitor-client.ts        # Azure Monitor API integration (NEW)
├── store/
│   └── health-store.ts          # Redux state for health data (NEW)
├── pages/
│   ├── HealthDashboardPage.tsx  # Main dashboard (NEW)
│   └── VMMetricsDetailPage.tsx  # Detailed drill-down (NEW)
├── components/
│   ├── HealthCard.tsx           # VM health card component (NEW)
│   ├── MetricChart.tsx          # Time-series graph (NEW)
│   ├── SignalIndicator.tsx      # Four signals mini-display (NEW)
│   └── HealthBadge.tsx          # Color-coded status badge (NEW)
└── utils/
    ├── health-calculator.ts     # Health scoring logic (NEW)
    ├── anomaly-detector.ts      # Anomaly detection (Phase 2) (NEW)
    └── metric-aggregator.ts     # Data transformation (NEW)
```

### 4.2 Key Interfaces

```typescript
// Health data models
export interface FourGoldenSignals {
  latency: Signal;
  traffic: Signal;
  errors: Signal;
  saturation: Signal;
}

export interface Signal {
  value: number;
  unit: string;
  status: HealthStatus;
  threshold: SignalThresholds;
  lastUpdated: string;
  explanation?: string; // What does this value mean?
}

export interface VMHealthInfo {
  vmId: string;
  vmName: string;
  overallHealth: HealthStatus;
  signals: FourGoldenSignals;
  anomalies: Anomaly[];
  lastUpdated: string;
}

export interface Anomaly {
  signalType: 'latency' | 'traffic' | 'errors' | 'saturation';
  severity: 'low' | 'medium' | 'high';
  description: string;
  detectedAt: string;
  recommendation?: string; // What should user do?
}
```

### 4.3 State Management (Redux)

```typescript
// health-store.ts
interface HealthState {
  vms: Record<string, VMHealthInfo>;  // Keyed by VM ID
  loading: boolean;
  error: string | null;
  lastRefresh: string | null;
  autoRefreshEnabled: boolean;
  refreshInterval: number; // seconds
}

// Async thunks
export const fetchVMHealth = createAsyncThunk(
  'health/fetchVMHealth',
  async ({ subscriptionId, vmId }: FetchHealthParams) => {
    const monitorClient = new AzureMonitorClient(subscriptionId);
    const metrics = await monitorClient.getVMMetrics(vmId, {
      timespan: 'PT15M', // Last 15 minutes
      metricnames: ['Percentage CPU', 'Available Memory Bytes', 'Network In Total', 'Network Out Total'],
      interval: 'PT1M', // 1-minute granularity
    });

    return calculateHealthFromMetrics(metrics);
  }
);
```

---

## 5. Azure Monitor API Integration

### 5.1 Monitor Client Implementation

```typescript
// src/api/monitor-client.ts
import { TokenStorage } from '../auth/token-storage';

export class AzureMonitorClient {
  private readonly baseUrl = 'https://management.azure.com';
  private readonly apiVersion = '2024-02-01';
  private tokenStorage: TokenStorage;

  constructor(private subscriptionId: string) {
    this.tokenStorage = new TokenStorage();
  }

  /**
   * Fetch VM metrics from Azure Monitor
   */
  async getVMMetrics(
    resourceId: string,
    options: MetricsQueryOptions
  ): Promise<MetricsResponse> {
    const token = await this.tokenStorage.getAccessToken();

    const url = new URL(`${this.baseUrl}${resourceId}/providers/microsoft.insights/metrics`);
    url.searchParams.set('api-version', this.apiVersion);
    url.searchParams.set('timespan', options.timespan);
    url.searchParams.set('interval', options.interval);
    url.searchParams.set('metricnames', options.metricnames.join(','));
    url.searchParams.set('aggregation', options.aggregation || 'Average');

    const response = await fetch(url.toString(), {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Azure Monitor API failed: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }
}

export interface MetricsQueryOptions {
  timespan: string;       // ISO 8601 duration, e.g., 'PT15M' (last 15 minutes)
  interval: string;       // Granularity, e.g., 'PT1M' (1 minute)
  metricnames: string[];  // e.g., ['Percentage CPU', 'Available Memory Bytes']
  aggregation?: 'Average' | 'Maximum' | 'Minimum' | 'Total';
}

export interface MetricsResponse {
  value: Metric[];
}

export interface Metric {
  name: { value: string };
  timeseries: Timeseries[];
  unit: string;
}

export interface Timeseries {
  data: DataPoint[];
}

export interface DataPoint {
  timeStamp: string;
  average?: number;
  maximum?: number;
  minimum?: number;
  total?: number;
}
```

### 5.2 Metrics API Endpoints

**Azure Monitor Metrics API**:
```
GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Compute/virtualMachines/{vmName}/providers/microsoft.insights/metrics
  ?api-version=2024-02-01
  &metricnames=Percentage CPU,Available Memory Bytes,Network In Total,Network Out Total,Disk Read Bytes,Disk Write Bytes
  &timespan=PT15M
  &interval=PT1M
  &aggregation=Average
```

**Available Metrics for VMs**:
- `Percentage CPU` - CPU utilization %
- `Available Memory Bytes` - Free memory (must calculate % from VM size)
- `Network In Total` - Bytes received
- `Network Out Total` - Bytes sent
- `Disk Read Bytes` - Disk read throughput
- `Disk Write Bytes` - Disk write throughput
- `Disk Read Operations/Sec` - IOPS for reads
- `Disk Write Operations/Sec` - IOPS for writes
- `OS Disk Latency` - Disk latency (if available)

**Limitations**:
- Metrics have 1-minute granularity minimum
- Up to 5-minute delay for metric availability
- Maximum 30-day retention for standard metrics
- Disk usage % requires Run Command (not in metrics API)

### 5.3 Disk Usage via Run Command

Since disk usage is not in Azure Monitor metrics, use Run Command:

```typescript
async function getDiskUsage(
  client: AzureClient,
  resourceGroup: string,
  vmName: string
): Promise<DiskUsageInfo> {
  const result = await client.runCommand(resourceGroup, vmName, {
    commandId: 'RunShellScript',
    script: ['df -h / | tail -1 | awk \'{print $5}\''], // Get root disk usage %
  });

  const usagePercent = parseInt(result.stdout.trim().replace('%', ''));
  return {
    used: usagePercent,
    available: 100 - usagePercent,
    status: calculateDiskStatus(usagePercent),
  };
}
```

---

## 6. Caching Strategy

### 6.1 Cache Requirements

**Challenge**: Azure Monitor API calls are expensive (rate limits, latency)

**Solution**: Multi-layer caching

```typescript
// Cache layers
interface CacheStrategy {
  l1: InMemoryCache;   // 30-second TTL, instant access
  l2: IndexedDBCache;  // 5-minute TTL, persistent across page reloads
  l3: AzureAPI;        // Source of truth, only call when cache miss
}
```

### 6.2 Cache Implementation

```typescript
// In health-store.ts
const CACHE_TTL_SECONDS = 30; // Refresh metrics every 30 seconds

export const fetchVMHealthCached = createAsyncThunk(
  'health/fetchVMHealthCached',
  async ({ vmId }: FetchHealthParams, { getState }) => {
    const state = getState() as RootState;
    const cachedHealth = state.health.vms[vmId];

    // Check L1 cache (in-memory)
    if (cachedHealth && isFresh(cachedHealth.lastUpdated, CACHE_TTL_SECONDS)) {
      return cachedHealth;
    }

    // Check L2 cache (IndexedDB) - implement with idb library
    const l2Cache = await db.get('health', vmId);
    if (l2Cache && isFresh(l2Cache.lastUpdated, CACHE_TTL_SECONDS)) {
      return l2Cache;
    }

    // L3: Fetch from Azure API
    const freshData = await fetchVMHealthFromAPI(vmId);

    // Populate caches
    await db.put('health', freshData);
    return freshData;
  }
);

function isFresh(timestamp: string, ttlSeconds: number): boolean {
  const age = Date.now() - new Date(timestamp).getTime();
  return age < ttlSeconds * 1000;
}
```

### 6.3 Auto-Refresh Logic

```typescript
// HealthDashboardPage.tsx
useEffect(() => {
  if (!autoRefreshEnabled) return;

  const intervalId = setInterval(() => {
    dispatch(refreshAllVMHealth());
  }, refreshInterval * 1000);

  return () => clearInterval(intervalId);
}, [autoRefreshEnabled, refreshInterval]);
```

**User Controls**:
- Toggle auto-refresh (default: ON)
- Set refresh interval (default: 60 seconds, options: 30s/60s/120s/300s)
- Battery warning if <20% battery and auto-refresh enabled

---

## 7. Mobile Optimization

### 7.1 Performance Budget

**Target Load Times**:
- Initial page load: <2 seconds (show cached data immediately)
- Full refresh: <5 seconds (fetch fresh data from Azure)
- Chart rendering: <500ms per chart
- Scroll performance: 60 FPS

### 7.2 Lightweight Charts

**Library Selection**:
```typescript
// Option 1: Recharts (Recommended)
// Pros: React-native, lightweight (~100KB gzipped), mobile-optimized
// Cons: Less feature-rich than Chart.js
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from 'recharts';

// Option 2: Chart.js
// Pros: Feature-rich, widely used
// Cons: Heavier (~200KB gzipped), not React-native
```

**Recommendation**: Use Recharts for mobile PWA

### 7.3 Data Reduction

**Challenge**: Azure Monitor returns high-granularity data (1-minute intervals)

**Solution**: Downsample for display

```typescript
function downsampleMetrics(
  data: DataPoint[],
  targetPoints: number = 30
): DataPoint[] {
  const step = Math.ceil(data.length / targetPoints);
  return data.filter((_, index) => index % step === 0);
}

// Example: 1-hour timespan with 1-minute intervals = 60 points
// Downsample to 30 points for mobile display
const displayData = downsampleMetrics(rawData, 30);
```

### 7.4 Progressive Loading

```typescript
// Load health cards progressively
const HealthDashboardPage = () => {
  const [visibleVMs, setVisibleVMs] = useState<string[]>([]);

  useEffect(() => {
    // Show first 5 VMs immediately
    setVisibleVMs(vms.slice(0, 5).map(vm => vm.id));

    // Load remaining VMs progressively
    const loadMore = async () => {
      for (let i = 5; i < vms.length; i += 5) {
        await new Promise(resolve => setTimeout(resolve, 100));
        setVisibleVMs(prev => [...prev, ...vms.slice(i, i + 5).map(vm => vm.id)]);
      }
    };

    loadMore();
  }, [vms]);

  return (
    <div>
      {visibleVMs.map(vmId => <HealthCard key={vmId} vmId={vmId} />)}
    </div>
  );
};
```

---

## 8. Testing Strategy

### 8.1 Unit Tests (60%)

```typescript
// health-calculator.test.ts
describe('calculateOverallHealth', () => {
  it('returns RED if any signal is critical', () => {
    const signals = {
      latency: { status: HealthStatus.GREEN },
      traffic: { status: HealthStatus.GREEN },
      errors: { status: HealthStatus.RED },  // One critical signal
      saturation: { status: HealthStatus.GREEN },
    };

    expect(calculateOverallHealth(signals)).toBe(HealthStatus.RED);
  });

  it('returns YELLOW if any signal is warning and none critical', () => {
    const signals = {
      latency: { status: HealthStatus.GREEN },
      traffic: { status: HealthStatus.YELLOW },  // One warning signal
      errors: { status: HealthStatus.GREEN },
      saturation: { status: HealthStatus.GREEN },
    };

    expect(calculateOverallHealth(signals)).toBe(HealthStatus.YELLOW);
  });
});
```

### 8.2 Integration Tests (30%)

```typescript
// health-store.test.ts
describe('fetchVMHealth thunk', () => {
  it('fetches health data and updates store', async () => {
    const mockMetrics = {
      value: [
        { name: { value: 'Percentage CPU' }, timeseries: [{ data: [{ average: 85 }] }] },
        { name: { value: 'Available Memory Bytes' }, timeseries: [{ data: [{ average: 2000000000 }] }] },
      ],
    };

    mockMonitorClient.getVMMetrics.mockResolvedValue(mockMetrics);

    await store.dispatch(fetchVMHealth({ vmId: 'test-vm' }));

    const state = store.getState().health;
    expect(state.vms['test-vm'].overallHealth).toBe(HealthStatus.YELLOW);
  });
});
```

### 8.3 E2E Tests (10%)

```typescript
// health-dashboard.e2e.test.ts
describe('Health Dashboard E2E', () => {
  it('shows fleet health summary and VM cards', async () => {
    await page.goto('/health');

    // Check fleet summary
    await expect(page.locator('.fleet-summary')).toContainText('3 Healthy');

    // Check VM cards rendered
    const cards = await page.locator('.health-card').count();
    expect(cards).toBeGreaterThan(0);

    // Click card to drill down
    await page.locator('.health-card').first().click();
    await expect(page.locator('h1')).toContainText('VM Details');
  });
});
```

---

## 9. Implementation Phases

### Phase 1: Metrics API Foundation (4-5 days) - MUST DO FIRST

**Goal**: Build Azure Monitor API client and basic metrics fetching

**Deliverables**:
1. `monitor-client.ts` - Azure Monitor API integration
2. Basic metrics fetching (CPU, memory, network)
3. Unit tests for API client
4. Redux store for metrics
5. Simple metrics display page (no health logic yet)

**Acceptance Criteria**:
- Can fetch VM metrics from Azure Monitor API
- Metrics displayed in simple list view
- Caching works (30-second TTL)
- Tests cover API integration

### Phase 2: Health Scoring (2 days)

**Goal**: Implement Four Golden Signals and health scoring algorithm

**Deliverables**:
1. `health-calculator.ts` - Health scoring logic
2. Four Golden Signals thresholds
3. Overall health calculation (worst-signal-wins)
4. Unit tests for health calculation

**Acceptance Criteria**:
- Health scores calculated correctly
- Thresholds configurable
- Tests cover edge cases

### Phase 3: Dashboard UI (3-4 days)

**Goal**: Build mobile-optimized dashboard

**Deliverables**:
1. `HealthDashboardPage.tsx` - Main dashboard
2. `HealthCard.tsx` - VM health card component
3. `HealthBadge.tsx` - Color-coded status badge
4. Fleet health summary
5. Filter by health status

**Acceptance Criteria**:
- Dashboard loads in <2 seconds
- Fleet summary shows correct counts
- Can filter by health status
- Mobile-responsive design

### Phase 4: Detailed Metrics & Drill-Down (2-3 days)

**Goal**: Add detailed metrics view with time-series charts

**Deliverables**:
1. `VMMetricsDetailPage.tsx` - Detailed view
2. `MetricChart.tsx` - Time-series chart component
3. Time range selector (15min/1hr/6hr/24hr)
4. Historical comparison (vs yesterday, last week)

**Acceptance Criteria**:
- Charts render in <500ms
- Can switch time ranges
- Historical data loads correctly

### Phase 5: Anomaly Detection (Phase 2 - Future)

**Goal**: AI-powered anomaly detection

**Deliverables**:
1. `anomaly-detector.ts` - Anomaly detection logic
2. Baseline calculation (7-day average)
3. Spike detection
4. Gradual increase detection (memory leaks)
5. Anomaly explanations

---

## 10. Dependencies & Prerequisites

### 10.1 Must Implement First

**Feature #4: VM Performance Metrics** (foundation for health dashboard)
- Monitor API client
- Metrics fetching and caching
- Basic metrics display

**Estimated Total Effort**:
- Feature #4 (Metrics API): 4-5 days
- Feature #9 (Health Dashboard): 3-4 days
- **Total: 7-9 days**

### 10.2 Azure Permissions Required

**RBAC Roles Needed**:
- `Reader` - Read VM information
- `Monitoring Reader` - Read Azure Monitor metrics
- `Virtual Machine Contributor` - Run commands (for disk usage)

**API Permissions**:
- `https://management.azure.com/.default` - Azure Management API

### 10.3 External Libraries

**New Dependencies**:
```json
{
  "dependencies": {
    "recharts": "^2.10.0",  // Lightweight charting library
    "idb": "^8.0.0"         // Already included (IndexedDB caching)
  }
}
```

---

## 11. Success Metrics

### 11.1 Performance Metrics

- **Page Load**: <2 seconds (cached), <5 seconds (fresh)
- **Chart Rendering**: <500ms per chart
- **API Response Time**: <2 seconds for metrics fetch
- **Cache Hit Rate**: >80% (reduce API calls)

### 11.2 User Adoption Metrics

- **Feature Usage**: >60% of users visit dashboard weekly
- **Problem Detection**: Users detect issues 50% faster
- **Time to Action**: <30 seconds from alert to taking action

### 11.3 Technical Metrics

- **API Error Rate**: <5%
- **Cache Efficiency**: >80% cache hit rate
- **Mobile Performance**: 60 FPS scrolling

---

## 12. Future Enhancements (Phase 2)

### 12.1 Predictive Alerts

"CPU trending up - may hit 100% in 2 hours"

### 12.2 Custom Thresholds

Users can customize health thresholds per VM

### 12.3 Health History

7-day health timeline showing when VMs were unhealthy

### 12.4 Multi-Subscription

Show health across multiple Azure subscriptions

### 12.5 Export & Reporting

Export health reports as PDF/CSV

---

## 13. Risk Assessment

### 13.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Azure Monitor API rate limiting | Medium | High | Implement aggressive caching, batch requests |
| Metrics data lag (5-minute delay) | High | Medium | Show "last updated" timestamp, explain lag to users |
| Disk usage requires Run Command (slow) | High | Medium | Cache disk usage for 5 minutes, mark as "approximate" |
| Memory % calculation requires VM size lookup | Medium | Medium | Pre-fetch VM sizes, cache in IndexedDB |

### 13.2 UX Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Too much data overwhelms users | Medium | High | Progressive disclosure: summary first, details on demand |
| False positives (alerts for normal behavior) | Medium | High | Phase 2: AI-powered baseline detection |
| Slow load times frustrate users | Low | High | Aggressive caching, progressive loading, performance budget |

---

## 14. Design Decisions & Rationale

### 14.1 Why Four Golden Signals?

**Decision**: Use Google's Four Golden Signals framework

**Rationale**:
- Industry-standard SRE practice (battle-tested)
- Comprehensive coverage (latency, traffic, errors, saturation)
- Avoids "metric overload" (only 4 categories)
- Mobile-friendly (fits on small screens)

**Alternative Considered**: USE Method (Utilization, Saturation, Errors)
- **Rejected**: Doesn't include latency, which is critical for user experience

### 14.2 Why Worst-Signal-Wins Algorithm?

**Decision**: Overall health determined by worst of four signals

**Rationale**:
- One bottleneck affects entire system (e.g., 98% CPU makes VM unusable even if memory is fine)
- Clear priority for action (fix the worst problem first)
- Aligns with SRE principles

**Alternative Considered**: Weighted average
- **Rejected**: Hides critical issues (e.g., 95% CPU + 50% memory + 50% disk = 65% "average health" looks fine)

### 14.3 Why Recharts Over Chart.js?

**Decision**: Use Recharts for charts

**Rationale**:
- React-native (better integration)
- Lightweight (~100KB vs ~200KB)
- Mobile-optimized out of the box
- Sufficient features for our needs

**Alternative Considered**: Chart.js
- **Rejected**: Heavier, not React-native, overkill for simple time-series

### 14.4 Why 30-Second Cache TTL?

**Decision**: Cache metrics for 30 seconds

**Rationale**:
- Balance freshness vs API cost
- Azure Monitor has 1-5 minute lag anyway (30s cache doesn't significantly increase staleness)
- Reduces API calls by ~90% (60-second refresh with 30-second cache = 50% cache hit rate minimum)

**Alternative Considered**: 60-second cache
- **Rejected**: Users expect "near real-time" on a health dashboard, 60s feels stale

---

## 15. Open Questions & Decisions Needed

### 15.1 Threshold Customization

**Question**: Should users be able to customize health thresholds (e.g., "80% CPU is normal for my workload")?

**Recommendation**: Phase 2 feature. Start with static thresholds, add customization later based on user feedback.

### 15.2 Multi-Signal Weights

**Question**: Should some signals be weighted higher than others (e.g., errors more important than saturation)?

**Recommendation**: No. Worst-signal-wins is simple and effective. Weighting adds complexity without clear benefit.

### 15.3 Historical Data Retention

**Question**: How long should we retain historical metrics data?

**Recommendation**:
- L1 cache (in-memory): 5 minutes
- L2 cache (IndexedDB): 1 hour
- Azure Monitor: 30 days (automatic)

For historical comparison, fetch from Azure Monitor on demand (e.g., when user views "vs yesterday" comparison).

---

## 16. Appendix: Azure Monitor API Examples

### 16.1 Fetch CPU Metrics

```bash
curl -X GET \
  "https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Compute/virtualMachines/{vmName}/providers/microsoft.insights/metrics?api-version=2024-02-01&metricnames=Percentage%20CPU&timespan=PT1H&interval=PT1M&aggregation=Average" \
  -H "Authorization: Bearer {token}"
```

**Response**:
```json
{
  "value": [
    {
      "name": { "value": "Percentage CPU" },
      "unit": "Percent",
      "timeseries": [
        {
          "data": [
            { "timeStamp": "2026-01-19T10:00:00Z", "average": 75.5 },
            { "timeStamp": "2026-01-19T10:01:00Z", "average": 78.2 },
            { "timeStamp": "2026-01-19T10:02:00Z", "average": 82.1 }
          ]
        }
      ]
    }
  ]
}
```

### 16.2 Fetch Multiple Metrics

```bash
curl -X GET \
  "https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Compute/virtualMachines/{vmName}/providers/microsoft.insights/metrics?api-version=2024-02-01&metricnames=Percentage%20CPU,Available%20Memory%20Bytes,Network%20In%20Total,Network%20Out%20Total&timespan=PT15M&interval=PT1M&aggregation=Average" \
  -H "Authorization: Bearer {token}"
```

---

## 17. Summary & Next Steps

### 17.1 What This Document Provides

1. **Clear scope**: Four Golden Signals for VM health
2. **Health scoring algorithm**: Worst-signal-wins with color-coded thresholds
3. **UI architecture**: Mobile-first dashboard with progressive disclosure
4. **Component design**: Modular "brick" architecture
5. **Azure API integration**: Monitor API endpoints and client implementation
6. **Caching strategy**: Multi-layer caching for performance
7. **Testing approach**: 60/30/10 pyramid
8. **Implementation phases**: 4 phases over 7-9 days total

### 17.2 Prerequisites

**MUST implement Feature #4 (VM Performance Metrics) first** (4-5 days):
- Azure Monitor API client
- Basic metrics fetching and caching
- Redux store for metrics

### 17.3 Next Actions

1. **Review this design** with stakeholders
2. **Implement Feature #4** (Metrics API foundation)
3. **Build health dashboard** (Phases 2-4)
4. **Test with real data**
5. **Iterate based on user feedback**

---

**Document Version**: 1.0
**Author**: Architect Agent (AI-powered)
**Date**: 2026-01-19
**Status**: Ready for Review

Arrr! This be yer complete design specification for the VM Health Dashboard, following the ruthless simplicity philosophy and brick architecture patterns! 🏴‍☠️
