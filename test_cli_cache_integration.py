#!/usr/bin/env python3
"""Integration test to verify CLI uses cache correctly."""

import sys
import time
from pathlib import Path
from unittest.mock import patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


from azlin.context_manager import Context
from azlin.multi_context_list_async import query_all_contexts_parallel


def create_mock_vm_data(name: str, rg: str) -> dict:
    """Create mock VM data that matches Azure CLI output."""
    return {
        "name": name,
        "resourceGroup": rg,
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


def test_cli_cache_integration():
    """Test that query_all_contexts_parallel actually uses cache."""
    print("Testing CLI cache integration...")

    cache_file = Path.home() / ".azlin" / "vm_list_cache.json"

    # Clear cache
    if cache_file.exists():
        cache_file.unlink()
    print("✓ Cleared cache")

    # Create test context
    test_context = Context(
        name="test-ctx",
        subscription_id="test-sub-id",
        resource_group="test-rg",
        location="westus2",
    )

    print("\n1. First run (should hit Azure API, populate cache)...")

    # Mock Azure CLI calls
    with patch("azlin.vm_manager_async.AsyncVMManager._run_az_command") as mock_az:
        # Mock the VM list call
        mock_vms_data = [create_mock_vm_data("test-vm-1", "test-rg")]
        mock_az.return_value = ""  # For subscription switch and instance view calls

        # We need to mock the actual az vm list call that returns JSON
        with patch("azlin.vm_manager_async.AsyncVMManager._get_vms_list") as mock_list:
            mock_list.return_value = [create_mock_vm_data("test-vm-1", "test-rg")]

            with patch("azlin.vm_manager_async.AsyncVMManager._get_public_ips") as mock_ips:
                mock_ips.return_value = {"test-vm-1PublicIP": "1.2.3.4"}

                with patch("azlin.vm_manager_async.AsyncVMManager._get_instance_view") as mock_view:
                    mock_view.return_value = {
                        "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
                    }

                    start = time.time()
                    result = query_all_contexts_parallel(
                        contexts=[test_context],
                        resource_group="test-rg",
                        include_stopped=True,
                        filter_prefix="azlin",
                        cache=None,  # This is what the CLI passes
                    )
                    duration1 = time.time() - start

    print(f"  Duration: {duration1:.3f}s")
    print(f"  VMs found: {result.total_vms}")
    print(f"  API calls made: {mock_list.call_count}")

    # Check if cache file was created
    if cache_file.exists():
        print(f"✓ Cache file created: {cache_file}")
        import json

        with open(cache_file) as f:
            cache_data = json.load(f)
        print(f"  Cache entries: {len(cache_data)}")
    else:
        print("✗ ERROR: Cache file NOT created!")
        return False

    print("\n2. Second run (should use cache, be MUCH faster)...")

    # Mock again but expect NO calls to Azure since cache should be used
    with patch("azlin.vm_manager_async.AsyncVMManager._run_az_command") as mock_az2:
        with patch("azlin.vm_manager_async.AsyncVMManager._get_vms_list") as mock_list2:
            mock_list2.return_value = [create_mock_vm_data("test-vm-1", "test-rg")]

            with patch("azlin.vm_manager_async.AsyncVMManager._get_public_ips") as mock_ips2:
                mock_ips2.return_value = {"test-vm-1PublicIP": "1.2.3.4"}

                with patch(
                    "azlin.vm_manager_async.AsyncVMManager._get_instance_view"
                ) as mock_view2:
                    mock_view2.return_value = {
                        "statuses": [{"code": "PowerState/running", "displayStatus": "VM running"}]
                    }

                    start = time.time()
                    result2 = query_all_contexts_parallel(
                        contexts=[test_context],
                        resource_group="test-rg",
                        include_stopped=True,
                        filter_prefix="azlin",
                        cache=None,  # Same as CLI
                    )
                    duration2 = time.time() - start

    print(f"  Duration: {duration2:.3f}s")
    print(f"  VMs found: {result2.total_vms}")
    print(f"  API calls made: {mock_list2.call_count}")

    # Check if cache was used (should have FEWER or ZERO API calls)
    if mock_list2.call_count == 0:
        print("✓ SUCCESS: Cache used! No API calls on second run")
        print(f"  Performance improvement: {(1 - duration2 / duration1) * 100:.1f}%")
        return True
    print(f"✗ ERROR: Cache NOT used! Still made {mock_list2.call_count} API calls")
    print("  Expected: 0 API calls (cache hit)")
    print(f"  Actual: {mock_list2.call_count} API calls")
    return False


if __name__ == "__main__":
    success = test_cli_cache_integration()
    sys.exit(0 if success else 1)
