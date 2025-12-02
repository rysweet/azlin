# Running Template System V2 Tests

Quick reference guide for running the comprehensive TDD test suite.

## Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-asyncio

# Navigate to project root
cd /home/azureuser/src/azlin/worktrees/feat-issue-441-template-v2
```

## Quick Start

### Run All Template Tests
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py -v
```

### Run All Tests with Coverage
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py \
  --cov=src/azlin/templates \
  --cov-report=html \
  --cov-report=term-missing
```

## By Test Level

### Unit Tests Only (118 tests)
```bash
pytest tests/unit/templates/ -v
```

### Integration Tests Only (37 tests)
```bash
pytest tests/integration/templates/ -v
```

### E2E Tests Only (19 tests)
```bash
pytest tests/e2e/test_template_system_e2e.py -v
```

## By Feature

### Versioning (26 tests)
```bash
pytest tests/unit/templates/test_versioning.py -v
```

### Marketplace/Registry (44 tests)
```bash
pytest tests/unit/templates/test_marketplace.py \
       tests/integration/templates/test_registry_integration.py -v
```

### Composition/Inheritance (22 tests)
```bash
pytest tests/unit/templates/test_composition.py \
       tests/integration/templates/test_template_workflows.py::TestTemplateCompositionWorkflow -v
```

### Validation & Linting (31 tests)
```bash
pytest tests/unit/templates/test_validation.py \
       tests/integration/templates/test_template_workflows.py::TestTemplateValidationWorkflow -v
```

### Analytics (38 tests)
```bash
pytest tests/unit/templates/test_analytics.py \
       tests/integration/templates/test_registry_integration.py::TestRegistryAnalyticsIntegration \
       tests/integration/templates/test_registry_integration.py::TestVersioningAnalyticsIntegration -v
```

## By Specific Test Class

### Example: Run only versioning comparison tests
```bash
pytest tests/unit/templates/test_versioning.py::TestTemplateVersion -v
```

### Example: Run only registry integration tests
```bash
pytest tests/integration/templates/test_registry_integration.py::TestRegistryValidationIntegration -v
```

## By Specific Test

### Example: Run single test
```bash
pytest tests/unit/templates/test_versioning.py::TestTemplateVersion::test_version_creation_with_semver -v
```

## Useful Options

### Show Output (stdout/stderr)
```bash
pytest tests/unit/templates/ -v -s
```

### Stop on First Failure
```bash
pytest tests/unit/templates/ -v -x
```

### Run Failed Tests Only
```bash
pytest tests/unit/templates/ -v --lf
```

### Run Last Failed Tests First
```bash
pytest tests/unit/templates/ -v --ff
```

### Parallel Execution (faster)
```bash
pip install pytest-xdist
pytest tests/unit/templates/ -v -n auto
```

### Show Slowest Tests
```bash
pytest tests/unit/templates/ -v --durations=10
```

## Coverage Reports

### Generate HTML Coverage Report
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py \
  --cov=src/azlin/templates \
  --cov-report=html

# View report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage with Missing Lines
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py \
  --cov=src/azlin/templates \
  --cov-report=term-missing
```

### Coverage Threshold (fail if below 75%)
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py \
  --cov=src/azlin/templates \
  --cov-fail-under=75
```

## Current Expected Behavior

**All tests are currently FAILING** with `ModuleNotFoundError: No module named 'azlin.templates'`

This is **correct and expected** for TDD approach:
- ✅ Tests written first
- ⏳ Implementation pending
- ⏳ Tests will pass after implementation

### Example Expected Output
```
tests/unit/templates/test_versioning.py FFFFFFFFFFFFFFFFFFFFFFFFFF [100%]

=================================== FAILURES ===================================
____________ TestTemplateVersion.test_version_creation_with_semver _____________
tests/unit/templates/test_versioning.py:18: in test_version_creation_with_semver
    from azlin.templates.versioning import TemplateVersion
E   ModuleNotFoundError: No module named 'azlin.templates'
```

## After Implementation

Once implementation is complete, you should see:
```bash
pytest tests/unit/templates/ tests/integration/templates/ tests/e2e/test_template_system_e2e.py -v

# Expected output:
tests/unit/templates/test_versioning.py::TestTemplateVersion::test_version_creation_with_semver PASSED
...
========================= 174 passed in X.XXs =========================
```

## Continuous Integration

### GitHub Actions Example
```yaml
- name: Run Template System Tests
  run: |
    pytest tests/unit/templates/ \
           tests/integration/templates/ \
           tests/e2e/test_template_system_e2e.py \
           --cov=src/azlin/templates \
           --cov-fail-under=75 \
           --junitxml=test-results.xml
```

## Troubleshooting

### Import Errors
If you see import errors:
```bash
# Ensure project is installed in development mode
pip install -e .
```

### SQLite Errors (Analytics Tests)
Analytics tests use temporary SQLite databases. If you see database errors:
```bash
# Run with verbose output
pytest tests/unit/templates/test_analytics.py -v -s
```

### Timeout Errors (E2E Tests)
E2E tests may take longer. Increase timeout:
```bash
pytest tests/e2e/test_template_system_e2e.py -v --timeout=300
```

## Test Statistics

| Metric | Value |
|--------|-------|
| Total Tests | 174 |
| Unit Tests | 118 (68%) |
| Integration Tests | 37 (21%) |
| E2E Tests | 19 (11%) |
| Target Coverage | >75% |
| Test Files | 8 files |
| Total Test Code | ~112 KB |

## Next Steps

1. **Implement Features**: Create `src/azlin/templates/` module
2. **Run Tests**: Watch tests turn from RED → GREEN
3. **Verify Coverage**: Ensure >75% coverage achieved
4. **Iterate**: Fix any failing tests, add more as needed

---

**Last Updated**: 2025-12-01
**Workstream**: WS7 - Template System V2
**Issue**: #441
