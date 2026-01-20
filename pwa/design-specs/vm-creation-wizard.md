# VM Creation Wizard - Design Specification

## Overview

Multi-step wizard for creating Azure VMs from mobile PWA, following iOS design patterns and progressive disclosure principles.

## Architecture

### Module Structure

```
src/components/VmWizard/
├── VmWizardContainer.tsx       # Main wizard orchestration
├── VmWizardSteps/
│   ├── BasicsStep.tsx          # Step 1: Name, RG, Location
│   ├── SizeStep.tsx            # Step 2: VM size selection
│   ├── ImageStep.tsx           # Step 3: OS image
│   ├── NetworkStep.tsx         # Step 4: Networking
│   ├── AuthStep.tsx            # Step 5: SSH authentication
│   └── ReviewStep.tsx          # Step 6: Review & create
├── hooks/
│   ├── useVmWizardState.ts     # State management
│   ├── useVmCreation.ts        # Azure API integration
│   └── useCostCalculation.ts   # Cost estimation
└── types/
    └── VmWizardTypes.ts        # Shared types
```

### Core Patterns

**Wizard State Management**:
- Single source of truth (reducer pattern)
- Step validation before navigation
- Draft persistence (localStorage)
- Progressive disclosure (show advanced options conditionally)

**Azure Integration**:
- Async operation polling (exponential backoff)
- Dependency chain: VNet → Subnet → NIC → VM
- Error recovery (retry logic, rollback on failure)
- Progress tracking (5 stages: VNet, Subnet, NIC, VM, Ready)

## Wizard Flow

### Step 1: Basics

**Contract**:
```typescript
interface BasicsStepData {
  vmName: string;           // lowercase, alphanumeric, hyphens only
  resourceGroup: string;    // existing or new
  location: string;         // Azure region
}
```

**Validation**:
- VM name: `^[a-z0-9-]+$` (3-64 chars)
- Resource group: Must exist or be valid new name
- Location: From Azure regions API

**Dependencies**: None

### Step 2: Size Selection

**Contract**:
```typescript
interface SizeStepData {
  vmSize: string;           // e.g., "Standard_B2s"
  tier: 'small' | 'medium' | 'large' | 'xlarge';
}

interface VmSizeOption {
  name: string;
  vCPUs: number;
  memoryGiB: number;
  tempStorageGiB: number;
  pricePerHour: number;
  pricePerMonth: number;
  recommended: boolean;
}
```

**Validation**:
- Must select valid size available in chosen location
- Cost preview updated on selection

**Dependencies**: `location` (from Step 1)

### Step 3: OS Image

**Contract**:
```typescript
interface ImageStepData {
  publisher: string;        // e.g., "Canonical"
  offer: string;            // e.g., "0001-com-ubuntu-server-jammy"
  sku: string;              // e.g., "22_04-lts-gen2"
  version: string;          // e.g., "latest"
}
```

**Presets**:
```typescript
const OS_PRESETS = {
  ubuntu2204: { publisher: "Canonical", offer: "0001-com-ubuntu-server-jammy", sku: "22_04-lts-gen2" },
  ubuntu2404: { publisher: "Canonical", offer: "ubuntu-24_04-lts", sku: "server-gen2" },
  debian12: { publisher: "Debian", offer: "debian-12", sku: "12-gen2" },
  rhel9: { publisher: "RedHat", offer: "RHEL", sku: "9-lvm-gen2" },
};
```

**Validation**:
- Must select valid image available in chosen location

**Dependencies**: `location` (from Step 1)

### Step 4: Networking

**Contract**:
```typescript
interface NetworkStepData {
  vnet: string;             // existing or new VNet name
  subnet: string;           // existing or new subnet name
  publicIp: boolean;        // attach public IP?
  nsg: string;              // network security group
}
```

**Defaults**:
```typescript
{
  vnet: "default-vnet",
  subnet: "default-subnet",
  publicIp: true,
  nsg: "default-nsg"
}
```

**Validation**:
- VNet CIDR: `10.0.0.0/16` (if creating new)
- Subnet CIDR: `10.0.1.0/24` (if creating new, must be within VNet)
- NSG rules: SSH (22), HTTP (80), HTTPS (443) if creating new

**Dependencies**: `resourceGroup`, `location` (from Step 1)

### Step 5: Authentication

**Contract**:
```typescript
interface AuthStepData {
  username: string;         // VM admin username
  sshPublicKey: string;     // SSH public key (RSA/Ed25519)
}
```

**Validation**:
- Username: `^[a-z_][a-z0-9_-]*$` (3-32 chars, no root/admin)
- SSH key: Must be valid RSA/Ed25519 public key format

**Key Sources**:
1. Paste from clipboard
2. Upload from Files app (.pub file)
3. Generate new keypair (download private key)

**Dependencies**: None

### Step 6: Review & Create

**Contract**:
```typescript
interface VmCreationRequest {
  basics: BasicsStepData;
  size: SizeStepData;
  image: ImageStepData;
  network: NetworkStepData;
  auth: AuthStepData;
}

interface VmCreationProgress {
  stage: 'vnet' | 'subnet' | 'nic' | 'vm' | 'ready' | 'error';
  progress: number;          // 0-100
  estimatedTimeRemaining: number; // seconds
  message: string;
}
```

**Cost Summary**:
```typescript
interface CostEstimate {
  vmCost: number;           // $/hour
  storageCost: number;      // $/month (OS disk)
  networkCost: number;      // $/month (public IP if enabled)
  totalHourly: number;
  totalMonthly: number;
}
```

**Create Flow**:
1. Validate all steps
2. Show cost confirmation modal
3. Execute Azure API sequence:
   - Create/verify VNet (if new)
   - Create/verify Subnet (if new)
   - Create Network Interface
   - Create VM
4. Poll operation status (5-15 minutes)
5. Show success/error result

**Dependencies**: All previous steps

## API Integration

### Azure API Sequence

```typescript
interface VmCreationService {
  // 1. Network Setup
  createOrGetVNet(rg: string, location: string, vnetName: string): Promise<VNet>;
  createOrGetSubnet(rg: string, vnetName: string, subnetName: string): Promise<Subnet>;

  // 2. NIC Creation
  createNetworkInterface(
    rg: string,
    location: string,
    nicName: string,
    subnetId: string,
    publicIp: boolean
  ): Promise<NetworkInterface>;

  // 3. VM Creation
  createVm(request: VmCreationRequest, nicId: string): Promise<VmCreationOperation>;

  // 4. Polling
  pollOperationStatus(operationUrl: string): Promise<VmCreationProgress>;
}
```

### Error Handling Strategy

**Network Errors**:
- Retry with exponential backoff (3 attempts)
- Clear error messages ("Connection lost, retrying...")
- Allow manual retry

**API Errors**:
- Quota exceeded → Show quota limits, link to increase
- Name conflict → Suggest alternative names
- Authorization → Link to Azure portal for permissions
- Invalid parameters → Highlight specific field

**Timeout Handling**:
- 15-minute timeout for VM creation
- Graceful degradation (can check status later)
- Background operation tracking

### Progress Tracking

```typescript
const CREATION_STAGES = [
  { stage: 'vnet', label: 'Creating virtual network', progress: 10, estimatedSeconds: 30 },
  { stage: 'subnet', label: 'Configuring subnet', progress: 30, estimatedSeconds: 20 },
  { stage: 'nic', label: 'Setting up network interface', progress: 50, estimatedSeconds: 40 },
  { stage: 'vm', label: 'Creating virtual machine', progress: 80, estimatedSeconds: 600 },
  { stage: 'ready', label: 'VM ready', progress: 100, estimatedSeconds: 0 },
];
```

## Cost Calculation Logic

### Pricing Components

```typescript
interface VmPricing {
  compute: number;          // $/hour (varies by size)
  osDisk: number;           // $/month (128GB standard HDD)
  publicIp: number;         // $/month (if enabled)
}

const PRICING = {
  compute: {
    'Standard_B1s': 0.0104,     // 1 vCPU, 1GB RAM
    'Standard_B2s': 0.0416,     // 2 vCPU, 4GB RAM
    'Standard_B4ms': 0.166,     // 4 vCPU, 16GB RAM
    'Standard_D2s_v5': 0.096,   // 2 vCPU, 8GB RAM
  },
  storage: {
    standardHdd: 1.92,          // $/month per 128GB
    standardSsd: 9.60,          // $/month per 128GB
  },
  network: {
    publicIp: 3.65,             // $/month (static)
  }
};
```

### Calculation Function

```typescript
function calculateCost(size: string, publicIp: boolean): CostEstimate {
  const computeHourly = PRICING.compute[size] || 0;
  const storageMonthly = PRICING.storage.standardHdd;
  const networkMonthly = publicIp ? PRICING.network.publicIp : 0;

  return {
    vmCost: computeHourly,
    storageCost: storageMonthly,
    networkCost: networkMonthly,
    totalHourly: computeHourly,
    totalMonthly: (computeHourly * 730) + storageMonthly + networkMonthly,
  };
}
```

## State Management

### Wizard State Reducer

```typescript
interface VmWizardState {
  currentStep: number;
  data: Partial<VmCreationRequest>;
  validation: Record<string, string[]>;  // errors by step
  isDirty: boolean;
  isSubmitting: boolean;
  creationProgress?: VmCreationProgress;
}

type VmWizardAction =
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'UPDATE_STEP'; step: number; data: unknown }
  | { type: 'SET_VALIDATION'; step: number; errors: string[] }
  | { type: 'START_CREATION' }
  | { type: 'UPDATE_PROGRESS'; progress: VmCreationProgress }
  | { type: 'CREATION_COMPLETE'; vmId: string }
  | { type: 'CREATION_ERROR'; error: string }
  | { type: 'RESET' };
```

### Draft Persistence

```typescript
// Save draft to localStorage on every step change
function saveDraft(state: VmWizardState): void {
  localStorage.setItem('vm-wizard-draft', JSON.stringify(state));
}

// Restore draft on wizard mount
function restoreDraft(): VmWizardState | null {
  const draft = localStorage.getItem('vm-wizard-draft');
  return draft ? JSON.parse(draft) : null;
}
```

## UI Components

### VmWizardContainer

**Responsibilities**:
- Manage wizard state (useReducer)
- Handle step navigation
- Persist draft state
- Trigger VM creation

**Contract**:
```typescript
interface VmWizardContainerProps {
  onComplete: (vmId: string) => void;
  onCancel: () => void;
}
```

### Step Components

**Common Interface**:
```typescript
interface WizardStepProps<T> {
  data: T;
  onChange: (data: T) => void;
  onNext: () => void;
  onPrev: () => void;
  errors: string[];
}
```

**iOS Design Patterns**:
- Native-style list groups for selections
- Sheet modals for sub-flows (e.g., VNet creation)
- Inline validation with error messages
- Progress indicator at top (Step X of 6)
- CTA buttons at bottom (Cancel, Back, Next/Create)

## Testing Strategy

### Unit Tests
- Validation logic (VM name, SSH key format)
- Cost calculation accuracy
- State reducer transitions

### Integration Tests
- Wizard flow (all steps)
- Draft persistence/restoration
- API error handling

### E2E Tests
- Complete VM creation flow
- Network failure recovery
- Progress polling

## Implementation Notes

### Key Design Decisions

1. **Progressive Disclosure**: Advanced options (custom images, advanced networking) hidden by default
2. **Sensible Defaults**: Pre-populate common values (default-vnet, ubuntu2204, public IP)
3. **Inline Help**: Contextual tooltips for technical terms (VNet, NSG, SKU)
4. **Cost Transparency**: Real-time cost preview on every selection change
5. **Draft Persistence**: Never lose work on accidental navigation

### Risks & Mitigations

**Risk: Azure API Rate Limits**
- Mitigation: Cache region/size lists, implement exponential backoff

**Risk: Long Creation Time (5-15 min)**
- Mitigation: Allow backgrounding, send notification on completion

**Risk: Network Errors During Creation**
- Mitigation: Idempotent operations, rollback on failure, resume from checkpoint

**Risk: Complex Networking Requirements**
- Mitigation: Start with simple defaults, progressive disclosure for advanced

### Future Enhancements

- VM templates (pre-configured stacks)
- Multiple VM creation (batch)
- Advanced networking (load balancers, NSG rules)
- Custom image upload
- Cost optimization recommendations

## Success Metrics

- Wizard completion rate > 80%
- VM creation success rate > 95%
- Average creation time < 8 minutes
- User-reported errors < 5%

## References

- Azure VM REST API: https://learn.microsoft.com/en-us/rest/api/compute/virtual-machines
- Azure Networking API: https://learn.microsoft.com/en-us/rest/api/virtualnetwork/
- iOS Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines/
