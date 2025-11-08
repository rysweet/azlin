"""Resource tagging utilities for doit."""

import json
import subprocess
from datetime import datetime
from typing import TypedDict


class DoItTags(TypedDict):
    """Tags applied to doit-created resources."""

    azlin_doit_owner: str
    azlin_doit_created: str


def get_azure_username() -> str:
    """Get current Azure user or service principal name.

    Returns:
        Username string from Azure account

    Raises:
        RuntimeError: If unable to get Azure username
    """
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "user.name", "-o", "tsv"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            username = result.stdout.strip()
            # For service principals, extract a simpler name from the client ID
            if "@" not in username and "-" in username:
                # Likely a service principal UUID - use first 8 chars
                return username[:8]
            return username

        raise RuntimeError(f"Failed to get Azure username: {result.stderr}")

    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout while getting Azure username")
    except Exception as e:
        raise RuntimeError(f"Error getting Azure username: {e}")


def generate_doit_tags(username: str | None = None) -> DoItTags:
    """Generate standard doit tags for resources.

    Args:
        username: Azure username (if None, will be retrieved)

    Returns:
        Dictionary of tags to apply to resources
    """
    if username is None:
        username = get_azure_username()

    timestamp = datetime.utcnow().isoformat() + "Z"

    return DoItTags(
        azlin_doit_owner=username,
        azlin_doit_created=timestamp,
    )


def format_tags_for_az_cli(tags: DoItTags) -> str:
    """Format tags for Azure CLI command.

    Args:
        tags: Tags dictionary

    Returns:
        String formatted for --tags parameter
    """
    # Azure CLI accepts tags as space-separated key=value pairs
    return " ".join(f"{k}={v}" for k, v in tags.items())


def format_tags_for_terraform(tags: DoItTags) -> str:
    """Format tags for Terraform code.

    Args:
        tags: Tags dictionary

    Returns:
        HCL formatted tags block
    """
    lines = ["  tags = {"]
    for key, value in tags.items():
        lines.append(f'    {key} = "{value}"')
    lines.append("  }")
    return "\n".join(lines)


def format_tags_for_bicep(tags: DoItTags) -> str:
    """Format tags for Bicep code.

    Args:
        tags: Tags dictionary

    Returns:
        Bicep formatted tags block
    """
    lines = ["  tags: {"]
    for key, value in tags.items():
        lines.append(f"    {key}: '{value}'")
    lines.append("  }")
    return "\n".join(lines)


def parse_tag_filter(username: str | None = None) -> str:
    """Generate tag filter for Azure CLI queries.

    Args:
        username: Azure username (if None, will be retrieved)

    Returns:
        Tag filter string for 'az resource list --tag' parameter
    """
    if username is None:
        username = get_azure_username()

    return f"azlin-doit-owner={username}"
