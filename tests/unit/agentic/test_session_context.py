"""Tests for SessionContext - context-aware natural language parsing.

Testing Strategy (TDD):
- 60% Unit tests (this file)
- 30% Integration tests
- 10% E2E tests

This module tests pronoun resolution and session state management.
"""

from datetime import datetime, timedelta

from azlin.agentic.session_context import CommandHistoryEntry, SessionContext


class TestSessionContextInitialization:
    """Test SessionContext initialization and basic properties."""

    def test_init_default_max_history(self):
        """SessionContext initializes with default max history of 10."""
        session = SessionContext()
        assert session.max_history == 10
        assert len(session.history) == 0

    def test_init_custom_max_history(self):
        """SessionContext accepts custom max history."""
        session = SessionContext(max_history=5)
        assert session.max_history == 5

    def test_init_creates_empty_state(self):
        """New session has empty history and entities."""
        session = SessionContext()
        assert session.history == []
        assert session.last_entities == {}

    def test_init_generates_session_id(self):
        """SessionContext generates unique session ID."""
        session1 = SessionContext()
        session2 = SessionContext()
        assert session1.session_id != session2.session_id
        assert len(session1.session_id) > 0


class TestAddCommand:
    """Test add_command() - recording commands and entities."""

    def test_add_command_records_request(self):
        """add_command() records the natural language request."""
        session = SessionContext()
        session.add_command("create vm called test", {"vm": ["test"]})

        assert len(session.history) == 1
        assert session.history[0].request == "create vm called test"

    def test_add_command_records_entities(self):
        """add_command() records extracted entities."""
        session = SessionContext()
        entities = {"vm": ["test-vm"], "resource_group": ["my-rg"]}
        session.add_command("create vm test-vm in my-rg", entities)

        assert len(session.history) == 1
        assert session.history[0].entities == entities

    def test_add_command_records_timestamp(self):
        """add_command() records command timestamp."""
        session = SessionContext()
        before = datetime.now()
        session.add_command("create vm test", {"vm": ["test"]})
        after = datetime.now()

        assert len(session.history) == 1
        timestamp = session.history[0].timestamp
        assert before <= timestamp <= after

    def test_add_command_updates_last_entities(self):
        """add_command() updates last_entities dict."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        assert session.last_entities["vm"] == "test"

    def test_add_command_updates_last_entities_multiple(self):
        """add_command() updates last entity when multiple of same type."""
        session = SessionContext()
        entities = {"vm": ["vm1", "vm2", "vm3"]}
        session.add_command("create 3 vms", entities)

        # Last entity should be the last in the list
        assert session.last_entities["vm"] == "vm3"

    def test_add_command_enforces_max_history(self):
        """add_command() removes oldest entry when max_history reached."""
        session = SessionContext(max_history=3)

        # Add 4 commands
        for i in range(4):
            session.add_command(f"command {i}", {"vm": [f"vm{i}"]})

        # Should only have last 3
        assert len(session.history) == 3
        assert session.history[0].request == "command 1"
        assert session.history[1].request == "command 2"
        assert session.history[2].request == "command 3"

    def test_add_command_handles_empty_entities(self):
        """add_command() handles empty entities dict."""
        session = SessionContext()
        session.add_command("list vms", {})

        assert len(session.history) == 1
        assert session.history[0].entities == {}
        assert len(session.last_entities) == 0


class TestResolvePronoun:
    """Test resolve_pronoun() - pronoun to entity name resolution."""

    def test_resolve_pronoun_it_returns_last_entity(self):
        """resolve_pronoun('it') returns last entity of specified type."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        result = session.resolve_pronoun("it", "vm")
        assert result == "test"

    def test_resolve_pronoun_that_returns_last_entity(self):
        """resolve_pronoun('that') returns last entity of specified type."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        result = session.resolve_pronoun("that", "vm")
        assert result == "test"

    def test_resolve_pronoun_returns_none_when_no_entity(self):
        """resolve_pronoun() returns None when entity type not in history."""
        session = SessionContext()

        result = session.resolve_pronoun("it", "vm")
        assert result is None

    def test_resolve_pronoun_returns_most_recent_entity(self):
        """resolve_pronoun() returns most recent entity when multiple exist."""
        session = SessionContext()
        session.add_command("create vm test1", {"vm": ["test1"]})
        session.add_command("create vm test2", {"vm": ["test2"]})

        result = session.resolve_pronoun("it", "vm")
        assert result == "test2"

    def test_resolve_pronoun_handles_different_entity_types(self):
        """resolve_pronoun() works for different entity types."""
        session = SessionContext()
        session.add_command("create vm in my-rg", {"vm": ["test"], "resource_group": ["my-rg"]})

        assert session.resolve_pronoun("it", "vm") == "test"
        assert session.resolve_pronoun("it", "resource_group") == "my-rg"

    def test_resolve_pronoun_case_insensitive(self):
        """resolve_pronoun() is case-insensitive for pronouns."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        assert session.resolve_pronoun("IT", "vm") == "test"
        assert session.resolve_pronoun("It", "vm") == "test"
        assert session.resolve_pronoun("that", "vm") == "test"
        assert session.resolve_pronoun("THAT", "vm") == "test"


class TestGetContext:
    """Test get_context() - context dict for IntentParser."""

    def test_get_context_returns_dict(self):
        """get_context() returns a dictionary."""
        session = SessionContext()
        context = session.get_context()
        assert isinstance(context, dict)

    def test_get_context_includes_last_entities(self):
        """get_context() includes last_entities."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        context = session.get_context()
        assert "last_entities" in context
        assert context["last_entities"]["vm"] == "test"

    def test_get_context_includes_recent_commands(self):
        """get_context() includes recent command history."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        context = session.get_context()
        assert "recent_commands" in context
        assert len(context["recent_commands"]) == 1
        assert "create vm test" in context["recent_commands"][0]

    def test_get_context_limits_recent_commands(self):
        """get_context() limits recent_commands to last 5."""
        session = SessionContext(max_history=10)

        # Add 8 commands
        for i in range(8):
            session.add_command(f"command {i}", {"vm": [f"vm{i}"]})

        context = session.get_context()
        # Should only include last 5 for context
        assert len(context["recent_commands"]) == 5
        assert "command 3" in context["recent_commands"][0]
        assert "command 7" in context["recent_commands"][4]

    def test_get_context_includes_session_metadata(self):
        """get_context() includes session ID and timestamps."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        context = session.get_context()
        assert "session_id" in context
        assert "created_at" in context
        assert "last_used" in context


class TestSessionExpiration:
    """Test session timeout and expiration logic."""

    def test_is_expired_false_for_new_session(self):
        """is_expired() returns False for newly created session."""
        session = SessionContext()
        assert session.is_expired() is False

    def test_is_expired_false_for_recently_used_session(self):
        """is_expired() returns False for recently used session."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})
        assert session.is_expired() is False

    def test_is_expired_true_after_timeout(self):
        """is_expired() returns True after 1 hour idle timeout."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        # Simulate time passing by manually setting last_used
        session.last_used = datetime.now() - timedelta(hours=2)

        assert session.is_expired() is True

    def test_is_expired_custom_timeout(self):
        """is_expired() accepts custom timeout duration."""
        session = SessionContext()
        session.add_command("create vm test", {"vm": ["test"]})

        # Set last_used to 31 minutes ago
        session.last_used = datetime.now() - timedelta(minutes=31)

        # Should not be expired with 1 hour timeout
        assert session.is_expired(timeout_hours=1) is False

        # Should be expired with 30 minute timeout
        assert session.is_expired(timeout_hours=0.5) is True


class TestCommandHistoryEntry:
    """Test CommandHistoryEntry dataclass."""

    def test_command_history_entry_creation(self):
        """CommandHistoryEntry can be created with required fields."""
        entry = CommandHistoryEntry(
            request="create vm test",
            entities={"vm": ["test"]},
            timestamp=datetime.now(),
        )

        assert entry.request == "create vm test"
        assert entry.entities == {"vm": ["test"]}
        assert isinstance(entry.timestamp, datetime)

    def test_command_history_entry_equality(self):
        """CommandHistoryEntry supports equality comparison."""
        timestamp = datetime.now()
        entry1 = CommandHistoryEntry(
            request="create vm test", entities={"vm": ["test"]}, timestamp=timestamp
        )
        entry2 = CommandHistoryEntry(
            request="create vm test", entities={"vm": ["test"]}, timestamp=timestamp
        )

        assert entry1 == entry2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_resolve_pronoun_with_empty_session(self):
        """resolve_pronoun() returns None for empty session."""
        session = SessionContext()
        assert session.resolve_pronoun("it", "vm") is None

    def test_get_context_with_empty_session(self):
        """get_context() works with empty session."""
        session = SessionContext()
        context = session.get_context()

        assert context["last_entities"] == {}
        assert context["recent_commands"] == []

    def test_add_command_with_none_entities(self):
        """add_command() handles None entities gracefully."""
        session = SessionContext()
        # Should not raise exception
        session.add_command("list vms", None)  # type: ignore

        assert len(session.history) == 1

    def test_max_history_zero(self):
        """SessionContext with max_history=0 keeps no history."""
        session = SessionContext(max_history=0)
        session.add_command("create vm test", {"vm": ["test"]})

        # History should be empty
        assert len(session.history) == 0
        # But last_entities should still be updated
        assert session.last_entities["vm"] == "test"

    def test_max_history_one(self):
        """SessionContext with max_history=1 keeps only last command."""
        session = SessionContext(max_history=1)
        session.add_command("command 1", {"vm": ["vm1"]})
        session.add_command("command 2", {"vm": ["vm2"]})

        assert len(session.history) == 1
        assert session.history[0].request == "command 2"


class TestIntegration:
    """Integration tests for SessionContext."""

    def test_full_workflow_context_resolution(self):
        """Test complete workflow: add commands, resolve pronouns, get context."""
        session = SessionContext()

        # Step 1: Create VM
        session.add_command("create vm called test-vm", {"vm": ["test-vm"]})

        # Step 2: Verify pronoun resolution
        assert session.resolve_pronoun("it", "vm") == "test-vm"

        # Step 3: Add another command
        session.add_command("start it", {"vm": ["test-vm"]})

        # Step 4: Get context for parser
        context = session.get_context()

        assert context["last_entities"]["vm"] == "test-vm"
        assert len(context["recent_commands"]) == 2
        assert "create vm called test-vm" in context["recent_commands"][0]

    def test_multiple_entity_types(self):
        """Test tracking multiple entity types simultaneously."""
        session = SessionContext()

        session.add_command(
            "create vm test in my-rg westus2",
            {"vm": ["test"], "resource_group": ["my-rg"], "region": ["westus2"]},
        )

        # All entity types should be resolvable
        assert session.resolve_pronoun("it", "vm") == "test"
        assert session.resolve_pronoun("it", "resource_group") == "my-rg"
        assert session.resolve_pronoun("it", "region") == "westus2"

    def test_context_for_multiple_vms(self):
        """Test context tracking when creating multiple VMs."""
        session = SessionContext()

        # Create 3 VMs
        session.add_command("create 3 vms test-{1,2,3}", {"vm": ["test-1", "test-2", "test-3"]})

        # Last entity should be test-3
        assert session.resolve_pronoun("it", "vm") == "test-3"

        # Context should include the original request
        context = session.get_context()
        assert "create 3 vms test-{1,2,3}" in context["recent_commands"]
        # Entities are tracked separately in last_entities
        assert context["last_entities"]["vm"] == "test-3"
