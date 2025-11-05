"""Auth command group for azlin.

This module provides CLI commands for managing service principal authentication:
- setup: Interactive setup wizard for service principal profiles
- test: Test authentication with a profile
- list: List available authentication profiles
- show: Show profile details
- remove: Remove authentication profile

Security:
- No secrets stored in config files
- Credentials from environment variables only
- Proper permission validation
"""

import logging
import os
import sys
from pathlib import Path

import click

# TOML library imports (Python 3.11+ compatibility)
try:
    import tomli  # type: ignore[import]
except ImportError:
    try:
        import tomllib as tomli  # type: ignore[import]
    except ImportError as e:
        raise ImportError(
            "toml library not available. Install with: pip install tomli tomli-w"
        ) from e

try:
    import tomli_w  # type: ignore[import]
except ImportError as e:
    raise ImportError("tomli-w library not available. Install with: pip install tomli-w") from e

from azlin.click_group import AzlinGroup
from azlin.config_manager import ConfigError, ConfigManager
from azlin.service_principal_auth import (
    ServicePrincipalConfig,
    ServicePrincipalError,
    ServicePrincipalManager,
)

logger = logging.getLogger(__name__)


@click.group(name="auth", cls=AzlinGroup)
def auth():
    """Manage service principal authentication profiles.

    Service principals enable automated Azure authentication without
    interactive login. Use these commands to set up and manage
    authentication profiles.

    \b
    EXAMPLES:
        # Set up a new profile
        $ azlin auth setup --profile production

        # Test authentication
        $ azlin auth test --profile production

        # List all profiles
        $ azlin auth list

        # Show profile details
        $ azlin auth show production

        # Remove a profile
        $ azlin auth remove production
    """
    pass


@auth.command()
@click.option("--profile", "-p", default="default", help="Profile name")
@click.option("--tenant-id", help="Azure Tenant ID")
@click.option("--client-id", help="Azure Client ID / Application ID")
@click.option("--subscription-id", help="Azure Subscription ID")
@click.option(
    "--use-certificate",
    is_flag=True,
    help="Use certificate-based auth (otherwise client secret)",
)
@click.option(
    "--certificate-path",
    type=click.Path(exists=True),
    help="Path to certificate file (for cert-based auth)",
)
def setup(
    profile: str,
    tenant_id: str | None,
    client_id: str | None,
    subscription_id: str | None,
    use_certificate: bool,
    certificate_path: str | None,
):
    """Set up service principal authentication profile.

    Creates a new authentication profile for service principal authentication.
    You can have multiple profiles for different environments (dev, prod, etc).

    \b
    REQUIRED:
        - Tenant ID
        - Client ID
        - Subscription ID
        - Auth method: certificate OR client secret (from env var)

    \b
    EXAMPLES:
        # Interactive setup
        $ azlin auth setup

        # Non-interactive with client secret
        $ azlin auth setup --profile prod \\
            --tenant-id "YOUR-TENANT-ID" \\
            --client-id "YOUR-CLIENT-ID" \\
            --subscription-id "YOUR-SUBSCRIPTION-ID"
        # Then set: export AZLIN_SP_CLIENT_SECRET="your-secret"

        # With certificate
        $ azlin auth setup --profile prod \\
            --tenant-id "YOUR-TENANT-ID" \\
            --client-id "YOUR-CLIENT-ID" \\
            --subscription-id "YOUR-SUBSCRIPTION-ID" \\
            --use-certificate \\
            --certificate-path ~/certs/sp-cert.pem
    """
    try:
        # Interactive prompts for missing values
        if not tenant_id:
            tenant_id = click.prompt("Azure Tenant ID", type=str)

        if not client_id:
            client_id = click.prompt("Azure Client ID / Application ID", type=str)

        if not subscription_id:
            subscription_id = click.prompt("Azure Subscription ID", type=str)

        # Validate all required IDs were provided
        if not tenant_id:
            raise ConfigError("Tenant ID is required but was not provided")
        if not client_id:
            raise ConfigError("Client ID is required but was not provided")
        if not subscription_id:
            raise ConfigError("Subscription ID is required but was not provided")

        # Ask about auth method if not specified
        if not use_certificate and not certificate_path:
            use_certificate = click.confirm(
                "Use certificate-based authentication? (otherwise client secret)", default=False
            )

        if use_certificate and not certificate_path:
            certificate_path = click.prompt(
                "Path to certificate file", type=click.Path(exists=True)
            )

        # Determine auth method
        auth_method = "certificate" if use_certificate or certificate_path else "client_secret"

        # Validate certificate if provided
        cert_path_obj = None
        if certificate_path:
            cert_path_obj = Path(certificate_path)
            click.echo(f"\nValidating certificate: {cert_path_obj}")
            try:
                ServicePrincipalManager.validate_certificate(cert_path_obj, auto_fix=True)
                click.echo(click.style("✓ Certificate is valid", fg="green"))
            except ServicePrincipalError as e:
                click.echo(click.style(f"✗ Certificate validation failed: {e}", fg="red"))
                sys.exit(1)

        # Create config
        config = ServicePrincipalConfig(
            client_id=client_id,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            auth_method=auth_method,
            certificate_path=cert_path_obj,
        )

        # Validate config
        ServicePrincipalManager.validate_config(config)

        # Save to config manager
        config_manager = ConfigManager()
        profile_config = config.to_dict(include_secret=False)

        # Use ConfigManager to store profile
        try:
            azlin_config = ConfigManager.load_config()
        except ConfigError:
            from azlin.config_manager import AzlinConfig

            azlin_config = AzlinConfig()

        # Add auth profile to config
        if not hasattr(azlin_config, "auth_profiles"):
            # Store in config dict manually since AzlinConfig doesn't have auth_profiles yet
            config_path = ConfigManager.get_config_path()

            # Load raw TOML

            if config_path.exists():
                with open(config_path, "rb") as f:
                    data = tomli.load(f)
            else:
                data = {}

            # Add auth section
            if "auth" not in data:
                data["auth"] = {}
            if "profiles" not in data["auth"]:
                data["auth"]["profiles"] = {}

            data["auth"]["profiles"][profile] = profile_config

            # Save
            ConfigManager.ensure_config_dir()
            temp_path = config_path.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                tomli_w.dump(data, f)
            os.chmod(temp_path, 0o600)
            temp_path.replace(config_path)

        click.echo(click.style(f"\n✓ Profile '{profile}' saved successfully!", fg="green"))

        # Show next steps
        click.echo("\nNext steps:")
        if auth_method == "client_secret":
            click.echo("1. Set your client secret:")
            click.echo("   export AZLIN_SP_CLIENT_SECRET='your-secret-here'")
            click.echo("2. Test authentication:")
            click.echo(f"   azlin auth test --profile {profile}")
        else:
            click.echo("1. Test authentication:")
            click.echo(f"   azlin auth test --profile {profile}")

        click.echo("\n3. Use the profile with azlin commands:")
        click.echo(f"   azlin --auth-profile {profile} list")

    except (ServicePrincipalError, ConfigError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during auth setup")
        click.echo(click.style(f"Unexpected error: {e}", fg="red"))
        sys.exit(1)


@auth.command()
@click.option("--profile", "-p", default="default", help="Profile name")
@click.option("--subscription-id", help="Test specific subscription access")
def test(profile: str, subscription_id: str | None):
    """Test service principal authentication.

    Validates that the authentication profile works correctly by attempting
    to authenticate and optionally test subscription access.

    \b
    EXAMPLES:
        # Test default profile
        $ azlin auth test

        # Test specific profile
        $ azlin auth test --profile production

        # Test with subscription validation
        $ azlin auth test --profile prod --subscription-id "YOUR-SUB-ID"
    """
    try:
        click.echo(f"Testing authentication profile: {profile}")

        # Load profile config
        config_path = ConfigManager.get_config_path()

        if not config_path.exists():
            click.echo(
                click.style("Error: No profiles found. Run 'azlin auth setup' first.", fg="red")
            )
            sys.exit(1)

        # Load TOML
        with open(config_path, "rb") as f:
            data = tomli.load(f)

        # Check if auth section exists
        if "auth" not in data or "profiles" not in data["auth"]:
            click.echo(
                click.style("Error: No profiles found. Run 'azlin auth setup' first.", fg="red")
            )
            sys.exit(1)

        profiles = data["auth"]["profiles"]
        if profile not in profiles:
            click.echo(click.style(f"Error: Profile '{profile}' not found.", fg="red"))
            click.echo(f"\nAvailable profiles: {', '.join(profiles.keys())}")
            sys.exit(1)

        profile_data = profiles[profile]

        # Create config
        sp_config = ServicePrincipalConfig.from_dict(profile_data)

        click.echo("\nProfile details:")
        click.echo(f"  Client ID: {sp_config.client_id}")
        click.echo(f"  Tenant ID: {sp_config.tenant_id}")
        click.echo(f"  Subscription ID: {sp_config.subscription_id}")
        click.echo(f"  Auth method: {sp_config.auth_method}")

        if sp_config.certificate_path:
            click.echo(f"  Certificate: {sp_config.certificate_path}")

        # Get credentials
        click.echo("\nValidating credentials...")
        try:
            creds = ServicePrincipalManager.get_credentials(sp_config)
            click.echo(click.style("✓ Credentials valid", fg="green"))
        except ServicePrincipalError as e:
            click.echo(click.style(f"✗ Credential validation failed: {e}", fg="red"))
            sys.exit(1)

        # Test authentication with Azure
        click.echo("\nTesting Azure authentication...")

        # Set credentials in environment temporarily
        import subprocess

        env = os.environ.copy()
        env.update(creds)

        # Try to get account info
        try:
            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )

            if result.returncode == 0:
                import json

                account_info = json.loads(result.stdout)
                click.echo(click.style("✓ Authentication successful!", fg="green"))
                click.echo("\n  Authenticated as:")
                click.echo(f"    Tenant: {account_info.get('tenantId', 'N/A')}")
                click.echo(f"    Subscription: {account_info.get('name', 'N/A')}")
                click.echo(f"    ID: {account_info.get('id', 'N/A')}")
            else:
                click.echo(click.style("✗ Authentication failed", fg="red"))
                click.echo(f"Error: {result.stderr}")
                sys.exit(1)

        except subprocess.TimeoutExpired:
            click.echo(click.style("✗ Authentication timed out", fg="yellow"))
            click.echo("The Azure CLI command timed out. This might be a network issue.")
            sys.exit(1)
        except FileNotFoundError:
            click.echo(click.style("✗ Azure CLI not found", fg="red"))
            click.echo(
                "Please install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
            )
            sys.exit(1)

    except (ServicePrincipalError, ConfigError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during auth test")
        click.echo(click.style(f"Unexpected error: {e}", fg="red"))
        sys.exit(1)


@auth.command(name="list")
def list_profiles():
    """List available authentication profiles.

    Shows all configured service principal profiles with their details.
    Secrets and sensitive information are masked.

    \b
    EXAMPLES:
        $ azlin auth list
    """
    try:
        config_path = ConfigManager.get_config_path()

        if not config_path.exists():
            click.echo("No authentication profiles found.")
            click.echo("\nCreate one with: azlin auth setup")
            return

        # Load TOML
        with open(config_path, "rb") as f:
            data = tomli.load(f)

        # Check if auth section exists
        if "auth" not in data or "profiles" not in data["auth"]:
            click.echo("No authentication profiles found.")
            click.echo("\nCreate one with: azlin auth setup")
            return

        profiles = data["auth"]["profiles"]

        if not profiles:
            click.echo("No authentication profiles found.")
            click.echo("\nCreate one with: azlin auth setup")
            return

        click.echo(f"\nAuthentication Profiles ({len(profiles)}):\n")

        for name, profile_data in profiles.items():
            click.echo(click.style(f"  {name}", bold=True))
            click.echo(f"    Client ID: {profile_data.get('client_id', 'N/A')[:8]}...")
            click.echo(f"    Tenant ID: {profile_data.get('tenant_id', 'N/A')[:8]}...")
            click.echo(f"    Auth method: {profile_data.get('auth_method', 'N/A')}")

            if profile_data.get("certificate_path"):
                click.echo(f"    Certificate: {profile_data['certificate_path']}")

            click.echo()

        click.echo("Use 'azlin auth show <profile>' for full details")

    except Exception as e:
        logger.exception("Error listing profiles")
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)


@auth.command()
@click.argument("profile")
def show(profile: str):
    """Show authentication profile details.

    Displays complete information about a specific profile.
    Secrets are masked for security.

    \b
    EXAMPLES:
        $ azlin auth show default
        $ azlin auth show production
    """
    try:
        config_path = ConfigManager.get_config_path()

        if not config_path.exists():
            click.echo(click.style("Error: No profiles found.", fg="red"))
            sys.exit(1)

        # Load TOML
        with open(config_path, "rb") as f:
            data = tomli.load(f)

        # Check if auth section exists
        if "auth" not in data or "profiles" not in data["auth"]:
            click.echo(click.style("Error: No profiles found.", fg="red"))
            sys.exit(1)

        profiles = data["auth"]["profiles"]
        if profile not in profiles:
            click.echo(click.style(f"Error: Profile '{profile}' not found.", fg="red"))
            click.echo(f"\nAvailable profiles: {', '.join(profiles.keys())}")
            sys.exit(1)

        profile_data = profiles[profile]

        click.echo(click.style(f"\nProfile: {profile}", bold=True))
        click.echo(f"\n  Client ID: {profile_data.get('client_id', 'N/A')}")
        click.echo(f"  Tenant ID: {profile_data.get('tenant_id', 'N/A')}")
        click.echo(f"  Subscription ID: {profile_data.get('subscription_id', 'N/A')}")
        click.echo(f"  Auth method: {profile_data.get('auth_method', 'N/A')}")

        if profile_data.get("certificate_path"):
            cert_path = Path(profile_data["certificate_path"])
            click.echo(f"  Certificate path: {cert_path}")

            # Validate certificate
            if cert_path.exists():
                try:
                    ServicePrincipalManager.validate_certificate(cert_path)
                    click.echo(click.style("  Certificate status: Valid ✓", fg="green"))
                except ServicePrincipalError as e:
                    click.echo(click.style(f"  Certificate status: Invalid - {e}", fg="red"))
            else:
                click.echo(click.style("  Certificate status: File not found", fg="red"))

        click.echo(f"\n  Config location: {config_path}")

    except Exception as e:
        logger.exception("Error showing profile")
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)


@auth.command()
@click.argument("profile")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def remove(profile: str, yes: bool):
    """Remove authentication profile.

    Deletes the specified authentication profile from configuration.
    This does not affect the actual service principal in Azure.

    \b
    EXAMPLES:
        $ azlin auth remove old-profile
        $ azlin auth remove staging --yes
    """
    try:
        config_path = ConfigManager.get_config_path()

        if not config_path.exists():
            click.echo(click.style("Error: No profiles found.", fg="red"))
            sys.exit(1)

        # Load TOML

        with open(config_path, "rb") as f:
            data = tomli.load(f)

        # Check if auth section exists
        if "auth" not in data or "profiles" not in data["auth"]:
            click.echo(click.style("Error: No profiles found.", fg="red"))
            sys.exit(1)

        profiles = data["auth"]["profiles"]
        if profile not in profiles:
            click.echo(click.style(f"Error: Profile '{profile}' not found.", fg="red"))
            click.echo(f"\nAvailable profiles: {', '.join(profiles.keys())}")
            sys.exit(1)

        # Confirm deletion
        if not yes:
            click.echo(f"\nProfile '{profile}' will be removed.")
            click.echo(
                "This will delete the profile configuration (not the Azure service principal)."
            )

            if not click.confirm("\nAre you sure?", default=False):
                click.echo("Cancelled.")
                return

        # Remove profile
        del profiles[profile]

        # Save
        temp_path = config_path.with_suffix(".tmp")
        with open(temp_path, "wb") as f:
            tomli_w.dump(data, f)
        os.chmod(temp_path, 0o600)
        temp_path.replace(config_path)

        click.echo(click.style(f"\n✓ Profile '{profile}' removed successfully!", fg="green"))

        if profiles:
            click.echo(f"\nRemaining profiles: {', '.join(profiles.keys())}")
        else:
            click.echo("\nNo profiles remaining. Create one with: azlin auth setup")

    except Exception as e:
        logger.exception("Error removing profile")
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)
