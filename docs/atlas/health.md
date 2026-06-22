---
title: Health Dashboard
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Health Dashboard
</nav>

# Health Dashboard

<div class="atlas-metadata">
Overall: :material-alert-circle:{ .atlas-health--warn } **PASS_WITH_WARNINGS** | Warnings: 3 | Failures: 0
</div>

## Check Results

| Check | Status | Details |
|-------|--------|---------|
| FILE_COVERAGE | :material-check-circle:{ .atlas-health--pass } | 18 .py files covered across layers 1, 2, 7 |
| CLI_COMMAND_COVERAGE | :material-check-circle:{ .atlas-health--pass } | 0 CLI commands all have journeys |
| EXPORT_CONSISTENCY | :material-check-circle:{ .atlas-health--pass } | 27 exported names all resolve to definitions |
| DEPENDENCY_CONSISTENCY | :material-check-circle:{ .atlas-health--pass } | All 0 Python dependencies are imported (87 non-Python deps not checked against imports) |
| IO_TRACEABILITY | :material-alert-circle:{ .atlas-health--warn } | 6/6 I/O files in unreachable packages |
| SUBPROCESS_TRACEABILITY | :material-alert-circle:{ .atlas-health--warn } | 4/4 subprocess files in unreachable packages |
| PACKAGE_CONSISTENCY | :material-alert-circle:{ .atlas-health--warn } | layer3 vs manifest: 0 missing, 16 extra |
| ROUTE_COVERAGE | :material-check-circle:{ .atlas-health--pass } | 0 HTTP routes all have journeys |
| IMPORT_RESOLUTION | :material-check-circle:{ .atlas-health--pass } | 31 internal import names all resolve |
| CLI_HANDLER_REACHABILITY | :material-check-circle:{ .atlas-health--pass } | 0 CLI commands have reachable handlers |
| DEAD_DEP_CROSS_VALIDATION | :material-check-circle:{ .atlas-health--pass } | No unused dependencies declared in layer3 |
| CIRCULAR_IMPORT_SEVERITY | :material-check-circle:{ .atlas-health--pass } | No circular dependencies detected |
| ENV_VAR_COMPLETENESS | :material-check-circle:{ .atlas-health--pass } | No environment variables detected |
| ROUTE_TEST_COVERAGE | :material-check-circle:{ .atlas-health--pass } | No HTTP routes to check |
| REEXPORT_CHAIN_VALIDATION | :material-check-circle:{ .atlas-health--pass } | 14 __init__.py re-export names all resolve |

## Warnings

### IO_TRACEABILITY

6/6 I/O files in unreachable packages

Missing items:

- `/home/azureuser/src/azlin/benchmarks/benchmark_parallel_vm_list.py`
- `/home/azureuser/src/azlin/benchmarks/benchmark_vm_list.py`
- `/home/azureuser/src/azlin/scripts/audit_key_operations.py`
- `/home/azureuser/src/azlin/scripts/cli_documentation/example_manager.py`
- `/home/azureuser/src/azlin/src/azlin/rust_bridge.py`
- `/home/azureuser/src/azlin/scripts/cli_documentation/hasher.py`

### SUBPROCESS_TRACEABILITY

4/4 subprocess files in unreachable packages

Missing items:

- `/home/azureuser/src/azlin/scripts/test_audit_key_operations.py`
- `/home/azureuser/src/azlin/benchmarks/benchmark_vm_list.py`
- `/home/azureuser/src/azlin/benchmarks/benchmark_parallel_vm_list.py`
- `/home/azureuser/src/azlin/src/azlin/rust_bridge.py`

### PACKAGE_CONSISTENCY

layer3 vs manifest: 0 missing, 16 extra

Missing items:

- `layer3 vs manifest: 0 missing, 16 extra`
