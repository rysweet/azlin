"""Resource manager for listing and cleaning up doit-created resources."""

import json
import subprocess
from datetime import datetime
from typing import Any, TypedDict

from azlin.doit.utils import get_azure_username, parse_tag_filter


class ResourceInfo(TypedDict):
    """Information about a doit-created resource."""

    id: str
    name: str
    type: str
    resource_group: str
    location: str
    tags: dict[str, str]
    created: str | None


class ResourceManager:
    """Manages doit-created Azure resources."""

    def __init__(self, username: str | None = None):
        """Initialize resource manager.

        Args:
            username: Azure username (if None, will be retrieved)
        """
        self.username = username or get_azure_username()
        self.tag_filter = parse_tag_filter(self.username)

    def list_resources(self) -> list[ResourceInfo]:
        """List all resources created by doit for current user.

        Returns:
            List of resource information dictionaries

        Raises:
            RuntimeError: If unable to list resources
        """
        try:
            result = subprocess.run(
                [
                    "az",
                    "resource",
                    "list",
                    "--tag",
                    self.tag_filter,
                    "--output",
                    "json",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to list resources: {result.stderr}")

            resources = json.loads(result.stdout)
            return [self._parse_resource(r) for r in resources]

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout while listing resources")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse resource list: {e}")
        except Exception as e:
            raise RuntimeError(f"Error listing resources: {e}")

    def get_resource_details(self, resource_id: str) -> dict[str, Any]:
        """Get detailed information about a specific resource.

        Args:
            resource_id: Full Azure resource ID

        Returns:
            Detailed resource information

        Raises:
            RuntimeError: If unable to get resource details
        """
        try:
            result = subprocess.run(
                [
                    "az",
                    "resource",
                    "show",
                    "--ids",
                    resource_id,
                    "--output",
                    "json",
                ],
                shell=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Failed to get resource details: {result.stderr}")

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout while getting resource details")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse resource details: {e}")
        except Exception as e:
            raise RuntimeError(f"Error getting resource details: {e}")

    def cleanup_resources(self, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
        """Delete all doit-created resources.

        Deletes resources in reverse dependency order (data resources last).

        Args:
            force: If True, skip confirmation
            dry_run: If True, show what would be deleted without deleting

        Returns:
            Dictionary with cleanup results

        Raises:
            RuntimeError: If cleanup fails
        """
        resources = self.list_resources()

        if not resources:
            return {
                "deleted": [],
                "failed": [],
                "message": "No resources found to delete",
            }

        # Group by resource group
        rg_resources: dict[str, list[ResourceInfo]] = {}
        for resource in resources:
            rg = resource["resource_group"]
            if rg not in rg_resources:
                rg_resources[rg] = []
            rg_resources[rg].append(resource)

        deleted = []
        failed = []

        for rg, rg_res_list in rg_resources.items():
            # Sort resources by type (delete certain types first)
            # Order: connections/APIs first, then apps, then data (cosmos/storage last)
            priority_order = {
                "Microsoft.Web/sites": 2,
                "Microsoft.Web/serverfarms": 3,
                "Microsoft.ApiManagement/service": 1,
                "Microsoft.KeyVault/vaults": 4,
                "Microsoft.DocumentDB/databaseAccounts": 5,
                "Microsoft.Storage/storageAccounts": 5,
            }

            sorted_resources = sorted(
                rg_res_list,
                key=lambda r: priority_order.get(r["type"], 0),
            )

            for resource in sorted_resources:
                if dry_run:
                    deleted.append(
                        {
                            "id": resource["id"],
                            "name": resource["name"],
                            "type": resource["type"],
                            "dry_run": True,
                        }
                    )
                    continue

                try:
                    result = subprocess.run(
                        [
                            "az",
                            "resource",
                            "delete",
                            "--ids",
                            resource["id"],
                            "--verbose",
                        ],
                        shell=False,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minutes per resource
                    )

                    if result.returncode == 0:
                        deleted.append(
                            {
                                "id": resource["id"],
                                "name": resource["name"],
                                "type": resource["type"],
                            }
                        )
                    else:
                        failed.append(
                            {
                                "id": resource["id"],
                                "name": resource["name"],
                                "type": resource["type"],
                                "error": result.stderr,
                            }
                        )

                except subprocess.TimeoutExpired:
                    failed.append(
                        {
                            "id": resource["id"],
                            "name": resource["name"],
                            "type": resource["type"],
                            "error": "Timeout during deletion",
                        }
                    )
                except Exception as e:
                    failed.append(
                        {
                            "id": resource["id"],
                            "name": resource["name"],
                            "type": resource["type"],
                            "error": str(e),
                        }
                    )

        return {
            "deleted": deleted,
            "failed": failed,
            "total_resources": len(resources),
            "successfully_deleted": len(deleted),
            "failed_count": len(failed),
        }

    def _parse_resource(self, resource_data: dict[str, Any]) -> ResourceInfo:
        """Parse resource data from Azure CLI.

        Args:
            resource_data: Raw resource data from az CLI

        Returns:
            Parsed resource information
        """
        tags = resource_data.get("tags", {})
        created = tags.get("azlin-doit-created", None)

        return ResourceInfo(
            id=resource_data.get("id", ""),
            name=resource_data.get("name", ""),
            type=resource_data.get("type", ""),
            resource_group=self._extract_rg_from_id(resource_data.get("id", "")),
            location=resource_data.get("location", ""),
            tags=tags,
            created=created,
        )

    def _extract_rg_from_id(self, resource_id: str) -> str:
        """Extract resource group name from resource ID.

        Args:
            resource_id: Full Azure resource ID

        Returns:
            Resource group name
        """
        parts = resource_id.split("/")
        try:
            rg_index = parts.index("resourceGroups")
            return parts[rg_index + 1]
        except (ValueError, IndexError):
            return "unknown"
