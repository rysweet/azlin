# Test Plan: Ripgrep Installation on VM Creation

## Issue #378: Add ripgrep installation to VM creation

## Prerequisites

1. Azure subscription with permissions to create VMs
2. Terraform installed locally
3. Azure CLI authenticated (`az login`)
4. Working directory: `terraform/azdoit-test/`

## Test Scenarios

### Scenario 1: Create New VM and Verify Ripgrep Installation ✅ (PRIMARY TEST)

**Purpose**: Verify that ripgrep is automatically installed during VM creation

**Steps**:
```bash
# 1. Navigate to Terraform directory
cd terraform/azdoit-test/

# 2. Initialize Terraform (if not already done)
terraform init

# 3. Create the VM
terraform apply -auto-approve

# 4. Wait for VM to complete provisioning (~2-3 minutes)

# 5. SSH into the VM
ssh azureuser@<public_ip>

# 6. Verify ripgrep is installed
which rg
rg --version

# 7. Check cloud-init logs
sudo cat /var/log/cloud-init-output.log | grep -i ripgrep
cloud-init status

# 8. Test ripgrep functionality
echo "test content" > test.txt
rg "test" test.txt
```

**Expected Results**:
- `which rg` returns: `/usr/bin/rg`
- `rg --version` shows ripgrep version (e.g., `ripgrep 13.0.0`)
- Cloud-init logs show: `Setting up ripgrep...` or similar
- `cloud-init status` shows: `status: done`
- `rg "test" test.txt` finds the match

**Cleanup**:
```bash
# Exit VM
exit

# Destroy test VM
terraform destroy -auto-approve
```

---

### Scenario 2: Verify VM Creation Not Delayed ✅

**Purpose**: Ensure cloud-init installation doesn't block VM availability

**Steps**:
```bash
# 1. Note start time
time terraform apply -auto-approve

# 2. Check when VM becomes available for SSH
```

**Expected Results**:
- Terraform completes in normal time (~2-3 minutes)
- SSH is available immediately after Terraform shows "Apply complete!"
- Ripgrep installation happens in background (may not be complete when SSH first available)

---

### Scenario 3: Idempotency Test ✅

**Purpose**: Verify that re-running cloud-init doesn't cause errors

**Steps**:
```bash
# SSH into existing VM
ssh azureuser@<public_ip>

# Manually re-run cloud-init
sudo cloud-init clean --logs
sudo cloud-init init
sudo cloud-init modules --mode final

# Verify ripgrep still works
rg --version
```

**Expected Results**:
- No errors during cloud-init re-run
- Ripgrep remains installed and functional
- `apt install -y ripgrep` handles "already installed" gracefully

---

### Scenario 4: Failure Handling Test ❌

**Purpose**: Verify VM remains operational if ripgrep installation fails

**Steps**:
```bash
# Create VM with temporarily modified cloud-init.yml
# Change to intentionally fail: apt-get install -y nonexistent-package

terraform apply -auto-approve

# SSH into VM
ssh azureuser@<public_ip>

# Verify VM is operational despite failed package
uptime
df -h
```

**Expected Results**:
- VM creation succeeds
- SSH works normally
- Cloud-init logs show error but VM is operational
- User can manually install ripgrep if needed

---

## Automated Testing (Limited)

Since Terraform integration tests require actual Azure resources, we can only validate:

### YAML Syntax Validation ✅
```bash
# Validate cloud-init.yml syntax
python3 -c "import yaml; yaml.safe_load(open('terraform/azdoit-test/cloud-init.yml'))"
```

**Expected**: No output (successful parse)

### Terraform Validation ✅
```bash
cd terraform/azdoit-test/
terraform init
terraform validate
```

**Expected**: `Success! The configuration is valid.`

### Terraform Plan (Dry Run) ✅
```bash
terraform plan
```

**Expected**: Shows `custom_data` will be set on VM resource

---

## Verification Checklist

Before considering this feature complete:

- [x] **YAML Syntax Valid**: cloud-init.yml parses correctly (verified ✅)
- [x] **Terraform Syntax Valid**: main.tf has no errors (verified ✅)
- [x] **Pre-commit Hooks Pass**: All checks passed (verified ✅)
- [ ] **Scenario 1 Pass**: Ripgrep installed on new VM (MANUAL TEST REQUIRED)
- [ ] **Scenario 2 Pass**: VM creation not delayed (MANUAL TEST REQUIRED)
- [ ] **Scenario 3 Pass**: Idempotent re-run works (MANUAL TEST OPTIONAL)
- [ ] **Scenario 4 Pass**: VM operational if install fails (MANUAL TEST OPTIONAL)

## Testing with Real Azure Resources

**Recommended Approach**:
1. Deploy VM with `terraform apply` in terraform/azdoit-test/
2. Verify ripgrep installed with `rg --version`
3. Test ripgrep functionality with sample search
4. Destroy VM with `terraform destroy`

**Time Estimate**: 10-15 minutes (VM creation ~3 min, testing ~2 min, destroy ~2 min)

---

## Success Criteria

The feature is successfully implemented when:
- ✅ New VMs have ripgrep installed automatically
- ✅ `rg --version` works on newly created VMs
- ✅ VM creation time unchanged
- ✅ Cloud-init logs show successful installation
- ✅ No errors in cloud-init execution

## Notes

- Cloud-init logs: `/var/log/cloud-init.log` and `/var/log/cloud-init-output.log`
- Cloud-init status: `cloud-init status` command
- Package installation is async - may take 30-60 seconds after SSH available
- Terraform doesn't wait for cloud-init completion (by design)
