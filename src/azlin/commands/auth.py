"""Authentication management CLI commands.

This module provides commands for managing Azure authentication profiles:
- Create and configure authentication profiles
- Test authentication with different methods
- List and manage profiles
- Show profile details

Commands:
    azlin auth setup    - Interactive setup wizard for creating profiles
    azlin auth test     - Test authentication with a profile
    azlin auth list     - List all configured profiles
    azlin auth delete   - Delete an authentication profile
    azlin auth show     - Show profile details (redacts secrets)

Philosophy:
- Ruthless simplicity: straightforward Click commands
- Self-contained module: isolated command group
- Quality over speed: user-friendly prompts
- Fail fast: validate before saving
"""

import logging
import sys

import click

from azlin.auth_resolver import AuthResolver, AuthResolverError
from azlin.config_auth import AuthConfig, load_auth_config
from azlin.profile_manager import ProfileError, ProfileManager

logger = logging.getLogger(__name__)


@click.group(name="auth")
def auth_group():
    """Manage Azure authentication profiles.

    Create and manage authentication profiles for different Azure environments.
    Supports multiple authentication methods including Azure CLI, service
    principals, and managed identities.

    \b
    COMMANDS:
        setup     Interactive setup wizard
        test      Test authentication
        list      List all profiles
        delete    Delete a profile
        show      Show profile details

    \b
    EXAMPLES:
        # Create new profile
        $ azlin auth setup

        # Test authentication
        $ azlin auth test --profile production

        # List all profiles
        $ azlin auth list

        # Show profile details
        $ azlin auth show --profile production

        # Delete profile
        $ azlin auth delete old-profile
    """
    pass


@auth_group.command(name="setup")
@click.option("--profile", help="Profile name (skips prompt)")
def setup_command(profile: str | None):
    """Interactive setup wizard for creating authentication profiles.

    Guides you through creating a new authentication profile with prompts
    for authentication method and required configuration. Profiles are saved
    to ~/.azlin/profiles/<profile_name>.toml

    \b
    Authentication Methods:
      1. Azure CLI (default) - Uses 'az login' credentials
      2. Service Principal + Secret - Client ID and secret
      3. Service Principal + Certificate - Client ID and certificate file
      4. Managed Identity - For Azure VMs and services

    \b
    Security:
      - Secrets NEVER stored in profile files
      - Client secrets MUST be in AZURE_CLIENT_SECRET environment variable
      - Profile files created with 0600 permissions (owner-only access)

    \b
    Examples:
      $ azlin auth setup
      $ azlin auth setup --profile production
    """
    try:
        click.echo("Azure Authentication Profile Setup")
        click.echo("=" * 80)
        click.echo()

        # Display authentication method menu
        click.echo("Choose authentication method:")
        click.echo("  1. Azure CLI (default)")
        click.echo("  2. Service principal with client secret")
        click.echo("  3. Service principal with certificate")
        click.echo("  4. Managed identity")
        click.echo()

        # Get authentication method
        method_choice = click.prompt(
            "Selection",
            type=click.IntRange(1, 4),
            default=1,
        )

        # Map choice to auth method
        method_map = {
            1: "az_cli",
            2: "service_principal_secret",
            3: "service_principal_cert",
            4: "managed_identity",
        }
        auth_method = method_map[method_choice]

        click.echo()

        # Collect configuration based on auth method
        tenant_id = None
        client_id = None
        client_certificate_path = None
        subscription_id = None

        if auth_method == "az_cli":
            # Azure CLI doesn't need additional config
            click.echo("Using Azure CLI authentication.")
            click.echo("Ensure you are logged in with: az login")

        elif auth_method == "service_principal_secret":
            click.echo("Service Principal with Client Secret")
            click.echo("-" * 40)
            tenant_id = click.prompt("Enter tenant ID (UUID)", type=str)
            client_id = click.prompt("Enter client ID (UUID)", type=str)
            subscription_id = click.prompt(
                "Enter subscription ID (UUID)",
                type=str,
                default="",
                show_default=False,
            )
            if not subscription_id:
                subscription_id = None

        elif auth_method == "service_principal_cert":
            click.echo("Service Principal with Certificate")
            click.echo("-" * 40)
            tenant_id = click.prompt("Enter tenant ID (UUID)", type=str)
            client_id = click.prompt("Enter client ID (UUID)", type=str)
            client_certificate_path = click.prompt(
                "Enter certificate file path",
                type=str,
            )
            subscription_id = click.prompt(
                "Enter subscription ID (UUID)",
                type=str,
                default="",
                show_default=False,
            )
            if not subscription_id:
                subscription_id = None

        elif auth_method == "managed_identity":
            click.echo("Managed Identity")
            click.echo("-" * 40)
            click.echo("Leave client ID empty for system-assigned managed identity.")
            client_id = click.prompt(
                "Enter client ID (UUID) for user-assigned MI",
                type=str,
                default="",
                show_default=False,
            )
            if not client_id:
                client_id = None
            subscription_id = click.prompt(
                "Enter subscription ID (UUID)",
                type=str,
                default="",
                show_default=False,
            )
            if not subscription_id:
                subscription_id = None

        click.echo()

        # Get profile name (if not provided via flag)
        if not profile:
            profile = click.prompt("Profile name", default="default", type=str)

        # Create AuthConfig
        config = AuthConfig(
            auth_method=auth_method,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=None,  # Never prompt for secrets
            client_certificate_path=client_certificate_path,
            subscription_id=subscription_id,
        )

        # Create profile
        manager = ProfileManager()
        assert profile is not None  # Type narrowing for mypy
        manager.create_profile(profile, config)

        # Success message
        click.echo()
        click.echo(f"✓ Profile '{profile}' created")
        click.echo()

        # Show additional instructions based on auth method
        if auth_method == "service_principal_secret":
            click.echo("Note: Set AZURE_CLIENT_SECRET environment variable to use this profile")
        elif auth_method == "service_principal_cert":
            click.echo(f"Note: Ensure certificate file is accessible at: {client_certificate_path}")
        elif auth_method == "managed_identity":
            click.echo(
                "Note: This profile will only work on Azure resources with managed identity enabled"
            )

        click.echo()
        click.echo(f"To test: azlin auth test --profile {profile}")

    except ProfileError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except click.Abort:
        click.echo("\nSetup cancelled.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error creating profile: {e}", err=True)
        logger.exception("Unexpected error in auth setup")
        sys.exit(1)


@auth_group.command(name="test")
@click.option("--profile", help="Profile name to test")
def test_command(profile: str | None):
    """Test authentication with profile or current configuration.

    Attempts to authenticate with Azure using the specified profile or
    default configuration. Reports success or failure with details about
    the authentication method and credentials.

    \b
    Examples:
      $ azlin auth test
      $ azlin auth test --profile production
    """
    try:
        click.echo("Testing Azure authentication...")
        click.echo()

        # Load configuration
        if profile:
            click.echo(f"Using profile: {profile}")
            manager = ProfileManager()
            config = manager.get_profile(profile)
        else:
            click.echo("Using default configuration")
            config = load_auth_config()

        click.echo(f"Method: {config.auth_method}")
        click.echo()

        # Create resolver and test credentials
        resolver = AuthResolver(config)
        creds = resolver.resolve_credentials()

        # Success
        click.echo("✓ Authentication successful")
        click.echo()
        click.echo("Credentials:")
        click.echo(f"  Method: {creds.method}")
        if creds.tenant_id:
            click.echo(f"  Tenant ID: {creds.tenant_id}")
        if creds.subscription_id:
            click.echo(f"  Subscription ID: {creds.subscription_id}")
        click.echo()

    except ProfileError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except AuthResolverError as e:
        click.echo(f"Authentication failed: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error testing authentication: {e}", err=True)
        logger.exception("Unexpected error in auth test")
        sys.exit(1)


@auth_group.command(name="list")
def list_command():
    """List all configured authentication profiles.

    Shows all profiles in ~/.azlin/profiles/ with their authentication
    method, created date, and last used date.

    \b
    Examples:
      $ azlin auth list
    """
    try:
        manager = ProfileManager()
        profiles = manager.list_profiles()

        if not profiles:
            click.echo("No authentication profiles found.")
            click.echo()
            click.echo("Create a profile with: azlin auth setup")
            return

        click.echo()
        click.echo("Authentication Profiles")
        click.echo("=" * 80)
        click.echo()

        for profile in profiles:
            click.echo(f"{profile.name}")
            click.echo(f"  Method: {profile.auth_method}")

            if profile.tenant_id:
                click.echo(f"  Tenant ID: {profile.tenant_id}")
            if profile.client_id:
                click.echo(f"  Client ID: {profile.client_id}")
            if profile.subscription_id:
                click.echo(f"  Subscription ID: {profile.subscription_id}")

            # Format timestamps
            created = profile.created_at.strftime("%Y-%m-%d %H:%M:%S")
            click.echo(f"  Created: {created}")

            if profile.last_used:
                last_used = profile.last_used.strftime("%Y-%m-%d %H:%M:%S")
                click.echo(f"  Last Used: {last_used}")
            else:
                click.echo("  Last Used: Never")

            click.echo()

        click.echo(f"Total: {len(profiles)} profile(s)")

    except Exception as e:
        click.echo(f"Error listing profiles: {e}", err=True)
        logger.exception("Unexpected error in auth list")
        sys.exit(1)


@auth_group.command(name="delete")
@click.argument("profile_name", type=str)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def delete_command(profile_name: str, force: bool):
    """Delete an authentication profile.

    Deletes the specified profile from ~/.azlin/profiles/. By default,
    prompts for confirmation before deletion.

    \b
    Examples:
      $ azlin auth delete old-profile
      $ azlin auth delete test-profile --force
    """
    try:
        manager = ProfileManager()

        # Confirm deletion unless --force
        if not force:
            click.echo(f"Delete profile '{profile_name}'?")
            if not click.confirm("Are you sure?"):
                click.echo("Cancelled.")
                return

        # Delete profile
        deleted = manager.delete_profile(profile_name)

        if not deleted:
            click.echo(f"Error: Profile '{profile_name}' not found", err=True)
            sys.exit(1)

        click.echo(f"✓ Profile '{profile_name}' deleted successfully")

    except ProfileError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error deleting profile: {e}", err=True)
        logger.exception("Unexpected error in auth delete")
        sys.exit(1)


@auth_group.command(name="show")
@click.option("--profile", default="default", help="Profile name to show")
def show_command(profile: str):
    """Show profile configuration details (secrets redacted).

    Displays the configuration for the specified profile. Secrets like
    client_secret are never shown (they should be in environment variables).

    \b
    Examples:
      $ azlin auth show
      $ azlin auth show --profile production
    """
    try:
        manager = ProfileManager()
        config = manager.get_profile(profile)

        click.echo()
        click.echo(f"Profile: {profile}")
        click.echo("=" * 80)
        click.echo()
        click.echo(f"Authentication Method: {config.auth_method}")
        click.echo()

        # Display configuration (redact secrets)
        click.echo("Configuration:")

        if config.tenant_id:
            click.echo(f"  Tenant ID: {config.tenant_id}")
        if config.client_id:
            click.echo(f"  Client ID: {config.client_id}")
        if config.subscription_id:
            click.echo(f"  Subscription ID: {config.subscription_id}")

        if config.client_certificate_path:
            click.echo(f"  Certificate Path: {config.client_certificate_path}")

        # Never show client_secret, but indicate if it should be set
        if config.auth_method == "service_principal_secret":
            click.echo("  Client Secret: (from AZURE_CLIENT_SECRET environment variable)")

        click.echo()

        # Additional notes
        if config.auth_method == "az_cli":
            click.echo("Note: This profile uses Azure CLI credentials (az login)")
        elif config.auth_method == "service_principal_secret":
            click.echo("Note: Set AZURE_CLIENT_SECRET environment variable before use")
        elif config.auth_method == "service_principal_cert":
            click.echo("Note: Ensure certificate file is accessible and has correct permissions")
        elif config.auth_method == "managed_identity":
            click.echo(
                "Note: This profile only works on Azure resources with managed identity enabled"
            )

    except ProfileError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error showing profile: {e}", err=True)
        logger.exception("Unexpected error in auth show")
        sys.exit(1)


__all__ = ["auth_group"]
