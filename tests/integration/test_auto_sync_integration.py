"""Integration tests for auto-sync SSH keys feature."""

import pytest

from azlin.modules.vm_key_sync import VMKeySync


class TestAutoSyncIntegration:
    """Integration tests for auto-sync SSH keys feature."""

    @pytest.mark.skip("Integration tests require real Azure environment")
    def test_connect_with_auto_sync_enabled(self):
        """Test connection with auto_sync_keys=true."""
        pass

    def test_vm_key_sync_imports(self):
        """Test VMKeySync can be instantiated."""
        sync = VMKeySync()
        assert sync is not None
