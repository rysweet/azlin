# Azure Files NFS Feature Requirements

**Epic**: Phase 1.1 - Core Storage Management  
**Date**: October 18, 2025  
**Status**: Requirements Definition

---

## User Requirements (EXPLICIT - Cannot be optimized away)

### Primary Requirement
Enable multiple azlin VMs to share a home directory via Azure Files NFS, allowing distributed development workflows.

### Explicit User Stories

1. **As a developer**, I want to provision shared storage once and reuse it across multiple VMs, so I don't have to manually sync files between VMs.

2. **As a developer**, I want to create a VM with shared home directory using a single command, so I can quickly spin up development environments.

3. **As a developer**, I want to attach existing VMs to shared storage, so I can migrate my workflow without recreating VMs.

4. **As a developer**, I want to see storage status and metrics, so I can monitor usage and costs.

5. **As a developer**, I want to detach VMs from shared storage, so I can switch between shared and local storage modes.

---

## Success Criteria

### Must Have (P0)
- [ ] Create Azure Files NFS storage account with single command
- [ ] Provision new VM with shared home directory mounted at `/home/azureuser`
- [ ] Attach existing VM to shared storage
- [ ] Detach VM from shared storage (revert to local)
- [ ] List all available storage accounts
- [ ] Show storage status (size, used space, connected VMs)
- [ ] Delete storage account with confirmation
- [ ] All operations work with VNet security (no public access)
- [ ] Storage costs included in cost tracking

### Should Have (P1)
- [ ] Automatic VNet creation if none exists
- [ ] Storage tier selection (Premium/Standard)
- [ ] Custom storage size specification
- [ ] Idempotent operations (safe to run multiple times)
- [ ] Progress indicators during long operations
- [ ] Error handling with clear messages

### Nice to Have (P2)
- [ ] Storage usage graphs
- [ ] Auto-cleanup of unused storage
- [ ] Storage templates (pre-configured layouts)
- [ ] Cross-region replication

---

## CLI Interface (Explicit Requirements)

### Commands Structure
```bash
# Storage management commands
azlin storage create <name> [OPTIONS]
azlin storage list
azlin storage status <name>
azlin storage attach <name> --vm <vm-name>
azlin storage detach --vm <vm-name>
azlin storage delete <name>

# VM provisioning with storage
azlin new --shared-home <storage-name> [OPTIONS]
```

### Command Details

#### `azlin storage create <name>`
**Purpose**: Create Azure Files NFS storage account

**Options**:
- `--tier {Premium|Standard}` - Storage tier (default: Premium)
- `--size <SIZE>` - Storage size, e.g., 100GB, 1TB (default: 100GB)
- `--region <REGION>` - Azure region (default: same as resource group)
- `--resource-group <RG>` - Resource group (default: from config)

**Example**:
```bash
azlin storage create shared-dev --tier Premium --size 1TB
```

#### `azlin storage list`
**Purpose**: List all storage accounts in resource group

**Output**:
```
Storage Accounts in 'azlin-rg-1234':
NAME          TIER      SIZE    USED     REGION    VMS
shared-dev    Premium   1TB     45GB     westus2   3
ml-data       Standard  5TB     2.1TB    westus2   1
```

#### `azlin storage status <name>`
**Purpose**: Show detailed storage status

**Output**:
```
Storage: shared-dev
Tier: Premium
Size: 1TB (45GB used, 4% utilization)
Region: westus2
Created: 2025-10-15
Cost: $153.60/month

Connected VMs:
  - azlin-vm-001 (worker-1) - mounted at /home/azureuser
  - azlin-vm-002 (worker-2) - mounted at /home/azureuser
  - azlin-vm-003 (worker-3) - mounted at /home/azureuser

NFS Endpoint: shared-dev.file.core.windows.net:/shared-dev
```

#### `azlin storage attach <name> --vm <vm-name>`
**Purpose**: Attach existing VM to shared storage

**Example**:
```bash
azlin storage attach shared-dev --vm worker-4
```

**Actions**:
1. Verify storage exists
2. Backup existing home directory to `/home/azureuser.backup`
3. Mount NFS share to `/home/azureuser`
4. Update `/etc/fstab` for persistence
5. Copy backed-up files to shared storage (if empty)

#### `azlin storage detach --vm <vm-name>`
**Purpose**: Detach VM from shared storage

**Example**:
```bash
azlin storage detach --vm worker-4
```

**Actions**:
1. Copy current shared home to `/home/azureuser.local`
2. Unmount NFS share
3. Move local copy back to `/home/azureuser`
4. Remove from `/etc/fstab`

#### `azlin storage delete <name>`
**Purpose**: Delete storage account

**Example**:
```bash
azlin storage delete shared-dev
```

**Safety**:
- Requires confirmation
- Shows connected VMs (must detach first)
- Warns about data loss

#### `azlin new --shared-home <storage-name>`
**Purpose**: Provision VM with shared home directory

**Example**:
```bash
azlin new --shared-home shared-dev --name worker-5
```

**Actions**:
1. Verify storage exists
2. Provision VM with standard flow
3. Add NFS mount to cloud-init
4. Mount storage at `/home/azureuser` during provisioning

---

## Technical Requirements

### Azure Resources
1. **Storage Account**
   - Type: StorageV2
   - Kind: FileStorage (for NFS support)
   - Performance: Premium (or Standard)
   - Protocol: NFS v4.1
   - Network: Private endpoint + VNet integration

2. **Virtual Network**
   - Create if not exists
   - Subnet for VMs
   - Service endpoint for Azure Storage

3. **File Share**
   - Protocol: NFS
   - Quota: User-specified
   - Access: VNet-only (no public access)

### Security Requirements (EXPLICIT)
- [ ] No public access to storage (VNet-only)
- [ ] Consistent UID/GID across VMs (azureuser = 1000)
- [ ] Private endpoint for storage access
- [ ] Network security group rules
- [ ] Storage account firewall rules
- [ ] Encrypted at rest (Azure default)
- [ ] Encrypted in transit (NFS 4.1 default)

### Performance Requirements
- [ ] NFS mount succeeds within 30 seconds
- [ ] Read/write performance meets 90% of local disk
- [ ] Support 10+ concurrent VM connections
- [ ] Storage operations complete within 5 minutes

### Reliability Requirements
- [ ] Auto-reconnect on network interruption
- [ ] Graceful handling of storage unavailability
- [ ] No data loss on VM reboot
- [ ] Atomic mount/unmount operations

---

## Implementation Constraints

### Must Use
- Azure CLI (`az`) for resource creation
- Standard NFS mount commands
- Existing azlin architecture (brick pattern)
- Existing error handling patterns
- Existing configuration management

### Must NOT
- Don't create custom NFS servers
- Don't use unsupported protocols
- Don't bypass VNet security
- Don't hardcode credentials
- Don't break existing VM provisioning

---

## Testing Requirements (EXPLICIT)

### Unit Tests
- [ ] Storage account creation
- [ ] Storage account validation
- [ ] Mount command generation
- [ ] Configuration persistence
- [ ] Error handling for all operations

### Integration Tests
- [ ] Create storage via Azure CLI
- [ ] Provision VM with shared storage
- [ ] Attach existing VM to storage
- [ ] Detach VM from storage
- [ ] Delete storage account
- [ ] Multiple VMs using same storage

### Manual Testing (Step 8)
- [ ] Create storage account
- [ ] Provision 2 VMs with shared home
- [ ] Verify files visible on both VMs
- [ ] Write file on VM1, read on VM2
- [ ] Attach 3rd VM to existing storage
- [ ] Detach VM and verify local home
- [ ] Delete storage with proper cleanup

---

## Acceptance Criteria

### Definition of Done
1. All commands implemented and working
2. All unit tests passing
3. Integration tests passing
4. Manual testing completed and documented
5. Security requirements verified
6. Performance requirements met
7. Documentation updated (README.md)
8. Example workflows added
9. Cost tracking integrated
10. No regressions in existing functionality

### Demo Scenario
```bash
# Create shared storage
azlin storage create dev-shared --tier Premium --size 500GB

# Provision 3 VMs with shared home
azlin new --shared-home dev-shared --name worker-1
azlin new --shared-home dev-shared --name worker-2
azlin new --shared-home dev-shared --name worker-3

# On worker-1: Create a file
ssh worker-1 "echo 'Hello from worker-1' > ~/shared-test.txt"

# On worker-2: Verify file exists
ssh worker-2 "cat ~/shared-test.txt"  # Should output: Hello from worker-1

# On worker-3: Append to file
ssh worker-3 "echo 'Hello from worker-3' >> ~/shared-test.txt"

# On worker-1: Verify append
ssh worker-1 "cat ~/shared-test.txt"  # Should show both messages

# Check storage status
azlin storage status dev-shared  # Should show 3 connected VMs

# Cleanup
azlin storage delete dev-shared  # After detaching all VMs
```

---

## Non-Requirements (Out of Scope)

### Explicitly NOT Required
- ❌ Azure NetApp Files support (too expensive)
- ❌ SMB/CIFS protocol support (Linux NFS only)
- ❌ Multi-region storage replication (Phase 4 feature)
- ❌ Storage snapshots (Phase 4 feature)
- ❌ Quota management per VM
- ❌ Access control lists (ACLs)
- ❌ Storage migration between regions
- ❌ Custom mount points (always `/home/azureuser`)

---

## Dependencies

### External
- Azure CLI (`az storage`) - already required
- NFS client tools (`nfs-common`) - add to cloud-init
- Existing VNet infrastructure - create if missing

### Internal
- `config_manager.py` - Store storage configurations
- `vm_provisioning.py` - Add NFS mount to cloud-init
- `cost_tracker.py` - Include storage costs
- `azure_auth.py` - Azure authentication

### New Modules Required
- `storage_manager.py` - Core storage operations
- `nfs_mount_manager.py` - NFS mount/unmount operations

---

## Risk Assessment

### High Risk
1. **NFS performance** - May not meet expectations
   - Mitigation: Test early, offer hybrid mode
   
2. **VNet complexity** - Networking issues
   - Mitigation: Auto-create VNet, clear error messages

### Medium Risk
1. **Cost overrun** - Storage costs add up
   - Mitigation: Clear cost estimates, warnings
   
2. **Data loss** - Accidental deletion
   - Mitigation: Confirmation prompts, backup warnings

### Low Risk
1. **Azure API changes** - Breaking changes
   - Mitigation: Use stable API versions
   
2. **Concurrent access issues** - File locking
   - Mitigation: Document limitations, best practices

---

## Timeline Estimate

### Phase 1.1 (This Epic)
- Design & Architecture: 2 days
- Implementation: 8 days
- Testing: 3 days
- Documentation: 2 days
- **Total**: 15 days (3 weeks)

### Breakdown
- Day 1-2: Design and TDD (write failing tests)
- Day 3-5: `storage_manager.py` implementation
- Day 6-7: `nfs_mount_manager.py` implementation
- Day 8-10: CLI commands integration
- Day 11-12: Integration testing
- Day 13: Manual testing and bug fixes
- Day 14-15: Documentation and cleanup

---

## Questions to Resolve

### Before Implementation
- [ ] Which Azure storage account tier should be default?
- [ ] What is the maximum number of concurrent VMs we should support?
- [ ] Should we auto-create VNet or require manual setup?
- [ ] How should we handle storage account naming conflicts?
- [ ] Should storage be regional or tied to resource group?

### During Implementation
- [ ] How to handle partial failures (VM created but mount failed)?
- [ ] Should we support multiple storage accounts per VM?
- [ ] How to handle storage quotas and limits?
- [ ] Should we cache storage metadata locally?

---

*Requirements documented on October 18, 2025*
