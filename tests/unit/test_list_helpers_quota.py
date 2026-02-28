"""Verification tests for Issue #687 - quota display with cached VMs.

Tests verify that the `-q` flag displays quota information regardless of
whether VM data is cached or fresh.
"""

from unittest.mock import MagicMock, patch

import pytest

from azlin.commands._list_helpers import enrich_vm_data
from azlin.quota_manager import QuotaInfo
from azlin.vm_manager import VMInfo


@pytest.fixture
def mock_vms():
    """Create mock VMs for testing."""
    vm1 = MagicMock(spec=VMInfo)
    vm1.location = "eastus"
    vm1.is_running.return_value = True
    vm1.public_ip = None
    vm1.private_ip = "10.0.0.1"

    vm2 = MagicMock(spec=VMInfo)
    vm2.location = "westus"
    vm2.is_running.return_value = True
    vm2.public_ip = None
    vm2.private_ip = "10.0.0.2"

    return [vm1, vm2]


@pytest.fixture
def mock_quota_info():
    """Create mock quota information."""
    return [
        QuotaInfo(region="eastus", quota_name="cores", current_usage=10, limit=100),
        QuotaInfo(
            region="eastus",
            quota_name="Standard DSv2 Family vCPUs",
            current_usage=5,
            limit=50,
        ),
    ]


@patch("azlin.commands._list_helpers.QuotaManager")
def test_quota_collected_when_cached_true(mock_quota_manager, mock_vms, mock_quota_info):
    """PRIMARY TEST: Verify quota IS collected when VM data is cached.

    This is the main bug fix test - before the fix, this would fail because
    quota collection was skipped when was_cached=True.
    """
    # Arrange
    mock_quota_manager.get_regional_quotas.return_value = {
        "eastus": mock_quota_info,
        "westus": mock_quota_info,
    }

    # Act
    quota_by_region, _, _, _, _ = enrich_vm_data(
        vms=mock_vms,
        was_cached=True,  # VM data from cache
        show_quota=True,  # User requested quota with -q flag
        show_tmux=False,
        with_latency=False,
        show_procs=False,
        resource_group="test-rg",
        verbose=False,
        console=MagicMock(),
        _collect_tmux_sessions_fn=lambda vms, with_latency=False: ({}, {}),
        _cache_tmux_sessions_fn=lambda *args: None,
    )

    # Assert
    assert len(quota_by_region) > 0, (
        "Quota should be collected when show_quota=True, even with was_cached=True"
    )
    assert "eastus" in quota_by_region or "westus" in quota_by_region


@patch("azlin.commands._list_helpers.QuotaManager")
def test_quota_collected_when_cached_false(mock_quota_manager, mock_vms, mock_quota_info):
    """REGRESSION TEST: Verify quota still works when VM data is fresh (not cached).

    This ensures the fix doesn't break existing behavior.
    """
    # Arrange
    mock_quota_manager.get_regional_quotas.return_value = {
        "eastus": mock_quota_info,
        "westus": mock_quota_info,
    }

    # Act
    quota_by_region, _, _, _, _ = enrich_vm_data(
        vms=mock_vms,
        was_cached=False,  # VM data is fresh
        show_quota=True,  # User requested quota with -q flag
        show_tmux=False,
        with_latency=False,
        show_procs=False,
        resource_group="test-rg",
        verbose=False,
        console=MagicMock(),
        _collect_tmux_sessions_fn=lambda vms, with_latency=False: ({}, {}),
        _cache_tmux_sessions_fn=lambda *args: None,
    )

    # Assert
    assert len(quota_by_region) > 0, (
        "Quota should be collected when show_quota=True and was_cached=False"
    )


@patch("azlin.commands._list_helpers.QuotaManager")
def test_quota_not_collected_when_flag_false(mock_quota_manager, mock_vms):
    """NEGATIVE TEST: Verify quota NOT collected when -q flag is not used."""
    # Act
    quota_by_region, _, _, _, _ = enrich_vm_data(
        vms=mock_vms,
        was_cached=True,
        show_quota=False,  # User did NOT request quota
        show_tmux=False,
        with_latency=False,
        show_procs=False,
        resource_group="test-rg",
        verbose=False,
        console=MagicMock(),
        _collect_tmux_sessions_fn=lambda vms, with_latency=False: ({}, {}),
        _cache_tmux_sessions_fn=lambda *args: None,
    )

    # Assert
    assert len(quota_by_region) == 0, "Quota should NOT be collected when show_quota=False"
    mock_quota_manager.get_regional_quotas.assert_not_called()
