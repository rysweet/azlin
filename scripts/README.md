# Documentation Validation Script

This directory contains the documentation validation automation that prevents future documentation drift.

## validate_documentation.py

Comprehensive validation script that ensures README.md stays in sync with the CLI implementation.

### Features

1. **Command Extraction** - Uses Click introspection to extract all CLI commands and options
2. **Markdown Parsing** - Parses README.md to find documented commands and their options
3. **Comparison** - Compares CLI vs docs and reports mismatches
4. **Example Validation** - Validates that code examples are syntactically correct
5. **Clear Reporting** - Color-coded output with errors and warnings

### Usage

```bash
# Run validation
python scripts/validate_documentation.py

# Or with uv (recommended)
uv run python scripts/validate_documentation.py

# Exit code 0 = consistent, 1 = inconsistencies found
```

### What It Catches

- **Missing Documentation**: Commands exist in CLI but aren't documented
- **Stale Documentation**: Commands documented but removed from CLI
- **Incorrect Options**: Option flags that don't exist or aren't documented
- **Broken Examples**: Code examples that reference non-existent commands
- **Syntax Errors**: Common mistakes like `==` instead of `=`

### Sample Output

```
Validating azlin documentation...

[1/4] Extracting commands from CLI...
      Found 64 commands in CLI
[2/4] Parsing README.md...
      Found 47 commands documented
[3/4] Comparing commands...
[4/4] Validating examples...
      Found 200 examples

Validation Results:

Warnings (3):
  ⚠️  Command 'cleanup' is documented but not yet implemented (planned feature)
  ⚠️  Command 'logs' is documented but not yet implemented (planned feature)
  ⚠️  Command 'tag' is documented but not yet implemented (planned feature)

Errors (52):
  ❌ Command 'do' exists in CLI but is not documented in README
  ❌ Command 'snapshot create' exists in CLI but is not documented in README
  ❌ Command 'auth list' is documented in README but doesn't exist in CLI
  ...

Documentation validation FAILED
```

### Integration

#### Pre-commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
  - repo: local
    hooks:
      - id: validate-docs
        name: Validate Documentation
        entry: uv run python scripts/validate_documentation.py
        language: system
        files: ^(README\.md|src/azlin/cli\.py)$
        pass_filenames: false
```

#### GitHub Actions

Add to `.github/workflows/docs.yml`:

```yaml
name: Documentation Validation
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Validate documentation
        run: uv run python scripts/validate_documentation.py
```

#### Manual Check

```bash
# Before committing documentation changes
python scripts/validate_documentation.py

# If errors found, fix them before committing
```

### Configuration

The script automatically handles:

- **Ignored Commands**: `version`, `help`, `create` (alias), `vm` (alias)
- **Planned Features**: Commands documented but not yet implemented
- **Internal Options**: `--config`, `--help`, `-h`
- **Option Aliases**: `--rg` vs `--resource-group`
- **Special Syntax**: `--` passthrough, `COMMAND` placeholder

### Extending

To add new validations:

1. **New Validator Class**: Add to script (e.g., `LinkValidator`)
2. **Update `validate()` method**: Call your new validator
3. **Add to Errors/Warnings**: Append to `self.errors` or `self.warnings`

Example:

```python
class LinkValidator:
    """Validate internal links in documentation."""

    def validate_links(self, content: str) -> List[str]:
        errors = []
        # Check for broken internal links
        links = re.findall(r'\[.*?\]\((#.*?)\)', content)
        for link in links:
            if not self._link_exists(link, content):
                errors.append(f"Broken link: {link}")
        return errors
```

### Why This Matters

**Before this script**, azlin had **47 documentation inconsistencies**:
- Missing documentation for 9 commands
- Documented commands that didn't exist
- Incorrect option flags
- Broken examples

**With this script**, future drift is prevented automatically in CI/CD and pre-commit hooks.

### Performance

- Validation time: ~2-5 seconds
- Fast enough for pre-commit hooks
- Caches Click CLI extraction
- No external API calls

### Troubleshooting

**ImportError when running script:**
```bash
# Install dependencies with uv
uv pip install click

# Or use uv run (recommended)
uv run python scripts/validate_documentation.py
```

**CLI not loading:**
The script will skip CLI comparison and only validate examples. This is fine for quick docs-only changes.

**Too many warnings:**
Warnings are informational. Only errors will cause CI to fail.
