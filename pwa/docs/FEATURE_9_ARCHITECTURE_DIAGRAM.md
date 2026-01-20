# Feature #9: VM Health Dashboard - Architecture Diagram

This document provides visual diagrams for the VM Health Dashboard architecture.

---

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph "Mobile PWA"
        UI[Health Dashboard UI]
        Store[Redux Health Store]
        Cache[Multi-Layer Cache]
    end

    subgraph "API Clients"
        MonitorClient[Azure Monitor Client]
        VMClient[Azure VM Client]
    end

    subgraph "Azure Services"
        Monitor[Azure Monitor API]
        Management[Azure Management API]
        RunCommand[Run Command API]
    end

    UI -->|dispatch actions| Store
    Store -->|fetch health| MonitorClient
    Store -->|fetch disk usage| VMClient
    MonitorClient -->|get metrics| Monitor
    VMClient -->|execute command| RunCommand
    Store <-->|read/write| Cache

    style UI fill:#4CAF50
    style Store fill:#2196F3
    style Cache fill:#FF9800
    style Monitor fill:#9C27B0
    style Management fill:#9C27B0
    style RunCommand fill:#9C27B0
```

---

## 2. Health Scoring Flow

```mermaid
flowchart TD
    Start[Fetch VM Metrics] --> GetMetrics[Azure Monitor API]
    GetMetrics --> CPU[CPU %]
    GetMetrics --> Memory[Memory %]
    GetMetrics --> Network[Network %]
    GetMetrics --> Disk[Disk IOPS]

    CPU --> CPUScore{Score CPU}
    Memory --> MemScore{Score Memory}
    Network --> NetScore{Score Network}
    Disk --> DiskScore{Score Disk}

    CPUScore -->|<80%| Green1[GREEN]
    CPUScore -->|80-95%| Yellow1[YELLOW]
    CPUScore -->|>95%| Red1[RED]

    MemScore -->|<80%| Green2[GREEN]
    MemScore -->|80-90%| Yellow2[YELLOW]
    MemScore -->|>90%| Red2[RED]

    NetScore -->|<80%| Green3[GREEN]
    NetScore -->|80-95%| Yellow3[YELLOW]
    NetScore -->|>95%| Red3[RED]

    DiskScore -->|<85%| Green4[GREEN]
    DiskScore -->|85-95%| Yellow4[YELLOW]
    DiskScore -->|>95%| Red4[RED]

    Green1 & Yellow1 & Red1 --> Aggregate[Worst Signal Wins]
    Green2 & Yellow2 & Red2 --> Aggregate
    Green3 & Yellow3 & Red3 --> Aggregate
    Green4 & Yellow4 & Red4 --> Aggregate

    Aggregate --> Overall{Overall Health}
    Overall -->|Any RED| FinalRed[🔴 CRITICAL]
    Overall -->|Any YELLOW| FinalYellow[🟡 WARNING]
    Overall -->|All GREEN| FinalGreen[🟢 HEALTHY]

    style FinalRed fill:#f44336,color:#fff
    style FinalYellow fill:#ff9800,color:#000
    style FinalGreen fill:#4caf50,color:#fff
```

---

## 3. Component Hierarchy

```mermaid
graph TB
    App[App.tsx]
    App --> Dashboard[HealthDashboardPage]

    Dashboard --> Summary[Fleet Health Summary]
    Dashboard --> Filters[Filter Controls]
    Dashboard --> VMList[VM Health Cards List]

    VMList --> Card1[HealthCard VM-1]
    VMList --> Card2[HealthCard VM-2]
    VMList --> Card3[HealthCard VM-N]

    Card1 --> Badge1[HealthBadge]
    Card1 --> Signals1[SignalIndicator x4]
    Card1 --> Actions1[Quick Actions]

    Card1 -->|Tap| Details[VMMetricsDetailPage]

    Details --> TimeSelect[Time Range Selector]
    Details --> Charts[MetricChart Components]
    Details --> Anomalies[Anomaly Detection]
    Details --> Historical[Historical Comparison]

    Charts --> CPUChart[CPU Chart]
    Charts --> MemChart[Memory Chart]
    Charts --> NetChart[Network Chart]
    Charts --> DiskChart[Disk Chart]

    style Dashboard fill:#2196F3,color:#fff
    style Card1 fill:#4CAF50,color:#fff
    style Details fill:#9C27B0,color:#fff
```

---

## 4. Data Flow & Caching

```mermaid
sequenceDiagram
    participant User
    participant UI as Dashboard UI
    participant Store as Redux Store
    participant L1 as L1 Cache (Memory)
    participant L2 as L2 Cache (IndexedDB)
    participant API as Azure Monitor API

    User->>UI: Open Health Dashboard
    UI->>Store: dispatch(fetchVMHealth)

    Store->>L1: Check cache (30s TTL)
    alt L1 Cache Hit
        L1-->>Store: Return cached data
        Store-->>UI: Update UI (instant)
    else L1 Cache Miss
        Store->>L2: Check IndexedDB (5min TTL)
        alt L2 Cache Hit
            L2-->>Store: Return cached data
            Store-->>UI: Update UI (<100ms)
        else L2 Cache Miss
            Store->>API: Fetch metrics
            API-->>Store: Return fresh data (2-5s)
            Store->>L2: Save to IndexedDB
            Store->>L1: Save to memory
            Store-->>UI: Update UI
        end
    end

    Note over Store,API: Auto-refresh every 60s<br/>if enabled
```

---

## 5. Four Golden Signals Mapping

```mermaid
mindmap
  root((Four Golden Signals))
    Latency
      SSH Connection Time
        Bastion API
        Custom Timing
      API Response Time
        Azure Management
        Response Headers
      Disk Latency
        Azure Monitor
        Read/Write Latency
    Traffic
      Network Throughput
        Bytes In/Out per sec
        Azure Monitor
      Disk IOPS
        Operations per sec
        Azure Monitor
      Active Connections
        Run Command
        netstat count
    Errors
      Failed SSH Attempts
        Activity Log
        Auth Failures
      Disk I/O Errors
        Azure Monitor
        Error Metrics
      OOM Events
        Boot Diagnostics
        Console Logs
    Saturation
      CPU Utilization
        Percentage CPU
        Azure Monitor
      Memory Usage
        Available Memory
        Calculate from Size
      Disk Space
        Run Command
        df command
      Network Bandwidth
        Bytes In/Out
        vs VM SKU Limit
```

---

## 6. Mobile UI Flow

```mermaid
stateDiagram-v2
    [*] --> Dashboard: Open App
    Dashboard --> VMCard: View VMs
    VMCard --> QuickActions: Swipe Left
    VMCard --> DetailView: Tap Card
    VMCard --> Favorite: Long Press

    DetailView --> TimeRange: Select Range
    TimeRange --> DetailView: Update Charts
    DetailView --> Comparison: View Historical
    Comparison --> DetailView: Back

    QuickActions --> Restart: Tap Restart
    QuickActions --> Stop: Tap Stop
    QuickActions --> Logs: View Logs

    Dashboard --> Filtered: Apply Filter
    Filtered --> Dashboard: Clear Filter

    DetailView --> Dashboard: Back Button
    Restart --> Dashboard: Action Complete
    Stop --> Dashboard: Action Complete
    Logs --> Dashboard: Back

    note right of Dashboard
        Fleet Summary
        🟢 3 Healthy
        🟡 1 Warning
        🔴 0 Critical
    end note

    note right of DetailView
        Full Metrics
        - CPU/Memory/Disk/Net
        - Time-series charts
        - Anomaly detection
    end note
```

---

## 7. Redux State Structure

```typescript
// Visualized as diagram
interface HealthState {
  // VM health data keyed by VM ID
  vms: {
    "vm-1": VMHealthInfo,
    "vm-2": VMHealthInfo,
    "vm-3": VMHealthInfo,
  },

  // UI state
  loading: boolean,
  error: string | null,

  // Cache metadata
  lastRefresh: "2026-01-19T10:30:00Z",
  autoRefreshEnabled: true,
  refreshInterval: 60, // seconds

  // Filters
  filters: {
    healthStatus: 'all' | 'healthy' | 'warning' | 'critical',
    resourceGroup: 'all' | 'specific-rg',
    sortBy: 'health' | 'name' | 'lastUpdated',
  }
}
```

**Diagram**:
```mermaid
graph LR
    subgraph "Redux Store"
        State[HealthState]
        State --> VMs[vms: Map<vmId, VMHealthInfo>]
        State --> UI[UI State: loading, error]
        State --> Cache[Cache Metadata]
        State --> Filters[Filters & Sorting]
    end

    subgraph "VMHealthInfo"
        VMH[VMHealthInfo]
        VMH --> Signals[Four Golden Signals]
        VMH --> Overall[Overall Health Status]
        VMH --> Anomalies[Detected Anomalies]
    end

    VMs --> VMH

    style State fill:#2196F3,color:#fff
    style VMH fill:#4CAF50,color:#fff
```

---

## 8. API Integration Pattern

```mermaid
sequenceDiagram
    participant Component
    participant Thunk as Async Thunk
    participant Monitor as MonitorClient
    participant Azure as Azure Monitor API

    Component->>Thunk: dispatch(fetchVMHealth)
    activate Thunk

    Thunk->>Monitor: getVMMetrics(vmId, options)
    activate Monitor

    Monitor->>Azure: GET /metrics
    activate Azure
    Azure-->>Monitor: Metrics Response
    deactivate Azure

    Monitor->>Monitor: Parse Response
    Monitor-->>Thunk: Structured Metrics
    deactivate Monitor

    Thunk->>Thunk: calculateHealthFromMetrics()
    Thunk->>Thunk: detectAnomalies()

    Thunk-->>Component: VMHealthInfo
    deactivate Thunk

    Component->>Component: Render HealthCard
```

---

## 9. Error Handling Flow

```mermaid
flowchart TD
    Start[Fetch VM Health] --> API[Call Azure API]

    API --> Success{API Success?}
    Success -->|Yes| Parse[Parse Response]
    Success -->|No| CheckError{Error Type?}

    CheckError -->|429 Rate Limit| Retry[Wait & Retry]
    CheckError -->|401 Auth| Refresh[Refresh Token]
    CheckError -->|500 Server| Fallback[Use Cached Data]
    CheckError -->|Network| Queue[Queue for Later]

    Retry --> API
    Refresh --> API
    Fallback --> Display[Display with Warning]
    Queue --> Display

    Parse --> Calculate[Calculate Health]
    Calculate --> Store[Update Redux Store]
    Store --> Display[Render UI]

    Display --> End[Done]

    style CheckError fill:#ff9800
    style Fallback fill:#4caf50
    style Display fill:#2196F3
```

---

## 10. Performance Optimization Strategy

```mermaid
graph TB
    subgraph "Performance Layers"
        L1[L1: In-Memory Cache<br/>30s TTL, Instant]
        L2[L2: IndexedDB<br/>5min TTL, <100ms]
        L3[L3: Azure API<br/>Fresh Data, 2-5s]
    end

    subgraph "Optimization Techniques"
        Downsample[Downsample Data<br/>60 points → 30 points]
        Progressive[Progressive Loading<br/>Load 5 VMs at a time]
        LazyCharts[Lazy Load Charts<br/>Only visible VMs]
    end

    subgraph "Target Metrics"
        Load[Page Load: <2s]
        Chart[Chart Render: <500ms]
        Scroll[Scroll: 60 FPS]
    end

    L1 --> Downsample
    L2 --> Progressive
    L3 --> LazyCharts

    Downsample --> Load
    Progressive --> Load
    LazyCharts --> Chart

    style L1 fill:#4caf50
    style L2 fill:#ff9800
    style L3 fill:#2196F3
    style Load fill:#9c27b0,color:#fff
```

---

## 11. Testing Pyramid

```mermaid
graph TB
    subgraph "Testing Strategy (60/30/10)"
        Unit[Unit Tests: 60%<br/>- Health calculation<br/>- Threshold logic<br/>- Data parsing]
        Integration[Integration Tests: 30%<br/>- API client<br/>- Redux thunks<br/>- Component rendering]
        E2E[E2E Tests: 10%<br/>- Full user flows<br/>- Dashboard interaction<br/>- Drill-down navigation]
    end

    Unit --> Fast[Fast: <1s]
    Integration --> Medium[Medium: 1-5s]
    E2E --> Slow[Slow: 10-30s]

    Fast --> CI[Run on every commit]
    Medium --> CI
    Slow --> PreMerge[Run before PR merge]

    style Unit fill:#4caf50
    style Integration fill:#ff9800
    style E2E fill:#2196F3
```

---

## Summary

These diagrams provide a comprehensive visual guide to the VM Health Dashboard architecture:

1. **System Architecture**: High-level component interaction
2. **Health Scoring Flow**: Decision tree for health calculation
3. **Component Hierarchy**: UI component structure
4. **Data Flow**: Caching and API integration
5. **Four Golden Signals**: Metric mapping
6. **Mobile UI Flow**: User interaction states
7. **Redux State**: Data structure
8. **API Integration**: Sequence diagram
9. **Error Handling**: Recovery strategies
10. **Performance**: Optimization layers
11. **Testing**: Test pyramid

**Next Steps**: Review these diagrams alongside the main design spec (`FEATURE_9_VM_HEALTH_DASHBOARD_DESIGN.md`) before implementation.

---

**Version**: 1.0
**Date**: 2026-01-19
**Status**: Complete

Arrr matey! These diagrams chart the course for yer VM Health Dashboard implementation! 🏴‍☠️
