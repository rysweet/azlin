# Feature #9: VM Health Dashboard - Summary

**Quick Reference**: Executive summary of the VM Health Dashboard design

---

## What Is This Feature?

An SRE-style health dashboard that shows VM fleet health at a glance using Google's Four Golden Signals, optimized for mobile.

**User Goal**: Answer "Is everything OK?" in <5 seconds on mobile

---

## Key Design Decisions

### 1. Four Golden Signals (Google SRE Standard)

- **Latency**: SSH connection time, API response time, disk latency
- **Traffic**: Network throughput, disk IOPS, active connections
- **Errors**: Failed SSH attempts, disk I/O errors, OOM events
- **Saturation**: CPU/memory/disk/network utilization %

**Why**: Industry-standard, comprehensive, mobile-friendly (only 4 categories)

### 2. Worst-Signal-Wins Health Scoring

Overall VM health = worst of the four signals

**Why**: One bottleneck affects entire system (e.g., 98% CPU makes VM unusable even if memory is fine)

### 3. Multi-Layer Caching (30s TTL)

- L1: In-memory (30s TTL, instant)
- L2: IndexedDB (5min TTL, <100ms)
- L3: Azure API (2-5s latency)

**Why**: Azure Monitor API has rate limits and 1-5 minute metric lag. Caching reduces API calls by ~90%.

### 4. Progressive Disclosure UI

Summary first → Details on demand

**Why**: Mobile screens are small. Show essential info immediately, drill down for details.

---

## Architecture at a Glance

```
User Interface (React)
    ↓
Redux Store (health-store.ts)
    ↓
API Clients (monitor-client.ts, azure-client.ts)
    ↓
Azure Services (Monitor API, Run Command API)
```

**Key Components**:
- `HealthDashboardPage` - Main dashboard with fleet summary
- `HealthCard` - Individual VM health card
- `VMMetricsDetailPage` - Drill-down with time-series charts
- `MetricChart` - Recharts-based time-series visualization

---

## Implementation Phases

| Phase | What | Duration |
|-------|------|----------|
| 1 | **Metrics API Foundation** (monitor-client, basic display) | 4-5 days |
| 2 | **Health Scoring** (health-calculator, thresholds) | 2 days |
| 3 | **Dashboard UI** (HealthCard, fleet summary, filters) | 3-4 days |
| 4 | **Detailed Metrics View** (charts, time ranges, comparisons) | 2-3 days |
| 5 | **Polish** (auto-refresh, error handling, optimization) | 1-2 days |

**Total: 12-16 days**

---

## Success Metrics

**Performance**:
- Page load: <2 seconds (cached)
- Chart rendering: <500ms
- Lighthouse score: >90

**User Experience**:
- Answer "Is everything OK?" in <5 seconds
- >60% weekly active usage
- 50% faster issue detection

---

## Files Created

### Design Documents (In `/docs`)

1. **`FEATURE_9_VM_HEALTH_DASHBOARD_DESIGN.md`** (Main Spec)
   - Complete design specification (17 sections)
   - Four Golden Signals detailed
   - Health scoring algorithm
   - Azure Monitor API integration
   - UI architecture
   - Testing strategy
   - Risk assessment

2. **`FEATURE_9_ARCHITECTURE_DIAGRAM.md`** (Visual Reference)
   - 11 Mermaid diagrams
   - System architecture
   - Health scoring flow
   - Component hierarchy
   - Data flow & caching
   - Mobile UI flow
   - Redux state structure
   - Testing pyramid

3. **`FEATURE_9_IMPLEMENTATION_CHECKLIST.md`** (Step-by-Step)
   - Complete implementation checklist (5 phases)
   - Checkboxes for every task
   - Test coverage requirements
   - Acceptance criteria
   - Timeline estimates

4. **`FEATURE_9_SUMMARY.md`** (This File)
   - Executive summary
   - Quick reference

---

## Critical Dependencies

### MUST Implement First

**Feature #4: VM Performance Metrics** (4-5 days)
- Azure Monitor API client
- Metrics fetching and caching
- Basic metrics display

**Why**: Health dashboard builds on top of metrics infrastructure

### Azure Permissions Required

- `Reader` - Read VM information
- `Monitoring Reader` - Read Azure Monitor metrics
- `Virtual Machine Contributor` - Run commands (for disk usage)

### External Libraries

```json
{
  "dependencies": {
    "recharts": "^2.10.0"  // Lightweight charting (NEW)
  }
}
```

Existing dependencies (already installed):
- `@azure/arm-monitor`
- `idb`
- `@reduxjs/toolkit`
- `react-router-dom`

---

## Key Technical Challenges & Solutions

### Challenge 1: Azure Monitor Metric Lag (1-5 minutes)

**Solution**: Show "Last updated" timestamp and explain lag to users. Cache aggressively (30s TTL).

### Challenge 2: Disk Usage Not in Azure Monitor

**Solution**: Use Run Command API to execute `df -h /` on VM. Cache for 5 minutes.

### Challenge 3: Memory % Calculation

**Solution**: Azure Monitor returns "Available Memory Bytes". Calculate % using VM size lookup:
```typescript
memoryPercent = ((vmSize.totalMemory - availableMemory) / vmSize.totalMemory) * 100
```

### Challenge 4: Mobile Performance

**Solution**:
- Downsample chart data (60 → 30 points)
- Progressive loading (5 VMs at a time)
- Lazy load charts (only visible VMs)
- Virtualize long lists (react-window if >20 VMs)

---

## Design Philosophy Compliance

### Ruthless Simplicity ✅

- Only 4 health signals (not 20+ metrics)
- Worst-signal-wins (no complex weighting)
- Static thresholds initially (no premature AI complexity)

### Zero-BS Implementation ✅

- Every function works or doesn't exist
- No stubs, no TODOs in code
- Real Azure API integration

### Modular Design (Bricks & Studs) ✅

- `monitor-client.ts` - Self-contained API client
- `health-calculator.ts` - Pure functions, testable
- `HealthCard.tsx` - Reusable component
- Each module has clear public API (`__all__`)

### Proportionality ✅

- Effort matches complexity (7-9 days for MEDIUM feature)
- Test ratio: 60% unit, 30% integration, 10% e2e
- Design depth matches implementation scope

---

## Next Steps

1. **Review** these design documents
2. **Validate** Azure Monitor API access (test credentials)
3. **Implement Phase 1** (Metrics API Foundation)
4. **Iterate** based on real data

---

## Related Documents

- **Main Spec**: `FEATURE_9_VM_HEALTH_DASHBOARD_DESIGN.md`
- **Diagrams**: `FEATURE_9_ARCHITECTURE_DIAGRAM.md`
- **Checklist**: `FEATURE_9_IMPLEMENTATION_CHECKLIST.md`
- **Roadmap**: `../FEATURE_ROADMAP.md` (all 10 features)
- **Top 10**: `../TOP_10_FEATURES.md` (quick reference)

---

## Questions?

**For technical details**: See main design spec
**For visual reference**: See architecture diagrams
**For implementation guidance**: See checklist

---

**Document Version**: 1.0
**Date**: 2026-01-19
**Status**: Complete

Arrr! This be yer comprehensive design for the VM Health Dashboard, ready to chart course toward implementation! 🏴‍☠️

**Pro Tip**: Start with Phase 1 (Metrics API) BEFORE building the dashboard UI. The foundation be critical, matey!
