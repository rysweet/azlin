# Implementation Plan: GitHub Issue #26 - azlin template command

## Overview
Add VM configuration template management system to azlin CLI, allowing users to save, reuse, and share VM configurations.

## Feature Specification

### Commands
```bash
azlin template create <name>     # Create template from current config or interactive
azlin template list              # List all available templates
azlin template delete <name>     # Delete a template
azlin template export <name>     # Export template to YAML file
azlin template import <file>     # Import template from YAML file
```

### Integration with existing commands
```bash
azlin new --template <name>      # Create VM from template
```

## Architecture

### Storage
- Location: `~/.azlin/templates/`
- Format: YAML files (one per template)
- Naming: `<template_name>.yaml`

### Template Structure (YAML)
```yaml
name: "dev-vm"
description: "Development VM with standard tools"
vm_size: "Standard_D2s_v3"
region: "eastus"
cloud_init: |
  #cloud-config
  packages:
    - docker
    - nodejs
custom_metadata:
  created_by: "user@example.com"
  created_at: "2025-10-15T05:30:00Z"
```

### Module Design

#### TemplateManager class
```python
class TemplateManager:
    """Manage VM configuration templates."""
    
    @staticmethod
    def create_template(name: str, config: VMTemplateConfig) -> None
    
    @staticmethod
    def list_templates() -> List[VMTemplateConfig]
    
    @staticmethod
    def get_template(name: str) -> VMTemplateConfig
    
    @staticmethod
    def delete_template(name: str) -> None
    
    @staticmethod
    def export_template(name: str, output_path: Path) -> None
    
    @staticmethod
    def import_template(input_path: Path) -> VMTemplateConfig
```

#### VMTemplateConfig dataclass
```python
@dataclass
class VMTemplateConfig:
    name: str
    description: str
    vm_size: str
    region: str
    cloud_init: Optional[str] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
```

## Implementation Steps (TDD)

### 1. Architecture Planning ✅
- Create this implementation plan
- Define module interfaces
- Define test scenarios

### 2. Write FAILING Tests (RED) 🔴
File: `tests/unit/test_template_manager.py`
- Test template creation
- Test template listing
- Test template retrieval
- Test template deletion
- Test template export
- Test template import
- Test YAML serialization/deserialization
- Test validation (invalid names, missing fields)
- Test directory creation
- Test file permissions

### 3. Implement Feature (GREEN) 🟢
File: `src/azlin/template_manager.py`
- Implement TemplateManager class
- Implement VMTemplateConfig dataclass
- Implement YAML I/O operations
- Implement validation logic
- Implement directory management

### 4. CLI Integration (GREEN continued) 🟢
File: `src/azlin/cli.py`
- Add `template` command group
- Add subcommands: create, list, delete, export, import
- Update `new` command with `--template` flag
- Add help text and examples

### 5. Refactor (REFACTOR) 🔵
- Extract common validation logic
- Add type hints
- Improve error messages
- Add docstrings
- Clean up code

### 6. Run Linter 🧹
- Run pre-commit hooks
- Fix any linting issues

### 7. Commit 💾
- Commit with message: "Implement template command (Fixes #26)"

### 8. Create Summary Document 📄
- Document implementation details
- Add usage examples
- Note any limitations

## Test Scenarios

### Template Creation
- Create template with all fields
- Create template with minimal fields
- Create template with custom cloud-init
- Fail on invalid template name
- Fail on duplicate template name

### Template Listing
- List empty templates directory
- List multiple templates
- Sort templates alphabetically

### Template Retrieval
- Get existing template
- Fail on non-existent template
- Validate all fields present

### Template Deletion
- Delete existing template
- Fail on non-existent template
- Confirm file is removed

### Template Export/Import
- Export template to file
- Import template from file
- Fail on invalid YAML
- Fail on missing required fields

### CLI Integration
- `azlin template create dev-vm`
- `azlin template list`
- `azlin template delete dev-vm`
- `azlin new --template dev-vm`
- Proper error messages
- Help text display

## Security Considerations
- Template file permissions: 0644 (read/write owner, read others)
- Templates directory permissions: 0755
- Validate template names (no path traversal)
- Validate YAML content (no code injection)
- Validate cloud-init scripts (basic syntax check)

## Edge Cases
- Template with same name as existing file
- Template with very long name
- Template with special characters in name
- Empty templates directory
- Corrupted YAML file
- Missing templates directory

## Integration Points
- ConfigManager: Use existing config directory structure
- VMProvisioner: Apply template config during provisioning
- CLI: Add new command group and integrate with `new`

## Files to Create
- `src/azlin/template_manager.py` - Main implementation
- `tests/unit/test_template_manager.py` - Unit tests

## Files to Modify
- `src/azlin/cli.py` - Add template commands and --template flag

## Success Criteria
- ✅ All tests pass (100% coverage for new code)
- ✅ Linter passes (no errors or warnings)
- ✅ Templates persist across CLI invocations
- ✅ Templates integrate with `azlin new` command
- ✅ All commands have proper help text
- ✅ Error messages are clear and actionable
