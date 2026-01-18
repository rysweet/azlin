/**
 * VM Size Specifications
 *
 * Maps Azure VM size names to their hardware specs.
 * Used to display vCPU and RAM info in the VM list.
 *
 * Based on azlin CLI's vm_size_tiers.py
 */

export interface VMSizeSpec {
  vcpus: number;
  ramGb: number;
  tier?: string;
  description?: string;
}

/**
 * Known VM size specs
 * Covers common Azure VM sizes used by azlin
 */
export const VM_SIZE_SPECS: Record<string, VMSizeSpec> = {
  // Azlin tier sizes
  'Standard_D2s_v3': { vcpus: 2, ramGb: 8, tier: 's', description: 'Small' },
  'Standard_E8as_v5': { vcpus: 8, ramGb: 64, tier: 'm', description: 'Medium' },
  'Standard_E16as_v5': { vcpus: 16, ramGb: 128, tier: 'l', description: 'Large' },
  'Standard_E32as_v5': { vcpus: 32, ramGb: 256, tier: 'xl', description: 'XL' },

  // Other common D-series (general purpose)
  'Standard_D2_v3': { vcpus: 2, ramGb: 8 },
  'Standard_D4_v3': { vcpus: 4, ramGb: 16 },
  'Standard_D8_v3': { vcpus: 8, ramGb: 32 },
  'Standard_D16_v3': { vcpus: 16, ramGb: 64 },
  'Standard_D4s_v3': { vcpus: 4, ramGb: 16 },
  'Standard_D8s_v3': { vcpus: 8, ramGb: 32 },
  'Standard_D16s_v3': { vcpus: 16, ramGb: 64 },
  'Standard_D32s_v3': { vcpus: 32, ramGb: 128 },

  // D-series v4/v5
  'Standard_D2s_v4': { vcpus: 2, ramGb: 8 },
  'Standard_D4s_v4': { vcpus: 4, ramGb: 16 },
  'Standard_D8s_v4': { vcpus: 8, ramGb: 32 },
  'Standard_D16s_v4': { vcpus: 16, ramGb: 64 },
  'Standard_D2s_v5': { vcpus: 2, ramGb: 8 },
  'Standard_D4s_v5': { vcpus: 4, ramGb: 16 },
  'Standard_D8s_v5': { vcpus: 8, ramGb: 32 },
  'Standard_D16s_v5': { vcpus: 16, ramGb: 64 },

  // E-series (memory optimized)
  'Standard_E2_v3': { vcpus: 2, ramGb: 16 },
  'Standard_E4_v3': { vcpus: 4, ramGb: 32 },
  'Standard_E8_v3': { vcpus: 8, ramGb: 64 },
  'Standard_E16_v3': { vcpus: 16, ramGb: 128 },
  'Standard_E2s_v3': { vcpus: 2, ramGb: 16 },
  'Standard_E4s_v3': { vcpus: 4, ramGb: 32 },
  'Standard_E8s_v3': { vcpus: 8, ramGb: 64 },
  'Standard_E16s_v3': { vcpus: 16, ramGb: 128 },
  'Standard_E2as_v5': { vcpus: 2, ramGb: 16 },
  'Standard_E4as_v5': { vcpus: 4, ramGb: 32 },

  // B-series (burstable)
  'Standard_B1s': { vcpus: 1, ramGb: 1 },
  'Standard_B1ms': { vcpus: 1, ramGb: 2 },
  'Standard_B2s': { vcpus: 2, ramGb: 4 },
  'Standard_B2ms': { vcpus: 2, ramGb: 8 },
  'Standard_B4ms': { vcpus: 4, ramGb: 16 },
  'Standard_B8ms': { vcpus: 8, ramGb: 32 },

  // F-series (compute optimized)
  'Standard_F2s_v2': { vcpus: 2, ramGb: 4 },
  'Standard_F4s_v2': { vcpus: 4, ramGb: 8 },
  'Standard_F8s_v2': { vcpus: 8, ramGb: 16 },
  'Standard_F16s_v2': { vcpus: 16, ramGb: 32 },
};

/**
 * Get specs for a VM size
 * Returns undefined if size is not in the mapping
 */
export function getVMSizeSpecs(size: string): VMSizeSpec | undefined {
  return VM_SIZE_SPECS[size];
}

/**
 * Format VM specs for display
 * Returns "16 vCPU, 128GB" or falls back to just the size name
 */
export function formatVMSpecs(size: string): string {
  const specs = getVMSizeSpecs(size);
  if (specs) {
    return `${specs.vcpus} vCPU, ${specs.ramGb}GB`;
  }
  return size;
}

/**
 * Get tier label if this is a known azlin tier size
 */
export function getVMTier(size: string): string | undefined {
  const specs = getVMSizeSpecs(size);
  return specs?.tier;
}
