# Brick 4: CLI Auth Decorator - Integration Guide

## Overview

Brick 4 (`cli_auth.py`) provides CLI argument parsing and authentication context injection for Azure authentication. It enables zero-breaking-change integration of service principal authentication into existing Click-based CLI commands.

## Quick Start

### Basic Integration Pattern

```python
import click
from azlin.cli_auth import auth_options, get_auth_resolver

@click.command()
@auth_options  # Add authentication options
def list_vms(**kwargs):
    """List VMs with optional authentication."""
    # Get configured resolver
    resolver = get_auth_resolver(
        profile=kwargs.get('profile'),
        tenant_id=kwargs.get('tenant_id'),
        client_id=kwargs.get('client_id'),
        client_certificate_path=kwargs.get('client_certificate_path'),
        subscription_id=kwargs.get('subscription_id'),
        auth_method=kwargs.get('auth_method'),
    )

    # Use resolver to get credentials
    credentials = resolver.resolve_credentials()

    # Your existing VM listing logic here
    subscription_id = resolver.get_subscription_id()
    # ... use credentials and subscription_id
```

### Command Line Usage

```bash
# Use default az_cli authentication (backward compatible)
$ azlin list

# Use a profile
$ azlin list --profile production

# Use service principal with secret
$ azlin list \
    --auth-method service_principal_secret \
    --tenant-id 12345678-1234-1234-1234-123456789abc \
    --client-id 87654321-4321-4321-4321-cba987654321 \
    --client-secret

# Use service principal with certificate
$ azlin list \
    --auth-method service_principal_cert \
    --tenant-id 12345678-1234-1234-1234-123456789abc \
    --client-id 87654321-4321-4321-4321-cba987654321 \
    --client-certificate-path ~/.azure/cert.pem

# Override profile with CLI args
$ azlin list --profile production --subscription-id override-sub-id
```

## Available CLI Options

When you use `@auth_options`, these options are added to your command:

- `--profile TEXT`: Authentication profile name from `~/.azlin/auth_profiles.toml`
- `--tenant-id TEXT`: Azure tenant ID (UUID format)
- `--client-id TEXT`: Azure client/application ID (UUID format)
- `--client-secret`: Flag to use `AZURE_CLIENT_SECRET` environment variable
- `--client-certificate-path TEXT`: Path to client certificate file (.pem)
- `--subscription-id TEXT`: Azure subscription ID (UUID format)
- `--auth-method TEXT`: Authentication method (az_cli, service_principal_secret, service_principal_cert, managed_identity)

## Configuration Priority

CLI arguments have **lowest priority** in the configuration chain:

1. **Environment variables** (highest priority)
2. **Profile config file** (`~/.azlin/auth_profiles.toml`)
3. **CLI arguments** (lowest priority - this module)
4. **Defaults** (az_cli method)

This ensures existing environment-based configurations continue to work.

## Integration Examples

### Example 1: Retrofit Existing Command

**Before (existing code):**
```python
@click.command()
def create_vm(name: str):
    """Create a new VM."""
    # Uses default Azure CLI auth
    vm_manager = VMManager()
    vm_manager.create(name)
```

**After (with auth options):**
```python
@click.command()
@auth_options  # Add this line
def create_vm(name: str, **kwargs):  # Add **kwargs
    """Create a new VM."""
    # Get resolver from CLI args
    resolver = get_auth_resolver(
        profile=kwargs.get('profile'),
        tenant_id=kwargs.get('tenant_id'),
        client_id=kwargs.get('client_id'),
        subscription_id=kwargs.get('subscription_id'),
        auth_method=kwargs.get('auth_method'),
    )

    # Use resolver for authentication
    credentials = resolver.resolve_credentials()

    vm_manager = VMManager(credentials=credentials)
    vm_manager.create(name)
```

### Example 2: Storage Command Integration

```python
import click
from azlin.cli_auth import auth_options, get_auth_resolver
from azlin.modules.storage_manager import StorageManager

@click.command()
@click.argument("name", type=str)
@click.option("--size", type=int, default=100)
@auth_options  # Add auth options
def create_storage(name: str, size: int, **kwargs):
    """Create Azure Files NFS storage account."""
    # Get auth resolver
    resolver = get_auth_resolver(
        profile=kwargs.get('profile'),
        tenant_id=kwargs.get('tenant_id'),
        client_id=kwargs.get('client_id'),
        subscription_id=kwargs.get('subscription_id'),
        auth_method=kwargs.get('auth_method'),
    )

    # Get credentials and subscription
    credentials = resolver.resolve_credentials()
    subscription_id = resolver.get_subscription_id()

    # Create storage with authenticated credentials
    result = StorageManager.create_storage(
        name=name,
        size_gb=size,
        credentials=credentials,
        subscription_id=subscription_id,
    )

    click.echo(f"Created storage: {result.name}")
```

### Example 3: Automated CI/CD Integration

```python
# In your CI/CD pipeline script
import click
from azlin.cli_auth import auth_options, get_auth_resolver

@click.command()
@auth_options
def deploy_infrastructure(**kwargs):
    """Deploy infrastructure using service principal."""
    # In CI/CD, use environment variables:
    # AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
    # AZURE_SUBSCRIPTION_ID, AZURE_AUTH_METHOD=service_principal_secret

    resolver = get_auth_resolver(
        # CLI args are optional - env vars take priority
        auth_method=kwargs.get('auth_method'),
    )

    # Validate credentials work
    if not resolver.validate_credentials():
        click.echo("ERROR: Invalid credentials", err=True)
        raise SystemExit(1)

    credentials = resolver.resolve_credentials()
    # Deploy infrastructure...
```

## Security Best Practices

### 1. Never Prompt for Secrets
```python
# ❌ WRONG - Don't do this
@click.option("--client-secret", prompt=True, hide_input=True)

# ✅ CORRECT - Use flag + environment variable
@auth_options
def my_command(**kwargs):
    # --client-secret flag indicates to use AZURE_CLIENT_SECRET env var
    pass
```

### 2. Use Environment Variables for Secrets
```bash
# Set secret in environment
export AZURE_CLIENT_SECRET="your-secret-here"

# Use flag to indicate "use environment variable"
azlin list --client-secret --auth-method service_principal_secret
```

### 3. Use Profiles for Team Configurations
```toml
# ~/.azlin/auth_profiles.toml
[profiles.production]
auth_method = "service_principal_secret"
tenant_id = "12345678-1234-1234-1234-123456789abc"
client_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "abcdef01-2345-6789-abcd-ef0123456789"
# Note: NO client_secret in file - only in environment!

[profiles.staging]
auth_method = "service_principal_cert"
tenant_id = "staging-tenant-id"
client_id = "staging-client-id"
client_certificate_path = "~/.azure/staging-cert.pem"
subscription_id = "staging-subscription-id"
```

```bash
# Use profile in CLI
azlin list --profile production
```

## Helper Function Pattern

For cleaner code, create a helper function:

```python
from azlin.cli_auth import get_auth_resolver

def resolve_auth_from_kwargs(**kwargs):
    """Extract auth parameters from kwargs and return resolver."""
    return get_auth_resolver(
        profile=kwargs.get('profile'),
        tenant_id=kwargs.get('tenant_id'),
        client_id=kwargs.get('client_id'),
        client_certificate_path=kwargs.get('client_certificate_path'),
        subscription_id=kwargs.get('subscription_id'),
        auth_method=kwargs.get('auth_method'),
    )

# Use in commands
@click.command()
@auth_options
def my_command(**kwargs):
    resolver = resolve_auth_from_kwargs(**kwargs)
    credentials = resolver.resolve_credentials()
    # ... rest of logic
```

## Testing with Auth Options

```python
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

def test_command_with_auth():
    """Test command with auth options."""
    from azlin.config_auth import AuthConfig

    @click.command()
    @auth_options
    def test_cmd(**kwargs):
        resolver = get_auth_resolver(**kwargs)
        click.echo(f"Method: {resolver.config.auth_method}")

    with patch('azlin.cli_auth.load_auth_config') as mock_load:
        mock_load.return_value = AuthConfig(auth_method="az_cli")

        runner = CliRunner()
        result = runner.invoke(test_cmd, ['--auth-method', 'az_cli'])

        assert result.exit_code == 0
        assert "Method: az_cli" in result.output
```

## Troubleshooting

### Issue: "Profile not found"
**Solution**: Create `~/.azlin/auth_profiles.toml` or use CLI args/env vars instead.

### Issue: "client_secret is required"
**Solution**: Set `AZURE_CLIENT_SECRET` environment variable when using service principal auth.

### Issue: CLI args not taking effect
**Solution**: Check priority order - environment variables override CLI args.

### Issue: Certificate file not found
**Solution**: Use absolute path or `~` for home directory: `--client-certificate-path ~/.azure/cert.pem`

## Design Decisions

### Why Flag for client_secret?
Security: We never want to accept secrets as command-line arguments (visible in process list). The `--client-secret` flag is just a marker that says "use the environment variable."

### Why Optional Everything?
Backward compatibility: Existing commands must work without any auth options. All auth options are optional to ensure zero breaking changes.

### Why Lowest Priority for CLI?
Predictability: Environment variables should always win (CI/CD standard). This prevents accidental override of production env vars.

### Why No Direct AuthConfig Return?
Encapsulation: `get_auth_resolver()` returns `AuthResolver` (Brick 2) which provides a clean, high-level API. Users don't need to know about config internals.

## Module API Reference

### `@auth_options`
Decorator that adds authentication CLI options to Click commands.

**Usage:**
```python
@click.command()
@auth_options
def my_command(**kwargs):
    pass
```

### `get_auth_resolver(...) -> AuthResolver`
Parse CLI args and return configured AuthResolver.

**Parameters:**
- `profile`: Profile name (str | None)
- `tenant_id`: Tenant ID (str | None)
- `client_id`: Client ID (str | None)
- `client_secret`: Use env var flag (bool | None)
- `client_certificate_path`: Cert path (str | None)
- `subscription_id`: Subscription ID (str | None)
- `auth_method`: Auth method (str | None)

**Returns:** `AuthResolver` instance

**Raises:** `AuthConfigError` if configuration is invalid

## Next Steps

1. **Apply to existing commands**: Add `@auth_options` to CLI commands that need auth
2. **Update documentation**: Document auth options in command help text
3. **Create profiles**: Set up team profiles in `~/.azlin/auth_profiles.toml`
4. **Test in CI/CD**: Verify service principal auth works in automated pipelines

## See Also

- **Brick 1** (`config_auth.py`): Configuration loading and merging
- **Brick 2** (`auth_resolver.py`): Credential resolution
- **Brick 7** (`auth_security.py`): Security controls and validation
