"""Template marketplace and registry for template sharing and discovery.

Provides:
- TemplateRegistry: Register, discover, and manage templates
- Template search by name, tags, and author
- Template rating and popularity tracking
- Export/import functionality for sharing

Philosophy:
- Zero-BS: All functions work, no stubs
- In-memory storage with file export/import
- Simple but complete implementation
"""

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

from azlin.templates.versioning import TemplateMetadata, VersionedTemplate


@dataclass
class RatingStats:
    """Rating statistics for a template."""
    average: float
    count: int


class TemplateRegistry:
    """Registry for template management and discovery."""

    def __init__(self):
        """Initialize empty registry."""
        self._templates: dict[str, VersionedTemplate] = {}
        self._ratings: dict[str, dict[str, int]] = {}  # {template_name: {user_id: rating}}

    def count(self) -> int:
        """Return number of registered templates."""
        return len(self._templates)

    def exists(self, name: str) -> bool:
        """Check if template exists in registry."""
        return name in self._templates

    def register(self, template: VersionedTemplate) -> None:
        """Register a new template.

        Args:
            template: Template to register

        Raises:
            ValueError: If template name already registered
        """
        name = template.metadata.name
        if name in self._templates:
            raise ValueError(f"Template '{name}' already registered")

        self._templates[name] = template
        self._ratings[name] = {}

    def get(self, name: str) -> VersionedTemplate | None:
        """Retrieve template by name.

        Args:
            name: Template name

        Returns:
            Template if found, None otherwise
        """
        return self._templates.get(name)

    def update_version(self, name: str, new_template: VersionedTemplate) -> None:
        """Update template to new version.

        Args:
            name: Template name
            new_template: New version of template

        Raises:
            ValueError: If template not found
        """
        if name not in self._templates:
            raise ValueError(f"Template '{name}' not found")

        self._templates[name] = new_template

    def list_all(self) -> list[VersionedTemplate]:
        """List all registered templates."""
        return list(self._templates.values())

    def search(
        self,
        name_pattern: str | None = None,
        tags: list[str] | None = None,
        author: str | None = None
    ) -> list[VersionedTemplate]:
        """Search templates by criteria.

        Args:
            name_pattern: Glob pattern for name (e.g., "vm-*")
            tags: List of tags to match (any tag matches)
            author: Author name to match

        Returns:
            List of matching templates
        """
        results = []

        for template in self._templates.values():
            # Check name pattern
            if name_pattern and not fnmatch.fnmatch(template.metadata.name, name_pattern):
                continue

            # Check tags (any tag match)
            if tags and not any(tag in template.metadata.tags for tag in tags):
                continue

            # Check author
            if author and template.metadata.author != author:
                continue

            results.append(template)

        return results

    def rate_template(self, template_name: str, user_id: str, rating: int) -> None:
        """Rate a template.

        Args:
            template_name: Name of template to rate
            user_id: User providing rating
            rating: Rating value (1-5)

        Raises:
            ValueError: If rating out of range or template not found
        """
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")

        if template_name not in self._templates:
            raise ValueError(f"Template '{template_name}' not found")

        # Update or add rating (users can update their ratings)
        self._ratings[template_name][user_id] = rating

    def get_rating_stats(self, template_name: str) -> dict[str, float]:
        """Get rating statistics for a template.

        Args:
            template_name: Template name

        Returns:
            Dictionary with 'average' and 'count' keys
        """
        ratings = self._ratings.get(template_name, {})

        if not ratings:
            return {"average": 0.0, "count": 0}

        rating_values = list(ratings.values())
        average = sum(rating_values) / len(rating_values)

        return {
            "average": average,
            "count": len(rating_values)
        }

    def get_top_rated(self, limit: int = 10) -> list[VersionedTemplate]:
        """Get top-rated templates.

        Args:
            limit: Maximum number of templates to return

        Returns:
            List of templates sorted by rating (highest first)
        """
        # Calculate average ratings
        rated_templates = []
        for template in self._templates.values():
            stats = self.get_rating_stats(template.metadata.name)
            if stats["count"] > 0:
                rated_templates.append((template, stats["average"]))

        # Sort by rating (descending)
        rated_templates.sort(key=lambda x: x[1], reverse=True)

        # Return top N templates
        return [t[0] for t in rated_templates[:limit]]

    def export_template(self, template_name: str, export_path: Path) -> None:
        """Export template to file.

        Args:
            template_name: Name of template to export
            export_path: Path to export file

        Raises:
            ValueError: If template not found
        """
        template = self.get(template_name)
        if template is None:
            raise ValueError(f"Template '{template_name}' not found")

        # Serialize template
        data = {
            "metadata": template.metadata.to_dict(),
            "content": template.content,
            "change_history": template.change_history.to_dict()
        }

        # Write to file
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(data, indent=2))

    def import_template(self, import_path: Path) -> None:
        """Import template from file.

        Args:
            import_path: Path to template file

        Raises:
            ValueError: If file is invalid or template already exists
        """
        try:
            data = json.loads(import_path.read_text())

            # Validate structure
            if "metadata" not in data or "content" not in data:
                raise ValueError("Invalid template file: missing required fields")

            # Reconstruct template
            metadata = TemplateMetadata.from_dict(data["metadata"])
            template = VersionedTemplate(
                metadata=metadata,
                content=data["content"]
            )

            # Register template
            self.register(template)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid template file: {e}")


__all__ = ["TemplateRegistry"]
