# PWA Configuration Generator Module

## Overview

Self-contained module for generating PWA `.env` configuration by inheriting Azure settings from azlin parent configuration.

## Public API

```python
from azlin.modules.pwa_config_generator import (
    ConfigSource,
    PWAConfigGenerator,
    PWAConfigResult,
)

# Generate PWA .env from azlin config
generator = PWAConfigGenerator()
result = generator.generate_pwa_env_from_azlin(
    pwa_dir=Path("/path/to/pwa"),
    azlin_config_dir=Path("/path/to/.azlin"),  # Optional
    force=False,  # Never overwrite by default
)

if result.success:
    print(f"Generated .env at: {result.env_path}")
    print(f"Values: {result.config_values}")
    print(f"Sources: {result.source_attribution}")
else:
    print(f"Error: {result.message}")
```

## Configuration Sources (Priority Order)

1. **Azure CLI** (`az account show`) - Highest priority
   - `subscription_id` → `VITE_AZURE_SUBSCRIPTION_ID`
   - `tenant_id` → `VITE_AZURE_TENANT_ID`

2. **azlin config.toml** - Fallback
   - `[azure]` section values

3. **Default values** - Last resort
   - `VITE_AZURE_REDIRECT_URI=http://localhost:3000`

## Critical Safety Features

- **NEVER overwrites existing `.env`** without `force=True`
- Validates subscription ID format (UUID)
- Graceful fallback when Azure CLI unavailable
- Clear source attribution for debugging

## Environment Variable Mapping

| Config Key | Environment Variable | Source |
|------------|---------------------|--------|
| subscription_id | VITE_AZURE_SUBSCRIPTION_ID | Azure CLI / config.toml |
| tenant_id | VITE_AZURE_TENANT_ID | Azure CLI / config.toml |
| N/A | VITE_AZURE_CLIENT_ID | Manual (placeholder comment) |
| N/A | VITE_AZURE_REDIRECT_URI | Default |

## Error Handling

The module provides clear, actionable error messages:

- Azure CLI not available → Suggest authentication or config.toml
- Existing .env → Mention `force=True` flag
- Permission errors → Clear permission denied message
- Invalid formats → Validation error with details

## Testing

See `tests/unit/test_pwa_config_generator.py` and `tests/integration/test_pwa_config_integration.py` for comprehensive test coverage.

## Philosophy Compliance

- ✅ Ruthless simplicity: Standard library only (subprocess, json, pathlib)
- ✅ Zero-BS implementation: Every function works, no stubs
- ✅ Self-contained module: No external dependencies
- ✅ Clear public API via `__all__`
- ✅ Regeneratable from this specification
