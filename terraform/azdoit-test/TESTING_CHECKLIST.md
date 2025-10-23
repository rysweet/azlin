# AZDOIT Testing Checklist

Comprehensive checklist to validate azdoit functionality using the test infrastructure.

## Pre-Deployment Checklist

- [ ] Azure CLI installed and authenticated (`az account show`)
- [ ] Terraform installed (>= 1.0) (`terraform version`)
- [ ] azdoit CLI installed (`azdoit --version`)
- [ ] SSH key pair available (`ls ~/.ssh/id_*.pub`)
- [ ] Azure subscription has quota for Standard_B2s VM
- [ ] Terraform.tfvars configured with SSH public key

## Deployment Checklist

- [ ] `terraform init` completed successfully
- [ ] `terraform validate` shows no errors
- [ ] `terraform plan` reviewed (should create 8 resources)
- [ ] `terraform apply` completed successfully
- [ ] All outputs displayed correctly
- [ ] Resource group visible in Azure Portal
- [ ] VM visible in Azure Portal

## AZDOIT Functionality Tests

### Category 1: Resource Discovery

- [ ] **Test 1.1**: List all VMs in resource group
  ```bash
  azdoit "list VMs in test-azdoit-rg"
  ```
  Expected: Shows test-azdoit-vm-1

- [ ] **Test 1.2**: List all resources in resource group
  ```bash
  azdoit "list all resources in test-azdoit-rg"
  ```
  Expected: Shows VM, VNet, Public IP, NSG, NIC, etc.

- [ ] **Test 1.3**: List network interfaces
  ```bash
  azdoit "list network interfaces in test-azdoit-rg"
  ```
  Expected: Shows test-azdoit-vm-1-nic

- [ ] **Test 1.4**: List public IPs
  ```bash
  azdoit "list public IPs in test-azdoit-rg"
  ```
  Expected: Shows test-azdoit-vm-1PublicIP

### Category 2: Resource Details

- [ ] **Test 2.1**: Get VM details
  ```bash
  azdoit "get VM test-azdoit-vm-1 details"
  ```
  Expected: Shows VM size, location, OS, status

- [ ] **Test 2.2**: Show VM with alternative phrasing
  ```bash
  azdoit "show details of test-azdoit-vm-1"
  ```
  Expected: Same information as 2.1

- [ ] **Test 2.3**: Get resource group details
  ```bash
  azdoit "show details of test-azdoit-rg"
  ```
  Expected: Shows location, tags, provisioning state

- [ ] **Test 2.4**: Get VM configuration
  ```bash
  azdoit "what is the configuration of test-azdoit-vm-1?"
  ```
  Expected: Shows VM size, network config, disk config

### Category 3: VM Power State

- [ ] **Test 3.1**: Check initial VM status
  ```bash
  azdoit "get status of test-azdoit-vm-1"
  ```
  Expected: Shows "PowerState/running" or similar

- [ ] **Test 3.2**: Check if VM is running
  ```bash
  azdoit "is test-azdoit-vm-1 running?"
  ```
  Expected: Confirms VM is running

- [ ] **Test 3.3**: Get power state with alternative phrasing
  ```bash
  azdoit "what is the power state of test-azdoit-vm-1?"
  ```
  Expected: Shows current power state

### Category 4: VM Power Management

- [ ] **Test 4.1**: Stop VM
  ```bash
  azdoit "stop VM test-azdoit-vm-1"
  ```
  Expected: Success message, VM stops/deallocates

- [ ] **Test 4.2**: Verify VM is stopped (wait 30s after stop)
  ```bash
  azdoit "get status of test-azdoit-vm-1"
  ```
  Expected: Shows "PowerState/deallocated" or "VM deallocated"

- [ ] **Test 4.3**: Verify VM is deallocated in Portal
  - Check Azure Portal
  Expected: VM status shows "Stopped (deallocated)"

- [ ] **Test 4.4**: Start VM
  ```bash
  azdoit "start VM test-azdoit-vm-1"
  ```
  Expected: Success message, VM starts

- [ ] **Test 4.5**: Verify VM is running (wait 60s after start)
  ```bash
  azdoit "get status of test-azdoit-vm-1"
  ```
  Expected: Shows "PowerState/running"

- [ ] **Test 4.6**: Restart VM (optional)
  ```bash
  azdoit "restart VM test-azdoit-vm-1"
  ```
  Expected: VM restarts successfully

### Category 5: Cost Analysis

- [ ] **Test 5.1**: Get resource group cost estimate
  ```bash
  azdoit "show cost estimate for test-azdoit-rg"
  ```
  Expected: Shows estimated costs

- [ ] **Test 5.2**: Get cost breakdown
  ```bash
  azdoit "what is the cost of test-azdoit-rg?"
  ```
  Expected: Shows cost information

- [ ] **Test 5.3**: Get VM cost specifically
  ```bash
  azdoit "how much does test-azdoit-vm-1 cost?"
  ```
  Expected: Shows VM cost estimate

### Category 6: Error Handling

- [ ] **Test 6.1**: Query non-existent VM
  ```bash
  azdoit "get VM non-existent-vm-99999 details"
  ```
  Expected: Graceful error message (not crash)

- [ ] **Test 6.2**: Query non-existent resource group
  ```bash
  azdoit "list VMs in non-existent-rg-99999"
  ```
  Expected: Graceful error message

- [ ] **Test 6.3**: Invalid operation
  ```bash
  azdoit "delete VM test-azdoit-vm-1"
  ```
  Expected: Either performs operation or explains why not

### Category 7: Natural Language Variations

- [ ] **Test 7.1**: Casual language
  ```bash
  azdoit "show me the VMs in test-azdoit-rg"
  ```
  Expected: Works same as formal phrasing

- [ ] **Test 7.2**: Question format
  ```bash
  azdoit "what VMs are in test-azdoit-rg?"
  ```
  Expected: Lists VMs

- [ ] **Test 7.3**: Abbreviated names
  ```bash
  azdoit "get vm-1 details"
  ```
  Expected: Understands partial name or asks for clarification

### Category 8: Complex Queries

- [ ] **Test 8.1**: Multi-part query
  ```bash
  azdoit "list all VMs in test-azdoit-rg and show their status"
  ```
  Expected: Lists VMs with status information

- [ ] **Test 8.2**: Conditional query
  ```bash
  azdoit "show me all running VMs in test-azdoit-rg"
  ```
  Expected: Filters to only running VMs

- [ ] **Test 8.3**: Comparison query
  ```bash
  azdoit "which VMs in test-azdoit-rg are stopped?"
  ```
  Expected: Lists stopped/deallocated VMs

## Automated Testing

- [ ] Run automated test script
  ```bash
  ./test-azdoit.sh
  ```
  Expected: All tests pass

- [ ] Review test script output
  Expected: Clear pass/fail indicators for each test

## SSH Connectivity Tests

- [ ] **Test 9.1**: Get SSH connection command
  ```bash
  terraform output ssh_connection_command
  ```
  Expected: Returns correct SSH command

- [ ] **Test 9.2**: Test SSH connection
  ```bash
  ssh azureuser@<public-ip>
  ```
  Expected: Successfully connects to VM

- [ ] **Test 9.3**: Verify VM is accessible after stop/start cycle
  Expected: Can still SSH after VM restart

## Azure Portal Verification

- [ ] Resource group visible and contains all resources
- [ ] VM shows correct status in Portal
- [ ] Network configuration visible
- [ ] Public IP assigned and visible
- [ ] NSG rules configured correctly
- [ ] Tags applied to all resources

## Cost Monitoring

- [ ] Check Azure Cost Management for resource group
- [ ] Verify estimated costs match expectations (~$0.20/day)
- [ ] Confirm stopped VM reduces costs appropriately

## Cleanup Tests

- [ ] **Test 10.1**: Stop VM before destroying
  ```bash
  azdoit "stop VM test-azdoit-vm-1"
  ```
  Expected: VM stops successfully

- [ ] **Test 10.2**: Terraform destroy plan
  ```bash
  terraform plan -destroy
  ```
  Expected: Shows 8 resources to be destroyed

- [ ] **Test 10.3**: Terraform destroy
  ```bash
  terraform destroy
  ```
  Expected: All resources removed

- [ ] **Test 10.4**: Verify cleanup in Portal
  Expected: Resource group no longer exists

- [ ] **Test 10.5**: Verify no lingering costs
  Expected: Azure Cost Management shows no ongoing charges

## Performance Tests

- [ ] VM start time < 2 minutes
- [ ] VM stop time < 1 minute
- [ ] azdoit query response time < 5 seconds
- [ ] Terraform apply time < 10 minutes
- [ ] Terraform destroy time < 5 minutes

## Documentation Tests

- [ ] README.md is clear and accurate
- [ ] QUICKSTART.md works for new users
- [ ] ARCHITECTURE.md matches actual deployment
- [ ] All example commands in docs are correct
- [ ] Test script runs without errors

## Integration Tests

- [ ] azdoit works with Azure CLI authenticated session
- [ ] azdoit works after VM operations (stop/start)
- [ ] azdoit handles rate limiting gracefully
- [ ] azdoit provides helpful error messages
- [ ] azdoit outputs are parseable/actionable

## Security Tests

- [ ] SSH key authentication works
- [ ] Password authentication disabled
- [ ] Only SSH port (22) accessible
- [ ] No unexpected open ports
- [ ] VM not accessible without SSH key

## Test Results Summary

**Total Tests**: _____ / _____
**Passed**: _____
**Failed**: _____
**Blocked**: _____
**Not Applicable**: _____

## Issues Found

| Test ID | Issue Description | Severity | Status |
|---------|------------------|----------|--------|
|         |                  |          |        |

## Notes

_Add any additional observations or notes here_

## Approval

- [ ] All critical tests passed
- [ ] No blocking issues found
- [ ] Documentation is accurate
- [ ] Ready for production use

**Tested By**: _______________
**Date**: _______________
**azdoit Version**: _______________
**Terraform Version**: _______________
