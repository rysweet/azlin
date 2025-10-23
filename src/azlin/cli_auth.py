"""CLI authentication decorator module (Brick 4).

This module provides CLI argument parsing and authentication context injection
for Azure authentication. It integrates Click options with the authentication
configuration system to enable flexible authentication from the command line.

Responsibility: CLI argument parsing and auth context injection

Public API:
- auth_options: Decorator to add authentication CLI options to Click commands
- get_auth_resolver: Parse CLI args and return configured AuthResolver

Design Philosophy:
- Zero breaking changes: All auth options are optional
- Ruthless simplicity: Thin wrapper around Click options
- Self-contained module: Minimal dependencies
- Quality over speed: Thorough option validation

Integration:
- Uses Brick 1 (config_auth.load_auth_config) to merge CLI args with config/env
- Returns Brick 2 (AuthResolver) ready to use

Security:
- Never prompts for secrets in CLI
- Client secret must come from stdin or env (--client-secret flag just indicates to use env var)
- All log messages sanitized via Brick 7 (auth_security)

Priority Order:
CLI arguments (this module) > Environment variables > Profile config > Defaults
"""

import logging
from typing import Any

import click

from azlin.auth_resolver import AuthResolver
from azlin.auth_security import sanitize_log
from azlin.config_auth import load_auth_config

logger = logging.getLogger(__name__)


def auth_options(func):
    """Decorator to add authentication CLI options to Click commands.

    This decorator adds optional authentication parameters to any Click command.
    All options have LOWEST priority (config/env override them as per priority chain).

    Added Options:
        --profile TEXT                  Authentication profile name
        --tenant-id TEXT                Azure tenant ID (UUID)
        --client-id TEXT                Azure client ID (UUID)
        --client-secret                 Flag to use client secret from environment
        --client-certificate-path TEXT  Path to client certificate (.pem)
        --subscription-id TEXT          Azure subscription ID (UUID)
        --auth-method TEXT              Auth method: az_cli, service_principal_secret,
                                        service_principal_cert, managed_identity

    Security:
        - All options are optional (zero breaking changes)
        - client-secret is a flag only (never prompts, actual secret from env)
        - No sensitive data logged

    Example:
        >>> @click.command()
        >>> @auth_options
        >>> def list_vms(**kwargs):
        >>>     resolver = get_auth_resolver(
        >>>         profile=kwargs.get('profile'),
        >>>         tenant_id=kwargs.get('tenant_id'),
        >>>         # ... other auth params
        >>>     )
        >>>     credentials = resolver.resolve_credentials()

    Args:
        func: Click command function to decorate

    Returns:
        Decorated function with auth options added
    """

    # Add auth method option (with choices)
    func = click.option(
        "--auth-method",
        type=click.Choice(
            [
                "az_cli",
                "service_principal_secret",
                "service_principal_cert",
                "managed_identity",
            ],
            case_sensitive=False,
        ),
        help="Authentication method: az_cli (default), service_principal_secret, "
        "service_principal_cert, or managed_identity",
    )(func)

    # Add subscription ID option
    func = click.option(
        "--subscription-id",
        type=str,
        help="Azure subscription ID (UUID format)",
    )(func)

    # Add client certificate path option
    func = click.option(
        "--client-certificate-path",
        type=str,
        help="Path to client certificate file (.pem)",
    )(func)

    # Add client secret option (FLAG ONLY - never prompt)
    # The actual secret must come from environment variable AZURE_CLIENT_SECRET
    func = click.option(
        "--client-secret",
        is_flag=True,
        default=False,
        help="Use client secret from AZURE_CLIENT_SECRET environment variable",
    )(func)

    # Add client ID option
    func = click.option(
        "--client-id",
        type=str,
        help="Azure client/application ID (UUID format)",
    )(func)

    # Add tenant ID option
    func = click.option(
        "--tenant-id",
        type=str,
        help="Azure tenant ID (UUID format)",
    )(func)

    # Add profile option (highest level grouping)
    return click.option(
        "--profile",
        type=str,
        help="Authentication profile name from ~/.azlin/auth_profiles.toml",
    )(func)


def get_auth_resolver(
    profile: str | None = None,
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: bool | None = None,
    client_certificate_path: str | None = None,
    subscription_id: str | None = None,
    auth_method: str | None = None,
) -> AuthResolver:
    """Parse CLI args and return configured AuthResolver.

    This function is the bridge between CLI arguments and the authentication system.
    It constructs the cli_args dict and delegates to Brick 1 (load_auth_config)
    to merge with config/env, then returns a Brick 2 (AuthResolver) instance.

    Priority Order (handled by load_auth_config):
        1. CLI arguments (parameters to this function)
        2. Environment variables
        3. Profile config file
        4. Defaults (az_cli method)

    Args:
        profile: Profile name to load from ~/.azlin/auth_profiles.toml
        tenant_id: Azure tenant ID (UUID format)
        client_id: Azure client/application ID (UUID format)
        client_secret: Flag indicating to use AZURE_CLIENT_SECRET env var
                      (True = use env var, False/None = don't require)
        client_certificate_path: Path to client certificate (.pem)
        subscription_id: Azure subscription ID (UUID format)
        auth_method: Authentication method (az_cli, service_principal_secret, etc.)

    Returns:
        AuthResolver instance ready to resolve credentials

    Raises:
        AuthConfigError: If configuration is invalid (raised by load_auth_config)

    Security:
        - client_secret is never the actual secret value, only a flag
        - Actual secret comes from AZURE_CLIENT_SECRET environment variable
        - All log messages are sanitized

    Example:
        >>> resolver = get_auth_resolver(
        ...     profile="production",
        ...     tenant_id="12345678-1234-1234-1234-123456789abc",
        ... )
        >>> credentials = resolver.resolve_credentials()
    """
    # Build cli_args dict from provided parameters
    # Filter out None values to avoid overriding config/env with explicit None
    cli_args: dict[str, Any] = {}

    if tenant_id is not None:
        cli_args["tenant_id"] = tenant_id

    if client_id is not None:
        cli_args["client_id"] = client_id

    # For client_secret: if flag is True, the actual secret will come from env
    # We don't pass the flag itself to load_auth_config, just let env handle it
    # If the flag is explicitly True, we could set a marker, but load_auth_config
    # already checks environment variables automatically
    if client_secret is True:
        # The flag just indicates "use environment variable"
        # load_auth_config will pick up AZURE_CLIENT_SECRET from environment
        # We don't need to pass anything here - env takes priority over CLI
        pass

    if client_certificate_path is not None:
        cli_args["client_certificate_path"] = client_certificate_path

    if subscription_id is not None:
        cli_args["subscription_id"] = subscription_id

    if auth_method is not None:
        cli_args["auth_method"] = auth_method

    # Log sanitized parameters (for debugging)
    logger.debug(
        sanitize_log(
            f"Loading auth config: profile={profile}, cli_args_keys={list(cli_args.keys())}"
        )
    )

    # Use Brick 1 to load and merge configuration
    # Priority: CLI args > env vars > profile config > defaults
    config = load_auth_config(profile=profile, cli_args=cli_args)

    # Create and return Brick 2 (AuthResolver)
    resolver = AuthResolver(config)

    logger.debug(
        sanitize_log(
            f"Created AuthResolver: method={config.auth_method}, "
            f"has_tenant={config.tenant_id is not None}, "
            f"has_client={config.client_id is not None}"
        )
    )

    return resolver


__all__ = [
    "auth_options",
    "get_auth_resolver",
]
