"""Unit tests for Async VM Manager module.

Tests cover:
- Parallel VM listing with asyncio
- Cache integration
- Performance statistics
- Error handling
- Backward compatibility with VMManager
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from azlin.cache.vm_list_cache import VMListCache
from azlin.vm_manager import VMInfo, VMManagerError
from azlin.vm_manager_async import (
    AsyncVMManager,
    ParallelListStats,
    list_vms_parallel,
    list_vms_parallel_with_stats,
)


class TestParallelListStats:
    """Test parallel list statistics model."""

    def test_create_stats(self):
        """Test creating statistics."""
        stats = ParallelListStats(
            total_duration=5.0,
            cache_hits=8,
            cache_misses=2,
            api_calls=3,
            vms_found=10,
        )

        assert stats.total_duration == 5.0
        assert stats.cache_hits == 8
        assert stats.cache_misses == 2
        assert stats.api_calls == 3
        assert stats.vms_found == 10

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        stats = ParallelListStats(
            total_duration=5.0,
            cache_hits=8,
            cache_misses=2,
            api_calls=3,
            vms_found=10,
        )

        assert stats.cache_hit_rate() == 0.8  # 8 / (8 + 2) = 0.8

    def test_cache_hit_rate_no_operations(self):
        """Test cache hit rate with no operations."""
        stats = ParallelListStats(
            total_duration=5.0,
            cache_hits=0,
            cache_misses=0,
            api_calls=0,
            vms_found=0,
        )

        assert stats.cache_hit_rate() == 0.0


class TestAsyncVMManager:
    """Test async VM manager operations."""

    @pytest.fixture
    def mock_cache(self, tmp_path):
        """Create mock cache for testing."""
        cache_path = tmp_path / "test_cache.json"
        return VMListCache(cache_path=cache_path)

    @pytest.mark.asyncio
    async def test_run_az_command_success(self, mock_cache):
        """Test running Azure CLI command successfully."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock successful command
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b'{"test": "data"}', b""))
            mock_exec.return_value = mock_process

            result = await manager._run_az_command(["az", "vm", "list"])

            assert result == '{"test": "data"}'
            assert manager.api_calls == 1

    @pytest.mark.asyncio
    async def test_run_az_command_failure(self, mock_cache):
        """Test running Azure CLI command with failure."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock failed command
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))
            mock_exec.return_value = mock_process

            with pytest.raises(VMManagerError, match="Command failed"):
                await manager._run_az_command(["az", "vm", "list"])

    @pytest.mark.asyncio
    async def test_run_az_command_timeout(self, mock_cache):
        """Test running Azure CLI command with timeout."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock command that times out
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=TimeoutError())
            mock_exec.return_value = mock_process

            with pytest.raises(VMManagerError, match="timed out"):
                await manager._run_az_command(["az", "vm", "list"], timeout=1)

    @pytest.mark.asyncio
    async def test_get_vms_list(self, mock_cache):
        """Test getting VMs list from Azure."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        vm_data = [
            {"name": "vm1", "location": "westus2"},
            {"name": "vm2", "location": "eastus"},
        ]

        with patch.object(manager, "_run_az_command") as mock_cmd:
            mock_cmd.return_value = json.dumps(vm_data)

            vms = await manager._get_vms_list()

            assert len(vms) == 2
            assert vms[0]["name"] == "vm1"
            assert vms[1]["name"] == "vm2"

    @pytest.mark.asyncio
    async def test_get_vms_list_empty(self, mock_cache):
        """Test getting empty VMs list."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        with patch.object(manager, "_run_az_command") as mock_cmd:
            mock_cmd.return_value = ""

            vms = await manager._get_vms_list()

            assert vms == []

    @pytest.mark.asyncio
    async def test_get_public_ips(self, mock_cache):
        """Test getting public IPs."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        ips_data = [
            {"name": "vm1PublicIP", "ip": "1.2.3.4"},
            {"name": "vm2PublicIP", "ip": "5.6.7.8"},
        ]

        with patch.object(manager, "_run_az_command") as mock_cmd:
            mock_cmd.return_value = json.dumps(ips_data)

            ips = await manager._get_public_ips()

            assert ips == {
                "vm1PublicIP": "1.2.3.4",
                "vm2PublicIP": "5.6.7.8",
            }

    @pytest.mark.asyncio
    async def test_get_instance_view(self, mock_cache):
        """Test getting VM instance view."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        instance_data = {
            "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
        }

        with patch.object(manager, "_run_az_command") as mock_cmd:
            mock_cmd.return_value = json.dumps(instance_data)

            view = await manager._get_instance_view("test-vm")

            assert view is not None
            assert view["statuses"][0]["code"] == "PowerState/running"

    @pytest.mark.asyncio
    async def test_enrich_vm_with_cache_hit(self, mock_cache):
        """Test enriching VM with cache hit."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        vm_data = {
            "name": "test-vm",
            "location": "westus2",
            "resourceGroup": "test-rg",
            "hardwareProfile": {"vmSize": "Standard_DS2_v2"},
        }

        # Pre-populate cache
        mock_cache.set_full(
            "test-vm",
            "test-rg",
            {"name": "test-vm", "location": "westus2"},
            {"power_state": "VM running", "public_ip": "1.2.3.4"},
        )

        # Enrich VM (should use cache)
        vm_info = await manager._enrich_vm_with_cache(vm_data, {})

        assert vm_info.name == "test-vm"
        assert vm_info.power_state == "VM running"
        assert vm_info.public_ip == "1.2.3.4"
        assert manager.cache_hits == 1
        assert manager.cache_misses == 0

    @pytest.mark.asyncio
    async def test_enrich_vm_with_cache_miss(self, mock_cache):
        """Test enriching VM with cache miss."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        vm_data = {
            "name": "test-vm",
            "location": "westus2",
            "resourceGroup": "test-rg",
            "hardwareProfile": {"vmSize": "Standard_DS2_v2"},
            "tags": {},
        }

        instance_data = {
            "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
        }

        with patch.object(manager, "_get_instance_view") as mock_view:
            mock_view.return_value = instance_data

            # Enrich VM (should fetch from API)
            vm_info = await manager._enrich_vm_with_cache(vm_data, {"test-vmPublicIP": "1.2.3.4"})

            assert vm_info.name == "test-vm"
            assert vm_info.power_state == "VM running"
            assert vm_info.public_ip == "1.2.3.4"
            assert manager.cache_hits == 0
            assert manager.cache_misses == 1

    @pytest.mark.asyncio
    async def test_list_vms_with_stats(self, mock_cache):
        """Test listing VMs with statistics."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        vms_data = [
            {
                "name": "azlin-vm1",
                "location": "westus2",
                "resourceGroup": "test-rg",
                "hardwareProfile": {"vmSize": "Standard_DS2_v2"},
                "tags": {},
            }
        ]

        with (
            patch.object(manager, "_get_vms_list") as mock_list,
            patch.object(manager, "_get_public_ips") as mock_ips,
            patch.object(manager, "_enrich_vm_with_cache") as mock_enrich,
        ):
            mock_list.return_value = vms_data
            mock_ips.return_value = {}
            mock_enrich.return_value = VMInfo(
                name="azlin-vm1",
                resource_group="test-rg",
                location="westus2",
                power_state="VM running",
            )

            vms, stats = await manager.list_vms_with_stats()

            assert len(vms) == 1
            assert vms[0].name == "azlin-vm1"
            assert stats.vms_found == 1
            assert stats.total_duration > 0

    @pytest.mark.asyncio
    async def test_list_vms_filter_prefix(self, mock_cache):
        """Test listing VMs with prefix filter."""
        manager = AsyncVMManager("test-rg", cache=mock_cache)

        vms_data = [
            {
                "name": "azlin-vm1",
                "location": "westus2",
                "resourceGroup": "test-rg",
                "tags": {},
            },
            {
                "name": "other-vm",
                "location": "westus2",
                "resourceGroup": "test-rg",
                "tags": {},
            },
        ]

        with (
            patch.object(manager, "_get_vms_list") as mock_list,
            patch.object(manager, "_get_public_ips") as mock_ips,
            patch.object(manager, "_enrich_vm_with_cache") as mock_enrich,
        ):
            mock_list.return_value = vms_data
            mock_ips.return_value = {}

            def enrich_side_effect(vm_data, ips):
                return VMInfo(
                    name=vm_data["name"],
                    resource_group="test-rg",
                    location="westus2",
                    power_state="VM running",
                )

            mock_enrich.side_effect = enrich_side_effect

            vms, stats = await manager.list_vms_with_stats(filter_prefix="azlin")

            assert len(vms) == 1
            assert vms[0].name == "azlin-vm1"


class TestSyncWrappers:
    """Test synchronous wrapper functions."""

    @pytest.fixture
    def mock_cache(self, tmp_path):
        """Create mock cache for testing."""
        cache_path = tmp_path / "test_cache.json"
        return VMListCache(cache_path=cache_path)

    def test_list_vms_parallel(self, mock_cache):
        """Test synchronous list_vms_parallel wrapper."""
        with patch("azlin.vm_manager_async.AsyncVMManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_vms = AsyncMock(
                return_value=[
                    VMInfo(
                        name="test-vm",
                        resource_group="test-rg",
                        location="westus2",
                        power_state="VM running",
                    )
                ]
            )
            mock_manager_class.return_value = mock_manager

            vms = list_vms_parallel("test-rg", cache=mock_cache)

            assert len(vms) == 1
            assert vms[0].name == "test-vm"

    def test_list_vms_parallel_with_stats(self, mock_cache):
        """Test synchronous list_vms_parallel_with_stats wrapper."""
        with patch("azlin.vm_manager_async.AsyncVMManager") as mock_manager_class:
            mock_manager = Mock()
            mock_stats = ParallelListStats(
                total_duration=2.0,
                cache_hits=1,
                cache_misses=0,
                api_calls=2,
                vms_found=1,
            )
            mock_manager.list_vms_with_stats = AsyncMock(
                return_value=(
                    [
                        VMInfo(
                            name="test-vm",
                            resource_group="test-rg",
                            location="westus2",
                            power_state="VM running",
                        )
                    ],
                    mock_stats,
                )
            )
            mock_manager_class.return_value = mock_manager

            vms, stats = list_vms_parallel_with_stats("test-rg", cache=mock_cache)

            assert len(vms) == 1
            assert vms[0].name == "test-vm"
            assert stats.total_duration == 2.0
            assert stats.cache_hits == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
