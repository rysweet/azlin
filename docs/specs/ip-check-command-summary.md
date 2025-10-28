# `azlin ip check` - Quick Reference

## Command Syntax

```bash
azlin ip check [VM_NAME]              # Check single VM
azlin ip check --all                  # Check all VMs
azlin ip check my-vm --verbose        # Detailed output
azlin ip check my-vm --json           # JSON output
```

## What It Checks

1. **VM Status**: Power state, provisioning status
2. **IP Classification**: Public/Public-Azure/Private/None
3. **Connectivity**: SSH port 22 reachability, latency
4. **Network Security**: NSG rules for SSH access
5. **SSH Keys**: Local key existence and permissions

## Key Features

- Identifies Azure's 172.171.x.x public IP range (main user pain point)
- Color-coded output (green/yellow/red)
- Parallel checking for multiple VMs (--all mode)
- Actionable recommendations for detected issues
- JSON output for automation

## Implementation Priority

**Phase 1** (4-6 hours): Core IP classification and connectivity testing
**Phase 2** (1-2 days): Azure resource verification and NSG parsing
**Phase 3** (3-4 hours): CLI command implementation
**Phase 4** (6-8 hours): Verbose/JSON modes and documentation

**Total Estimated Effort**: 4-6 days

## Success Criteria

- Correctly identifies 172.171.x.x as public IPs ✓
- Single VM check completes in < 10 seconds ✓
- Clear actionable output for all failure scenarios ✓
- Test coverage > 85% ✓

## Next Steps

1. Implement `src/azlin/modules/ip_diagnostics.py` module
2. Extend `VMManager` with network detail queries
3. Add CLI command to `src/azlin/cli.py`
4. Write comprehensive test suite

## File Locations

- **Spec**: `/Users/ryan/src/azlin/docs/specs/ip-check-command-spec.md`
- **Implementation**:
  - `src/azlin/modules/ip_diagnostics.py` (new)
  - `src/azlin/vm_manager.py` (extend)
  - `src/azlin/cli.py` (add command)
- **Tests**:
  - `tests/unit/test_ip_diagnostics.py` (new)
  - `tests/integration/test_ip_check_command.py` (new)
