# Test Pyramid Rebalance Plan - Issue #426

## Current State
- **Total Tests**: 166 files
- **Current Distribution**: 128 unit (77%) / 26 integration (15%) / 12 e2e (7%)
- **Target Distribution**: 99 unit (60%) / 50 integration (30%) / 17 e2e (10%)

## Required Changes
- **Remove**: 29 over-mocked unit tests
- **Add**: 24 integration tests
- **Add**: 5 e2e tests

## Critical Workflows Needing Integration Tests (from Issue #426)

### 1. Authentication Chain (5 tests)
- `test_azure_cli_to_service_principal_fallback.py` - Test real Azure CLI → Service Principal fallback
- `test_managed_identity_authentication.py` - Test managed identity flow without mocks
- `test_auth_credential_rotation.py` - Test credential rotation workflow
- `test_auth_multi_subscription.py` - Test multi-subscription authentication
- `test_certificate_based_auth_flow.py` - Test certificate-based authentication

### 2. VM Provisioning Workflow (5 tests)
- `test_vm_config_to_bastion_workflow.py` - Config validation → Bastion setup → VM provision
- `test_vm_with_nfs_provisioning.py` - VM provision with NFS mount workflow
- `test_vm_ssh_key_injection.py` - SSH key management during provisioning
- `test_vm_network_setup_workflow.py` - Network security group → VNet → VM
- `test_vm_template_to_deployment.py` - Template expansion → ARM deployment

### 3. File Transfer Workflow (4 tests)
- `test_file_transfer_path_parsing.py` - Path parsing → Session creation → Transfer
- `test_file_transfer_bastion_routing.py` - File transfer via bastion routing
- `test_file_transfer_large_files.py` - Large file transfer with resume
- `test_file_transfer_bidirectional.py` - Upload and download workflow

### 4. Cleanup Orchestration (4 tests)
- `test_cleanup_orphaned_detection.py` - Orphaned resource detection workflow
- `test_cleanup_cost_calculation.py` - Cost estimation during cleanup
- `test_cleanup_user_interaction.py` - User prompts → Deletion workflow
- `test_cleanup_rollback_workflow.py` - Cleanup with rollback on failure

### 5. Cross-Region Operations (3 tests)
- `test_cross_region_vnet_peering.py` - VNet peering setup workflow
- `test_cross_region_private_endpoint.py` - Private endpoint creation workflow
- `test_cross_region_dns_propagation.py` - DNS zone configuration workflow

### 6. Storage Management (3 tests)
- `test_storage_quota_enforcement_flow.py` - Quota check → Warning → Block workflow
- `test_storage_tier_optimization.py` - Tier analysis → Recommendation → Change
- `test_storage_cross_region_replication.py` - Storage replication workflow

## Unit Tests to Remove (29 tests with heavy mocking)

### Category 1: Over-Mocked Component Interaction (15 tests)
These tests mock so heavily they don't test real behavior:
- `tests/unit/test_tag_manager.py` (100% mocked subprocess)
- `tests/unit/test_vm_updater.py` (RemoteExecutor completely mocked)
- `tests/unit/test_interactive_connect.py` (CLI fully mocked)
- `tests/unit/test_batch_executor.py` (All batch operations mocked)
- `tests/unit/test_vm_lifecycle_control.py` (Azure calls mocked)
- `tests/unit/test_nfs_auto_detection.py` (Storage manager mocked)
- `tests/unit/test_list_wide_flag.py` (Console output mocked)
- `tests/unit/test_ssh_connector_backward_compat.py` (SSH completely mocked)
- `tests/unit/test_vm_lifecycle.py` (All Azure interactions mocked)
- `tests/unit/test_tag.py` (TagManager mocked)
- `tests/unit/test_multi_context_list.py` (VMManager mocked)
- `tests/unit/test_context_selector.py` (Context operations mocked)
- `tests/unit/test_quota_manager.py` (subprocess.run mocked)
- `tests/unit/test_remote_exec.py` (SSH operations mocked)
- `tests/unit/test_security_audit_integration.py` (misnamed - should be integration test)

### Category 2: Redundant Testing (8 tests)
These test the same logic as other tests:
- `tests/unit/test_bastion_vm_boot_wait.py` (covered by integration tests)
- `tests/unit/test_ssh_reconnect.py` (covered by integration tests)
- `tests/unit/test_env_manager.py` (duplicate of env_manager_security tests)
- `tests/unit/test_log_viewer.py` (covered by integration tests)
- `tests/unit/test_terminal_launcher_tmux.py` (covered by e2e tests)
- `tests/unit/test_ssh_bastion_routing.py` (covered by integration tests)
- `tests/unit/test_session_cleanup.py` (covered by cleanup workflow tests)
- `tests/unit/test_backward_compatibility_bastion.py` (covered by integration tests)

### Category 3: Trivial Tests (6 tests)
These test simple data structures that don't need unit tests:
- `tests/unit/costs/test_cost_dashboard.py` (dataclass tests)
- `tests/unit/monitoring/test_collector.py` (dataclass tests)
- `tests/unit/test_multi_context_display.py` (display logic with mocked console)
- `tests/unit/templates/test_composition.py` (simple composition logic)
- `tests/unit/modules/test_parallel_deployer_minimal.py` (dataclass tests)
- `tests/unit/modules/test_cross_region_sync.py` (dataclass tests)

## E2E Tests to Add (5 tests)

1. `test_complete_vm_lifecycle_e2e.py` - Create → Connect → Update → Delete
2. `test_multi_vm_orchestration_e2e.py` - Create multiple VMs with dependencies
3. `test_disaster_recovery_e2e.py` - Backup → Failure → Restore workflow
4. `test_cost_optimization_complete_e2e.py` - Cost analysis → Optimization → Validation
5. `test_template_system_complete_e2e.py` - Template create → Use → Modify → Delete

## Implementation Strategy

### Phase 1: Add Integration Tests (Week 1-2)
1. Create 24 new integration tests following the categories above
2. Ensure they test real component interactions (no mocking of core logic)
3. Use test fixtures for Azure resources (real or containerized)
4. Verify all integration tests pass

### Phase 2: Remove Redundant Unit Tests (Week 2)
1. Remove 29 over-mocked and redundant unit tests
2. Verify coverage doesn't drop significantly
3. Update test documentation

### Phase 3: Add E2E Tests (Week 3)
1. Create 5 new e2e tests for complete workflows
2. Use real Azure resources in test subscriptions
3. Ensure proper cleanup after tests

### Phase 4: Verification (Week 3)
1. Run full test suite
2. Verify pyramid ratio: 60/30/10
3. Ensure CI passes
4. Document new test structure

## Success Criteria

- [ ] 60% unit tests (99 files)
- [ ] 30% integration tests (50 files)
- [ ] 10% e2e tests (17 files)
- [ ] All tests passing in CI
- [ ] No reduction in code coverage
- [ ] Documentation updated
