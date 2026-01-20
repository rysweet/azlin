/**
 * Unit tests for health-calculator.ts
 *
 * Testing Strategy:
 * - Test threshold boundaries (edge cases)
 * - Test each signal calculation function
 * - Test overall health calculation (worst-signal-wins)
 * - Test handling of undefined/null/NaN values
 * - Test utility functions (labels, colors)
 *
 * Coverage goal: 100% of health calculation logic
 */

import { describe, it, expect } from 'vitest';
import {
  HealthStatus,
  calculateStatus,
  calculateCPUHealth,
  calculateMemoryHealth,
  calculateDiskHealth,
  calculateNetworkHealth,
  calculateDiskLatencyHealth,
  calculateOverallHealth,
  getHealthStatusLabel,
  getHealthStatusColor,
  CPU_THRESHOLDS,
  MEMORY_THRESHOLDS,
  DISK_THRESHOLDS,
  NETWORK_THRESHOLDS,
  DISK_LATENCY_THRESHOLDS,
  type FourGoldenSignals,
} from '../health-calculator';

describe('health-calculator', () => {
  describe('calculateStatus', () => {
    const testThresholds = { good: 80, warning: 80, critical: 95 };

    it('should return GREEN for values below good threshold', () => {
      expect(calculateStatus(0, testThresholds)).toBe(HealthStatus.GREEN);
      expect(calculateStatus(50, testThresholds)).toBe(HealthStatus.GREEN);
      expect(calculateStatus(79.9, testThresholds)).toBe(HealthStatus.GREEN);
    });

    it('should return YELLOW for values between warning and critical', () => {
      expect(calculateStatus(80, testThresholds)).toBe(HealthStatus.YELLOW);
      expect(calculateStatus(85, testThresholds)).toBe(HealthStatus.YELLOW);
      expect(calculateStatus(94.9, testThresholds)).toBe(HealthStatus.YELLOW);
    });

    it('should return RED for values above critical threshold', () => {
      expect(calculateStatus(95, testThresholds)).toBe(HealthStatus.RED);
      expect(calculateStatus(98, testThresholds)).toBe(HealthStatus.RED);
      expect(calculateStatus(100, testThresholds)).toBe(HealthStatus.RED);
    });

    it('should return GRAY for undefined values', () => {
      expect(calculateStatus(undefined, testThresholds)).toBe(HealthStatus.GRAY);
    });

    it('should return GRAY for null values', () => {
      expect(calculateStatus(null, testThresholds)).toBe(HealthStatus.GRAY);
    });

    it('should return GRAY for NaN values', () => {
      expect(calculateStatus(NaN, testThresholds)).toBe(HealthStatus.GRAY);
    });
  });

  describe('calculateCPUHealth', () => {
    it('should return GREEN for low CPU usage', () => {
      const result = calculateCPUHealth(50);
      expect(result.status).toBe(HealthStatus.GREEN);
      expect(result.value).toBe(50);
      expect(result.unit).toBe('%');
      expect(result.threshold).toEqual(CPU_THRESHOLDS);
      expect(result.explanation).toContain('normal');
    });

    it('should return YELLOW for high CPU usage', () => {
      const result = calculateCPUHealth(88);
      expect(result.status).toBe(HealthStatus.YELLOW);
      expect(result.value).toBe(88);
      expect(result.explanation).toContain('high');
    });

    it('should return RED for critical CPU usage', () => {
      const result = calculateCPUHealth(98);
      expect(result.status).toBe(HealthStatus.RED);
      expect(result.value).toBe(98);
      expect(result.explanation).toContain('critical');
    });

    it('should handle undefined CPU value', () => {
      const result = calculateCPUHealth(undefined);
      expect(result.status).toBe(HealthStatus.GRAY);
      expect(isNaN(result.value)).toBe(true);
    });

    it('should test exact threshold boundaries', () => {
      // Boundary tests
      expect(calculateCPUHealth(79.9).status).toBe(HealthStatus.GREEN);
      expect(calculateCPUHealth(80).status).toBe(HealthStatus.YELLOW);
      expect(calculateCPUHealth(94.9).status).toBe(HealthStatus.YELLOW);
      expect(calculateCPUHealth(95).status).toBe(HealthStatus.RED);
    });
  });

  describe('calculateMemoryHealth', () => {
    it('should return GREEN for low memory usage', () => {
      const result = calculateMemoryHealth(60);
      expect(result.status).toBe(HealthStatus.GREEN);
      expect(result.unit).toBe('%');
      expect(result.explanation).toContain('normal');
    });

    it('should return YELLOW for high memory usage', () => {
      const result = calculateMemoryHealth(85);
      expect(result.status).toBe(HealthStatus.YELLOW);
      expect(result.explanation).toContain('pressure');
    });

    it('should return RED for critical memory usage', () => {
      const result = calculateMemoryHealth(92);
      expect(result.status).toBe(HealthStatus.RED);
      expect(result.explanation).toContain('OOM risk');
    });

    it('should test exact threshold boundaries', () => {
      expect(calculateMemoryHealth(79.9).status).toBe(HealthStatus.GREEN);
      expect(calculateMemoryHealth(80).status).toBe(HealthStatus.YELLOW);
      expect(calculateMemoryHealth(89.9).status).toBe(HealthStatus.YELLOW);
      expect(calculateMemoryHealth(90).status).toBe(HealthStatus.RED);
    });
  });

  describe('calculateDiskHealth', () => {
    it('should return GREEN for plenty of disk space', () => {
      const result = calculateDiskHealth(55);
      expect(result.status).toBe(HealthStatus.GREEN);
      expect(result.explanation).toContain('adequate');
    });

    it('should return YELLOW for low disk space', () => {
      const result = calculateDiskHealth(90);
      expect(result.status).toBe(HealthStatus.YELLOW);
      expect(result.explanation).toContain('warning');
    });

    it('should return RED for critical disk space', () => {
      const result = calculateDiskHealth(97);
      expect(result.status).toBe(HealthStatus.RED);
      expect(result.explanation).toContain('nearly full');
    });

    it('should test exact threshold boundaries', () => {
      expect(calculateDiskHealth(84.9).status).toBe(HealthStatus.GREEN);
      expect(calculateDiskHealth(85).status).toBe(HealthStatus.YELLOW);
      expect(calculateDiskHealth(94.9).status).toBe(HealthStatus.YELLOW);
      expect(calculateDiskHealth(95).status).toBe(HealthStatus.RED);
    });
  });

  describe('calculateNetworkHealth', () => {
    it('should return GREEN for low network utilization', () => {
      const result = calculateNetworkHealth(45);
      expect(result.status).toBe(HealthStatus.GREEN);
      expect(result.explanation).toContain('normal');
    });

    it('should return YELLOW for high network utilization', () => {
      const result = calculateNetworkHealth(88);
      expect(result.status).toBe(HealthStatus.YELLOW);
      expect(result.explanation).toContain('high traffic');
    });

    it('should return RED for critical network utilization', () => {
      const result = calculateNetworkHealth(98);
      expect(result.status).toBe(HealthStatus.RED);
      expect(result.explanation).toContain('bottleneck');
    });

    it('should test exact threshold boundaries', () => {
      expect(calculateNetworkHealth(79.9).status).toBe(HealthStatus.GREEN);
      expect(calculateNetworkHealth(80).status).toBe(HealthStatus.YELLOW);
      expect(calculateNetworkHealth(94.9).status).toBe(HealthStatus.YELLOW);
      expect(calculateNetworkHealth(95).status).toBe(HealthStatus.RED);
    });
  });

  describe('calculateDiskLatencyHealth', () => {
    it('should return GREEN for low latency', () => {
      const result = calculateDiskLatencyHealth(5);
      expect(result.status).toBe(HealthStatus.GREEN);
      expect(result.unit).toBe('ms');
      expect(result.explanation).toContain('normal');
    });

    it('should return YELLOW for medium latency', () => {
      const result = calculateDiskLatencyHealth(25);
      expect(result.status).toBe(HealthStatus.YELLOW);
      expect(result.explanation).toContain('slow disk');
    });

    it('should return RED for high latency', () => {
      const result = calculateDiskLatencyHealth(75);
      expect(result.status).toBe(HealthStatus.RED);
      expect(result.explanation).toContain('bottleneck');
    });

    it('should test exact threshold boundaries', () => {
      expect(calculateDiskLatencyHealth(9.9).status).toBe(HealthStatus.GREEN);
      expect(calculateDiskLatencyHealth(10).status).toBe(HealthStatus.YELLOW);
      expect(calculateDiskLatencyHealth(49.9).status).toBe(HealthStatus.YELLOW);
      expect(calculateDiskLatencyHealth(50).status).toBe(HealthStatus.RED);
    });
  });

  describe('calculateOverallHealth - Worst Signal Wins', () => {
    // Helper to create a signal with specific status
    const createSignal = (status: HealthStatus) => ({
      value: 0,
      unit: 'test',
      status,
      threshold: { good: 0, warning: 0, critical: 0 },
      lastUpdated: new Date().toISOString(),
    });

    it('should return GREEN when all signals are GREEN', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GREEN),
        traffic: createSignal(HealthStatus.GREEN),
        errors: createSignal(HealthStatus.GREEN),
        saturation: createSignal(HealthStatus.GREEN),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.GREEN);
    });

    it('should return YELLOW when one signal is YELLOW and rest are GREEN', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GREEN),
        traffic: createSignal(HealthStatus.YELLOW), // One warning
        errors: createSignal(HealthStatus.GREEN),
        saturation: createSignal(HealthStatus.GREEN),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.YELLOW);
    });

    it('should return RED when any signal is RED', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GREEN),
        traffic: createSignal(HealthStatus.GREEN),
        errors: createSignal(HealthStatus.RED), // One critical
        saturation: createSignal(HealthStatus.GREEN),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.RED);
    });

    it('should return RED when multiple signals are RED', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.RED),
        traffic: createSignal(HealthStatus.GREEN),
        errors: createSignal(HealthStatus.RED),
        saturation: createSignal(HealthStatus.YELLOW),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.RED);
    });

    it('should return RED even when most signals are GREEN', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GREEN),
        traffic: createSignal(HealthStatus.GREEN),
        errors: createSignal(HealthStatus.GREEN),
        saturation: createSignal(HealthStatus.RED), // One critical dominates
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.RED);
    });

    it('should return GRAY when any signal is GRAY and none are RED', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GREEN),
        traffic: createSignal(HealthStatus.GRAY), // Unknown data
        errors: createSignal(HealthStatus.GREEN),
        saturation: createSignal(HealthStatus.YELLOW),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.GRAY);
    });

    it('should prioritize RED over GRAY', () => {
      const signals: FourGoldenSignals = {
        latency: createSignal(HealthStatus.GRAY),
        traffic: createSignal(HealthStatus.RED), // RED takes precedence
        errors: createSignal(HealthStatus.GRAY),
        saturation: createSignal(HealthStatus.GREEN),
      };
      expect(calculateOverallHealth(signals)).toBe(HealthStatus.RED);
    });
  });

  describe('getHealthStatusLabel', () => {
    it('should return correct label for GREEN', () => {
      expect(getHealthStatusLabel(HealthStatus.GREEN)).toBe('Healthy');
    });

    it('should return correct label for YELLOW', () => {
      expect(getHealthStatusLabel(HealthStatus.YELLOW)).toBe('Warning');
    });

    it('should return correct label for RED', () => {
      expect(getHealthStatusLabel(HealthStatus.RED)).toBe('Critical');
    });

    it('should return correct label for GRAY', () => {
      expect(getHealthStatusLabel(HealthStatus.GRAY)).toBe('Unknown');
    });
  });

  describe('getHealthStatusColor', () => {
    it('should return green color for GREEN status', () => {
      expect(getHealthStatusColor(HealthStatus.GREEN)).toBe('#4caf50');
    });

    it('should return orange color for YELLOW status', () => {
      expect(getHealthStatusColor(HealthStatus.YELLOW)).toBe('#ff9800');
    });

    it('should return red color for RED status', () => {
      expect(getHealthStatusColor(HealthStatus.RED)).toBe('#f44336');
    });

    it('should return gray color for GRAY status', () => {
      expect(getHealthStatusColor(HealthStatus.GRAY)).toBe('#9e9e9e');
    });
  });

  describe('Threshold Constants', () => {
    it('should have valid CPU thresholds', () => {
      expect(CPU_THRESHOLDS.good).toBe(80);
      expect(CPU_THRESHOLDS.warning).toBe(80);
      expect(CPU_THRESHOLDS.critical).toBe(95);
    });

    it('should have valid Memory thresholds', () => {
      expect(MEMORY_THRESHOLDS.good).toBe(80);
      expect(MEMORY_THRESHOLDS.warning).toBe(80);
      expect(MEMORY_THRESHOLDS.critical).toBe(90);
    });

    it('should have valid Disk thresholds', () => {
      expect(DISK_THRESHOLDS.good).toBe(85);
      expect(DISK_THRESHOLDS.warning).toBe(85);
      expect(DISK_THRESHOLDS.critical).toBe(95);
    });

    it('should have valid Network thresholds', () => {
      expect(NETWORK_THRESHOLDS.good).toBe(80);
      expect(NETWORK_THRESHOLDS.warning).toBe(80);
      expect(NETWORK_THRESHOLDS.critical).toBe(95);
    });

    it('should have valid Disk Latency thresholds', () => {
      expect(DISK_LATENCY_THRESHOLDS.good).toBe(10);
      expect(DISK_LATENCY_THRESHOLDS.warning).toBe(10);
      expect(DISK_LATENCY_THRESHOLDS.critical).toBe(50);
    });
  });

  describe('Edge Cases and Error Handling', () => {
    it('should handle zero values correctly', () => {
      expect(calculateCPUHealth(0).status).toBe(HealthStatus.GREEN);
      expect(calculateMemoryHealth(0).status).toBe(HealthStatus.GREEN);
      expect(calculateDiskHealth(0).status).toBe(HealthStatus.GREEN);
    });

    it('should handle 100% values correctly', () => {
      expect(calculateCPUHealth(100).status).toBe(HealthStatus.RED);
      expect(calculateMemoryHealth(100).status).toBe(HealthStatus.RED);
      expect(calculateDiskHealth(100).status).toBe(HealthStatus.RED);
    });

    it('should handle negative values (treated as valid numbers)', () => {
      // Negative values are technically invalid but should not crash
      expect(calculateCPUHealth(-10).status).toBe(HealthStatus.GREEN);
    });

    it('should handle very large values', () => {
      expect(calculateCPUHealth(10000).status).toBe(HealthStatus.RED);
    });

    it('should include timestamp in signal output', () => {
      const result = calculateCPUHealth(50);
      expect(result.lastUpdated).toBeDefined();
      expect(new Date(result.lastUpdated).getTime()).toBeGreaterThan(0);
    });
  });
});
