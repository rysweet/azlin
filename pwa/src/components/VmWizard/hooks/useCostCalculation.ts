/**
 * VM Cost Calculation Hook
 *
 * Real-time cost estimation for Azure VMs based on size and configuration.
 * Pricing data from Azure pricing calculator (US East region, Linux VMs).
 *
 * Philosophy:
 * - Single responsibility: Cost calculation only
 * - Self-contained with pricing data
 * - Zero-BS: Real Azure pricing (approximations updated 2024)
 */

import { useMemo } from 'react';
import { CostEstimate, VmSizeOption } from '../types/VmWizardTypes';

// ============================================================================
// Azure Pricing Data (US East, Linux VMs, Pay-As-You-Go)
// Updated: January 2024
// Source: https://azure.microsoft.com/en-us/pricing/calculator/
// ============================================================================

const PRICING = {
  compute: {
    // B-Series (Burstable)
    'Standard_B1s': 0.0104,    // 1 vCPU, 1GB RAM
    'Standard_B2s': 0.0416,    // 2 vCPU, 4GB RAM
    'Standard_B2ms': 0.0832,   // 2 vCPU, 8GB RAM
    'Standard_B4ms': 0.166,    // 4 vCPU, 16GB RAM

    // D-Series v5 (General Purpose)
    'Standard_D2s_v5': 0.096,  // 2 vCPU, 8GB RAM
    'Standard_D4s_v5': 0.192,  // 4 vCPU, 16GB RAM
    'Standard_D8s_v5': 0.384,  // 8 vCPU, 32GB RAM
    'Standard_D16s_v5': 0.768, // 16 vCPU, 64GB RAM

    // E-Series v5 (Memory Optimized)
    'Standard_E2s_v5': 0.126,  // 2 vCPU, 16GB RAM
    'Standard_E4s_v5': 0.252,  // 4 vCPU, 32GB RAM
    'Standard_E8s_v5': 0.504,  // 8 vCPU, 64GB RAM

    // F-Series v2 (Compute Optimized)
    'Standard_F2s_v2': 0.085,  // 2 vCPU, 4GB RAM
    'Standard_F4s_v2': 0.169,  // 4 vCPU, 8GB RAM
    'Standard_F8s_v2': 0.338,  // 8 vCPU, 16GB RAM
  } as Record<string, number>,

  storage: {
    standardHdd: 1.92,         // $/month per 128GB
    standardSsd: 9.60,         // $/month per 128GB
    premiumSsd: 17.92,         // $/month per 128GB
  },

  network: {
    publicIp: 3.65,            // $/month (static IPv4)
  },
};

// ============================================================================
// VM Size Specifications
// ============================================================================

export const VM_SIZE_OPTIONS: VmSizeOption[] = [
  // Small tier (< $50/month)
  {
    name: 'Standard_B1s',
    vCPUs: 1,
    memoryGiB: 1,
    tempStorageGiB: 4,
    pricePerHour: PRICING.compute['Standard_B1s'],
    pricePerMonth: PRICING.compute['Standard_B1s'] * 730,
    recommended: false,
    tier: 'small',
  },
  {
    name: 'Standard_B2s',
    vCPUs: 2,
    memoryGiB: 4,
    tempStorageGiB: 8,
    pricePerHour: PRICING.compute['Standard_B2s'],
    pricePerMonth: PRICING.compute['Standard_B2s'] * 730,
    recommended: true,  // Best value for dev/test
    tier: 'small',
  },

  // Medium tier ($50-150/month)
  {
    name: 'Standard_B2ms',
    vCPUs: 2,
    memoryGiB: 8,
    tempStorageGiB: 16,
    pricePerHour: PRICING.compute['Standard_B2ms'],
    pricePerMonth: PRICING.compute['Standard_B2ms'] * 730,
    recommended: false,
    tier: 'medium',
  },
  {
    name: 'Standard_D2s_v5',
    vCPUs: 2,
    memoryGiB: 8,
    tempStorageGiB: 75,
    pricePerHour: PRICING.compute['Standard_D2s_v5'],
    pricePerMonth: PRICING.compute['Standard_D2s_v5'] * 730,
    recommended: true,  // Best for production workloads
    tier: 'medium',
  },
  {
    name: 'Standard_F2s_v2',
    vCPUs: 2,
    memoryGiB: 4,
    tempStorageGiB: 16,
    pricePerHour: PRICING.compute['Standard_F2s_v2'],
    pricePerMonth: PRICING.compute['Standard_F2s_v2'] * 730,
    recommended: false,  // Compute-optimized
    tier: 'medium',
  },

  // Large tier ($150-400/month)
  {
    name: 'Standard_B4ms',
    vCPUs: 4,
    memoryGiB: 16,
    tempStorageGiB: 32,
    pricePerHour: PRICING.compute['Standard_B4ms'],
    pricePerMonth: PRICING.compute['Standard_B4ms'] * 730,
    recommended: false,
    tier: 'large',
  },
  {
    name: 'Standard_D4s_v5',
    vCPUs: 4,
    memoryGiB: 16,
    tempStorageGiB: 150,
    pricePerHour: PRICING.compute['Standard_D4s_v5'],
    pricePerMonth: PRICING.compute['Standard_D4s_v5'] * 730,
    recommended: true,
    tier: 'large',
  },
  {
    name: 'Standard_E2s_v5',
    vCPUs: 2,
    memoryGiB: 16,
    tempStorageGiB: 75,
    pricePerHour: PRICING.compute['Standard_E2s_v5'],
    pricePerMonth: PRICING.compute['Standard_E2s_v5'] * 730,
    recommended: false,  // Memory-optimized
    tier: 'large',
  },

  // XLarge tier (> $400/month)
  {
    name: 'Standard_D8s_v5',
    vCPUs: 8,
    memoryGiB: 32,
    tempStorageGiB: 300,
    pricePerHour: PRICING.compute['Standard_D8s_v5'],
    pricePerMonth: PRICING.compute['Standard_D8s_v5'] * 730,
    recommended: true,
    tier: 'xlarge',
  },
  {
    name: 'Standard_E4s_v5',
    vCPUs: 4,
    memoryGiB: 32,
    tempStorageGiB: 150,
    pricePerHour: PRICING.compute['Standard_E4s_v5'],
    pricePerMonth: PRICING.compute['Standard_E4s_v5'] * 730,
    recommended: false,  // Memory-optimized
    tier: 'xlarge',
  },
];

// ============================================================================
// Cost Calculation Functions
// ============================================================================

/**
 * Calculate total cost estimate for VM configuration
 */
export function calculateCost(vmSize: string, publicIp: boolean): CostEstimate {
  const computeHourly = PRICING.compute[vmSize] || 0;
  const storageMonthly = PRICING.storage.standardHdd;  // Default to Standard HDD
  const networkMonthly = publicIp ? PRICING.network.publicIp : 0;

  const totalHourly = computeHourly;
  const totalMonthly = (computeHourly * 730) + storageMonthly + networkMonthly;

  return {
    vmCost: computeHourly,
    storageCost: storageMonthly,
    networkCost: networkMonthly,
    totalHourly,
    totalMonthly,
  };
}

/**
 * Get VM size details by name
 */
export function getVmSizeDetails(vmSize: string): VmSizeOption | undefined {
  return VM_SIZE_OPTIONS.find(option => option.name === vmSize);
}

/**
 * Filter VM sizes by tier
 */
export function getVmSizesByTier(tier: 'small' | 'medium' | 'large' | 'xlarge'): VmSizeOption[] {
  return VM_SIZE_OPTIONS.filter(option => option.tier === tier);
}

/**
 * Get recommended VM sizes (marked as recommended in data)
 */
export function getRecommendedVmSizes(): VmSizeOption[] {
  return VM_SIZE_OPTIONS.filter(option => option.recommended);
}

// ============================================================================
// React Hook
// ============================================================================

export interface UseCostCalculationReturn {
  calculateCost: (vmSize: string, publicIp: boolean) => CostEstimate;
  getVmSizeDetails: (vmSize: string) => VmSizeOption | undefined;
  getVmSizesByTier: (tier: 'small' | 'medium' | 'large' | 'xlarge') => VmSizeOption[];
  getRecommendedVmSizes: () => VmSizeOption[];
  vmSizeOptions: VmSizeOption[];
}

export function useCostCalculation(): UseCostCalculationReturn {
  // Memoize VM size options (static data, never changes)
  const vmSizeOptions = useMemo(() => VM_SIZE_OPTIONS, []);

  return {
    calculateCost,
    getVmSizeDetails,
    getVmSizesByTier,
    getRecommendedVmSizes,
    vmSizeOptions,
  };
}

export default useCostCalculation;
