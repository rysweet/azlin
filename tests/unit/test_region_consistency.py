"""Test region consistency between config_manager and vm_provisioning.

This test prevents Issue #421 from recurring by ensuring all regions in
COMMON_REGIONS are also in VALID_REGIONS.

Testing Philosophy:
- TDD approach: Tests written BEFORE implementation
- Clear error messages showing which regions are missing
- Regression test for specific issue (#421)
- Fast unit tests with no external dependencies
"""

from azlin.config_manager import COMMON_REGIONS
from azlin.vm_provisioning import VMProvisioner


class TestRegionConsistency:
    """Ensure region configuration consistency across modules."""

    def test_common_regions_are_valid(self):
        """All regions in COMMON_REGIONS must be in VALID_REGIONS.

        This test prevents configuration drift where COMMON_REGIONS
        contains regions not recognized as valid by the provisioning system.

        Should FAIL initially because westcentralus is in COMMON_REGIONS
        but not in VALID_REGIONS.
        """
        # Find regions in COMMON_REGIONS that are not in VALID_REGIONS
        invalid_common_regions = [
            region for region in COMMON_REGIONS if region not in VMProvisioner.VALID_REGIONS
        ]

        # Build detailed error message
        error_msg = (
            f"Found {len(invalid_common_regions)} region(s) in COMMON_REGIONS "
            f"that are not in VALID_REGIONS: {invalid_common_regions}\n"
            f"COMMON_REGIONS: {COMMON_REGIONS}\n"
            f"VALID_REGIONS: {VMProvisioner.VALID_REGIONS}\n"
            f"All COMMON_REGIONS must also be in VALID_REGIONS to prevent "
            f"provisioning failures."
        )

        assert len(invalid_common_regions) == 0, error_msg

    def test_westcentralus_specifically(self):
        """Regression test for Issue #421: westcentralus must be valid.

        Issue #421 occurred because westcentralus was in COMMON_REGIONS
        but not in VALID_REGIONS, causing provisioning to fail.

        This test explicitly verifies the fix for that specific issue.

        Should FAIL initially because westcentralus is not in VALID_REGIONS.
        """
        assert "westcentralus" in VMProvisioner.VALID_REGIONS, (
            "westcentralus must be in VALID_REGIONS (Issue #421 fix). "
            f"Current VALID_REGIONS: {VMProvisioner.VALID_REGIONS}"
        )

    def test_valid_regions_not_empty(self):
        """VALID_REGIONS must contain at least one region.

        Sanity check to ensure VALID_REGIONS is properly configured.
        """
        assert len(VMProvisioner.VALID_REGIONS) > 0, (
            "VALID_REGIONS must contain at least one region"
        )

    def test_common_regions_not_empty(self):
        """COMMON_REGIONS must contain at least one region.

        Sanity check to ensure COMMON_REGIONS is properly configured.
        """
        assert len(COMMON_REGIONS) > 0, "COMMON_REGIONS must contain at least one region"


class TestRegionDataStructures:
    """Verify the data structures of region constants."""

    def test_valid_regions_is_set(self):
        """VALID_REGIONS should be a set (immutable, no duplicates)."""
        assert isinstance(VMProvisioner.VALID_REGIONS, set), (
            f"VALID_REGIONS should be a set, got {type(VMProvisioner.VALID_REGIONS)}"
        )

    def test_common_regions_is_list(self):
        """COMMON_REGIONS should be a list for order preservation."""
        assert isinstance(COMMON_REGIONS, list), (
            f"COMMON_REGIONS should be a list, got {type(COMMON_REGIONS)}"
        )

    def test_no_duplicate_common_regions(self):
        """COMMON_REGIONS should not contain duplicates."""
        assert len(COMMON_REGIONS) == len(set(COMMON_REGIONS)), (
            f"COMMON_REGIONS contains duplicates: "
            f"{[r for r in COMMON_REGIONS if COMMON_REGIONS.count(r) > 1]}"
        )
