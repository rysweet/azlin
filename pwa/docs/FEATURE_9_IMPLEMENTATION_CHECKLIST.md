# Feature #9: VM Health Dashboard - Implementation Checklist

**Purpose**: Step-by-step checklist for implementing the VM Health Dashboard

**Prerequisites**: Read `FEATURE_9_VM_HEALTH_DASHBOARD_DESIGN.md` first

---

## Phase 1: Metrics API Foundation (4-5 days) ⚓

**MUST COMPLETE BEFORE STARTING DASHBOARD**

### 1.1 Azure Monitor API Client

- [ ] Create `src/api/monitor-client.ts`
- [ ] Implement `AzureMonitorClient` class
  - [ ] Constructor with subscriptionId
  - [ ] Private `request()` method with auth
  - [ ] Public `getVMMetrics()` method
  - [ ] Error handling (rate limits, auth failures)
  - [ ] Retry logic (exponential backoff)
- [ ] Define TypeScript interfaces:
  - [ ] `MetricsQueryOptions`
  - [ ] `MetricsResponse`
  - [ ] `Metric`, `Timeseries`, `DataPoint`
- [ ] Add comprehensive JSDoc comments

**Test Coverage**:
- [ ] `monitor-client.test.ts` - Unit tests
  - [ ] Successful metrics fetch
  - [ ] Error handling (401, 429, 500)
  - [ ] Retry logic verification
  - [ ] Query parameter construction

**Acceptance Criteria**:
- [ ] Can fetch CPU, memory, network, disk metrics
- [ ] Handles Azure API errors gracefully
- [ ] Tests pass with 100% coverage

---

### 1.2 Redux Metrics Store

- [ ] Create `src/store/metrics-store.ts`
- [ ] Define state interface:
  ```typescript
  interface MetricsState {
    vms: Record<string, VMMetrics>;
    loading: boolean;
    error: string | null;
    lastRefresh: string | null;
  }
  ```
- [ ] Create async thunks:
  - [ ] `fetchVMMetrics` - Fetch fresh data from API
  - [ ] `refreshAllVMMetrics` - Bulk refresh
- [ ] Create reducers:
  - [ ] Handle pending/fulfilled/rejected states
  - [ ] Update lastRefresh timestamp
- [ ] Export selectors:
  - [ ] `selectVMMetrics(vmId)`
  - [ ] `selectLoadingState`
  - [ ] `selectError`

**Test Coverage**:
- [ ] `metrics-store.test.ts` - Integration tests
  - [ ] Thunk execution updates state
  - [ ] Error handling sets error state
  - [ ] Selectors return correct data

**Acceptance Criteria**:
- [ ] Redux DevTools shows state updates
- [ ] Thunks handle loading states correctly
- [ ] Error messages are user-friendly

---

### 1.3 Multi-Layer Caching

- [ ] Create `src/utils/metric-cache.ts`
- [ ] Implement L1 cache (in-memory):
  ```typescript
  class MetricCache {
    private cache: Map<string, CacheEntry>;
    private ttl: number = 30000; // 30 seconds
  }
  ```
- [ ] Implement L2 cache (IndexedDB):
  - [ ] Use `idb` library (already installed)
  - [ ] Create `metrics` object store
  - [ ] TTL: 5 minutes
- [ ] Add cache invalidation:
  - [ ] `invalidate(vmId)` - Clear specific VM
  - [ ] `invalidateAll()` - Clear entire cache
- [ ] Add cache statistics:
  - [ ] Hit/miss tracking
  - [ ] Hit rate calculation

**Test Coverage**:
- [ ] `metric-cache.test.ts`
  - [ ] L1 cache hit/miss
  - [ ] L2 cache fallback
  - [ ] TTL expiration
  - [ ] Cache invalidation

**Acceptance Criteria**:
- [ ] Cache hit rate >80% in production
- [ ] Stale data never shown (TTL respected)
- [ ] Tests verify cache behavior

---

### 1.4 Basic Metrics Display Page

- [ ] Create `src/pages/VMMetricsPage.tsx`
- [ ] Display metrics in simple list:
  - [ ] VM name
  - [ ] CPU %
  - [ ] Memory %
  - [ ] Network In/Out
  - [ ] Disk IOPS
- [ ] Add refresh button
- [ ] Show loading spinner
- [ ] Show error messages
- [ ] Add "Last updated" timestamp

**Test Coverage**:
- [ ] `VMMetricsPage.test.tsx` - Component tests
  - [ ] Renders loading state
  - [ ] Displays metrics when loaded
  - [ ] Shows error message on failure
  - [ ] Refresh button works

**Acceptance Criteria**:
- [ ] Page loads in <2 seconds (cached)
- [ ] Metrics update when refresh clicked
- [ ] Mobile-responsive layout

---

## Phase 2: Health Scoring (2 days) 🏴‍☠️

### 2.1 Health Calculator Utility

- [ ] Create `src/utils/health-calculator.ts`
- [ ] Define health enums and interfaces:
  ```typescript
  enum HealthStatus { GREEN, YELLOW, RED, GRAY }
  interface SignalThresholds { good, warning, critical }
  interface Signal { value, unit, status, threshold }
  interface FourGoldenSignals { latency, traffic, errors, saturation }
  ```
- [ ] Implement threshold functions:
  - [ ] `calculateCPUHealth(cpuPercent)`
  - [ ] `calculateMemoryHealth(memoryPercent)`
  - [ ] `calculateDiskHealth(diskPercent)`
  - [ ] `calculateNetworkHealth(networkPercent)`
- [ ] Implement overall health:
  - [ ] `calculateOverallHealth(signals)` - Worst-signal-wins

**Test Coverage**:
- [ ] `health-calculator.test.ts` - Comprehensive unit tests
  - [ ] CPU thresholds (75%, 85%, 95%)
  - [ ] Memory thresholds (80%, 90%, 100%)
  - [ ] Disk thresholds (85%, 95%, 100%)
  - [ ] Overall health (worst signal wins)
  - [ ] Edge cases (NaN, undefined, null)

**Acceptance Criteria**:
- [ ] All thresholds match design spec
- [ ] Tests cover 100% of logic
- [ ] JSDoc explains each function

---

### 2.2 Metrics-to-Health Transformation

- [ ] Create `src/utils/metric-aggregator.ts`
- [ ] Implement transformation functions:
  - [ ] `aggregateMetrics(rawMetrics)` - Parse Azure API response
  - [ ] `calculateLatencySignal(metrics)`
  - [ ] `calculateTrafficSignal(metrics)`
  - [ ] `calculateErrorsSignal(metrics)`
  - [ ] `calculateSaturationSignal(metrics)`
- [ ] Handle missing data:
  - [ ] Return `HealthStatus.GRAY` if insufficient data
  - [ ] Log warnings for missing metrics
- [ ] Calculate derived metrics:
  - [ ] Memory % from Available Memory Bytes + VM size
  - [ ] Network % from throughput + VM SKU limits

**Test Coverage**:
- [ ] `metric-aggregator.test.ts`
  - [ ] Successful transformation
  - [ ] Handles missing metrics
  - [ ] Derived metric calculations
  - [ ] Edge cases (zero values, spikes)

**Acceptance Criteria**:
- [ ] Correctly parses Azure Monitor API responses
- [ ] Handles all edge cases gracefully
- [ ] Tests use real API response fixtures

---

### 2.3 Health Redux Store

- [ ] Create `src/store/health-store.ts`
- [ ] Define state interface:
  ```typescript
  interface HealthState {
    vms: Record<string, VMHealthInfo>;
    loading: boolean;
    error: string | null;
    lastRefresh: string | null;
    autoRefreshEnabled: boolean;
    refreshInterval: number;
  }
  ```
- [ ] Create async thunks:
  - [ ] `fetchVMHealth(vmId)` - Fetch metrics + calculate health
  - [ ] `refreshAllVMHealth()` - Bulk health refresh
- [ ] Create reducers:
  - [ ] Update VM health in state
  - [ ] Handle auto-refresh toggle
  - [ ] Update refresh interval
- [ ] Export selectors:
  - [ ] `selectVMHealth(vmId)`
  - [ ] `selectFleetHealthSummary()` - Count healthy/warning/critical
  - [ ] `selectAutoRefreshSettings()`

**Test Coverage**:
- [ ] `health-store.test.ts` - Integration tests
  - [ ] Thunk fetches metrics and calculates health
  - [ ] Fleet summary counts correctly
  - [ ] Auto-refresh settings update

**Acceptance Criteria**:
- [ ] Health data updates in Redux DevTools
- [ ] Fleet summary accurate
- [ ] Tests verify complete flow

---

## Phase 3: Dashboard UI (3-4 days) 🗺️

### 3.1 Health Badge Component

- [ ] Create `src/components/HealthBadge.tsx`
- [ ] Props: `status: HealthStatus`
- [ ] Render color-coded badge:
  - [ ] 🟢 GREEN - "Healthy" - Background: #4caf50
  - [ ] 🟡 YELLOW - "Warning" - Background: #ff9800
  - [ ] 🔴 RED - "Critical" - Background: #f44336
  - [ ] ⚫ GRAY - "Unknown" - Background: #9e9e9e
- [ ] Add accessibility:
  - [ ] ARIA labels
  - [ ] High contrast colors
- [ ] Mobile-optimized sizing

**Test Coverage**:
- [ ] `HealthBadge.test.tsx`
  - [ ] Renders correct color for each status
  - [ ] Accessibility attributes present

**Acceptance Criteria**:
- [ ] Visually distinct colors
- [ ] Passes accessibility audit

---

### 3.2 Signal Indicator Component

- [ ] Create `src/components/SignalIndicator.tsx`
- [ ] Props: `signal: Signal`
- [ ] Layout:
  ```
  [Icon] Latency
  🟢    <2s
  ```
- [ ] Show icon + name + status + value
- [ ] Tap to show explanation popover
- [ ] Mobile-optimized touch targets (min 44x44px)

**Test Coverage**:
- [ ] `SignalIndicator.test.tsx`
  - [ ] Renders signal data
  - [ ] Popover shows on tap
  - [ ] Correct colors displayed

**Acceptance Criteria**:
- [ ] Touch-friendly on mobile
- [ ] Clear visual hierarchy

---

### 3.3 VM Health Card Component

- [ ] Create `src/components/HealthCard.tsx`
- [ ] Props: `vmId: string`
- [ ] Layout (following design spec):
  - [ ] VM name + overall health badge
  - [ ] VM size + location
  - [ ] Four signal indicators
  - [ ] Anomaly warning (if present)
  - [ ] "Last updated" timestamp
  - [ ] Action buttons
- [ ] Interactions:
  - [ ] Tap card → Navigate to detail view
  - [ ] Swipe left → Show quick actions
  - [ ] Long press → Add to favorites
- [ ] Performance:
  - [ ] Memoize with `React.memo`
  - [ ] Lazy load images if any

**Test Coverage**:
- [ ] `HealthCard.test.tsx`
  - [ ] Renders VM info correctly
  - [ ] Tap navigation works
  - [ ] Swipe reveals actions
  - [ ] Long press adds to favorites

**Acceptance Criteria**:
- [ ] Smooth 60 FPS scrolling
- [ ] Touch gestures responsive
- [ ] Mobile-optimized layout

---

### 3.4 Fleet Health Summary Component

- [ ] Create `src/components/FleetHealthSummary.tsx`
- [ ] Props: None (reads from Redux)
- [ ] Display:
  - [ ] 🟢 X Healthy
  - [ ] 🟡 Y Warning
  - [ ] 🔴 Z Critical
- [ ] Tap status to filter
- [ ] Show total VM count
- [ ] Refresh button

**Test Coverage**:
- [ ] `FleetHealthSummary.test.tsx`
  - [ ] Counts match Redux state
  - [ ] Filter works on tap
  - [ ] Refresh updates data

**Acceptance Criteria**:
- [ ] Real-time updates
- [ ] Correct counts

---

### 3.5 Health Dashboard Page

- [ ] Create `src/pages/HealthDashboardPage.tsx`
- [ ] Layout:
  - [ ] Fleet health summary at top
  - [ ] Filter controls (dropdown)
  - [ ] VM health cards (scrollable list)
  - [ ] Floating refresh button (bottom-right)
- [ ] Features:
  - [ ] Filter by health status (all/healthy/warning/critical)
  - [ ] Sort by (health/name/last updated)
  - [ ] Pull-to-refresh (mobile gesture)
  - [ ] Auto-refresh toggle
  - [ ] Empty state (no VMs)
  - [ ] Error state
  - [ ] Loading skeleton
- [ ] Performance:
  - [ ] Progressive loading (5 VMs at a time)
  - [ ] Virtualized list (react-window) if >20 VMs
  - [ ] Debounce filter changes

**Test Coverage**:
- [ ] `HealthDashboardPage.test.tsx`
  - [ ] Renders all components
  - [ ] Filtering works
  - [ ] Sorting works
  - [ ] Pull-to-refresh triggers fetch
  - [ ] Auto-refresh timer works

**Acceptance Criteria**:
- [ ] Page loads in <2 seconds
- [ ] Smooth scrolling (60 FPS)
- [ ] Mobile-responsive

---

### 3.6 Routing & Navigation

- [ ] Update `src/App.tsx`
- [ ] Add route: `/health`
- [ ] Add navigation link in main menu
- [ ] Add route: `/health/:vmId` (detail view)
- [ ] Handle back navigation
- [ ] Add route guards (auth required)

**Test Coverage**:
- [ ] `App.test.tsx` - Integration tests
  - [ ] Routes render correctly
  - [ ] Navigation works
  - [ ] Auth guards redirect

**Acceptance Criteria**:
- [ ] Deep linking works
- [ ] Back button behaves correctly

---

## Phase 4: Detailed Metrics View (2-3 days) 📊

### 4.1 Metric Chart Component

- [ ] Install `recharts`: `npm install recharts`
- [ ] Create `src/components/MetricChart.tsx`
- [ ] Props: `metric: Metric, threshold: SignalThresholds`
- [ ] Features:
  - [ ] Line chart with time-series data
  - [ ] Threshold lines (warning, critical)
  - [ ] Tooltips on hover/tap
  - [ ] Responsive to container size
  - [ ] Gradient fill under line
  - [ ] Legend
- [ ] Optimizations:
  - [ ] Downsample data (60 → 30 points)
  - [ ] Memoize chart rendering
  - [ ] Lazy load chart library

**Test Coverage**:
- [ ] `MetricChart.test.tsx`
  - [ ] Renders chart correctly
  - [ ] Threshold lines displayed
  - [ ] Tooltips work
  - [ ] Responsive sizing

**Acceptance Criteria**:
- [ ] Chart renders in <500ms
- [ ] Mobile-optimized touch interactions

---

### 4.2 Time Range Selector

- [ ] Create `src/components/TimeRangeSelector.tsx`
- [ ] Options: [15min] [1hr] [6hr] [24hr]
- [ ] Highlight selected range
- [ ] Trigger data refetch on change
- [ ] Persist selection (localStorage)

**Test Coverage**:
- [ ] `TimeRangeSelector.test.tsx`
  - [ ] Selection changes state
  - [ ] Triggers data fetch
  - [ ] Persists to localStorage

**Acceptance Criteria**:
- [ ] Selection persists across sessions
- [ ] Data loads within 2 seconds

---

### 4.3 Historical Comparison Component

- [ ] Create `src/components/HistoricalComparison.tsx`
- [ ] Show comparison:
  - [ ] vs. Yesterday
  - [ ] vs. Last Week
- [ ] Display delta (% change):
  - [ ] 🔺 +12% CPU (red if increase)
  - [ ] 🔻 -5% Memory (green if decrease)
- [ ] Fetch historical data from Azure Monitor

**Test Coverage**:
- [ ] `HistoricalComparison.test.tsx`
  - [ ] Calculates delta correctly
  - [ ] Handles missing historical data
  - [ ] Displays direction indicators

**Acceptance Criteria**:
- [ ] Accurate comparisons
- [ ] Clear visual indicators

---

### 4.4 VM Metrics Detail Page

- [ ] Create `src/pages/VMMetricsDetailPage.tsx`
- [ ] Layout:
  - [ ] Header: VM name + overall health
  - [ ] Time range selector
  - [ ] Four metric charts (CPU, Memory, Disk, Network)
  - [ ] Historical comparison
  - [ ] Anomaly detection section
  - [ ] Quick actions (restart, stop, view logs)
- [ ] Features:
  - [ ] Fetch detailed metrics on mount
  - [ ] Update when time range changes
  - [ ] Back button navigation
  - [ ] Loading skeleton for charts
  - [ ] Error handling
- [ ] Performance:
  - [ ] Lazy load charts
  - [ ] Only fetch visible time range

**Test Coverage**:
- [ ] `VMMetricsDetailPage.test.tsx`
  - [ ] Renders all sections
  - [ ] Time range changes update charts
  - [ ] Back navigation works
  - [ ] Error state displays

**Acceptance Criteria**:
- [ ] Page loads in <3 seconds
- [ ] Charts render smoothly
- [ ] Mobile-optimized

---

## Phase 5: Polish & Optimization (1-2 days) ⚡

### 5.1 Auto-Refresh Logic

- [ ] Add auto-refresh toggle to UI
- [ ] Default: ON, 60-second interval
- [ ] Settings UI:
  - [ ] Toggle switch
  - [ ] Interval selector (30s/60s/120s/300s)
  - [ ] Battery warning (<20% battery)
- [ ] Implementation:
  - [ ] `useEffect` hook with `setInterval`
  - [ ] Clear interval on unmount
  - [ ] Pause when tab backgrounded (Page Visibility API)

**Test Coverage**:
- [ ] Auto-refresh integration tests
  - [ ] Timer fires at correct interval
  - [ ] Pauses when tab hidden
  - [ ] Battery warning shows at 20%

**Acceptance Criteria**:
- [ ] Auto-refresh works reliably
- [ ] Battery-conscious behavior

---

### 5.2 Error Handling & Recovery

- [ ] Implement error boundaries
- [ ] Add retry logic for failed fetches
- [ ] Fallback to cached data on API failure
- [ ] User-friendly error messages:
  - [ ] "Unable to fetch metrics. Showing cached data."
  - [ ] "Rate limit exceeded. Retrying in X seconds."
  - [ ] "Authentication expired. Please sign in again."
- [ ] Error reporting (console logs for debugging)

**Test Coverage**:
- [ ] Error handling tests
  - [ ] Error boundary catches errors
  - [ ] Retry logic works
  - [ ] Fallback displays cached data

**Acceptance Criteria**:
- [ ] App never crashes
- [ ] Errors shown with recovery actions

---

### 5.3 Performance Optimization

- [ ] Measure performance:
  - [ ] Lighthouse audit (target: >90 score)
  - [ ] React DevTools Profiler
  - [ ] Network tab (minimize API calls)
- [ ] Optimizations:
  - [ ] Code splitting (lazy load routes)
  - [ ] Memoize expensive calculations
  - [ ] Virtualize long lists (react-window)
  - [ ] Compress images
  - [ ] Service worker caching
- [ ] Monitor metrics:
  - [ ] First Contentful Paint <1.5s
  - [ ] Time to Interactive <3s
  - [ ] Cumulative Layout Shift <0.1

**Acceptance Criteria**:
- [ ] Lighthouse score >90
- [ ] 60 FPS scrolling
- [ ] No memory leaks

---

### 5.4 Accessibility Audit

- [ ] Run accessibility tests:
  - [ ] Lighthouse accessibility audit
  - [ ] Screen reader testing (VoiceOver/TalkBack)
  - [ ] Keyboard navigation
- [ ] Fixes:
  - [ ] ARIA labels on all interactive elements
  - [ ] Focus indicators visible
  - [ ] Color contrast ratio ≥4.5:1
  - [ ] Semantic HTML (headings, landmarks)
- [ ] Documentation:
  - [ ] Accessibility statement in README

**Acceptance Criteria**:
- [ ] WCAG 2.1 AA compliant
- [ ] Lighthouse accessibility score 100

---

### 5.5 Documentation

- [ ] User-facing docs:
  - [ ] Update README with health dashboard feature
  - [ ] Screenshot of dashboard UI
  - [ ] Explanation of Four Golden Signals
- [ ] Developer docs:
  - [ ] Architecture diagram
  - [ ] API integration guide
  - [ ] Component documentation (Storybook or similar)
- [ ] Inline code comments:
  - [ ] JSDoc on all public functions
  - [ ] Complex logic explained

**Acceptance Criteria**:
- [ ] Comprehensive documentation
- [ ] Screenshots up-to-date
- [ ] All public APIs documented

---

## Final Checklist ✅

### Pre-Launch

- [ ] All tests pass (unit, integration, e2e)
- [ ] Test coverage >80%
- [ ] Lighthouse audit passed (>90 score)
- [ ] Accessibility audit passed (WCAG AA)
- [ ] Manual testing on real devices:
  - [ ] iOS Safari
  - [ ] Android Chrome
  - [ ] Desktop Chrome
- [ ] Performance benchmarks met:
  - [ ] Page load <2s
  - [ ] Chart render <500ms
  - [ ] Scroll 60 FPS
- [ ] Error handling verified
- [ ] Documentation complete

### Post-Launch

- [ ] Monitor production metrics:
  - [ ] Cache hit rate
  - [ ] API error rate
  - [ ] User engagement (visits to dashboard)
- [ ] Gather user feedback
- [ ] Plan Phase 2 features (anomaly detection, custom thresholds)

---

## Dependencies Installed

```bash
# Install required packages
npm install recharts
npm install @types/recharts --save-dev
```

Existing packages (already installed):
- `@azure/arm-monitor` - Azure Monitor API
- `idb` - IndexedDB caching
- `@reduxjs/toolkit` - State management
- `react-router-dom` - Routing

---

## Estimated Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Phase 1: Metrics API Foundation | 4-5 days | 5 days |
| Phase 2: Health Scoring | 2 days | 7 days |
| Phase 3: Dashboard UI | 3-4 days | 11 days |
| Phase 4: Detailed Metrics View | 2-3 days | 14 days |
| Phase 5: Polish & Optimization | 1-2 days | 16 days |

**Total: 12-16 days** (including Feature #4 foundation)

**Note**: Original estimate was 7-9 days assuming Feature #4 complete. Adjusted to 12-16 days for full implementation from scratch.

---

## Success Criteria

**Technical**:
- [ ] All tests pass with >80% coverage
- [ ] Lighthouse score >90
- [ ] Page load <2 seconds
- [ ] Chart rendering <500ms
- [ ] Cache hit rate >80%

**User Experience**:
- [ ] Can answer "Is everything OK?" in <5 seconds
- [ ] Fleet health summary accurate
- [ ] Drill-down to VM details intuitive
- [ ] Mobile-optimized and responsive

**Business**:
- [ ] >60% of users visit dashboard weekly
- [ ] Users detect issues 50% faster
- [ ] Time to action <30 seconds from alert

---

**Document Version**: 1.0
**Date**: 2026-01-19
**Status**: Ready for Implementation

Arrr! This checklist be yer treasure map to implementin' the VM Health Dashboard, step by step! 🏴‍☠️

**Pro Tip**: Check off items as ye complete 'em, and update the timeline if things change. Good luck, matey!
