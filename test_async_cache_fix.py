#!/usr/bin/env python3
"""Test the async cache fix - verify cache prevents Azure API calls."""

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from azlin.cache.vm_list_cache import VMListCache
from azlin.vm_manager_async import AsyncVMManager


def create_mock_vm_data():
    """Create mock Azure CLI VM data."""
    return [
        {
            "name": "test-vm-1",
            "resourceGroup": "test-rg",
            "location": "westus2",
            "hardwareProfile": {"vmSize": "Standard_D2s_v3"},
            "storageProfile": {"osDisk": {"osType": "Linux"}},
            "tags": {"managed-by": "azlin"},
            "timeCreated": "2026-01-15T10:00:00Z",
            "powerState": "VM running",
            "publicIps": "1.2.3.4",
            "privateIps": "10.0.0.4",
            "provisioningState": "Succeeded",
        }
    ]


async def test_async_cache_prevents_azure_calls():
    """Test that cache prevents Azure API calls on second run."""
    print("Testing AsyncVMManager cache-first optimization...")

    cache_file = Path.home() / ".azlin" / "vm_list_cache.json"

    # Clear cache
    if cache_file.exists():
        cache_file.unlink()
    print("✓ Cleared cache\n")

    # Create shared cache instance
    cache = VMListCache()

    print("1. First run (cold cache - should hit Azure API)...")

    with patch.object(AsyncVMManager, "_run_az_command", new_callable=AsyncMock) as mock_az:
        mock_az.return_value = ""

        with patch.object(AsyncVMManager, "_get_vms_list", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = create_mock_vm_data()

            with patch.object(
                AsyncVMManager, "_get_public_ips", new_callable=AsyncMock
            ) as mock_ips:
                mock_ips.return_value = {"test-vm-1PublicIP": "1.2.3.4"}

                with patch.object(
                    AsyncVMManager, "_get_instance_view", new_callable=AsyncMock
                ) as mock_view:
                    mock_view.return_value = {
                        "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
                    }

                    manager = AsyncVMManager(resource_group="test-rg", cache=cache)

                    start = time.time()
                    vms, stats = await manager.list_vms_with_stats(include_stopped=True)
                    duration1 = time.time() - start

    print(f"  Duration: {duration1:.3f}s")
    print(f"  VMs found: {len(vms)}")
    print(f"  API calls: {mock_list.call_count}")
    print(f"  Cache hits: {stats.cache_hits}")
    print(f"  Cache misses: {stats.cache_misses}")

    if mock_list.call_count != 1:
        print(f"✗ ERROR: Expected 1 API call, got {mock_list.call_count}")
        return False

    print("✓ First run hit Azure API as expected")

    # Check cache file was created
    if not cache_file.exists():
        print("✗ ERROR: Cache file not created!")
        return False

    with open(cache_file) as f:
        cache_data = json.load(f)
    print(f"✓ Cache file created with {len(cache_data)} entries\n")

    print("2. Second run (warm cache - should NOT hit Azure API)...")

    # Create NEW cache instance to simulate new CLI run
    cache2 = VMListCache()

    with patch.object(AsyncVMManager, "_run_az_command", new_callable=AsyncMock) as mock_az2:
        mock_az2.return_value = ""

        with patch.object(AsyncVMManager, "_get_vms_list", new_callable=AsyncMock) as mock_list2:
            mock_list2.return_value = create_mock_vm_data()

            with patch.object(
                AsyncVMManager, "_get_public_ips", new_callable=AsyncMock
            ) as mock_ips2:
                mock_ips2.return_value = {"test-vm-1PublicIP": "1.2.3.4"}

                with patch.object(
                    AsyncVMManager, "_get_instance_view", new_callable=AsyncMock
                ) as mock_view2:
                    mock_view2.return_value = {
                        "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
                    }

                    manager2 = AsyncVMManager(resource_group="test-rg", cache=cache2)

                    start = time.time()
                    vms2, stats2 = await manager2.list_vms_with_stats(include_stopped=True)
                    duration2 = time.time() - start

    print(f"  Duration: {duration2:.3f}s")
    print(f"  VMs found: {len(vms2)}")
    print(f"  API calls: {mock_list2.call_count}")
    print(f"  Cache hits: {stats2.cache_hits}")
    print(f"  Cache misses: {stats2.cache_misses}")

    # THE CRITICAL TEST: Second run should make ZERO API calls
    if mock_list2.call_count == 0:
        print("✓ SUCCESS: Cache prevented Azure API calls!")
        print(f"  Performance improvement: {(1 - duration2 / duration1) * 100:.1f}%")
        print("  Fix WORKS - async cache now prevents expensive Azure calls")
        return True
    print(f"✗ FAILURE: Cache NOT working! Still made {mock_list2.call_count} API calls")
    print("  Expected: 0 API calls (100% cache hit)")
    print(f"  Actual: {mock_list2.call_count} API calls")
    print("  The fix didn't work - cache-first logic not activated")
    return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_async_cache_prevents_azure_calls())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
