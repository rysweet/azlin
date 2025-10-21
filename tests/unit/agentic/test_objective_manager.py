"""Unit tests for ObjectiveManager (Phase 1).

Tests objective state persistence with proper API.
"""

import json
import pytest
from pathlib import Path
from datetime import datetime
import time

from azlin.agentic.objective_manager import ObjectiveManager, ObjectiveError
from azlin.agentic.types import Intent, ObjectiveStatus, Strategy


class TestObjectiveManagerBasics:
    """Test basic ObjectiveManager operations."""

    def test_initialize_with_default_dir(self, temp_objectives_dir):
        """Test initializing with custom directory."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)
        assert manager is not None
        assert manager.objectives_dir == temp_objectives_dir

    def test_create_objectives_dir_if_missing(self, temp_config_dir):
        """Test automatically creating objectives directory."""
        objectives_dir = temp_config_dir / "objectives"
        assert not objectives_dir.exists()

        manager = ObjectiveManager(objectives_dir=objectives_dir)

        assert objectives_dir.exists()

    def test_create_new_objective(self, temp_objectives_dir):
        """Test creating new objective."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm"},
            confidence=0.95,
            azlin_commands=[],
        )

        objective = manager.create(
            natural_language="Create a test VM",
            intent=intent,
        )

        assert objective.id
        assert objective.status == ObjectiveStatus.PENDING
        assert objective.natural_language == "Create a test VM"
        assert objective.intent.intent == "provision_vm"

    def test_save_objective_to_file(self, temp_objectives_dir):
        """Test objective is saved to file."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)

        objective_file = temp_objectives_dir / f"{objective.id}.json"
        assert objective_file.exists()

        # Verify file content
        with open(objective_file) as f:
            saved_data = json.load(f)
        assert saved_data["id"] == objective.id


class TestObjectiveLoading:
    """Test loading objectives from disk."""

    def test_load_objective_by_id(self, temp_objectives_dir):
        """Test loading objective by ID."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        created = manager.create("Test", intent)
        loaded = manager.load(created.id)

        assert loaded.id == created.id
        assert loaded.status == ObjectiveStatus.PENDING

    def test_load_nonexistent_objective(self, temp_objectives_dir):
        """Test loading nonexistent objective raises error."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        with pytest.raises(FileNotFoundError, match="Objective not found"):
            manager.load("nonexistent-id")

    def test_list_all_objectives(self, temp_objectives_dir):
        """Test listing all objectives."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        # Create multiple objectives
        for i in range(3):
            manager.create(f"Test {i}", intent)

        objectives = manager.list_objectives()

        assert len(objectives) == 3

    def test_list_objectives_by_status(self, temp_objectives_dir):
        """Test filtering objectives by status."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        # Create objectives with different statuses
        obj1 = manager.create("Test 1", intent)
        obj2 = manager.create("Test 2", intent)
        obj3 = manager.create("Test 3", intent)

        manager.update(obj2.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(obj3.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(obj3.id, status=ObjectiveStatus.COMPLETED)

        in_progress = manager.list_objectives(status=ObjectiveStatus.IN_PROGRESS)
        assert len(in_progress) == 1
        assert in_progress[0].status == ObjectiveStatus.IN_PROGRESS


class TestObjectiveUpdates:
    """Test updating objectives."""

    def test_update_objective_status(self, temp_objectives_dir):
        """Test updating objective status."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        assert objective.status == ObjectiveStatus.PENDING

        manager.update(objective.id, status=ObjectiveStatus.IN_PROGRESS)

        updated = manager.load(objective.id)
        assert updated.status == ObjectiveStatus.IN_PROGRESS

    def test_update_multiple_fields(self, temp_objectives_dir):
        """Test updating multiple fields atomically."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)

        manager.update(
            objective.id,
            status=ObjectiveStatus.IN_PROGRESS,
            selected_strategy=Strategy.TERRAFORM,
        )

        updated = manager.load(objective.id)
        assert updated.status == ObjectiveStatus.IN_PROGRESS
        assert updated.selected_strategy == Strategy.TERRAFORM

    def test_auto_update_timestamp(self, temp_objectives_dir):
        """Test updated_at timestamp is automatically updated."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        original_timestamp = objective.updated_at

        time.sleep(0.1)
        manager.update(objective.id, status=ObjectiveStatus.IN_PROGRESS)

        updated = manager.load(objective.id)
        assert updated.updated_at != original_timestamp

    def test_append_execution_history(self, temp_objectives_dir):
        """Test appending to execution history."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)

        manager.append_history(
            objective.id,
            {
                "timestamp": datetime.now().isoformat(),
                "action": "strategy_selected",
                "details": {"strategy": "azure_cli"},
            },
        )

        updated = manager.load(objective.id)
        assert len(updated.execution_history) == 1
        assert updated.execution_history[0]["action"] == "strategy_selected"


class TestStateTransitions:
    """Test valid state transitions."""

    def test_valid_transition_pending_to_in_progress(self, temp_objectives_dir):
        """Test valid transition: pending → in_progress."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        manager.update(objective.id, status=ObjectiveStatus.IN_PROGRESS)

        assert manager.load(objective.id).status == ObjectiveStatus.IN_PROGRESS

    def test_valid_transition_in_progress_to_completed(self, temp_objectives_dir):
        """Test valid transition: in_progress → completed."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        manager.update(objective.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(objective.id, status=ObjectiveStatus.COMPLETED)

        assert manager.load(objective.id).status == ObjectiveStatus.COMPLETED

    def test_invalid_transition_completed_to_pending(self, temp_objectives_dir):
        """Test invalid transition: completed → pending."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        manager.update(objective.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(objective.id, status=ObjectiveStatus.COMPLETED)

        with pytest.raises(ValueError, match="Invalid state transition"):
            manager.update(objective.id, status=ObjectiveStatus.PENDING)

    def test_get_valid_transitions(self):
        """Test getting valid transitions map."""
        manager = ObjectiveManager()

        transitions = manager.get_valid_transitions()

        assert "pending" in transitions
        assert "in_progress" in transitions["pending"]
        assert "completed" in transitions["in_progress"]
        assert "failed" in transitions["in_progress"]


class TestRetryTracking:
    """Test retry count tracking."""

    def test_increment_retry_count(self, temp_objectives_dir):
        """Test incrementing retry count."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        assert objective.retry_count == 0

        manager.increment_retry(objective.id)

        updated = manager.load(objective.id)
        assert updated.retry_count == 1

    def test_max_retries_reached(self, temp_objectives_dir):
        """Test detecting max retries reached."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent, max_retries=3)

        for _ in range(3):
            manager.increment_retry(objective.id)

        assert manager.has_max_retries_reached(objective.id) is True

    def test_reset_retry_count(self, temp_objectives_dir):
        """Test resetting retry count after success."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        manager.increment_retry(objective.id)
        manager.increment_retry(objective.id)

        manager.reset_retry_count(objective.id)

        updated = manager.load(objective.id)
        assert updated.retry_count == 0


class TestStateRecovery:
    """Test state recovery after crashes."""

    def test_recover_in_progress_objectives(self, temp_objectives_dir):
        """Test recovering in_progress objectives after restart."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        # Create in_progress objectives
        obj1 = manager.create("Test 1", intent)
        obj2 = manager.create("Test 2", intent)

        manager.update(obj1.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(obj2.id, status=ObjectiveStatus.IN_PROGRESS)
        manager.update(obj2.id, status=ObjectiveStatus.COMPLETED)

        # Simulate restart
        new_manager = ObjectiveManager(objectives_dir=temp_objectives_dir)
        recoverable = new_manager.recover_incomplete_objectives()

        assert len(recoverable) == 1
        assert recoverable[0].id == obj1.id


class TestSerialization:
    """Test state serialization and deserialization."""

    def test_serialize_datetime_fields(self, temp_objectives_dir):
        """Test datetime fields are serialized to ISO format."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)

        # Load raw JSON
        objective_file = temp_objectives_dir / f"{objective.id}.json"
        with open(objective_file) as f:
            raw_data = json.load(f)

        # Datetime fields should be strings in ISO format
        assert isinstance(raw_data["created_at"], str)
        assert "T" in raw_data["created_at"]  # ISO 8601 format

    def test_handle_invalid_json(self, temp_objectives_dir):
        """Test handling corrupted JSON files."""
        # Create corrupted JSON file
        corrupted_file = temp_objectives_dir / "corrupted.json"
        corrupted_file.write_text("{invalid json")

        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        with pytest.raises(ObjectiveError):
            manager.load("corrupted")


class TestBoundaryConditions:
    """Test boundary conditions and error handling."""

    def test_empty_natural_language(self, temp_objectives_dir):
        """Test handling empty natural language input."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        with pytest.raises(ValueError, match="Natural language cannot be empty"):
            manager.create("", intent)

    def test_very_long_objective_text(self, temp_objectives_dir):
        """Test handling very long objective text."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        long_text = "Create VM " * 10000  # 100KB text
        objective = manager.create(long_text, intent)

        assert len(objective.natural_language) > 10000

    def test_delete_objective(self, temp_objectives_dir):
        """Test deleting an objective."""
        manager = ObjectiveManager(objectives_dir=temp_objectives_dir)

        intent = Intent(
            intent="test",
            parameters={},
            confidence=0.9,
            azlin_commands=[],
        )

        objective = manager.create("Test", intent)
        objective_file = temp_objectives_dir / f"{objective.id}.json"

        assert objective_file.exists()

        manager.delete(objective.id)

        assert not objective_file.exists()
