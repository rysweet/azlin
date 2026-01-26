"""Tests to verify timeout values are correctly set for Windows compatibility."""

import inspect

import pytest

from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.vm_key_sync import DEFAULT_TIMEOUT, VMKeySync


class TestTimeoutValues:
    """Test that timeout values are set appropriately for Windows/WSL2 environments."""

    def test_bastion_detector_responsive_check_timeout_default(self):
        """Verify Azure CLI responsive check has sufficient timeout for Windows."""
        # Get the method signature
        sig = inspect.signature(BastionDetector._check_azure_cli_responsive)
        timeout_param = sig.parameters["timeout"]

        # Should have a default of at least 10 seconds for Windows compatibility
        assert timeout_param.default >= 10, (
            f"Azure CLI responsive check timeout ({timeout_param.default}s) "
            "should be at least 10s for Windows/WSL2 compatibility"
        )

    def test_vm_key_sync_default_timeout(self):
        """Verify VM key sync operations have sufficient timeout for Windows."""
        # DEFAULT_TIMEOUT constant should be at least 60 seconds
        assert DEFAULT_TIMEOUT >= 60, (
            f"VM key sync DEFAULT_TIMEOUT ({DEFAULT_TIMEOUT}s) "
            "should be at least 60s for Windows/WSL2 compatibility"
        )

    def test_vm_key_sync_ensure_key_authorized_timeout_default(self):
        """Verify ensure_key_authorized uses appropriate default timeout."""
        sig = inspect.signature(VMKeySync.ensure_key_authorized)
        timeout_param = sig.parameters["timeout"]

        # Should default to DEFAULT_TIMEOUT
        assert timeout_param.default == DEFAULT_TIMEOUT, (
            f"ensure_key_authorized timeout default ({timeout_param.default}s) "
            f"should match DEFAULT_TIMEOUT ({DEFAULT_TIMEOUT}s)"
        )

    def test_vm_key_sync_check_key_exists_timeout_default(self):
        """Verify check_key_exists uses appropriate default timeout."""
        sig = inspect.signature(VMKeySync.check_key_exists)
        timeout_param = sig.parameters["timeout"]

        # Should default to DEFAULT_TIMEOUT
        assert timeout_param.default == DEFAULT_TIMEOUT, (
            f"check_key_exists timeout default ({timeout_param.default}s) "
            f"should match DEFAULT_TIMEOUT ({DEFAULT_TIMEOUT}s)"
        )

    def test_vm_key_sync_append_key_timeout_default(self):
        """Verify append_key_to_vm uses appropriate default timeout."""
        sig = inspect.signature(VMKeySync.append_key_to_vm)
        timeout_param = sig.parameters["timeout"]

        # Should default to DEFAULT_TIMEOUT
        assert timeout_param.default == DEFAULT_TIMEOUT, (
            f"append_key_to_vm timeout default ({timeout_param.default}s) "
            f"should match DEFAULT_TIMEOUT ({DEFAULT_TIMEOUT}s)"
        )
