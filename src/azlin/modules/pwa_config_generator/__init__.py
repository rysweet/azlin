"""PWA Configuration Generator Module.

This module provides configuration inheritance from azlin parent config to PWA projects.
Extracts Azure configuration from Azure CLI and/or azlin config files.

Philosophy:
- Single responsibility: Generate PWA .env from available config sources
- Standard library only (subprocess for Azure CLI, json/toml for parsing)
- Self-contained and regeneratable
- NEVER overwrite existing .env without explicit force flag

Public API (the "studs"):
    ConfigSource: Enum for tracking value origins
    PWAConfigResult: Dataclass for operation results
    PWAConfigGenerator: Main configuration generator class
    generate_pwa_env_from_azlin: Convenience function (wraps PWAConfigGenerator)
"""

from pathlib import Path

from .generator import ConfigSource, PWAConfigGenerator, PWAConfigResult


def generate_pwa_env_from_azlin(pwa_dir: Path, force: bool = False) -> PWAConfigResult:
    """Convenience function: Generate PWA .env from azlin config.

    This is a wrapper around PWAConfigGenerator.generate_pwa_env_from_azlin()
    for easier CLI integration.

    Args:
        pwa_dir: Path to PWA directory
        force: If True, overwrite existing .env (default: False)

    Returns:
        PWAConfigResult with operation status and messages
    """
    generator = PWAConfigGenerator()
    return generator.generate_pwa_env_from_azlin(pwa_dir, force=force)


__all__ = [
    "ConfigSource",
    "PWAConfigGenerator",
    "PWAConfigResult",
    "generate_pwa_env_from_azlin",
]
