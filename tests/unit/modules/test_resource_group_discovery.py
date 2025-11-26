"""Unit tests for resource_group_discovery module - WORKING IMPLEMENTATIONS"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import pytest

from azlin.modules.resource_group_discovery import (
    ResourceGroupDiscovery,
    ResourceGroupInfo,
    ResourceGroupDiscoveryError,
)


class TestFindVMResourceGroup:
    """Test ResourceGroupDiscovery.find_vm_resource_group()."""

    def test_cache_hit_fast_return(self):
        """Test cache hit returns cached data without Azure query."""
        cache_data = {
            "version": 1,
            "entries": {
                "my-vm": {
                    "vm_name": "my-vm",
                    "resource_group": "rg-prod",
                    "session_name": None,
                    "timestamp": time.time(),
                    "ttl": 900,
                }
            },
        }

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(cache_data))),
            patch("subprocess.run") as mock_run,
        ):
            discovery = ResourceGroupDiscovery()
            result = discovery.find_vm_resource_group("my-vm")

            assert result is not None
            assert result.resource_group == "rg-prod"
            assert result.cached is True
            assert mock_run.call_count == 0  # No Azure query

    def test_cache_miss_queries_azure(self):
        """Test cache miss triggers Azure query."""
        cache_data = {"version": 1, "entries": {}}
        azure_response = [{"name": "my-vm", "resourceGroup": "rg-prod", "sessionName": None}]

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(cache_data))),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps(azure_response))

            discovery = ResourceGroupDiscovery()
            result = discovery.find_vm_resource_group("my-vm")

            assert result is not None
            assert result.resource_group == "rg-prod"
            assert result.source == "tags"

    def test_force_refresh_bypasses_cache(self):
        """Test force_refresh=True bypasses cache."""
        cache_data = {
            "version": 1,
            "entries": {
                "my-vm": {"vm_name": "my-vm", "resource_group": "rg-old", "timestamp": time.time()}
            },
        }
        azure_response = [{"name": "my-vm", "resourceGroup": "rg-new", "sessionName": None}]

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(cache_data))),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps(azure_response))

            discovery = ResourceGroupDiscovery()
            result = discovery.find_vm_resource_group("my-vm", force_refresh=True)

            assert result is not None
            assert result.resource_group == "rg-new"

    def test_no_matches_returns_none(self):
        """Test returns None when no VMs match."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps([]))

            discovery = ResourceGroupDiscovery()
            result = discovery.find_vm_resource_group("nonexistent-vm")

            assert result is None


class TestQueryAllResourceGroups:
    """Test ResourceGroupDiscovery.query_all_resource_groups()."""

    def test_single_vm_match(self):
        """Test returns single VM match."""
        azure_response = [{"name": "my-vm", "resourceGroup": "rg-prod", "sessionName": None}]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps(azure_response))

            discovery = ResourceGroupDiscovery()
            result = discovery.query_all_resource_groups("my-vm")

            assert result is not None
            assert result.vm_name == "my-vm"
            assert result.resource_group == "rg-prod"

    def test_multiple_matches_raises_error(self):
        """Test multiple VMs with same identifier raises error."""
        azure_response = [
            {"name": "my-vm", "resourceGroup": "rg-dev", "sessionName": "dev"},
            {"name": "my-vm", "resourceGroup": "rg-prod", "sessionName": "prod"},
        ]

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=json.dumps(azure_response))

            discovery = ResourceGroupDiscovery()

            with pytest.raises(ResourceGroupDiscoveryError, match="Multiple VMs found"):
                discovery.query_all_resource_groups("my-vm")


class TestCacheManagement:
    """Test cache loading, saving, and expiration."""

    def test_load_cache_valid_format(self):
        """Test loads cache with valid JSON format."""
        cache_data = {
            "version": 1,
            "entries": {
                "vm1": {"vm_name": "vm1", "resource_group": "rg1", "timestamp": time.time()}
            },
        }

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(cache_data))),
        ):
            discovery = ResourceGroupDiscovery()
            cache = discovery._load_cache()

            assert cache["version"] == 1
            assert "vm1" in cache["entries"]

    def test_load_cache_missing_file(self):
        """Test handles missing cache file gracefully."""
        with patch("pathlib.Path.exists", return_value=False):
            discovery = ResourceGroupDiscovery()
            cache = discovery._load_cache()

            assert cache == {"version": 1, "entries": {}}

    def test_is_cache_expired_within_ttl(self):
        """Test cache entry within TTL is not expired."""
        entry = {"timestamp": time.time(), "ttl": 900}

        discovery = ResourceGroupDiscovery()
        assert discovery._is_cache_expired(entry) is False

    def test_is_cache_expired_beyond_ttl(self):
        """Test cache entry beyond TTL is expired."""
        entry = {
            "timestamp": time.time() - 1000,  # 16.6 minutes ago
            "ttl": 900,  # 15 minutes
        }

        discovery = ResourceGroupDiscovery()
        assert discovery._is_cache_expired(entry) is True

    def test_invalidate_cache_single_entry(self):
        """Test invalidates specific cache entry."""
        cache_data = {
            "version": 1,
            "entries": {
                "vm1": {"vm_name": "vm1", "resource_group": "rg1"},
                "vm2": {"vm_name": "vm2", "resource_group": "rg2"},
            },
        }

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(cache_data))) as mock_file,
        ):
            discovery = ResourceGroupDiscovery()
            discovery.invalidate_cache("vm1")

            # Should write cache with vm1 removed
            assert mock_file.called


class TestFallbacks:
    """Test fallback behavior."""

    def test_fallback_to_default_resource_group(self):
        """Test uses default resource group as last resort."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=json.dumps([]),  # No matches
            )

            config = {
                "default_resource_group": "rg-default",
                "resource_group": {"fallback_to_default": True},
            }

            discovery = ResourceGroupDiscovery(config)
            result = discovery.find_vm_resource_group("my-vm")

            assert result is not None
            assert result.resource_group == "rg-default"
            assert result.source == "default"


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_vm_identifier_returns_none(self):
        """Test empty VM identifier returns None."""
        discovery = ResourceGroupDiscovery()
        result = discovery.find_vm_resource_group("")

        assert result is None

    def test_whitespace_only_identifier_returns_none(self):
        """Test whitespace-only identifier returns None."""
        discovery = ResourceGroupDiscovery()
        result = discovery.find_vm_resource_group("   ")

        assert result is None
