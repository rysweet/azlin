/**
 * VM Wizard Types
 *
 * TypeScript interfaces for the VM creation wizard.
 * Based on Azure VM creation requirements and design specification.
 *
 * Philosophy:
 * - Single source of truth for wizard data structures
 * - Clear contracts between wizard steps
 * - Self-contained type definitions
 */

// ============================================================================
// Step Data Interfaces
// ============================================================================

export interface BasicsStepData {
  vmName: string;           // lowercase, alphanumeric, hyphens only (3-64 chars)
  resourceGroup: string;    // existing or new resource group
  location: string;         // Azure region (e.g., "eastus")
}

export interface SizeStepData {
  vmSize: string;           // e.g., "Standard_B2s"
  tier: 'small' | 'medium' | 'large' | 'xlarge';
}

export interface VmSizeOption {
  name: string;             // e.g., "Standard_B2s"
  vCPUs: number;
  memoryGiB: number;
  tempStorageGiB: number;
  pricePerHour: number;
  pricePerMonth: number;
  recommended: boolean;
  tier: 'small' | 'medium' | 'large' | 'xlarge';
}

export interface ImageStepData {
  publisher: string;        // e.g., "Canonical"
  offer: string;            // e.g., "0001-com-ubuntu-server-jammy"
  sku: string;              // e.g., "22_04-lts-gen2"
  version: string;          // e.g., "latest"
}

export interface NetworkStepData {
  vnet: string;             // existing or new VNet name
  subnet: string;           // existing or new subnet name
  publicIp: boolean;        // attach public IP?
  nsg: string;              // network security group name
}

export interface AuthStepData {
  username: string;         // VM admin username (3-32 chars)
  sshPublicKey: string;     // SSH public key (RSA/Ed25519)
}

// ============================================================================
// Complete VM Creation Request
// ============================================================================

export interface VmCreationRequest {
  basics: BasicsStepData;
  size: SizeStepData;
  image: ImageStepData;
  network: NetworkStepData;
  auth: AuthStepData;
}

// ============================================================================
// Progress and Status
// ============================================================================

export type VmCreationStage = 'vnet' | 'subnet' | 'nic' | 'vm' | 'ready' | 'error';

export interface VmCreationProgress {
  stage: VmCreationStage;
  progress: number;          // 0-100
  estimatedTimeRemaining: number; // seconds
  message: string;
}

export interface StageDefinition {
  stage: VmCreationStage;
  label: string;
  progress: number;
  estimatedSeconds: number;
}

// ============================================================================
// Cost Estimation
// ============================================================================

export interface CostEstimate {
  vmCost: number;           // $/hour
  storageCost: number;      // $/month (OS disk)
  networkCost: number;      // $/month (public IP if enabled)
  totalHourly: number;
  totalMonthly: number;
}

// ============================================================================
// Wizard State Management
// ============================================================================

export interface VmWizardState {
  currentStep: number;      // 0-5 (6 steps total)
  data: Partial<VmCreationRequest>;
  validation: Record<string, string[]>;  // errors by step
  isDirty: boolean;
  isSubmitting: boolean;
  creationProgress?: VmCreationProgress;
  vmId?: string;            // Set after successful creation
  error?: string;           // Error message if creation failed
}

export type VmWizardAction =
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'GO_TO_STEP'; step: number }
  | { type: 'UPDATE_STEP'; step: number; data: unknown }
  | { type: 'SET_VALIDATION'; step: number; errors: string[] }
  | { type: 'START_CREATION' }
  | { type: 'UPDATE_PROGRESS'; progress: VmCreationProgress }
  | { type: 'CREATION_COMPLETE'; vmId: string }
  | { type: 'CREATION_ERROR'; error: string }
  | { type: 'RESET' }
  | { type: 'RESTORE_DRAFT'; state: VmWizardState };

// ============================================================================
// Wizard Step Component Props
// ============================================================================

export interface WizardStepProps<T> {
  data: T;
  onChange: (data: T) => void;
  onNext: () => void;
  onPrev: () => void;
  errors: string[];
  isFirst?: boolean;
  isLast?: boolean;
}

// ============================================================================
// Azure Resource Interfaces
// ============================================================================

export interface AzureVNet {
  id: string;
  name: string;
  addressPrefix: string;    // e.g., "10.0.0.0/16"
  location: string;
}

export interface AzureSubnet {
  id: string;
  name: string;
  addressPrefix: string;    // e.g., "10.0.1.0/24"
  vnetName: string;
}

export interface AzureNetworkInterface {
  id: string;
  name: string;
  privateIpAddress: string;
  publicIpAddress?: string;
}

export interface AzureLocation {
  name: string;             // e.g., "eastus"
  displayName: string;      // e.g., "East US"
  regionalDisplayName: string;
}

// ============================================================================
// OS Presets
// ============================================================================

export interface OsPreset {
  id: string;
  name: string;
  publisher: string;
  offer: string;
  sku: string;
  version: string;
  description: string;
}

// ============================================================================
// Validation Errors
// ============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

// ============================================================================
// Export all types
// ============================================================================

export type {
  // Re-export for convenience
};
