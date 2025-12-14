"""Integration test for cleanup user interaction workflow."""

from azlin.modules.interaction_handler import CLIInteractionHandler, MockInteractionHandler


class TestCleanupUserInteraction:
    """Test user interaction during cleanup workflow."""

    def test_mock_interaction_handler_confirmation(self):
        """Test mock interaction handler for testing."""
        handler = MockInteractionHandler(confirm_responses={"cleanup": True, "delete_all": False})

        # Test confirmation
        assert handler.confirm("Proceed with cleanup?", key="cleanup") is True
        assert handler.confirm("Delete all resources?", key="delete_all") is False

    def test_cli_interaction_handler_creation(self):
        """Test creating CLI interaction handler."""
        handler = CLIInteractionHandler()
        assert handler is not None
