"""Base strategy interface."""

from abc import ABC, abstractmethod

from azlin.doit.goals import Goal, GoalHierarchy
from azlin.doit.utils import DoItTags, format_tags_for_az_cli


class Strategy(ABC):
    """Base strategy for deploying Azure resources."""

    def __init__(self):
        """Initialize strategy."""
        self._tags: DoItTags | None = None

    def set_tags(self, tags: DoItTags) -> None:
        """Set tags to be applied to resources.

        Args:
            tags: Tags to apply to all resources created by this strategy
        """
        self._tags = tags

    def get_tags_string(self) -> str:
        """Get tags formatted for Azure CLI.

        Returns:
            Formatted tags string for --tags parameter, or empty string if no tags
        """
        if self._tags:
            return format_tags_for_az_cli(self._tags)
        return ""

    @abstractmethod
    def build_command(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Build Azure CLI command to deploy resource.

        Args:
            goal: Goal to achieve
            hierarchy: Full goal hierarchy for context

        Returns:
            Azure CLI command string
        """
        pass

    @abstractmethod
    def generate_terraform(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Terraform code for this resource.

        Args:
            goal: Goal to achieve
            hierarchy: Full goal hierarchy for context

        Returns:
            Terraform HCL code
        """
        pass

    @abstractmethod
    def generate_bicep(self, goal: Goal, hierarchy: GoalHierarchy) -> str:
        """Generate Bicep code for this resource.

        Args:
            goal: Goal to achieve
            hierarchy: Full goal hierarchy for context

        Returns:
            Bicep code
        """
        pass

    def get_dependencies(self, goal: Goal, hierarchy: GoalHierarchy) -> dict[str, str]:
        """Get dependency outputs needed by this resource.

        Args:
            goal: Goal to achieve
            hierarchy: Full goal hierarchy

        Returns:
            Dict of dependency_id -> output_value
        """
        deps = {}
        for dep_id in goal.dependencies:
            dep_goal = hierarchy.get_goal(dep_id)
            if dep_goal and dep_goal.outputs:
                deps[dep_id] = dep_goal.outputs
        return deps
