# Using azlin with uv

azlin is now configured as a `uv` project for ultra-fast dependency management and execution.

## Installation Methods

### Method 1: Run with uvx (No Installation)

The fastest way to use azlin - no installation required:

```bash
# Run azlin directly with uvx
uvx --from /Users/ryan/src/azlin-feat-1 azlin --help

# Provision a VM
uvx --from /Users/ryan/src/azlin-feat-1 azlin

# List VMs
uvx --from /Users/ryan/src/azlin-feat-1 azlin list
```

### Method 2: Install from Local Directory

Install azlin in your environment:

```bash
uv pip install /Users/ryan/src/azlin-feat-1
azlin --help
```

### Method 3: Development Mode

For development with hot-reload:

```bash
cd /Users/ryan/src/azlin-feat-1
uv sync               # Install dependencies
uv run azlin --help   # Run azlin
```

### Method 4: Traditional pip (Still Works)

```bash
cd /Users/ryan/src/azlin-feat-1
pip install -e .
azlin --help
```

## Why uv?

- **Ultra-fast**: 10-100x faster than pip
- **Reliable**: Deterministic dependency resolution with uv.lock
- **No installation needed**: `uvx` runs tools without installing
- **Better caching**: Shared dependency cache across projects

## Development Commands

```bash
# Sync dependencies (creates/updates .venv)
uv sync

# Add a new dependency
uv add requests

# Add a dev dependency
uv add --dev black

# Run azlin
uv run azlin

# Run tests
uv run pytest

# Update dependencies
uv lock --upgrade
```

## Files Created

- `uv.lock` - Locked dependency versions (commit this!)
- `.venv/` - Virtual environment (gitignored)
- `pyproject.toml` - Updated for uv/hatchling

## Publishing

When ready to publish to PyPI:

```bash
uv build
uv publish
```

Then users can run:

```bash
uvx azlin --help
```

Without needing the local path!
