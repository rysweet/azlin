"""Template versioning system with semantic versioning and change tracking.

Provides:
- TemplateVersion: Semantic versioning (major.minor.patch)
- TemplateMetadata: Template metadata with version info
- ChangeRecord: Individual change records
- ChangeHistory: Change history management
- VersionedTemplate: Template with version and change tracking

Philosophy:
- Zero-BS: All functions work, no stubs
- Standard library only for core functionality
- Immutable version objects (new instances on change)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TemplateVersion:
    """Semantic version for templates (major.minor.patch)."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        """Return version as string in format 'major.minor.patch'."""
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "TemplateVersion") -> bool:
        """Compare versions (less than)."""
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: "TemplateVersion") -> bool:
        """Compare versions (less than or equal)."""
        return self < other or self == other

    def __gt__(self, other: "TemplateVersion") -> bool:
        """Compare versions (greater than)."""
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: "TemplateVersion") -> bool:
        """Compare versions (greater than or equal)."""
        return self > other or self == other

    @classmethod
    def from_string(cls, version_str: str) -> "TemplateVersion":
        """Parse version from string format 'major.minor.patch'.

        Args:
            version_str: Version string (e.g., "1.2.3")

        Returns:
            TemplateVersion instance

        Raises:
            ValueError: If version string is invalid
        """
        pattern = r"^(\d+)\.(\d+)\.(\d+)$"
        match = re.match(pattern, version_str)

        if not match:
            raise ValueError(f"Invalid version format: {version_str}. Expected 'major.minor.patch'")

        major, minor, patch = match.groups()
        return cls(int(major), int(minor), int(patch))

    def increment_patch(self) -> "TemplateVersion":
        """Return new version with patch incremented."""
        return TemplateVersion(self.major, self.minor, self.patch + 1)

    def increment_minor(self) -> "TemplateVersion":
        """Return new version with minor incremented and patch reset."""
        return TemplateVersion(self.major, self.minor + 1, 0)

    def increment_major(self) -> "TemplateVersion":
        """Return new version with major incremented and minor/patch reset."""
        return TemplateVersion(self.major + 1, 0, 0)


@dataclass
class TemplateMetadata:
    """Metadata for a template."""

    name: str
    version: TemplateVersion
    description: str
    author: str
    created_at: datetime
    tags: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize metadata to dictionary."""
        return {
            "name": self.name,
            "version": str(self.version),
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateMetadata":
        """Deserialize metadata from dictionary."""
        return cls(
            name=data["name"],
            version=TemplateVersion.from_string(data["version"]),
            description=data["description"],
            author=data["author"],
            created_at=datetime.fromisoformat(data["created_at"]),
            tags=data.get("tags", []),
            dependencies=data.get("dependencies", {}),
        )


@dataclass
class ChangeRecord:
    """Record of a single change to a template."""

    version: TemplateVersion
    timestamp: datetime
    author: str
    change_type: str
    description: str

    VALID_TYPES = {"major", "minor", "patch", "metadata"}

    def __post_init__(self):
        """Validate change type after initialization."""
        if self.change_type not in self.VALID_TYPES:
            raise ValueError(
                f"Invalid change type: {self.change_type}. "
                f"Must be one of {self.VALID_TYPES}"
            )

    def to_dict(self) -> dict:
        """Serialize change record to dictionary."""
        return {
            "version": str(self.version),
            "timestamp": self.timestamp.isoformat(),
            "author": self.author,
            "change_type": self.change_type,
            "description": self.description,
        }


class ChangeHistory:
    """Manage change history for a template."""

    def __init__(self):
        """Initialize empty change history."""
        self._changes: list[ChangeRecord] = []

    def append(self, record: ChangeRecord) -> None:
        """Add a change record to history."""
        self._changes.append(record)

    def __len__(self) -> int:
        """Return number of changes in history."""
        return len(self._changes)

    def __getitem__(self, index: int) -> ChangeRecord:
        """Get change record by index."""
        return self._changes[index]

    def get_changes_for_version(self, version: TemplateVersion) -> list[ChangeRecord]:
        """Get all changes for a specific version."""
        return [c for c in self._changes if c.version == version]

    def get_latest(self) -> ChangeRecord | None:
        """Get the most recent change record."""
        if not self._changes:
            return None
        return self._changes[-1]

    def to_dict(self) -> dict:
        """Serialize change history to dictionary."""
        return {
            "changes": [c.to_dict() for c in self._changes]
        }


@dataclass
class VersionedTemplate:
    """Template with versioning and change tracking."""

    metadata: TemplateMetadata
    content: dict
    change_history: ChangeHistory = field(default_factory=ChangeHistory)

    def update_version(
        self,
        new_version: TemplateVersion,
        author: str,
        change_type: str,
        description: str
    ) -> None:
        """Update template version with change tracking.

        Args:
            new_version: New version to set
            author: Author of the change
            change_type: Type of change (major, minor, patch, metadata)
            description: Description of the change

        Raises:
            ValueError: If trying to downgrade version
        """
        if new_version < self.metadata.version:
            raise ValueError(
                f"Cannot downgrade version from {self.metadata.version} to {new_version}"
            )

        # Create change record
        record = ChangeRecord(
            version=new_version,
            timestamp=datetime.now(),
            author=author,
            change_type=change_type,
            description=description
        )

        # Update version and add to history
        self.metadata.version = new_version
        self.change_history.append(record)


__all__ = [
    "ChangeHistory",
    "ChangeRecord",
    "TemplateMetadata",
    "TemplateVersion",
    "VersionedTemplate",
]
