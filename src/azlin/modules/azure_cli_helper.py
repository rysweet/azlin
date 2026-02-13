"""Azure CLI command helper for WSL2 compatibility.

Provides centralized Azure CLI path detection to ensure all azlin modules
use the Linux version of Azure CLI in WSL2 environments.

Philosophy:
- Single responsibility: Provide correct Azure CLI command
- Standard library only
- Caching for performance

Public API:
    get_az_command: Get correct Azure CLI command for current environment
"""

# Cache the detection result for performance
_cached_az_command: str | None = None


def get_az_command() -> str:
    """Get Azure CLI command, preferring Linux version in WSL2.

    In WSL2 environments with both Windows and Linux Azure CLI installed,
    this function ensures the Linux version is used to avoid compatibility
    issues (especially with 'az network bastion tunnel' commands).

    Returns:
        str: Azure CLI command to use ("az" or explicit path like "/usr/bin/az")

    Examples:
        >>> az_cmd = get_az_command()
        >>> subprocess.run([az_cmd, "account", "show"])
    """
    global _cached_az_command

    # Return cached result if available
    if _cached_az_command is not None:
        return _cached_az_command

    # Try to import CLI detector
    try:
        from azlin.modules.cli_detector import CLIDetector

        detector = CLIDetector()
        env_info = detector.detect()

        # In WSL2, prefer Linux CLI if available
        if env_info.environment.value == "wsl2":
            linux_cli = detector.get_linux_cli_path()
            if linux_cli:
                _cached_az_command = str(linux_cli)
                return _cached_az_command

        # Fall back to 'az' in PATH
        _cached_az_command = "az"
        return _cached_az_command

    except ImportError:
        # CLIDetector not available - use default
        _cached_az_command = "az"
        return _cached_az_command

    except Exception:
        # Detection failed - use default
        _cached_az_command = "az"
        return _cached_az_command


def clear_cache() -> None:
    """Clear cached Azure CLI command.

    Useful for testing or if Azure CLI installation changes during runtime.
    """
    global _cached_az_command
    _cached_az_command = None


__all__ = ["clear_cache", "get_az_command"]
