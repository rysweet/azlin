# CLI Documentation Sync System

Automated documentation generation for azlin CLI commands that keeps examples and documentation synchronized with the codebase.

## Overview

The CLI Documentation Sync System automatically generates documentation from Click command definitions and maintains example synchronization. Instead of manually updating docs when commands change, the system extracts metadata from the CLI code and generates consistent, accurate documentation.

## Quick Start

Generate documentation for all commands:

```bash
python scripts/doc_sync.py
```

The system scans all Click commands in `azlin/cli/`, extracts their metadata, loads examples from `scripts/examples/*.yaml`, and generates markdown files in `docs/cli/commands/`.

## Adding Examples to Commands

Examples are defined in YAML files under `scripts/examples/`. Each example shows a real-world use case with input, output, and explanation.

### Example File Structure

Create a file `scripts/examples/deploy.yaml`:

```yaml
command: deploy
examples:
  - title: Deploy to staging environment
    description: Deploy the current branch to staging with health checks enabled
    command: azlin deploy staging --health-check --timeout 300
    output: |
      Deploying to staging...
      Health check: PASSED
      Deployment complete: https://staging.example.com

  - title: Deploy with custom configuration
    description: Deploy using a specific configuration file
    command: azlin deploy production --config deploy-config.yaml
    output: |
      Loading configuration from deploy-config.yaml
      Deploying to production...
      Deployment complete: https://production.example.com
```

### YAML Fields

- `command`: Name of the CLI command (must match Click command name)
- `examples`: List of example objects
  - `title`: Brief title describing the example
  - `description`: Detailed explanation of what the example demonstrates
  - `command`: Full command with arguments and options
  - `output`: Expected output (optional)

### Adding Examples to Existing Commands

1. Find or create the YAML file for your command in `scripts/examples/`
2. Add your example to the `examples` list
3. Run the sync: `python scripts/doc_sync.py`
4. Verify the generated docs in `docs/cli/commands/`

Example session:

```bash
# Create new example file
cat > scripts/examples/init.yaml << EOF
command: init
examples:
  - title: Initialize new project
    description: Create a new azlin project with default configuration
    command: azlin init my-project
    output: |
      Creating project structure...
      Generated azlin.yaml
      Project initialized successfully
EOF

# Run sync to generate docs
python scripts/doc_sync.py

# Check generated documentation
cat docs/cli/commands/init.md
```

## Common Workflows

### Adding a New Command

When you add a new Click command:

1. Define the command in `azlin/cli/` using Click decorators
2. Add `@click.command()` decorator and document with docstrings
3. Create examples in `scripts/examples/{command_name}.yaml`
4. Run sync: `python scripts/doc_sync.py`

Example command definition:

```python
import click

@click.command()
@click.argument('environment')
@click.option('--config', '-c', help='Configuration file path')
@click.option('--dry-run', is_flag=True, help='Simulate deployment without executing')
def deploy(environment, config, dry_run):
    """Deploy application to specified environment.

    This command handles deployment orchestration including
    configuration validation, health checks, and rollback support.
    """
    if dry_run:
        click.echo(f"Dry run: Would deploy to {environment}")
        return

    click.echo(f"Deploying to {environment}...")
```

After defining the command, create `scripts/examples/deploy.yaml` and run the sync.

### Updating Command Documentation

The system performs full regeneration of command documentation when command signatures change. To update:

1. Modify the Click command definition (docstring, options, arguments)
2. Update or add examples in the corresponding YAML file
3. Run sync: `python scripts/doc_sync.py`
4. Review generated docs: `git diff docs/cli/commands/`

**Important**: When command signatures change (detected via hash comparison), the entire command section is regenerated. Manual edits within command sections will be overwritten. To add custom content:
- Add file-level header/footer content outside command sections
- Create separate documentation files that link to generated command docs

### Validating Generated Documentation

The sync system validates documentation after generation:

```bash
# Run sync with validation
python scripts/doc_sync.py

# Output shows validation results:
# ✓ Generated: docs/cli/commands/deploy.md
# ✓ Validation passed
# ✓ Examples: 2 found, 2 included
```

## Documentation Structure

Generated documentation follows this structure:

```markdown
# command-name

Brief description from docstring

## Usage

```bash
azlin command-name [OPTIONS] [ARGUMENTS]
```

## Arguments

- `argument-name` - Description

## Options

- `--option-name` - Description
- `--flag` - Boolean flag description

## Examples

### Example Title

Description of what this example demonstrates

```bash
azlin command-name --option value
```

Output:
```
Expected output here
```
```

## Troubleshooting

### Examples not appearing in documentation

**Problem**: Added examples to YAML but they don't appear in generated docs.

**Solution**:
1. Check that `command` field in YAML matches the Click command name exactly
2. Verify YAML syntax is valid: `python -m yaml scripts/examples/{file}.yaml`
3. Check sync output for parsing errors
4. Ensure the YAML file is in `scripts/examples/` directory

```bash
# Verify YAML syntax
python -c "import yaml; yaml.safe_load(open('scripts/examples/deploy.yaml'))"

# Check if command name matches
grep "command:" scripts/examples/deploy.yaml
grep "@click.command(name=" azlin/cli/commands.py
```

### Documentation not regenerating

**Problem**: Made changes to CLI code but docs aren't updating.

**Solution**:
1. Run sync explicitly: `python scripts/doc_sync.py`
2. Check if the command is properly registered in Click
3. Verify the command file is in a scanned directory
4. Check for Python syntax errors in the command file

```bash
# Test command is importable
python -c "from azlin.cli import deploy; print(deploy)"

# Check for syntax errors
python -m py_compile azlin/cli/commands.py
```

### Missing command metadata

**Problem**: Generated docs are missing options or arguments.

**Solution**:
1. Ensure all options use `@click.option()` decorator
2. Verify arguments use `@click.argument()` decorator
3. Add help text to all options and arguments
4. Check that decorators are above the function definition

```python
# Correct decorator order (decorators closest to function execute first)
@click.command()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.argument('input_file')
def process(input_file, verbose):
    """Process input file with optional verbose output."""
    pass
```

### YAML formatting errors

**Problem**: Sync fails with YAML parsing errors.

**Solution**:
1. Use proper YAML indentation (2 spaces, not tabs)
2. Quote strings containing special characters
3. Use `|` for multi-line strings
4. Validate YAML online or with linter

```yaml
# Correct YAML formatting
command: deploy
examples:
  - title: Example with special characters
    description: Shows proper quoting
    command: 'azlin deploy --message "Fix: deployment issue"'
    output: |
      Multi-line output
      Uses pipe character
      Preserves newlines
```

### Documentation out of sync with code

**Problem**: Documentation doesn't match current command behavior.

**Solution**: The sync system runs automatically in CI but can be run manually:

```bash
# Force regeneration
rm -rf docs/cli/commands/
python scripts/doc_sync.py

# Verify changes
git diff docs/cli/commands/
```

## Integration with CI

The documentation sync runs automatically in GitHub Actions on every PR. If CLI code changes without corresponding documentation updates, the CI check fails.

To fix CI failures:

1. Run sync locally: `python scripts/doc_sync.py`
2. Commit generated documentation: `git add docs/cli/commands/`
3. Push changes: `git push`

CI validates:
- All commands have generated documentation
- Examples match command signatures
- No placeholder or stub documentation
- YAML files are valid

## Best Practices

1. **Write descriptive docstrings**: First line becomes the command summary
2. **Add help text to all options**: Appears in generated documentation
3. **Create realistic examples**: Show actual use cases, not toy examples
4. **Include expected output**: Helps users verify correct behavior
5. **Test examples before committing**: Run each example command to verify output
6. **One YAML file per command**: Keeps examples organized and maintainable

## Examples Directory Structure

```
scripts/examples/
├── deploy.yaml          # Examples for 'azlin deploy'
├── init.yaml            # Examples for 'azlin init'
├── config.yaml          # Examples for 'azlin config'
└── remote/
    ├── create.yaml      # Examples for 'azlin remote create'
    └── list.yaml        # Examples for 'azlin remote list'
```

## Further Reading

- [CLI Implementation Guide](../reference/cli-implementation.md) - How to write Click commands
- [Testing CLI Commands](../howto/test-cli-commands.md) - Testing strategies for CLI
- [scripts/cli_documentation/README.md](../../scripts/cli_documentation/README.md) - Developer documentation
