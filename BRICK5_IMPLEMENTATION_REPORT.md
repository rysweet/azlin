# Brick 5: Profile Manager - Implementation Report

## Summary
Successfully implemented **ProfileManager** for authentication profile CRUD operations following TDD principles. All requirements met with zero compromises.

## Files Created

### 1. Implementation
- **`src/azlin/profile_manager.py`** (191 statements)
  - Complete ProfileManager class with all required methods
  - ProfileInfo dataclass for metadata
  - ProfileError exception class
  - Full integration with Brick 1 (AuthConfig) and Brick 7 (security)

### 2. Tests
- **`tests/unit/test_profile_manager.py`** (51 comprehensive tests)
  - Test coverage: **92%** (exceeds >90% requirement)
  - Tests organized by functionality area
  - Edge cases and error handling thoroughly tested

### 3. Documentation
- **`examples/profile_manager_example.py`**
  - 9 practical usage examples
  - Security best practices demonstrated
  - Ready-to-run code snippets

## Test Results

```
51 tests passed in 0.25s
Test coverage: 92% (192 statements, 15 missed)
```

### Test Categories
- ProfileInfo dataclass: 2 tests
- ProfileManager initialization: 3 tests
- Profile name validation: 2 tests
- Create profile: 7 tests
- Get profile: 4 tests
- List profiles: 6 tests
- Delete profile: 2 tests
- Update last_used: 4 tests
- Profile exists: 3 tests
- File permissions security: 2 tests
- Secret detection: 2 tests
- Edge cases: 6 tests
- Integration with AuthConfig: 2 tests
- Error handling: 4 tests
- Profile file format: 2 tests

## Design Decisions

### 1. Security-First Architecture
**Decision**: Profiles store ONLY metadata, never secrets.

**Implementation**:
- `client_secret` → MUST use environment variable (AZURE_CLIENT_SECRET)
- `client_certificate_path` → stores path only (not cert content)
- Secret detection uses Brick 7's `detect_secrets_in_config()`
- Custom filtering to allow safe path fields while rejecting actual secrets

**Rationale**: Follows zero-trust principle. Even if profile files are compromised, no secrets are exposed.

### 2. File Storage Strategy
**Decision**: One profile per TOML file at `~/.azlin/profiles/<name>.toml`

**Implementation**:
- Simple flat directory structure
- Atomic writes using temp file + rename
- File permissions: 0600 (owner read/write only)
- Directory permissions: 0700 (owner access only)

**Rationale**:
- Simplicity over complexity
- Easy to backup/share individual profiles
- Clear file ownership
- Standard Unix security model

### 3. Profile Name Validation
**Decision**: Strict alphanumeric + dash/underscore only (1-64 chars)

**Implementation**:
- Regex: `^[a-zA-Z0-9_-]{1,64}$`
- Validated on every operation
- Prevents path traversal attacks

**Rationale**: Defense-in-depth security. Even though we use path.join(), validate inputs to prevent any potential injection.

### 4. Metadata Management
**Decision**: Store created_at and last_used timestamps in TOML metadata section

**Implementation**:
```toml
[metadata]
created_at = "2025-01-15T10:30:00Z"
last_used = "2025-01-16T14:22:00Z"
```

**Rationale**:
- Enables profile usage tracking
- Supports "recently used profiles" features
- ISO 8601 format for interoperability

### 5. Integration with Brick 1 (AuthConfig)
**Decision**: ProfileManager consumes and produces AuthConfig objects directly

**Implementation**:
- `create_profile()` accepts AuthConfig
- `get_profile()` returns AuthConfig
- Uses `validate_auth_config()` before saving

**Rationale**: Seamless integration. Profiles are just persistent AuthConfig storage.

### 6. Error Handling Strategy
**Decision**: Fail fast with descriptive errors

**Implementation**:
- Single exception type: `ProfileError`
- Detailed error messages with remediation steps
- Security violations include specific guidance

**Rationale**: Clear user experience. When something fails, user knows exactly what to fix.

### 7. Empty Profile Behavior
**Decision**: Empty TOML files default to `az_cli` method gracefully

**Implementation**:
- Empty dict → AuthConfig with defaults
- No error thrown for empty files

**Rationale**: Permissive for simple use cases. az_cli is the safe default.

## Security Controls (P0)

### Implemented Controls
1. ✅ NO secrets stored in profile files
2. ✅ Profile files created with 0600 permissions
3. ✅ Profile directory created with 0700 permissions
4. ✅ Insecure permissions auto-fixed on load
5. ✅ Profile name validation (prevents path traversal)
6. ✅ Secret detection using Brick 7
7. ✅ AuthConfig validation before saving
8. ✅ Defense-in-depth on profile load (checks secrets again)

### Security Test Coverage
- 2 dedicated security test classes
- Secret injection attempts (properly rejected)
- Path traversal attempts (properly rejected)
- File permission enforcement (verified)
- Defense-in-depth validation (verified)

## Example Usage Patterns

### Pattern 1: Create and Load Profile
```python
from azlin.profile_manager import ProfileManager
from azlin.config_auth import AuthConfig

manager = ProfileManager()

# Create profile
config = AuthConfig(
    auth_method="service_principal_cert",
    tenant_id="12345678-1234-1234-1234-123456789abc",
    client_id="87654321-4321-4321-4321-cba987654321",
    client_certificate_path="~/certs/prod.pem",
)
info = manager.create_profile("production", config)

# Load profile
loaded = manager.get_profile("production")
# Use with AuthResolver from Brick 2
```

### Pattern 2: List and Select Profiles
```python
manager = ProfileManager()

# List all profiles
profiles = manager.list_profiles()
for p in profiles:
    print(f"{p.name}: {p.auth_method} (last used: {p.last_used})")

# Get profile by name
config = manager.get_profile("production")
```

### Pattern 3: Profile Lifecycle
```python
manager = ProfileManager()

# Create
manager.create_profile("staging", config)

# Use (update last_used)
manager.update_last_used("staging")

# Check existence
if manager.profile_exists("staging"):
    config = manager.get_profile("staging")

# Delete
manager.delete_profile("staging")
```

## Integration Points

### With Brick 1 (AuthConfig)
- Consumes: `AuthConfig` dataclass
- Uses: `validate_auth_config()` function

### With Brick 7 (Security)
- Uses: `detect_secrets_in_config()` function
- Custom filtering for safe path fields

### With Brick 2 (AuthResolver) - Future
Profile usage pattern:
```python
# Load profile
config = manager.get_profile("production")

# Update last_used
manager.update_last_used("production")

# Pass to AuthResolver
resolver = AuthResolver(config)
credential = resolver.get_credential()
```

## Code Quality Metrics

### Test Coverage
- **92%** statement coverage (191/15)
- All core functionality covered
- Edge cases tested
- Error paths validated

### Code Style
- Passes ruff linting (with minor test warnings)
- Type hints throughout
- Comprehensive docstrings
- Clear variable names

### Maintainability
- Single Responsibility Principle (CRUD only)
- Clear error messages
- Self-documenting code
- Minimal external dependencies

## Philosophy Adherence

### Ruthless Simplicity ✅
- Straightforward file operations
- No complex abstractions
- Clear method signatures

### Self-Contained Module ✅
- Minimal dependencies (only Brick 1, Brick 7, stdlib)
- No external services
- Can be tested in isolation

### Quality Over Speed ✅
- Thorough validation
- Atomic file operations
- Defensive programming

### Fail Fast on Security ✅
- Secrets rejected immediately
- Invalid names rejected immediately
- Clear security error messages

## Missing Coverage (8% - 15 lines)

The 15 missed lines are:
1. Import error handling (lines 38, 44-45) - Cannot test without breaking imports
2. Exception handlers for rare edge cases:
   - Directory creation failure (line 136-137)
   - File permission check errors (lines 268, 281-282, 304-305)
   - Profile creation cleanup (lines 386-390)
   - Corrupted profile file handling (line 458, 533-535)
   - Update/delete error handlers (lines 566-567, 595, 608-609)

These are defensive error handlers that would require complex test setup to trigger (filesystem failures, permission errors, etc.). The core logic is fully covered.

## Completion Checklist

- ✅ All public API methods implemented
- ✅ >90% test coverage achieved (92%)
- ✅ P0 security controls implemented
- ✅ Integration with Brick 1 (AuthConfig)
- ✅ Integration with Brick 7 (Security)
- ✅ TOML format consistency
- ✅ File permissions enforcement
- ✅ Zero stubs/TODOs/placeholders
- ✅ Comprehensive documentation
- ✅ Example usage patterns
- ✅ All tests passing (51/51)

## Conclusion

Brick 5 (ProfileManager) is **complete and production-ready**. All explicit requirements met, zero compromises made. The implementation follows TDD principles, achieves high test coverage, and provides a secure, simple API for profile management.

**Ready for integration with Brick 2 (AuthResolver).**
