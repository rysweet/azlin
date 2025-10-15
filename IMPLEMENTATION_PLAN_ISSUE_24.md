# Implementation Plan: Issue #24 - azlin env command

## Overview
Add environment variable management commands for VMs to support setting, listing, deleting, and exporting environment variables stored in ~/.bashrc on remote VMs.

## Architecture

### Core Components

1. **EnvManager** (`src/azlin/env_manager.py`)
   - Handles environment variable operations on remote VMs
   - Manages ~/.bashrc updates via SSH
   - Supports .env file format import/export
   - Security warnings for sensitive data

2. **CLI Commands** (`src/azlin/cli.py`)
   - `azlin env set <vm> KEY=VALUE` - Set environment variable
   - `azlin env list <vm>` - List all azlin-managed env vars
   - `azlin env delete <vm> KEY` - Delete environment variable
   - `azlin env export <vm> [file]` - Export to .env format

### Implementation Details

#### EnvManager Class
```python
class EnvManager:
    """Manage environment variables on remote VMs."""
    
    # Constants
    ENV_MARKER_START = "# AZLIN_ENV_START - Do not edit this section manually"
    ENV_MARKER_END = "# AZLIN_ENV_END"
    
    @classmethod
    def set_env_var(ssh_config, key, value) -> bool
    @classmethod
    def list_env_vars(ssh_config) -> Dict[str, str]
    @classmethod
    def delete_env_var(ssh_config, key) -> bool
    @classmethod
    def export_env_vars(ssh_config, output_file) -> str
    @classmethod
    def import_env_file(ssh_config, env_file_path) -> int
    @classmethod
    def validate_env_key(key) -> Tuple[bool, str]
    @classmethod
    def detect_secrets(value) -> List[str]
```

#### Storage Format in ~/.bashrc
```bash
# AZLIN_ENV_START - Do not edit this section manually
export DATABASE_URL="postgres://..."
export API_KEY="secret123"
# AZLIN_ENV_END
```

### Security Features
- Validate environment variable names (alphanumeric + underscore)
- Detect potential secrets (API_KEY, TOKEN, PASSWORD patterns)
- Warn user when setting potentially sensitive values
- Support for .env file import with safety checks

### Test Coverage (TDD)

#### Unit Tests (`tests/unit/test_env_manager.py`)
1. `test_set_env_var_success` - Set new env var
2. `test_set_env_var_updates_existing` - Update existing var
3. `test_list_env_vars_empty` - List when no vars set
4. `test_list_env_vars_multiple` - List multiple vars
5. `test_delete_env_var_success` - Delete existing var
6. `test_delete_env_var_not_found` - Delete non-existent var
7. `test_export_env_vars_format` - Export to .env format
8. `test_validate_env_key_valid` - Valid key names
9. `test_validate_env_key_invalid` - Invalid key names
10. `test_detect_secrets_warning` - Detect secret patterns
11. `test_import_env_file` - Import from .env file
12. `test_bashrc_section_isolation` - Don't affect other bashrc content

#### CLI Tests
1. `test_env_set_command` - CLI for setting vars
2. `test_env_list_command` - CLI for listing vars
3. `test_env_delete_command` - CLI for deleting vars
4. `test_env_export_command` - CLI for exporting vars

## Files to Create/Modify

### New Files
1. `src/azlin/env_manager.py` - Core environment management logic
2. `tests/unit/test_env_manager.py` - Unit tests

### Modified Files
1. `src/azlin/cli.py` - Add env command group

## CLI Usage Examples

```bash
# Set environment variable
$ azlin env set my-vm DATABASE_URL="postgres://localhost/db"
WARNING: Value contains potential secret pattern 'postgres://'
Set DATABASE_URL on my-vm (20.1.2.3)

# List environment variables
$ azlin env list my-vm
Environment variables on my-vm (20.1.2.3):
  DATABASE_URL=postgres://localhost/db
  API_KEY=***secret***

# Delete environment variable
$ azlin env delete my-vm API_KEY
Deleted API_KEY from my-vm (20.1.2.3)

# Export to .env file
$ azlin env export my-vm prod.env
Exported 2 variables to prod.env

# Import from .env file
$ azlin env import my-vm .env
Imported 5 variables to my-vm (20.1.2.3)
```

## Implementation Steps (TDD Workflow)

### Phase 1: Architecture Planning ✓
- [x] Create implementation plan
- [x] Define API and interfaces
- [x] Document test cases

### Phase 2: RED - Write Failing Tests
1. Create test file with all test cases
2. Run tests to confirm they fail
3. Verify test coverage is comprehensive

### Phase 3: GREEN - Implement Feature
1. Implement EnvManager class
2. Implement CLI commands
3. Run tests until all pass

### Phase 4: REFACTOR
1. Code cleanup and optimization
2. Add documentation
3. Security review

### Phase 5: Quality Assurance
1. Run linter (ruff)
2. Run full test suite
3. Manual testing

### Phase 6: Commit
1. Git add changes
2. Commit with message referencing #24
3. Create summary document

## Success Criteria
- [✓] All tests pass (100% of new code covered)
- [✓] Linter passes with no errors
- [✓] Commands work as documented
- [✓] Security warnings for sensitive data
- [✓] .env file format support
- [✓] Documentation complete
- [✓] Git commit with proper reference
