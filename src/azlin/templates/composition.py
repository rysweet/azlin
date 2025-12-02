"""Template composition with inheritance and dependency resolution.

Provides:
- CompositeTemplate: Template inheritance via `extends` keyword
- TemplateResolver: Dependency resolution with version checking
- Deep merging of resources, parameters, and variables

Philosophy:
- Zero-BS: All functions work, no stubs
- Child overrides parent (standard inheritance model)
- Deep merge for nested structures
"""

import copy

from azlin.templates.marketplace import TemplateRegistry
from azlin.templates.versioning import TemplateVersion, VersionedTemplate


class CompositeTemplate:
    """Template with inheritance support."""

    def __init__(self, child: dict, parent: dict | None = None):
        """Initialize composite template.

        Args:
            child: Child template dictionary
            parent: Parent template dictionary (if extending)

        Raises:
            ValueError: If parent required but not provided or circular inheritance detected
        """
        self.child = child
        self.parent = parent

        # Check if child extends parent
        extends = child.get("metadata", {}).get("extends")

        if extends and parent is None:
            raise ValueError(f"Parent template '{extends}' not found")

        # Detect circular inheritance
        if parent and self._has_circular_inheritance(child, parent):
            raise ValueError("Circular inheritance detected")

    def _has_circular_inheritance(self, child: dict, parent: dict) -> bool:
        """Check for circular inheritance.

        Args:
            child: Child template
            parent: Parent template

        Returns:
            True if circular inheritance detected
        """
        child_name = child.get("metadata", {}).get("name")
        parent_extends = parent.get("metadata", {}).get("extends")

        if parent_extends == child_name:
            return True

        return False

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries (override takes precedence).

        Args:
            base: Base dictionary
            override: Override dictionary

        Returns:
            Merged dictionary
        """
        result = copy.deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override value
                result[key] = copy.deepcopy(value)

        return result

    def _merge_resources(self, parent_resources: list[dict], child_resources: list[dict]) -> list[dict]:
        """Merge resources from parent and child (child overrides by name).

        Args:
            parent_resources: Parent resources
            child_resources: Child resources

        Returns:
            Merged resources list
        """
        # Create dict by resource name for easy lookup
        merged_by_name = {}
        unnamed_resources = []

        # Add parent resources
        for resource in parent_resources:
            name = resource.get("name")
            if name:
                merged_by_name[name] = copy.deepcopy(resource)
            else:
                # Keep unnamed resources
                unnamed_resources.append(copy.deepcopy(resource))

        # Add/override with child resources
        for resource in child_resources:
            name = resource.get("name")
            if name:
                if name in merged_by_name:
                    # Deep merge if resource exists
                    merged_by_name[name] = self._deep_merge(merged_by_name[name], resource)
                else:
                    # Add new resource
                    merged_by_name[name] = copy.deepcopy(resource)
            else:
                # Keep unnamed resources from child
                unnamed_resources.append(copy.deepcopy(resource))

        # Combine named and unnamed resources
        return list(merged_by_name.values()) + unnamed_resources

    def resolve(self) -> dict:
        """Resolve composite template by merging parent and child.

        Returns:
            Resolved template dictionary
        """
        if self.parent is None:
            # No parent, return child as-is
            return copy.deepcopy(self.child)

        # Start with parent as base
        resolved = copy.deepcopy(self.parent)

        # Merge content sections
        parent_content = resolved.get("content", {})
        child_content = self.child.get("content", {})

        # Handle resources specially (merge by name)
        if "resources" in parent_content or "resources" in child_content:
            parent_resources = parent_content.get("resources", [])
            child_resources = child_content.get("resources", [])
            merged_resources = self._merge_resources(parent_resources, child_resources)

            # Create merged content
            merged_content = self._deep_merge(parent_content, child_content)
            merged_content["resources"] = merged_resources
        else:
            # No resources, just deep merge
            merged_content = self._deep_merge(parent_content, child_content)

        # Update resolved template
        resolved["content"] = merged_content
        resolved["metadata"] = copy.deepcopy(self.child["metadata"])

        return resolved


class TemplateResolver:
    """Resolve template dependencies from registry."""

    def __init__(self, registry: TemplateRegistry):
        """Initialize resolver with template registry.

        Args:
            registry: Template registry for dependency lookup
        """
        self.registry = registry

    def _check_version_constraint(self, version: TemplateVersion, constraint: str) -> bool:
        """Check if version satisfies constraint.

        Args:
            version: Version to check
            constraint: Constraint string (e.g., ">=1.0.0")

        Returns:
            True if version satisfies constraint
        """
        # Parse constraint (simple implementation for >=, >, =, <, <=)
        if constraint.startswith(">="):
            required = TemplateVersion.from_string(constraint[2:])
            return version >= required
        if constraint.startswith(">"):
            required = TemplateVersion.from_string(constraint[1:])
            return version > required
        if constraint.startswith("<="):
            required = TemplateVersion.from_string(constraint[2:])
            return version <= required
        if constraint.startswith("<"):
            required = TemplateVersion.from_string(constraint[1:])
            return version < required
        if constraint.startswith("==") or "==" in constraint:
            required = TemplateVersion.from_string(constraint.replace("==", ""))
            return version == required
        # Assume exact match
        required = TemplateVersion.from_string(constraint)
        return version == required

    def _resolve_single_dependency(
        self,
        dep_name: str,
        constraint: str,
        visited: set[str]
    ) -> VersionedTemplate:
        """Resolve a single dependency.

        Args:
            dep_name: Dependency name
            constraint: Version constraint
            visited: Set of visited dependencies (for circular detection)

        Returns:
            Resolved dependency template

        Raises:
            ValueError: If dependency not found, version conflict, or circular dependency
        """
        # Check for circular dependency
        if dep_name in visited:
            raise ValueError(f"Circular dependency detected: {dep_name}")

        # Get dependency from registry
        dep_template = self.registry.get(dep_name)
        if dep_template is None:
            raise ValueError(f"Dependency '{dep_name}' not found in registry")

        # Check version constraint
        if not self._check_version_constraint(dep_template.metadata.version, constraint):
            raise ValueError(
                f"Version conflict: {dep_name} version {dep_template.metadata.version} "
                f"does not satisfy constraint {constraint}"
            )

        # Mark as visited
        visited.add(dep_name)

        # Recursively resolve dependencies
        if dep_template.metadata.dependencies:
            for sub_dep_name, sub_constraint in dep_template.metadata.dependencies.items():
                self._resolve_single_dependency(sub_dep_name, sub_constraint, visited)

        return dep_template

    def resolve_dependencies(self, template: VersionedTemplate) -> VersionedTemplate:
        """Resolve all dependencies for a template.

        Args:
            template: Template to resolve dependencies for

        Returns:
            Template with all dependencies merged

        Raises:
            ValueError: If dependency resolution fails
        """
        if not template.metadata.dependencies:
            # No dependencies, return as-is
            return template

        # Resolve all dependencies (including transitive)
        resolved_deps_map: dict[str, VersionedTemplate] = {}
        resolving: set[str] = set()  # Track what's currently being resolved for circular detection

        def resolve_recursive(dep_name: str, constraint: str):
            """Recursively resolve a dependency and its sub-dependencies."""
            if dep_name in resolved_deps_map:
                return  # Already resolved

            if dep_name in resolving:
                raise ValueError(f"Circular dependency detected: {dep_name}")

            # Mark as currently resolving
            resolving.add(dep_name)

            # Get dependency from registry
            dep_template = self.registry.get(dep_name)
            if dep_template is None:
                raise ValueError(f"Dependency '{dep_name}' not found in registry")

            # Check version constraint
            if not self._check_version_constraint(dep_template.metadata.version, constraint):
                raise ValueError(
                    f"Version conflict: {dep_name} version {dep_template.metadata.version} "
                    f"does not satisfy constraint {constraint}"
                )

            # Recursively resolve sub-dependencies first
            if dep_template.metadata.dependencies:
                for sub_dep_name, sub_constraint in dep_template.metadata.dependencies.items():
                    resolve_recursive(sub_dep_name, sub_constraint)

            # Add this dependency after its sub-dependencies
            resolved_deps_map[dep_name] = dep_template

            # Mark as fully resolved
            resolving.remove(dep_name)

        # Resolve all direct dependencies and their transitive dependencies
        for dep_name, constraint in template.metadata.dependencies.items():
            resolve_recursive(dep_name, constraint)

        # Merge dependencies into template (in dependency order)
        if not resolved_deps_map:
            return template

        # Build merged content from all dependencies
        resolved_deps = list(resolved_deps_map.values())
        merged_content = resolved_deps[0].content

        for dep in resolved_deps[1:]:
            # Merge each dependency's content
            composite = CompositeTemplate(
                child={"metadata": dep.metadata.to_dict(), "content": dep.content},
                parent={"metadata": {}, "content": merged_content}
            )
            merged_content = composite.resolve()["content"]

        # Finally merge template on top
        composite = CompositeTemplate(
            child={"metadata": template.metadata.to_dict(), "content": template.content},
            parent={"metadata": {}, "content": merged_content}
        )

        resolved_dict = composite.resolve()

        # Create new template with merged content
        return VersionedTemplate(
            metadata=template.metadata,
            content=resolved_dict["content"],
            change_history=template.change_history
        )


__all__ = ["CompositeTemplate", "TemplateResolver"]
