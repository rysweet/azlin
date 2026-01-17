"""Unit tests for QuotaManager memory query functionality.

Tests the get_vm_size_memory() method following TDD approach.
These tests WILL FAIL until implementation is complete.

Testing Coverage:
- Known VM sizes return correct memory
- Unknown VM sizes return 0
- Edge cases (empty string, None, malformed)
- Case sensitivity
- Common VM families (B, D, E, F series)
"""

from azlin.quota_manager import QuotaManager


class TestQuotaManagerMemory:
    """Unit tests for memory query functionality."""

    # ============================================================================
    # HAPPY PATH TESTS (Known VM Sizes)
    # ============================================================================

    def test_get_vm_size_memory_b_series(self):
        """Test B-series (Burstable) VM sizes return correct memory."""
        # Standard_B1s: 1 vCPU, 1 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B1s") == 1

        # Standard_B1ms: 1 vCPU, 2 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B1ms") == 2

        # Standard_B2s: 2 vCPU, 4 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B2s") == 4

        # Standard_B2ms: 2 vCPU, 8 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B2ms") == 8

        # Standard_B4ms: 4 vCPU, 16 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B4ms") == 16

        # Standard_B8ms: 8 vCPU, 32 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B8ms") == 32

    def test_get_vm_size_memory_d_series(self):
        """Test D-series (General Purpose) VM sizes return correct memory."""
        # Standard_D2s_v3: 2 vCPU, 8 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_D2s_v3") == 8

        # Standard_D4s_v3: 4 vCPU, 16 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_D4s_v3") == 16

        # Standard_D8s_v3: 8 vCPU, 32 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_D8s_v3") == 32

        # Standard_D16s_v3: 16 vCPU, 64 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_D16s_v3") == 64

        # Standard_D32s_v3: 32 vCPU, 128 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_D32s_v3") == 128

    def test_get_vm_size_memory_e_series(self):
        """Test E-series (Memory Optimized) VM sizes return correct memory."""
        # Standard_E2as_v5: 2 vCPU, 16 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E2as_v5") == 16

        # Standard_E4as_v5: 4 vCPU, 32 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E4as_v5") == 32

        # Standard_E8as_v5: 8 vCPU, 64 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E8as_v5") == 64

        # Standard_E16as_v5: 16 vCPU, 128 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E16as_v5") == 128

        # Standard_E32as_v5: 32 vCPU, 256 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E32as_v5") == 256

        # Standard_E48as_v5: 48 vCPU, 384 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E48as_v5") == 384

        # Standard_E64as_v5: 64 vCPU, 512 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_E64as_v5") == 512

    def test_get_vm_size_memory_f_series(self):
        """Test F-series (Compute Optimized) VM sizes return correct memory."""
        # Standard_F2s_v2: 2 vCPU, 4 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_F2s_v2") == 4

        # Standard_F4s_v2: 4 vCPU, 8 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_F4s_v2") == 8

        # Standard_F8s_v2: 8 vCPU, 16 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_F8s_v2") == 16

        # Standard_F16s_v2: 16 vCPU, 32 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_F16s_v2") == 32

        # Standard_F32s_v2: 32 vCPU, 64 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_F32s_v2") == 64

    # ============================================================================
    # EDGE CASE TESTS (Unknown/Invalid VM Sizes)
    # ============================================================================

    def test_get_vm_size_memory_unknown_size(self):
        """Test unknown VM size returns 0."""
        assert QuotaManager.get_vm_size_memory("Standard_UnknownSize") == 0
        assert QuotaManager.get_vm_size_memory("Custom_VM_Size") == 0
        assert QuotaManager.get_vm_size_memory("NonExistent_Size") == 0

    def test_get_vm_size_memory_empty_string(self):
        """Test empty string returns 0."""
        assert QuotaManager.get_vm_size_memory("") == 0

    def test_get_vm_size_memory_whitespace_only(self):
        """Test whitespace-only string returns 0."""
        assert QuotaManager.get_vm_size_memory("   ") == 0
        assert QuotaManager.get_vm_size_memory("\t") == 0
        assert QuotaManager.get_vm_size_memory("\n") == 0

    def test_get_vm_size_memory_case_sensitive(self):
        """Test that VM size lookup is case-sensitive (exact match required)."""
        # Correct case should work
        assert QuotaManager.get_vm_size_memory("Standard_B2s") == 4

        # Wrong case should return 0 (not found)
        assert QuotaManager.get_vm_size_memory("standard_b2s") == 0
        assert QuotaManager.get_vm_size_memory("STANDARD_B2S") == 0
        assert QuotaManager.get_vm_size_memory("Standard_b2s") == 0

    def test_get_vm_size_memory_malformed_input(self):
        """Test malformed VM size strings return 0."""
        assert QuotaManager.get_vm_size_memory("NotAValidFormat") == 0
        assert QuotaManager.get_vm_size_memory("B2s") == 0  # Missing Standard_ prefix
        assert QuotaManager.get_vm_size_memory("Standard_") == 0  # Missing size
        assert QuotaManager.get_vm_size_memory("_B2s") == 0  # Malformed prefix

    def test_get_vm_size_memory_special_characters(self):
        """Test VM sizes with special characters return 0."""
        assert QuotaManager.get_vm_size_memory("Standard_B2s@") == 0
        assert QuotaManager.get_vm_size_memory("Standard-B2s") == 0  # Wrong separator
        assert QuotaManager.get_vm_size_memory("Standard B2s") == 0  # Space instead of underscore

    # ============================================================================
    # BOUNDARY TESTS
    # ============================================================================

    def test_get_vm_size_memory_smallest_vm(self):
        """Test smallest VM size (1 GB)."""
        # Standard_B1s is one of the smallest with 1 GB RAM
        assert QuotaManager.get_vm_size_memory("Standard_B1s") == 1

    def test_get_vm_size_memory_largest_common_vm(self):
        """Test large VM sizes."""
        # Standard_E64as_v5: 64 vCPU, 512 GB RAM (one of the largest common sizes)
        assert QuotaManager.get_vm_size_memory("Standard_E64as_v5") == 512

    # ============================================================================
    # CONSISTENCY TESTS
    # ============================================================================

    def test_get_vm_size_memory_consistent_with_vcpus(self):
        """Test that all VM sizes in VM_SIZE_VCPUS also have memory mappings."""
        # If a VM size has vCPU info, it should also have memory info (or 0 if unknown)
        # This test verifies consistency between the two mappings

        # Get all VM sizes that have vCPU mappings
        for vm_size in QuotaManager.VM_SIZE_VCPUS:
            memory = QuotaManager.get_vm_size_memory(vm_size)
            # Memory should be > 0 for all known VM sizes
            assert memory > 0, f"VM size {vm_size} has vCPU mapping but memory is {memory}"

    def test_get_vm_size_memory_return_type(self):
        """Test that return value is always an integer."""
        # Known size should return int
        result = QuotaManager.get_vm_size_memory("Standard_B2s")
        assert isinstance(result, int)
        assert result == 4

        # Unknown size should return int (0)
        result = QuotaManager.get_vm_size_memory("Unknown_Size")
        assert isinstance(result, int)
        assert result == 0

    # ============================================================================
    # PERFORMANCE TESTS
    # ============================================================================

    def test_get_vm_size_memory_no_api_calls(self, monkeypatch):
        """Test that memory lookup does NOT make Azure API calls (hardcoded only)."""
        # Mock subprocess to ensure no Azure CLI calls are made
        mock_subprocess = None

        def mock_run(*args, **kwargs):
            nonlocal mock_subprocess
            raise AssertionError("Memory lookup should NOT make subprocess calls")

        monkeypatch.setattr("subprocess.run", mock_run)

        # These should work without any API calls
        assert QuotaManager.get_vm_size_memory("Standard_B2s") == 4
        assert QuotaManager.get_vm_size_memory("Standard_D4s_v3") == 16
        assert QuotaManager.get_vm_size_memory("Unknown_Size") == 0

    def test_get_vm_size_memory_fast_lookup(self):
        """Test that memory lookup is fast (< 1ms)."""
        import time

        start = time.perf_counter()
        for _ in range(1000):
            QuotaManager.get_vm_size_memory("Standard_B2s")
        elapsed = time.perf_counter() - start

        # 1000 lookups should take less than 10ms (very generous threshold)
        assert elapsed < 0.01, f"Memory lookup too slow: {elapsed * 1000:.2f}ms for 1000 lookups"


class TestQuotaManagerMemoryMapping:
    """Test the VM_SIZE_MEMORY mapping dictionary itself."""

    def test_vm_size_memory_mapping_exists(self):
        """Test that VM_SIZE_MEMORY class attribute exists."""
        assert hasattr(QuotaManager, "VM_SIZE_MEMORY")
        assert isinstance(QuotaManager.VM_SIZE_MEMORY, dict)

    def test_vm_size_memory_mapping_not_empty(self):
        """Test that VM_SIZE_MEMORY has entries."""
        assert len(QuotaManager.VM_SIZE_MEMORY) > 0

    def test_vm_size_memory_mapping_all_positive(self):
        """Test that all memory values are positive integers."""
        for vm_size, memory in QuotaManager.VM_SIZE_MEMORY.items():
            assert isinstance(memory, int), f"{vm_size} memory is not int: {memory}"
            assert memory > 0, f"{vm_size} has invalid memory: {memory}"

    def test_vm_size_memory_mapping_covers_common_sizes(self):
        """Test that VM_SIZE_MEMORY covers all common VM sizes from VM_SIZE_VCPUS."""
        # All VM sizes in VM_SIZE_VCPUS should have memory mappings
        for vm_size in QuotaManager.VM_SIZE_VCPUS:
            assert vm_size in QuotaManager.VM_SIZE_MEMORY, (
                f"VM size {vm_size} missing from VM_SIZE_MEMORY"
            )

    def test_vm_size_memory_mapping_reasonable_values(self):
        """Test that memory values are reasonable (1-1024 GB range for common VMs)."""
        for vm_size, memory in QuotaManager.VM_SIZE_MEMORY.items():
            # Azure VMs typically range from 0.5 GB to 12 TB
            # Common sizes: 1 GB to 1024 GB
            assert 1 <= memory <= 12288, f"{vm_size} has unreasonable memory: {memory} GB"

    def test_vm_size_memory_mapping_format_consistency(self):
        """Test that all VM size keys follow Standard_* naming convention."""
        for vm_size in QuotaManager.VM_SIZE_MEMORY:
            assert vm_size.startswith("Standard_"), (
                f"VM size {vm_size} doesn't start with Standard_"
            )
            assert "_" in vm_size, f"VM size {vm_size} missing underscore separator"
