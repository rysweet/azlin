"""Tests for goal parsing module."""

import pytest

from azlin.doit.goals import GoalParser, GoalStatus, ResourceType


class TestGoalParser:
    """Test goal parsing functionality."""

    def test_parse_simple_request(self):
        """Test parsing a simple request."""
        parser = GoalParser()
        request = "Give me App Service with Cosmos DB"

        parsed = parser.parse(request)

        assert parsed is not None
        assert parsed.raw_request == request
        assert parsed.goal_hierarchy is not None

        hierarchy = parsed.goal_hierarchy
        assert len(hierarchy.goals) > 0

        # Should have at least: RG, App Service, Cosmos DB
        types = [g.type for g in hierarchy.goals]
        assert ResourceType.RESOURCE_GROUP in types
        assert ResourceType.APP_SERVICE in types or ResourceType.APP_SERVICE_PLAN in types
        assert ResourceType.COSMOS_DB in types

    def test_parse_complex_request(self):
        """Test parsing a complex request."""
        parser = GoalParser()
        request = "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

        parsed = parser.parse(request)
        hierarchy = parsed.goal_hierarchy

        assert hierarchy is not None
        types = [g.type for g in hierarchy.goals]

        # Should have all requested resources
        assert ResourceType.RESOURCE_GROUP in types
        assert ResourceType.STORAGE_ACCOUNT in types
        assert ResourceType.KEY_VAULT in types
        assert ResourceType.COSMOS_DB in types
        assert ResourceType.API_MANAGEMENT in types

    def test_dependency_levels(self):
        """Test that goals have correct dependency levels."""
        parser = GoalParser()
        request = "Give me App Service with Cosmos DB"

        parsed = parser.parse(request)
        hierarchy = parsed.goal_hierarchy

        # Level 0 should be resource group
        level_0 = hierarchy.get_goals_by_level(0)
        assert len(level_0) > 0
        assert all(g.type == ResourceType.RESOURCE_GROUP for g in level_0)

        # Level 1 should be data resources
        level_1 = hierarchy.get_goals_by_level(1)
        level_1_types = [g.type for g in level_1]
        assert any(
            t in level_1_types
            for t in [
                ResourceType.COSMOS_DB,
                ResourceType.KEY_VAULT,
                ResourceType.STORAGE_ACCOUNT,
            ]
        )

    def test_goal_status_transitions(self):
        """Test goal status transitions."""
        parser = GoalParser()
        request = "Create storage account"

        parsed = parser.parse(request)
        hierarchy = parsed.goal_hierarchy
        goal = hierarchy.goals[0]

        # Initial status
        assert goal.status == GoalStatus.PENDING

        # Mark in progress
        goal.mark_in_progress()
        assert goal.status == GoalStatus.IN_PROGRESS
        assert goal.attempts == 1

        # Mark completed
        goal.mark_completed({"id": "/subscriptions/.../resourceGroups/test"})
        assert goal.status == GoalStatus.COMPLETED
        assert goal.outputs is not None

    def test_goal_ready_check(self):
        """Test goal readiness checking."""
        parser = GoalParser()
        request = "Give me App Service"

        parsed = parser.parse(request)
        hierarchy = parsed.goal_hierarchy

        # Initially, only level 0 should be ready
        ready = hierarchy.get_ready_goals()
        assert all(g.level == 0 for g in ready)

        # Mark level 0 complete
        for goal in hierarchy.get_goals_by_level(0):
            goal.mark_completed({})

        # Now level 1 should be ready
        ready = hierarchy.get_ready_goals()
        assert any(g.level == 1 for g in ready)

    def test_constraint_extraction(self):
        """Test constraint extraction from request."""
        parser = GoalParser()
        request = "Deploy app in westus for production"

        parsed = parser.parse(request)

        # Should extract region
        assert "region" in parsed.constraints
        assert parsed.constraints["region"] == "westus"

        # Should extract environment
        assert "environment" in parsed.constraints
        assert parsed.constraints["environment"] == "prod"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
