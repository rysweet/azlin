/**
 * Health Calculator - Four Golden Signals VM Health Scoring
 *
 * Implements Google's Four Golden Signals adapted for VM infrastructure:
 * 1. Latency - Response time and disk latency
 * 2. Traffic - Network throughput and disk IOPS
 * 3. Errors - Failed operations and error rates
 * 4. Saturation - Resource utilization (CPU, memory, disk, network)
 *
 * Philosophy:
 * - Worst-signal-wins algorithm (one bottleneck affects entire system)
 * - Simple threshold-based scoring (no premature AI complexity)
 * - Color-coded health status (GREEN, YELLOW, RED, GRAY)
 *
 * @module health-calculator
 */

/**
 * Health status levels with color-coded visual representation
 */
export enum HealthStatus {
  /** All metrics within normal range - green indicator */
  GREEN = 'healthy',
  /** One or more metrics approaching limits - yellow warning */
  YELLOW = 'warning',
  /** One or more metrics exceeded critical limits - red alert */
  RED = 'critical',
  /** Insufficient data or VM stopped - gray unknown */
  GRAY = 'unknown',
}

/**
 * Threshold configuration for a signal
 */
export interface SignalThresholds {
  /** Below this value = GREEN status */
  good: number;
  /** Between good and critical = YELLOW status */
  warning: number;
  /** Above this value = RED status */
  critical: number;
}

/**
 * Individual signal measurement with health status
 */
export interface Signal {
  /** Current numeric value */
  value: number;
  /** Unit of measurement (e.g., '%', 'ms', 'MB/s') */
  unit: string;
  /** Calculated health status based on thresholds */
  status: HealthStatus;
  /** Threshold configuration for this signal */
  threshold: SignalThresholds;
  /** ISO 8601 timestamp of last update */
  lastUpdated: string;
  /** Optional human-readable explanation */
  explanation?: string;
}

/**
 * Google's Four Golden Signals adapted for VMs
 */
export interface FourGoldenSignals {
  /** Latency signal (response time, disk latency) */
  latency: Signal;
  /** Traffic signal (network throughput, disk IOPS) */
  traffic: Signal;
  /** Errors signal (failed operations, error rates) */
  errors: Signal;
  /** Saturation signal (CPU, memory, disk, network utilization) */
  saturation: Signal;
}

/**
 * Complete VM health information
 */
export interface VMHealthInfo {
  /** Azure VM resource ID */
  vmId: string;
  /** VM display name */
  vmName: string;
  /** Overall health status (worst of four signals) */
  overallHealth: HealthStatus;
  /** Four Golden Signals measurements */
  signals: FourGoldenSignals;
  /** ISO 8601 timestamp of last update */
  lastUpdated: string;
}

// ============================================================================
// Threshold Configurations (Based on SRE Best Practices)
// ============================================================================

/**
 * CPU utilization thresholds
 * - Good: <80% (system has headroom)
 * - Warning: 80-95% (approaching capacity)
 * - Critical: >95% (system overloaded)
 */
export const CPU_THRESHOLDS: SignalThresholds = {
  good: 80,
  warning: 80,
  critical: 95,
};

/**
 * Memory utilization thresholds
 * - Good: <80% (sufficient free memory)
 * - Warning: 80-90% (memory pressure)
 * - Critical: >90% (OOM risk)
 */
export const MEMORY_THRESHOLDS: SignalThresholds = {
  good: 80,
  warning: 80,
  critical: 90,
};

/**
 * Disk space utilization thresholds
 * - Good: <85% (plenty of space)
 * - Warning: 85-95% (should monitor)
 * - Critical: >95% (near full)
 */
export const DISK_THRESHOLDS: SignalThresholds = {
  good: 85,
  warning: 85,
  critical: 95,
};

/**
 * Network bandwidth utilization thresholds
 * - Good: <80% (network not saturated)
 * - Warning: 80-95% (high traffic)
 * - Critical: >95% (network bottleneck)
 */
export const NETWORK_THRESHOLDS: SignalThresholds = {
  good: 80,
  warning: 80,
  critical: 95,
};

/**
 * Disk latency thresholds (milliseconds)
 * - Good: <10ms (fast disk I/O)
 * - Warning: 10-50ms (slow disk)
 * - Critical: >50ms (disk bottleneck)
 */
export const DISK_LATENCY_THRESHOLDS: SignalThresholds = {
  good: 10,
  warning: 10,
  critical: 50,
};

// ============================================================================
// Health Calculation Functions
// ============================================================================

/**
 * Calculate health status based on value and thresholds
 *
 * @param value - Current metric value
 * @param thresholds - Threshold configuration
 * @returns Health status (GREEN, YELLOW, RED, or GRAY if value is NaN/undefined)
 *
 * @example
 * ```typescript
 * const status = calculateStatus(85, CPU_THRESHOLDS);
 * // Returns HealthStatus.YELLOW (85% is between 80% and 95%)
 * ```
 */
export function calculateStatus(
  value: number | undefined | null,
  thresholds: SignalThresholds
): HealthStatus {
  // Handle missing or invalid data
  if (value === undefined || value === null || isNaN(value)) {
    return HealthStatus.GRAY;
  }

  // Apply threshold logic
  if (value < thresholds.good) {
    return HealthStatus.GREEN;
  } else if (value < thresholds.critical) {
    return HealthStatus.YELLOW;
  } else {
    return HealthStatus.RED;
  }
}

/**
 * Calculate CPU health from percentage utilization
 *
 * @param cpuPercent - CPU utilization percentage (0-100)
 * @returns Signal with health status
 *
 * @example
 * ```typescript
 * const cpuHealth = calculateCPUHealth(88);
 * // Returns Signal with status YELLOW (88% is above 80% warning threshold)
 * ```
 */
export function calculateCPUHealth(cpuPercent: number | undefined): Signal {
  const status = calculateStatus(cpuPercent, CPU_THRESHOLDS);
  return {
    value: cpuPercent ?? NaN,
    unit: '%',
    status,
    threshold: CPU_THRESHOLDS,
    lastUpdated: new Date().toISOString(),
    explanation:
      status === HealthStatus.RED
        ? 'CPU utilization critical - system overloaded'
        : status === HealthStatus.YELLOW
        ? 'CPU utilization high - approaching capacity'
        : 'CPU utilization normal',
  };
}

/**
 * Calculate memory health from percentage utilization
 *
 * @param memoryPercent - Memory utilization percentage (0-100)
 * @returns Signal with health status
 *
 * @example
 * ```typescript
 * const memHealth = calculateMemoryHealth(75);
 * // Returns Signal with status GREEN (75% is below 80% threshold)
 * ```
 */
export function calculateMemoryHealth(
  memoryPercent: number | undefined
): Signal {
  const status = calculateStatus(memoryPercent, MEMORY_THRESHOLDS);
  return {
    value: memoryPercent ?? NaN,
    unit: '%',
    status,
    threshold: MEMORY_THRESHOLDS,
    lastUpdated: new Date().toISOString(),
    explanation:
      status === HealthStatus.RED
        ? 'Memory utilization critical - OOM risk'
        : status === HealthStatus.YELLOW
        ? 'Memory utilization high - memory pressure'
        : 'Memory utilization normal',
  };
}

/**
 * Calculate disk health from percentage utilization
 *
 * @param diskPercent - Disk space utilization percentage (0-100)
 * @returns Signal with health status
 *
 * @example
 * ```typescript
 * const diskHealth = calculateDiskHealth(92);
 * // Returns Signal with status YELLOW (92% is between 85% and 95%)
 * ```
 */
export function calculateDiskHealth(diskPercent: number | undefined): Signal {
  const status = calculateStatus(diskPercent, DISK_THRESHOLDS);
  return {
    value: diskPercent ?? NaN,
    unit: '%',
    status,
    threshold: DISK_THRESHOLDS,
    lastUpdated: new Date().toISOString(),
    explanation:
      status === HealthStatus.RED
        ? 'Disk space critical - nearly full'
        : status === HealthStatus.YELLOW
        ? 'Disk space warning - should monitor'
        : 'Disk space adequate',
  };
}

/**
 * Calculate network health from percentage utilization
 *
 * @param networkPercent - Network bandwidth utilization percentage (0-100)
 * @returns Signal with health status
 *
 * @example
 * ```typescript
 * const netHealth = calculateNetworkHealth(60);
 * // Returns Signal with status GREEN (60% is below 80% threshold)
 * ```
 */
export function calculateNetworkHealth(
  networkPercent: number | undefined
): Signal {
  const status = calculateStatus(networkPercent, NETWORK_THRESHOLDS);
  return {
    value: networkPercent ?? NaN,
    unit: '%',
    status,
    threshold: NETWORK_THRESHOLDS,
    lastUpdated: new Date().toISOString(),
    explanation:
      status === HealthStatus.RED
        ? 'Network bandwidth critical - network bottleneck'
        : status === HealthStatus.YELLOW
        ? 'Network bandwidth high - high traffic'
        : 'Network bandwidth normal',
  };
}

/**
 * Calculate disk latency health from milliseconds
 *
 * @param latencyMs - Disk latency in milliseconds
 * @returns Signal with health status
 *
 * @example
 * ```typescript
 * const latencyHealth = calculateDiskLatencyHealth(25);
 * // Returns Signal with status YELLOW (25ms is between 10ms and 50ms)
 * ```
 */
export function calculateDiskLatencyHealth(
  latencyMs: number | undefined
): Signal {
  const status = calculateStatus(latencyMs, DISK_LATENCY_THRESHOLDS);
  return {
    value: latencyMs ?? NaN,
    unit: 'ms',
    status,
    threshold: DISK_LATENCY_THRESHOLDS,
    lastUpdated: new Date().toISOString(),
    explanation:
      status === HealthStatus.RED
        ? 'Disk latency critical - disk bottleneck'
        : status === HealthStatus.YELLOW
        ? 'Disk latency high - slow disk I/O'
        : 'Disk latency normal',
  };
}

/**
 * Calculate overall VM health using Worst-Signal-Wins algorithm
 *
 * The overall health is determined by the worst of the four signals.
 * This aligns with SRE principles: one bottleneck affects the entire system.
 *
 * @param signals - Four Golden Signals measurements
 * @returns Overall health status (RED if any signal is RED, YELLOW if any is YELLOW, etc.)
 *
 * @example
 * ```typescript
 * const signals = {
 *   latency: { status: HealthStatus.GREEN, ... },
 *   traffic: { status: HealthStatus.GREEN, ... },
 *   errors: { status: HealthStatus.RED, ... },   // One critical signal
 *   saturation: { status: HealthStatus.GREEN, ... }
 * };
 * const overall = calculateOverallHealth(signals);
 * // Returns HealthStatus.RED (worst signal wins)
 * ```
 */
export function calculateOverallHealth(
  signals: FourGoldenSignals
): HealthStatus {
  const signalStatuses = [
    signals.latency.status,
    signals.traffic.status,
    signals.errors.status,
    signals.saturation.status,
  ];

  // Worst signal determines overall health
  // Priority: RED > GRAY > YELLOW > GREEN
  // GRAY (unknown) is worse than YELLOW (known warning) because missing data prevents proper assessment
  if (signalStatuses.includes(HealthStatus.RED)) {
    return HealthStatus.RED;
  }
  if (signalStatuses.includes(HealthStatus.GRAY)) {
    return HealthStatus.GRAY;
  }
  if (signalStatuses.includes(HealthStatus.YELLOW)) {
    return HealthStatus.YELLOW;
  }
  return HealthStatus.GREEN;
}

/**
 * Get human-readable health status label
 *
 * @param status - Health status enum value
 * @returns Human-readable label
 *
 * @example
 * ```typescript
 * getHealthStatusLabel(HealthStatus.YELLOW); // Returns "Warning"
 * ```
 */
export function getHealthStatusLabel(status: HealthStatus): string {
  switch (status) {
    case HealthStatus.GREEN:
      return 'Healthy';
    case HealthStatus.YELLOW:
      return 'Warning';
    case HealthStatus.RED:
      return 'Critical';
    case HealthStatus.GRAY:
      return 'Unknown';
    default:
      return 'Unknown';
  }
}

/**
 * Get color code for health status (for UI rendering)
 *
 * @param status - Health status enum value
 * @returns Hex color code
 *
 * @example
 * ```typescript
 * getHealthStatusColor(HealthStatus.RED); // Returns "#f44336"
 * ```
 */
export function getHealthStatusColor(status: HealthStatus): string {
  switch (status) {
    case HealthStatus.GREEN:
      return '#4caf50'; // Material Design Green 500
    case HealthStatus.YELLOW:
      return '#ff9800'; // Material Design Orange 500
    case HealthStatus.RED:
      return '#f44336'; // Material Design Red 500
    case HealthStatus.GRAY:
      return '#9e9e9e'; // Material Design Grey 500
    default:
      return '#9e9e9e';
  }
}
