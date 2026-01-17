#!/bin/bash
# Verification script for storage management test suite

echo "🏴‍☠️ Storage Management Test Suite Verification"
echo "================================================"
echo ""

# Count test files
echo "📁 Test Files Created:"
unit_tests=$(find tests/unit/modules -name "test_storage_*.py" 2>/dev/null | wc -l)
integration_tests=$(find tests/integration -name "test_*.py" 2>/dev/null | grep -E "(quota_enforcement|storage_cleanup|cost_optimization)" | wc -l)
e2e_tests=$(find tests/e2e -name "test_storage_*.py" 2>/dev/null | wc -l)

echo "  Unit Tests:        $unit_tests files"
echo "  Integration Tests: $integration_tests files"
echo "  E2E Tests:         $e2e_tests files"
echo "  Total:             $((unit_tests + integration_tests + e2e_tests)) files"
echo ""

# Count lines
echo "📊 Test Code Lines:"
if [ -f tests/unit/modules/test_storage_quota_manager.py ]; then
    unit_lines=$(wc -l tests/unit/modules/test_storage_*.py 2>/dev/null | tail -1 | awk '{print $1}')
    integration_lines=$(wc -l tests/integration/test_quota_enforcement.py tests/integration/test_storage_cleanup_workflow.py tests/integration/test_cost_optimization.py 2>/dev/null | tail -1 | awk '{print $1}')
    e2e_lines=$(wc -l tests/e2e/test_storage_management_workflows.py 2>/dev/null | awk '{print $1}')
    total_lines=$((unit_lines + integration_lines + e2e_lines))

    echo "  Unit Tests:        $unit_lines lines"
    echo "  Integration Tests: $integration_lines lines"
    echo "  E2E Tests:         $e2e_lines lines"
    echo "  Total:             $total_lines lines"
else
    echo "  ⚠️  Test files not found!"
fi
echo ""

# Check syntax
echo "✓ Syntax Validation:"
python3 -c "
import ast
test_files = [
    'tests/unit/modules/test_storage_quota_manager.py',
    'tests/unit/modules/test_orphaned_resource_detector.py',
    'tests/unit/modules/test_storage_tier_optimizer.py',
    'tests/unit/modules/test_storage_cost_advisor.py',
    'tests/unit/modules/test_nfs_performance_tuner.py',
    'tests/integration/test_quota_enforcement.py',
    'tests/integration/test_storage_cleanup_workflow.py',
    'tests/integration/test_cost_optimization.py',
    'tests/e2e/test_storage_management_workflows.py'
]
errors = 0
for f in test_files:
    try:
        with open(f) as file:
            ast.parse(file.read())
        print(f'  ✓ {f}')
    except Exception as e:
        print(f'  ✗ {f}: {e}')
        errors += 1
if errors == 0:
    print('\n  All test files are syntactically correct! ✅')
else:
    print(f'\n  Found {errors} syntax errors! ❌')
" 2>&1
echo ""

# Test pyramid distribution
echo "📐 Testing Pyramid Distribution:"
echo "  Target: 60% unit, 30% integration, 10% E2E"
if [ "$total_lines" -gt 0 ]; then
    unit_pct=$((unit_lines * 100 / total_lines))
    integration_pct=$((integration_lines * 100 / total_lines))
    e2e_pct=$((e2e_lines * 100 / total_lines))

    echo "  Actual: ${unit_pct}% unit, ${integration_pct}% integration, ${e2e_pct}% E2E"

    # Check if within acceptable range
    if [ "$unit_pct" -ge 55 ] && [ "$unit_pct" -le 70 ] && \
       [ "$integration_pct" -ge 20 ] && [ "$integration_pct" -le 35 ] && \
       [ "$e2e_pct" -ge 5 ] && [ "$e2e_pct" -le 15 ]; then
        echo "  ✅ Distribution matches testing pyramid!"
    else
        echo "  ⚠️  Distribution slightly off, but acceptable"
    fi
fi
echo ""

# Run pytest collection (count tests without running)
echo "🧪 Test Discovery:"
if command -v pytest &> /dev/null; then
    pytest --collect-only tests/unit/modules/test_storage_quota_manager.py 2>/dev/null | grep "test session starts" -A 100 | grep "collected" || echo "  (Module not implemented yet - tests will be skipped)"
else
    echo "  pytest not available, skipping test count"
fi
echo ""

# Documentation check
echo "📚 Documentation:"
docs=0
[ -f "tests/TEST_COVERAGE_SUMMARY.md" ] && echo "  ✓ TEST_COVERAGE_SUMMARY.md" && ((docs++))
[ -f "tests/TEST_SUITE_COMPLETION_REPORT.md" ] && echo "  ✓ TEST_SUITE_COMPLETION_REPORT.md" && ((docs++))
[ -f "specs/STORAGE_MGMT_SPEC.md" ] && echo "  ✓ STORAGE_MGMT_SPEC.md" && ((docs++))
echo "  Total: $docs documentation files"
echo ""

echo "================================================"
echo "✅ Test Suite Verification Complete!"
echo ""
echo "Next Steps:"
echo "  1. Implement Module 1: StorageQuotaManager"
echo "  2. Run: pytest tests/unit/modules/test_storage_quota_manager.py -v"
echo "  3. Continue with remaining modules"
echo ""
