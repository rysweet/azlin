# PWA Configuration Generator - Test Documentation

## Overview

This document describes the test suite for the PWA configuration inheritance feature (Issue #572).

## Test Structure

Following TDD methodology and the testing pyramid principle:

- **60% Unit Tests**: `tests/unit/test_pwa_config_generator.py`
- **30% Integration Tests**: `tests/integration/test_pwa_config_integration.py`
- **10% E2E Tests**: Manual verification (documented below)

## Test Files

### Unit Tests (`test_pwa_config_generator.py`)

**Lines of Code**: ~650

**Coverage Areas**:
1. ConfigSource enum validation
2. PWAConfigResult dataclass behavior
3. Azure CLI availability checking
4. Config extraction from `az account show`
5. Config value mapping to environment variables
6. .env file generation
7. Source attribution tracking
8. Error handling for various failure modes
9. Config value priority and fallback logic
10. **CRITICAL**: Never overwrite existing .env files

**Key Test Classes**:
- `TestConfigSource` - Enum validation
- `TestPWAConfigResult` - Result dataclass behavior
- `TestPWAConfigGenerator` - Main generator functionality
- `TestConfigValueExtraction` - Specific extraction logic
- `TestErrorMessages` - Error message quality

### Integration Tests (`test_pwa_config_integration.py`)

**Lines of Code**: ~550

**Coverage Areas**:
1. Complete config generation workflow
2. File system operations (create, read, write)
3. Subprocess integration with Azure CLI
4. Multiple config sources working together
5. Error recovery and fallback mechanisms
6. CLI integration points
7. .env file format validation (Vite compatibility)
8. Real-world usage scenarios

**Key Test Classes**:
- `TestFullConfigGenerationWorkflow` - End-to-end workflows
- `TestFileSystemIntegration` - File operations
- `TestSubprocessIntegration` - Azure CLI subprocess calls
- `TestMultiSourceIntegration` - Multiple config sources
- `TestErrorRecoveryIntegration` - Failure handling
- `TestCLIIntegration` - CLI command integration
- `TestEnvFileFormatIntegration` - Format validation
- `TestRealWorldScenarios` - User scenarios

## Critical Test Cases

### 1. NEVER Overwrite Existing .env (CRITICAL)

**Test**: `test_never_overwrite_existing_env_file`

This is the #1 requirement from the architecture specification.

```python
def test_never_overwrite_existing_env_file(self, temp_pwa_dir):
    # Create existing .env
    existing_env = temp_pwa_dir / ".env"
    existing_content = "VITE_USER_CONFIG=important_value"
    existing_env.write_text(existing_content)

    # Attempt generation without force flag
    generator = PWAConfigGenerator()
    result = generator.generate_pwa_env_from_azlin(
        pwa_dir=temp_pwa_dir, force=False
    )

    # MUST NOT overwrite
    assert result.success is False
    assert ".env already exists" in result.message.lower()
    assert existing_env.read_text() == existing_content
```

### 2. Azure CLI Integration

**Test**: `test_extract_azure_config_success`

Validates extraction from `az account show`:

```bash
az account show --output json
```

Expected JSON structure:
```json
{
  "id": "subscription-id",
  "tenantId": "tenant-id",
  "name": "subscription-name"
}
```

### 3. Source Attribution Tracking

**Test**: `test_source_attribution_tracking`

Every config value must track its source:
- `ConfigSource.AZURE_CLI` - From `az account show`
- `ConfigSource.AZLIN_CONFIG` - From `~/.azlin/config.toml`
- `ConfigSource.DEFAULT` - Fallback values
- `ConfigSource.EXISTING_ENV` - Already in .env file

### 4. Config Value Priority

**Test**: `test_azure_cli_takes_priority_over_config_file`

Priority order:
1. Azure CLI (`az account show`) - HIGHEST
2. azlin config.toml
3. Default values - LOWEST

## Running the Tests

### Run All Tests

```bash
# Run all PWA config tests
pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py -v

# Run with coverage
pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py --cov=azlin.modules.pwa_config_generator --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/test_pwa_config_generator.py -v

# Integration tests only
pytest tests/integration/test_pwa_config_integration.py -v

# Critical tests only
pytest tests/unit/test_pwa_config_generator.py::TestPWAConfigGenerator::test_never_overwrite_existing_env_file -v
```

### Expected Behavior (TDD)

**ALL TESTS SHOULD FAIL** until implementation is complete!

Expected failures:
```
FAILED tests/unit/test_pwa_config_generator.py::TestConfigSource::test_config_source_values - ImportError: cannot import name 'ConfigSource'
FAILED tests/unit/test_pwa_config_generator.py::TestPWAConfigResult::test_result_creation_success - ImportError: cannot import name 'PWAConfigResult'
FAILED tests/unit/test_pwa_config_generator.py::TestPWAConfigGenerator::test_never_overwrite_existing_env_file - ImportError: cannot import name 'PWAConfigGenerator'
...
```

This is **correct** - tests are written first, implementation comes next.

## E2E Manual Tests (10%)

### Test 1: Fresh PWA Setup

```bash
# Prerequisites: Azure CLI authenticated
az login
az account show

# Create new PWA project
mkdir test-pwa && cd test-pwa

# Generate config
python -c "from azlin.modules.pwa_config_generator import PWAConfigGenerator; PWAConfigGenerator().generate_pwa_env_from_azlin(pwa_dir='.')"

# Verify .env exists
cat .env

# Expected output:
# VITE_AZURE_SUBSCRIPTION_ID=<your-sub-id>
# VITE_AZURE_TENANT_ID=<your-tenant-id>
```

### Test 2: Existing .env Protection

```bash
# Create PWA with existing .env
mkdir test-pwa-2 && cd test-pwa-2
echo "VITE_IMPORTANT=do-not-delete" > .env

# Attempt generation (should fail)
python -c "from azlin.modules.pwa_config_generator import PWAConfigGenerator; result = PWAConfigGenerator().generate_pwa_env_from_azlin(pwa_dir='.'); print(f'Success: {result.success}, Message: {result.message}')"

# Expected output:
# Success: False, Message: .env already exists. Use force=True to overwrite.

# Verify original content unchanged
cat .env
# Should still show: VITE_IMPORTANT=do-not-delete
```

### Test 3: Force Overwrite

```bash
# Create PWA with existing .env
mkdir test-pwa-3 && cd test-pwa-3
echo "OLD_VALUE=replace-me" > .env

# Generate with force=True
python -c "from azlin.modules.pwa_config_generator import PWAConfigGenerator; PWAConfigGenerator().generate_pwa_env_from_azlin(pwa_dir='.', force=True)"

# Verify new content
cat .env
# Should have new Azure config values
```

### Test 4: CLI Integration

```bash
# Use via azlin CLI (once CLI integration is complete)
cd existing-pwa-project
azlin web start

# Should:
# 1. Check for .env
# 2. Generate if missing
# 3. Start dev server
```

## Test Fixtures and Mocks

### Shared Fixtures (from `conftest.py`)

Available fixtures:
- `temp_pwa_dir` - Temporary PWA directory
- `temp_config_dir` - Temporary azlin config directory
- `mock_azure_cli_available` - Mock Azure CLI as available
- `mock_azure_cli_unavailable` - Mock Azure CLI as unavailable
- `mock_az_account_show_success` - Mock successful `az account show`
- `mock_subprocess_success` - Mock successful subprocess calls
- `mock_subprocess_failure` - Mock failed subprocess calls

### Custom Fixtures

- `test_environment` - Complete test environment with all directories
- `mock_azure_authenticated` - Full authenticated Azure CLI mock
- `multi_source_environment` - Environment with multiple config sources

## Coverage Goals

### Minimum Coverage Targets

- **Line Coverage**: 90% (for new code)
- **Branch Coverage**: 85% (all major code paths)
- **Critical Path Coverage**: 100% (must cover .env overwrite protection)

### Coverage Report

```bash
pytest tests/unit/test_pwa_config_generator.py tests/integration/test_pwa_config_integration.py \
  --cov=azlin.modules.pwa_config_generator \
  --cov-report=html \
  --cov-report=term-missing

# View report
open htmlcov/index.html
```

## Test Proportionality Analysis

### Implementation vs Test Ratio

**Expected Implementation**: ~200-300 lines
**Test Code**: ~1200 lines total
**Ratio**: 4-6:1

**Justification**:
- Critical safety requirement (never overwrite .env)
- Multiple config sources and fallback logic
- Subprocess integration requires extensive mocking
- Error handling for multiple failure modes
- File system operations need careful testing

This ratio is appropriate for:
- ✅ Business logic with safety-critical requirements
- ✅ External system integration (Azure CLI)
- ✅ File system operations
- ✅ Multiple failure modes

### Comparison to Philosophy Guidelines

From `PHILOSOPHY.md`:
```
Business logic: 3:1 to 8:1 (comprehensive)
Critical paths: 5:1 to 15:1 (exhaustive)
```

Our ratio (4-6:1) falls within the business logic range, appropriate for this feature's complexity and criticality.

## Known Issues and Limitations

### Limitations of Current Test Suite

1. **No real Azure CLI calls** - All Azure CLI interactions are mocked
   - Rationale: Tests must run in CI without Azure authentication
   - Mitigation: E2E manual tests verify real Azure CLI integration

2. **Limited cross-platform testing** - Tests assume POSIX file system
   - Rationale: Focus on Linux/macOS (primary azlin platforms)
   - Future: Add Windows-specific tests if needed

3. **No performance tests** - No benchmarks for config generation speed
   - Rationale: Config generation is not performance-critical
   - Acceptable: <1 second for typical config generation

## Next Steps

1. **Verify tests fail** - Run tests to confirm they fail as expected (TDD)
2. **Implement module** - Create `src/azlin/modules/pwa_config_generator/`
3. **Watch tests pass** - Implement until all tests pass
4. **Add E2E tests** - Run manual E2E scenarios
5. **CI integration** - Add to CI pipeline
6. **Documentation** - Update user-facing docs

## References

- Architecture Design: `.claude/docs/ARCHITECTURE_pwa_config_inheritance.md`
- Issue: #572
- Testing Pyramid: 60% unit, 30% integration, 10% E2E
- Philosophy: `PHILOSOPHY.md` - Proportionality Principle
