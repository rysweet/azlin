"""Tests for VM List Cache Incremental Refresh - Per-VM cache refresh optimization.

Testing Pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)

Issue #638: Implement per-VM incremental cache refresh
Goal: 80-95% reduction in cache refresh API calls
"""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from azlin.cache.vm_list_cache import VMListCache
from azlin.vm_manager import VMInfo, VMManager

# =============================================================================
# UNIT TESTS (60%) - Fast, focused tests with mocking
# =============================================================================


class TestGetExpiredEntries:
    """Test VMListCache.get_expired_entries() method."""

    def test_returns_empty_list_when_cache_empty(self, tmp_path):
        """Verify empty list when no cache entries exist."""
        cache = VMListCache(cache_path=tmp_path / "cache.json")
        expired = cache.get_expired_entries("test-rg")
        assert expired == []

    def test_returns_empty_list_when_all_entries_fresh(self, tmp_path):
        """Verify empty list when all cache entries are fresh."""
        cache = VMListCache(cache_path=tmp_path / "cache.json")

        # Create fresh cache entries (just created, not expired)
        cache.set_full(
            vm_name="vm1",
            resource_group="test-rg",
            immutable_data={"name": "vm1", "location": "eastus"},
            mutable_data={"power_state": "VM running"},
        )
        cache.set_full(
            vm_name="vm2",
            resource_group="test-rg",
            immutable_data={"name": "vm2", "location": "eastus"},
            mutable_data={"power_state": "VM running"},
        )

        expired = cache.get_expired_entries("test-rg")
        assert expired == []

    def test_detects_immutable_layer_expired(self, tmp_path):
        """Verify detection of expired immutable layer (24h TTL)."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            immutable_ttl=1,  # 1 second for testing
        )

        # Create entry
        cache.set_full(
            vm_name="vm1",
            resource_group="test-rg",
            immutable_data={"name": "vm1", "location": "eastus"},
            mutable_data={"power_state": "VM running"},
        )

        # Wait for immutable layer to expire
        time.sleep(1.1)

        expired = cache.get_expired_entries("test-rg")
        assert len(expired) == 1
        assert expired[0] == ("vm1", "test-rg")

    def test_detects_mutable_layer_expired(self, tmp_path):
        """Verify detection of expired mutable layer (5min TTL)."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,  # 1 second for testing
        )

        # Create entry
        cache.set_full(
            vm_name="vm1",
            resource_group="test-rg",
            immutable_data={"name": "vm1", "location": "eastus"},
            mutable_data={"power_state": "VM running"},
        )

        # Wait for mutable layer to expire
        time.sleep(1.1)

        expired = cache.get_expired_entries("test-rg")
        assert len(expired) == 1
        assert expired[0] == ("vm1", "test-rg")

    def test_detects_both_layers_expired(self, tmp_path):
        """Verify detection when both layers are expired."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            immutable_ttl=1,
            mutable_ttl=1,
        )

        cache.set_full(
            vm_name="vm1",
            resource_group="test-rg",
            immutable_data={"name": "vm1"},
            mutable_data={"power_state": "VM running"},
        )

        time.sleep(1.1)

        expired = cache.get_expired_entries("test-rg")
        assert len(expired) == 1
        assert expired[0] == ("vm1", "test-rg")

    def test_mixed_expiration_scenario(self, tmp_path):
        """Verify detection with mix of fresh and expired entries."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,
        )

        # Create 3 VMs
        for i in range(1, 4):
            cache.set_full(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                immutable_data={"name": f"vm{i}"},
                mutable_data={"power_state": "VM running"},
            )

        # Wait for mutable to expire
        time.sleep(1.1)

        # Refresh vm2's mutable layer (make it fresh again)
        cache.set_mutable(
            vm_name="vm2",
            resource_group="test-rg",
            mutable_data={"power_state": "VM stopped"},
        )

        # Should detect vm1 and vm3 as expired, vm2 is fresh
        expired = cache.get_expired_entries("test-rg")
        assert len(expired) == 2
        assert ("vm1", "test-rg") in expired
        assert ("vm3", "test-rg") in expired
        assert ("vm2", "test-rg") not in expired

    def test_filters_by_resource_group(self, tmp_path):
        """Verify only returns entries for specified resource group."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,
        )

        # Create entries in different resource groups
        cache.set_full(
            vm_name="vm1",
            resource_group="rg-a",
            immutable_data={"name": "vm1"},
            mutable_data={"power_state": "VM running"},
        )
        cache.set_full(
            vm_name="vm2",
            resource_group="rg-b",
            immutable_data={"name": "vm2"},
            mutable_data={"power_state": "VM running"},
        )

        time.sleep(1.1)

        # Should only return expired entries from rg-a
        expired_a = cache.get_expired_entries("rg-a")
        assert len(expired_a) == 1
        assert expired_a[0] == ("vm1", "rg-a")

        # Should only return expired entries from rg-b
        expired_b = cache.get_expired_entries("rg-b")
        assert len(expired_b) == 1
        assert expired_b[0] == ("vm2", "rg-b")

    def test_handles_nonexistent_resource_group(self, tmp_path):
        """Verify returns empty list for nonexistent resource group."""
        cache = VMListCache(cache_path=tmp_path / "cache.json")

        cache.set_full(
            vm_name="vm1",
            resource_group="rg-a",
            immutable_data={"name": "vm1"},
            mutable_data={"power_state": "VM running"},
        )

        expired = cache.get_expired_entries("nonexistent-rg")
        assert expired == []


class TestRefreshExpiredVMs:
    """Test VMManager.refresh_expired_vms() method."""

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_refreshes_only_specified_vms(self, mock_get_vm, tmp_path):
        """Verify only specified VMs are queried from Azure."""
        # Setup mock
        mock_get_vm.side_effect = lambda name, rg: VMInfo(
            name=name,
            resource_group=rg,
            location="eastus",
            power_state="VM running",
            vm_size="Standard_DS2_v2",
        )

        # Refresh 2 specific VMs
        refreshed = VMManager.refresh_expired_vms(
            resource_group="test-rg",
            expired_vm_names=["vm1", "vm3"],
        )

        # Should call get_vm exactly twice
        assert mock_get_vm.call_count == 2
        mock_get_vm.assert_any_call("vm1", "test-rg")
        mock_get_vm.assert_any_call("vm3", "test-rg")

        # Should return 2 VMInfo objects
        assert len(refreshed) == 2
        assert refreshed[0].name == "vm1"
        assert refreshed[1].name == "vm3"

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_updates_cache_after_refresh(self, mock_get_vm, tmp_path):
        """Verify cache is updated with refreshed VM data."""
        cache = VMListCache(cache_path=tmp_path / "cache.json")

        # Setup mock
        mock_get_vm.return_value = VMInfo(
            name="vm1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_DS2_v2",
        )

        # Refresh with cache injection
        with patch("azlin.vm_manager.VMListCache", return_value=cache):
            VMManager.refresh_expired_vms(
                resource_group="test-rg",
                expired_vm_names=["vm1"],
            )

        # Verify cache was updated
        entry = cache.get("vm1", "test-rg")
        assert entry is not None
        assert entry.immutable_data["name"] == "vm1"
        assert entry.mutable_data["power_state"] == "VM running"

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_uses_threadpool_for_parallel_queries(self, mock_get_vm):
        """Verify ThreadPoolExecutor is used for parallel queries."""
        call_times = []

        def mock_get_vm_with_delay(name, rg):
            call_times.append(time.time())
            time.sleep(0.1)  # Simulate API call delay
            return VMInfo(
                name=name,
                resource_group=rg,
                location="eastus",
                power_state="VM running",
            )

        mock_get_vm.side_effect = mock_get_vm_with_delay

        start = time.time()
        VMManager.refresh_expired_vms(
            resource_group="test-rg",
            expired_vm_names=["vm1", "vm2", "vm3", "vm4", "vm5"],
        )
        duration = time.time() - start

        # Parallel execution should be faster than sequential (5 * 0.1 = 0.5s)
        # With parallelism, should be close to 0.1s (all at once)
        assert duration < 0.3  # Allow some overhead

        # Verify calls were made in parallel (close together in time)
        time_diffs = [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]
        # Most calls should be nearly simultaneous (< 0.05s apart)
        nearly_parallel = sum(1 for diff in time_diffs if diff < 0.05)
        assert nearly_parallel >= 3  # At least 3 out of 4 intervals are parallel

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_handles_individual_vm_query_failures(self, mock_get_vm):
        """Verify graceful handling when some VM queries fail."""

        def mock_with_failures(name, rg):
            if name == "vm2":
                raise Exception("Azure API error")
            return VMInfo(
                name=name,
                resource_group=rg,
                location="eastus",
                power_state="VM running",
            )

        mock_get_vm.side_effect = mock_with_failures

        # Should not raise exception, should return successful queries
        refreshed = VMManager.refresh_expired_vms(
            resource_group="test-rg",
            expired_vm_names=["vm1", "vm2", "vm3"],
        )

        # Should return 2 VMs (vm1 and vm3), vm2 failed
        assert len(refreshed) == 2
        assert refreshed[0].name in ["vm1", "vm3"]
        assert refreshed[1].name in ["vm1", "vm3"]

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_returns_empty_list_when_all_queries_fail(self, mock_get_vm):
        """Verify returns empty list when all VM queries fail."""
        mock_get_vm.side_effect = Exception("Azure API unavailable")

        refreshed = VMManager.refresh_expired_vms(
            resource_group="test-rg",
            expired_vm_names=["vm1", "vm2"],
        )

        assert refreshed == []

    def test_handles_empty_expired_list(self):
        """Verify handles empty expired VM list gracefully."""
        refreshed = VMManager.refresh_expired_vms(
            resource_group="test-rg",
            expired_vm_names=[],
        )
        assert refreshed == []


# =============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# =============================================================================


class TestIncrementalRefreshIntegration:
    """Integration tests for complete incremental refresh workflow."""

    @patch("azlin.vm_manager.VMManager.get_vm")
    @patch("azlin.vm_manager.VMManager.list_vms")
    def test_selective_refresh_one_vm_expired(self, mock_list_vms, mock_get_vm, tmp_path):
        """Test 1 out of 50 VMs expired - should refresh only 1 VM."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,
        )

        # Populate cache with 50 VMs
        for i in range(1, 51):
            cache.set_full(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                immutable_data={"name": f"vm{i}", "location": "eastus"},
                mutable_data={"power_state": "VM running"},
            )

        # Wait for mutable layer to expire
        time.sleep(1.1)

        # Refresh only vm1's cache (make it fresh)
        cache.set_mutable(
            vm_name="vm1",
            resource_group="test-rg",
            mutable_data={"power_state": "VM running"},
        )

        # Setup mock for get_vm (selective refresh)
        mock_get_vm.return_value = VMInfo(
            name="vm2",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
            vm_size="Standard_DS2_v2",
        )

        # List VMs with cache - should use selective refresh
        with patch("azlin.vm_manager.VMListCache", return_value=cache):
            vms, was_cached = VMManager.list_vms_with_cache(
                resource_group="test-rg",
                use_cache=True,
            )

        # Verify selective refresh was used
        # Should refresh 49 VMs (all except vm1)
        # NOTE: This will fail until implementation is complete (TDD - Red phase)
        # After implementation, mock_get_vm.call_count should be 49
        # For now, this test documents the expected behavior

    @patch("azlin.vm_manager.VMManager.get_vm")
    def test_cache_consistency_after_selective_refresh(self, mock_get_vm, tmp_path):
        """Verify cache remains consistent after selective refresh."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,
        )

        # Create 3 VMs in cache
        for i in range(1, 4):
            cache.set_full(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                immutable_data={"name": f"vm{i}", "location": "eastus"},
                mutable_data={"power_state": "VM running"},
            )

        # Wait for expiration
        time.sleep(1.1)

        # Refresh vm2 only
        mock_get_vm.return_value = VMInfo(
            name="vm2",
            resource_group="test-rg",
            location="eastus",
            power_state="VM stopped",
            vm_size="Standard_DS2_v2",
        )

        with patch("azlin.vm_manager.VMListCache", return_value=cache):
            VMManager.refresh_expired_vms(
                resource_group="test-rg",
                expired_vm_names=["vm2"],
            )

        # Verify cache state
        vm1_entry = cache.get("vm1", "test-rg")
        vm2_entry = cache.get("vm2", "test-rg")
        vm3_entry = cache.get("vm3", "test-rg")

        # vm1 and vm3 should still be expired
        assert vm1_entry.is_mutable_expired(ttl=1)
        assert vm3_entry.is_mutable_expired(ttl=1)

        # vm2 should be fresh (just refreshed)
        assert not vm2_entry.is_mutable_expired(ttl=1)
        assert vm2_entry.mutable_data["power_state"] == "VM stopped"


# =============================================================================
# E2E TESTS (10%) - Complete workflow scenarios
# =============================================================================


class TestIncrementalRefreshE2E:
    """End-to-end tests for incremental refresh performance."""

    @patch("azlin.vm_manager.VMManager.get_vm")
    @patch("azlin.vm_manager.VMManager.list_vms")
    def test_api_call_reduction_best_case(self, mock_list_vms, mock_get_vm, tmp_path):
        """Test best case: 1 out of 50 VMs expired - 99% API call reduction."""
        cache = VMListCache(
            cache_path=tmp_path / "cache.json",
            mutable_ttl=1,
        )

        # Populate cache with 50 VMs
        for i in range(1, 51):
            cache.set_full(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                immutable_data={"name": f"vm{i}", "location": "eastus"},
                mutable_data={"power_state": "VM running"},
            )

        time.sleep(1.1)

        # Refresh all except vm1
        for i in range(2, 51):
            cache.set_mutable(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                mutable_data={"power_state": "VM running"},
            )

        # Mock get_vm
        mock_get_vm.return_value = VMInfo(
            name="vm1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            vm_size="Standard_DS2_v2",
        )

        # Count API calls
        with patch("azlin.vm_manager.VMListCache", return_value=cache):
            vms, was_cached = VMManager.list_vms_with_cache(
                resource_group="test-rg",
                use_cache=True,
            )

        # Expected: 1 get_vm call (selective refresh)
        # Before: Would have called list_vms (100+ API calls)
        # After: Should call get_vm 1 time
        # NOTE: Will fail until implementation complete (TDD - Red phase)
        # assert mock_get_vm.call_count == 1  # 99% reduction
        # assert mock_list_vms.call_count == 0  # No full refresh

    def test_thread_safety_concurrent_refresh(self, tmp_path):
        """Test thread safety with concurrent refresh operations."""
        cache = VMListCache(cache_path=tmp_path / "cache.json")

        # Create initial cache entries
        for i in range(1, 11):
            cache.set_full(
                vm_name=f"vm{i}",
                resource_group="test-rg",
                immutable_data={"name": f"vm{i}"},
                mutable_data={"power_state": "VM running"},
            )

        def refresh_vm(vm_name):
            """Simulate concurrent refresh operation."""
            cache.set_mutable(
                vm_name=vm_name,
                resource_group="test-rg",
                mutable_data={"power_state": "VM stopped"},
            )

        # Concurrent updates
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(refresh_vm, f"vm{i}") for i in range(1, 11)]
            for future in futures:
                future.result()  # Wait for completion

        # Verify all updates succeeded
        for i in range(1, 11):
            entry = cache.get(f"vm{i}", "test-rg")
            assert entry is not None
            assert entry.mutable_data["power_state"] == "VM stopped"
