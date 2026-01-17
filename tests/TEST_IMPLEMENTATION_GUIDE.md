# Test-Driven Implementation Guide: Separate /home Disk Feature

**Status**: ✅ Comprehensive TDD test suite created (68 tests, ALL FAILING as expected)

**Test Execution Confirmation**:
```
FAILED tests/unit/test_vm_provisioning_home_disk.py::TestVMConfigDefaults::test_home_disk_enabled_default_is_true
AttributeError: 'VMConfig' object has no attribute 'home_disk_enabled'
```

This is **EXACTLY CORRECT** for TDD - tests fail first, then we implement to make them pass.

---

## Implementation Roadmap

Follow these steps in order to make tests pass incrementally:

### Phase 1: VMConfig Updates (6 tests)

**Tests to pass**: `TestVMConfigDefaults` (6 tests)

**Implementation**:
```python
@dataclass
class VMConfig:
    """VM configuration parameters."""

    name: str
    resource_group: str
    location: str = "westus2"
    size: str = "Standard_E16as_v5"
    image: str = "Ubuntu2204"
    ssh_public_key: str | None = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True
    session_name: str | None = None
    public_ip_enabled: bool = True

    # NEW FIELDS FOR HOME DISK
    home_disk_enabled: bool = True
    home_disk_size_gb: int = 100
    home_disk_sku: str = "Standard_LRS"
```

**Location**: `src/azlin/vm_provisioning.py` (line 40-54)

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestVMConfigDefaults -v
# Expected: 6 tests PASS
```

---

### Phase 2: _create_home_disk() Implementation (5 tests)

**Tests to pass**: `TestCreateHomeDisk` (5 tests)

**Implementation**:
```python
def _create_home_disk(
    self,
    vm_name: str,
    resource_group: str,
    location: str,
    size_gb: int,
    sku: str
) -> str:
    """Create managed disk for /home directory.

    Args:
        vm_name: VM name (disk will be named {vm_name}-home)
        resource_group: Resource group name
        location: Azure region
        size_gb: Disk size in GB
        sku: Disk SKU (Standard_LRS, Premium_LRS, etc.)

    Returns:
        Disk resource ID

    Raises:
        ProvisioningError: If disk creation fails
    """
    disk_name = f"{vm_name}-home"

    cmd = [
        "az", "disk", "create",
        "--name", disk_name,
        "--resource-group", resource_group,
        "--location", location,
        "--size-gb", str(size_gb),
        "--sku", sku,
        "--output", "json"
    ]

    try:
        executor = AzureCLIExecutor(show_progress=True, timeout=120)
        result = executor.execute(cmd)

        if not result["success"]:
            raise subprocess.CalledProcessError(
                result["returncode"], cmd, result["stdout"], result["stderr"]
            )

        disk_data = json.loads(result["stdout"])
        disk_id = disk_data["id"]

        logger.info(f"Home disk created: {disk_name} ({disk_id})")
        return disk_id

    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to create home disk '{disk_name}': {e.stderr}"
        logger.error(error_msg)
        raise ProvisioningError(error_msg) from e
    except json.JSONDecodeError as e:
        raise ProvisioningError(f"Failed to parse disk creation response") from e
```

**Location**: `src/azlin/vm_provisioning.py` (add as new method in VMProvisioner class)

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestCreateHomeDisk -v
# Expected: 5 tests PASS
```

---

### Phase 3: _attach_home_disk() Implementation (3 tests)

**Tests to pass**: `TestAttachHomeDisk` (3 tests)

**Implementation**:
```python
def _attach_home_disk(
    self,
    vm_name: str,
    resource_group: str,
    disk_id: str
) -> str:
    """Attach managed disk to VM.

    Args:
        vm_name: VM name
        resource_group: Resource group name
        disk_id: Disk resource ID

    Returns:
        LUN number as string

    Raises:
        ProvisioningError: If disk attachment fails
    """
    cmd = [
        "az", "vm", "disk", "attach",
        "--vm-name", vm_name,
        "--resource-group", resource_group,
        "--disk", disk_id,
        "--output", "json"
    ]

    try:
        executor = AzureCLIExecutor(show_progress=True, timeout=120)
        result = executor.execute(cmd)

        if not result["success"]:
            raise subprocess.CalledProcessError(
                result["returncode"], cmd, result["stdout"], result["stderr"]
            )

        attachment_data = json.loads(result["stdout"])
        lun = str(attachment_data["lun"])

        logger.info(f"Home disk attached to {vm_name} at LUN {lun}")
        return lun

    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to attach home disk to '{vm_name}': {e.stderr}"
        logger.error(error_msg)
        raise ProvisioningError(error_msg) from e
    except json.JSONDecodeError as e:
        raise ProvisioningError(f"Failed to parse disk attachment response") from e
```

**Location**: `src/azlin/vm_provisioning.py` (add as new method in VMProvisioner class)

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestAttachHomeDisk -v
# Expected: 3 tests PASS
```

---

### Phase 4: _generate_cloud_init() Updates (10 tests)

**Tests to pass**: `TestGenerateCloudInitWithHomeDisk` (10 tests)

**Implementation**:
1. Update method signature:
```python
def _generate_cloud_init(
    self,
    ssh_public_key: str | None = None,
    has_home_disk: bool = False  # NEW PARAMETER
) -> str:
```

2. Add disk configuration sections when `has_home_disk=True`:
```python
disk_sections = ""
if has_home_disk:
    disk_sections = """
disk_setup:
  /dev/disk/azure/scsi1/lun0:
    table_type: gpt
    layout: true
    overwrite: false

fs_setup:
  - label: home
    filesystem: ext4
    device: /dev/disk/azure/scsi1/lun0-part1
    partition: auto

mounts:
  - ["/dev/disk/azure/scsi1/lun0-part1", "/home", "ext4", "defaults,nofail", "0", "2"]

"""

return f"""#cloud-config
{ssh_keys_section}{disk_sections}package_update: true
package_upgrade: true
...
```

**Location**: `src/azlin/vm_provisioning.py` (modify existing `_generate_cloud_init` method, line 711)

**Key Points**:
- Use Azure stable device paths: `/dev/disk/azure/scsi1/lun0`
- Include `nofail` mount option for graceful boot if disk missing
- Use `ext4` filesystem
- Set `overwrite: false` to protect existing data
- Use `partition: auto` for automatic partitioning

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestGenerateCloudInitWithHomeDisk -v
# Expected: 10 tests PASS
```

---

### Phase 5: provision_vm() Integration (4 tests)

**Tests to pass**: `TestProvisionVMWithHomeDisk` (4 tests)

**Implementation**:

Modify `_try_provision_vm()` method to integrate home disk operations:

```python
def _try_provision_vm(
    self, config: VMConfig, progress_callback: Callable[[str], None] | None = None
) -> VMDetails:
    """Attempt to provision VM (internal method)."""

    def report_progress(msg: str):
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    # Create resource group
    report_progress(f"Creating resource group: {config.resource_group}")
    self.create_resource_group(config.resource_group, config.location)

    # NEW: Create home disk BEFORE VM provisioning
    disk_id = None
    if config.home_disk_enabled:
        try:
            report_progress(f"Creating home disk ({config.home_disk_size_gb}GB)...")
            disk_id = self._create_home_disk(
                vm_name=config.name,
                resource_group=config.resource_group,
                location=config.location,
                size_gb=config.home_disk_size_gb,
                sku=config.home_disk_sku
            )
            report_progress("Home disk created successfully")
        except ProvisioningError as e:
            # Disk creation failure is terminal - don't proceed
            logger.error(f"Home disk creation failed: {e}")
            raise

    # Generate cloud-init with home disk support
    cloud_init = self._generate_cloud_init(
        config.ssh_public_key,
        has_home_disk=config.home_disk_enabled  # MODIFIED
    )

    # Build VM create command (existing code)...
    # ... existing VM creation code ...

    # Extract VM details (existing code)...

    # NEW: Attach home disk AFTER VM creation
    if config.home_disk_enabled and disk_id:
        try:
            report_progress("Attaching home disk to VM...")
            lun = self._attach_home_disk(
                vm_name=config.name,
                resource_group=config.resource_group,
                disk_id=disk_id
            )
            report_progress(f"Home disk attached at LUN {lun}")
        except ProvisioningError as e:
            # Attachment failure is non-terminal (graceful degradation)
            logger.warning(f"Failed to attach home disk (VM still usable): {e}")
            report_progress(f"Warning: Home disk attachment failed, but VM is running")

    # Set azlin management tags (existing code)...

    return vm_details
```

**Location**: `src/azlin/vm_provisioning.py` (modify `_try_provision_vm` method, line 535-656)

**Key Points**:
- Create disk BEFORE VM provisioning
- Disk creation failure is TERMINAL (raise exception)
- Attach disk AFTER VM creation
- Disk attachment failure is NON-TERMINAL (graceful degradation, just log warning)

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestProvisionVMWithHomeDisk -v
# Expected: 4 tests PASS
```

---

### Phase 6: Error Handling (3 tests)

**Tests to pass**: `TestHomeDiskErrorHandling` (3 tests)

**Implementation**: Already covered in phases 2-5

**Validation**:
```bash
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestHomeDiskErrorHandling -v
# Expected: 3 tests PASS
```

---

### Phase 7: CLI Integration (3 tests - currently skipped)

**Tests to pass**: `TestCLIHomeDiskFlags` (3 tests)

**Implementation**: Add CLI flags to NewCommand

Location: `src/azlin/commands/new.py` (or similar)

```python
@click.command()
@click.option('--home-disk-size', type=int, default=100, help='Home disk size in GB (default: 100)')
@click.option('--no-home-disk', is_flag=True, help='Disable separate home disk')
def new(..., home_disk_size, no_home_disk):
    """Provision new VM."""

    # Determine home disk configuration
    config = VMConfig(
        name=name,
        resource_group=resource_group,
        location=location,
        size=size,
        home_disk_enabled=not no_home_disk,
        home_disk_size_gb=home_disk_size,
        home_disk_sku="Standard_LRS"
    )
```

**Validation**: Un-skip tests and run

---

### Phase 8: NFS Precedence Logic (3 tests - currently skipped)

**Tests to pass**: `TestNFSPrecedenceLogic` (3 tests)

**Implementation**: Add logic to NewCommand

```python
# NFS takes precedence over home disk
if nfs_storage and not no_nfs:
    # NFS provides /home via network mount
    home_disk_enabled = False
else:
    home_disk_enabled = not no_home_disk
```

**Validation**: Un-skip tests and run

---

### Phase 9: Integration Tests (15 tests)

**File**: `tests/integration/test_home_disk_integration.py`

**Implementation**: Already complete if phases 1-5 implemented correctly

**Validation**:
```bash
uv run pytest tests/integration/test_home_disk_integration.py -v -m integration
# Expected: 15 tests PASS (some may be skipped)
```

---

### Phase 10: E2E Tests (5 tests - manual)

**File**: `tests/e2e/test_home_disk_e2e.py`

**Implementation**: Manual execution only

**Validation**: Run manually before major releases
```bash
# Remove @pytest.skip decorator from one test
# Requires Azure credentials
uv run pytest tests/e2e/test_home_disk_e2e.py::TestHomeDiskE2E::test_azlin_new_creates_vm_with_home_disk -v -m e2e --slow
```

---

## Incremental Validation Strategy

Run tests after each phase to ensure progress:

```bash
# Phase 1 complete
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestVMConfigDefaults -v
# ✅ 6 tests should PASS

# Phase 2 complete
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestCreateHomeDisk -v
# ✅ 5 tests should PASS

# Phase 3 complete
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestAttachHomeDisk -v
# ✅ 3 tests should PASS

# Phase 4 complete
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestGenerateCloudInitWithHomeDisk -v
# ✅ 10 tests should PASS

# Phase 5 complete
uv run pytest tests/unit/test_vm_provisioning_home_disk.py::TestProvisionVMWithHomeDisk -v
# ✅ 4 tests should PASS

# All unit tests
uv run pytest tests/unit/test_vm_provisioning_home_disk.py -v
# ✅ 31 tests should PASS (6 skipped for CLI integration)

# Integration tests
uv run pytest tests/integration/test_home_disk_integration.py -v -m integration
# ✅ 15 tests should PASS (some skipped)
```

---

## Test Coverage Goals

After implementation:

```bash
# Check coverage
uv run pytest --cov=azlin.vm_provisioning --cov-report=html tests/unit/test_vm_provisioning_home_disk.py

# Expected coverage: >90% for new code
```

---

## Common Implementation Pitfalls

1. **Don't forget to add `_execute_azure_command` helper** if it doesn't exist
   - Wrap AzureCLIExecutor in a method for easy mocking

2. **Use Azure stable device paths** (`/dev/disk/azure/scsi1/lun0`)
   - NOT `/dev/sdc` which can change

3. **Include `nofail` mount option**
   - Prevents boot failure if disk is missing

4. **Handle graceful degradation**
   - Disk creation failure = TERMINAL (stop)
   - Disk attachment failure = NON-TERMINAL (warn and continue)

5. **Update cloud-init signature carefully**
   - Add `has_home_disk=False` as default for backwards compatibility
   - Don't break existing tests

6. **Test error scenarios**
   - Mock Azure CLI failures
   - Verify error messages are clear
   - Ensure proper exception types

---

## Success Criteria

Implementation is complete when:

- [ ] All 31 unit tests pass
- [ ] All 15 integration tests pass
- [ ] At least 1 E2E test executed successfully (manual)
- [ ] Test coverage >90% for new code
- [ ] No existing tests broken
- [ ] CLI flags work as expected
- [ ] NFS precedence logic works
- [ ] Documentation updated

---

## Next Steps After Implementation

1. Run full test suite: `uv run pytest -v`
2. Check test coverage: `uv run pytest --cov=azlin --cov-report=html`
3. Manual E2E validation with real Azure VM
4. Update user documentation
5. Create PR with test results

---

**Remember**: Tests fail FIRST (red), then implement to make them pass (green), then refactor (if needed). This is TDD!
