/**
 * Unit Tests for VM Size Specifications (60% of testing pyramid)
 *
 * Tests VM size lookup and formatting utilities.
 * Covers happy path, edge cases (unknown sizes), and tier detection.
 */

import { describe, it, expect } from 'vitest';
import {
  getVMSizeSpecs,
  formatVMSpecs,
  getVMTier,
  VM_SIZE_SPECS,
  VMSizeSpec,
} from '../vm-size-specs';

describe('VM Size Specs', () => {
  describe('getVMSizeSpecs', () => {
    it('should return specs for known azlin tier sizes', () => {
      const specs = getVMSizeSpecs('Standard_D2s_v3');
      expect(specs).toEqual({
        vcpus: 2,
        ramGb: 8,
        tier: 's',
        description: 'Small',
      });
    });

    it('should return specs for Standard_E8as_v5 (medium tier)', () => {
      const specs = getVMSizeSpecs('Standard_E8as_v5');
      expect(specs).toEqual({
        vcpus: 8,
        ramGb: 64,
        tier: 'm',
        description: 'Medium',
      });
    });

    it('should return specs for Standard_E16as_v5 (large tier)', () => {
      const specs = getVMSizeSpecs('Standard_E16as_v5');
      expect(specs).toEqual({
        vcpus: 16,
        ramGb: 128,
        tier: 'l',
        description: 'Large',
      });
    });

    it('should return specs for Standard_E32as_v5 (xl tier)', () => {
      const specs = getVMSizeSpecs('Standard_E32as_v5');
      expect(specs).toEqual({
        vcpus: 32,
        ramGb: 256,
        tier: 'xl',
        description: 'XL',
      });
    });

    it('should return specs for D-series VMs', () => {
      const specs = getVMSizeSpecs('Standard_D4_v3');
      expect(specs).toEqual({
        vcpus: 4,
        ramGb: 16,
      });
    });

    it('should return specs for E-series memory optimized VMs', () => {
      const specs = getVMSizeSpecs('Standard_E8_v3');
      expect(specs).toEqual({
        vcpus: 8,
        ramGb: 64,
      });
    });

    it('should return specs for B-series burstable VMs', () => {
      const specs = getVMSizeSpecs('Standard_B2s');
      expect(specs).toEqual({
        vcpus: 2,
        ramGb: 4,
      });
    });

    it('should return specs for F-series compute optimized VMs', () => {
      const specs = getVMSizeSpecs('Standard_F4s_v2');
      expect(specs).toEqual({
        vcpus: 4,
        ramGb: 8,
      });
    });

    it('should return undefined for unknown VM size', () => {
      const specs = getVMSizeSpecs('Unknown_VM_Size');
      expect(specs).toBeUndefined();
    });

    it('should be case-sensitive', () => {
      const specs = getVMSizeSpecs('standard_d2s_v3');
      expect(specs).toBeUndefined();
    });

    it('should handle empty string', () => {
      const specs = getVMSizeSpecs('');
      expect(specs).toBeUndefined();
    });
  });

  describe('formatVMSpecs', () => {
    it('should format specs with vCPU and RAM', () => {
      const formatted = formatVMSpecs('Standard_D2s_v3');
      expect(formatted).toBe('2 vCPU, 8GB');
    });

    it('should format large VM specs', () => {
      const formatted = formatVMSpecs('Standard_E16as_v5');
      expect(formatted).toBe('16 vCPU, 128GB');
    });

    it('should format extra large VM specs', () => {
      const formatted = formatVMSpecs('Standard_E32as_v5');
      expect(formatted).toBe('32 vCPU, 256GB');
    });

    it('should format single vCPU burstable VM', () => {
      const formatted = formatVMSpecs('Standard_B1s');
      expect(formatted).toBe('1 vCPU, 1GB');
    });

    it('should return original size name for unknown VM', () => {
      const formatted = formatVMSpecs('Unknown_VM_Size');
      expect(formatted).toBe('Unknown_VM_Size');
    });

    it('should return empty string when given empty string', () => {
      const formatted = formatVMSpecs('');
      expect(formatted).toBe('');
    });

    it('should not include tier in formatted output', () => {
      const formatted = formatVMSpecs('Standard_D2s_v3');
      expect(formatted).not.toContain('tier');
      expect(formatted).not.toContain('Small');
    });
  });

  describe('getVMTier', () => {
    it('should return "s" tier for small VMs', () => {
      const tier = getVMTier('Standard_D2s_v3');
      expect(tier).toBe('s');
    });

    it('should return "m" tier for medium VMs', () => {
      const tier = getVMTier('Standard_E8as_v5');
      expect(tier).toBe('m');
    });

    it('should return "l" tier for large VMs', () => {
      const tier = getVMTier('Standard_E16as_v5');
      expect(tier).toBe('l');
    });

    it('should return "xl" tier for extra large VMs', () => {
      const tier = getVMTier('Standard_E32as_v5');
      expect(tier).toBe('xl');
    });

    it('should return undefined for VMs without tier', () => {
      const tier = getVMTier('Standard_D4_v3');
      expect(tier).toBeUndefined();
    });

    it('should return undefined for unknown VMs', () => {
      const tier = getVMTier('Unknown_VM_Size');
      expect(tier).toBeUndefined();
    });

    it('should return undefined for burstable VMs', () => {
      const tier = getVMTier('Standard_B2s');
      expect(tier).toBeUndefined();
    });

    it('should return undefined for compute optimized VMs', () => {
      const tier = getVMTier('Standard_F4s_v2');
      expect(tier).toBeUndefined();
    });
  });

  describe('VM_SIZE_SPECS data structure', () => {
    it('should have all azlin tier sizes defined', () => {
      expect(VM_SIZE_SPECS['Standard_D2s_v3']).toBeDefined();
      expect(VM_SIZE_SPECS['Standard_E8as_v5']).toBeDefined();
      expect(VM_SIZE_SPECS['Standard_E16as_v5']).toBeDefined();
      expect(VM_SIZE_SPECS['Standard_E32as_v5']).toBeDefined();
    });

    it('should have valid vCPU counts', () => {
      Object.values(VM_SIZE_SPECS).forEach((spec: VMSizeSpec) => {
        expect(spec.vcpus).toBeGreaterThan(0);
        expect(Number.isInteger(spec.vcpus)).toBe(true);
      });
    });

    it('should have valid RAM sizes', () => {
      Object.values(VM_SIZE_SPECS).forEach((spec: VMSizeSpec) => {
        expect(spec.ramGb).toBeGreaterThan(0);
        expect(Number.isInteger(spec.ramGb)).toBe(true);
      });
    });

    it('should have tier defined only for azlin tier sizes', () => {
      const tierSizes = ['Standard_D2s_v3', 'Standard_E8as_v5', 'Standard_E16as_v5', 'Standard_E32as_v5'];

      tierSizes.forEach((size) => {
        expect(VM_SIZE_SPECS[size].tier).toBeDefined();
        expect(VM_SIZE_SPECS[size].description).toBeDefined();
      });
    });

    it('should have memory optimized E-series with higher RAM ratio', () => {
      const eSeriesSpec = VM_SIZE_SPECS['Standard_E2_v3'];
      const dSeriesSpec = VM_SIZE_SPECS['Standard_D2_v3'];

      // E-series should have more RAM per vCPU
      const eRatio = eSeriesSpec.ramGb / eSeriesSpec.vcpus;
      const dRatio = dSeriesSpec.ramGb / dSeriesSpec.vcpus;

      expect(eRatio).toBeGreaterThan(dRatio);
    });

    it('should have compute optimized F-series with lower RAM ratio', () => {
      const fSeriesSpec = VM_SIZE_SPECS['Standard_F2s_v2'];
      const dSeriesSpec = VM_SIZE_SPECS['Standard_D2s_v3'];

      // F-series should have less RAM per vCPU (compute optimized)
      const fRatio = fSeriesSpec.ramGb / fSeriesSpec.vcpus;
      const dRatio = dSeriesSpec.ramGb / dSeriesSpec.vcpus;

      expect(fRatio).toBeLessThan(dRatio);
    });
  });

  describe('edge cases', () => {
    it('should handle null input gracefully', () => {
      const specs = getVMSizeSpecs(null as any);
      expect(specs).toBeUndefined();
    });

    it('should handle undefined input gracefully', () => {
      const specs = getVMSizeSpecs(undefined as any);
      expect(specs).toBeUndefined();
    });

    it('should handle numeric input', () => {
      const formatted = formatVMSpecs(123 as any);
      expect(formatted).toBe(123); // formatVMSpecs returns the value as-is for unknown types
    });

    it('should handle special characters in size name', () => {
      const specs = getVMSizeSpecs('Standard_D2s!@#$%');
      expect(specs).toBeUndefined();
    });
  });
});
