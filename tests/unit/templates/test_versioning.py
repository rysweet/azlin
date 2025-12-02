"""Unit tests for template versioning system.

Test coverage: Template versioning (metadata-based, change tracking)

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import pytest
from datetime import datetime
from pathlib import Path


class TestTemplateVersion:
    """Test template version metadata handling."""

    def test_version_creation_with_semver(self):
        """Test creating a template version with semantic versioning."""
        from azlin.templates.versioning import TemplateVersion

        version = TemplateVersion(major=1, minor=0, patch=0)

        assert version.major == 1
        assert version.minor == 0
        assert version.patch == 0
        assert str(version) == "1.0.0"

    def test_version_comparison_major(self):
        """Test version comparison for major version differences."""
        from azlin.templates.versioning import TemplateVersion

        v1 = TemplateVersion(major=2, minor=0, patch=0)
        v2 = TemplateVersion(major=1, minor=0, patch=0)

        assert v1 > v2
        assert v2 < v1
        assert v1 != v2

    def test_version_comparison_minor(self):
        """Test version comparison for minor version differences."""
        from azlin.templates.versioning import TemplateVersion

        v1 = TemplateVersion(major=1, minor=2, patch=0)
        v2 = TemplateVersion(major=1, minor=1, patch=0)

        assert v1 > v2
        assert v2 < v1

    def test_version_comparison_patch(self):
        """Test version comparison for patch version differences."""
        from azlin.templates.versioning import TemplateVersion

        v1 = TemplateVersion(major=1, minor=0, patch=2)
        v2 = TemplateVersion(major=1, minor=0, patch=1)

        assert v1 > v2
        assert v2 < v1

    def test_version_equality(self):
        """Test version equality comparison."""
        from azlin.templates.versioning import TemplateVersion

        v1 = TemplateVersion(major=1, minor=2, patch=3)
        v2 = TemplateVersion(major=1, minor=2, patch=3)

        assert v1 == v2
        assert not v1 != v2

    def test_version_from_string(self):
        """Test parsing version from string format."""
        from azlin.templates.versioning import TemplateVersion

        version = TemplateVersion.from_string("2.5.1")

        assert version.major == 2
        assert version.minor == 5
        assert version.patch == 1

    def test_version_from_string_invalid(self):
        """Test parsing invalid version string raises error."""
        from azlin.templates.versioning import TemplateVersion

        with pytest.raises(ValueError, match="Invalid version format"):
            TemplateVersion.from_string("invalid")

        with pytest.raises(ValueError, match="Invalid version format"):
            TemplateVersion.from_string("1.2")

    def test_version_increment_patch(self):
        """Test incrementing patch version."""
        from azlin.templates.versioning import TemplateVersion

        version = TemplateVersion(major=1, minor=2, patch=3)
        new_version = version.increment_patch()

        assert new_version.major == 1
        assert new_version.minor == 2
        assert new_version.patch == 4
        # Original should be unchanged
        assert version.patch == 3

    def test_version_increment_minor(self):
        """Test incrementing minor version resets patch."""
        from azlin.templates.versioning import TemplateVersion

        version = TemplateVersion(major=1, minor=2, patch=3)
        new_version = version.increment_minor()

        assert new_version.major == 1
        assert new_version.minor == 3
        assert new_version.patch == 0

    def test_version_increment_major(self):
        """Test incrementing major version resets minor and patch."""
        from azlin.templates.versioning import TemplateVersion

        version = TemplateVersion(major=1, minor=2, patch=3)
        new_version = version.increment_major()

        assert new_version.major == 2
        assert new_version.minor == 0
        assert new_version.patch == 0


class TestTemplateMetadata:
    """Test template metadata storage and retrieval."""

    def test_metadata_creation(self):
        """Test creating template metadata with all required fields."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 0, 0),
            description="Basic VM template",
            author="test-author",
            created_at=datetime.now()
        )

        assert metadata.name == "vm-basic"
        assert metadata.version.major == 1
        assert metadata.description == "Basic VM template"
        assert metadata.author == "test-author"

    def test_metadata_with_tags(self):
        """Test metadata with optional tags."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 0, 0),
            description="Basic VM template",
            author="test-author",
            created_at=datetime.now(),
            tags=["compute", "basic", "vm"]
        )

        assert "compute" in metadata.tags
        assert "basic" in metadata.tags
        assert len(metadata.tags) == 3

    def test_metadata_with_dependencies(self):
        """Test metadata with template dependencies."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-advanced",
            version=TemplateVersion(1, 0, 0),
            description="Advanced VM template",
            author="test-author",
            created_at=datetime.now(),
            dependencies={"network-basic": ">=1.0.0", "storage-basic": ">=2.0.0"}
        )

        assert "network-basic" in metadata.dependencies
        assert metadata.dependencies["network-basic"] == ">=1.0.0"

    def test_metadata_serialization_to_dict(self):
        """Test serializing metadata to dictionary."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 2, 3),
            description="Basic VM template",
            author="test-author",
            created_at=datetime(2025, 1, 1, 12, 0, 0)
        )

        data = metadata.to_dict()

        assert data["name"] == "vm-basic"
        assert data["version"] == "1.2.3"
        assert data["description"] == "Basic VM template"
        assert data["author"] == "test-author"

    def test_metadata_deserialization_from_dict(self):
        """Test deserializing metadata from dictionary."""
        from azlin.templates.versioning import TemplateMetadata

        data = {
            "name": "vm-basic",
            "version": "1.2.3",
            "description": "Basic VM template",
            "author": "test-author",
            "created_at": "2025-01-01T12:00:00"
        }

        metadata = TemplateMetadata.from_dict(data)

        assert metadata.name == "vm-basic"
        assert metadata.version.major == 1
        assert metadata.version.minor == 2
        assert metadata.version.patch == 3


class TestChangeTracking:
    """Test template change tracking functionality."""

    def test_change_record_creation(self):
        """Test creating a change record."""
        from azlin.templates.versioning import ChangeRecord, TemplateVersion

        record = ChangeRecord(
            version=TemplateVersion(1, 0, 1),
            timestamp=datetime.now(),
            author="test-author",
            change_type="patch",
            description="Fixed typo in description"
        )

        assert record.version.patch == 1
        assert record.author == "test-author"
        assert record.change_type == "patch"

    def test_change_record_types(self):
        """Test valid change record types."""
        from azlin.templates.versioning import ChangeRecord, TemplateVersion

        valid_types = ["major", "minor", "patch", "metadata"]

        for change_type in valid_types:
            record = ChangeRecord(
                version=TemplateVersion(1, 0, 0),
                timestamp=datetime.now(),
                author="test",
                change_type=change_type,
                description="Test change"
            )
            assert record.change_type == change_type

    def test_change_record_invalid_type(self):
        """Test invalid change type raises error."""
        from azlin.templates.versioning import ChangeRecord, TemplateVersion

        with pytest.raises(ValueError, match="Invalid change type"):
            ChangeRecord(
                version=TemplateVersion(1, 0, 0),
                timestamp=datetime.now(),
                author="test",
                change_type="invalid",
                description="Test"
            )

    def test_change_history_append(self):
        """Test appending changes to change history."""
        from azlin.templates.versioning import ChangeHistory, ChangeRecord, TemplateVersion

        history = ChangeHistory()

        record1 = ChangeRecord(
            version=TemplateVersion(1, 0, 0),
            timestamp=datetime(2025, 1, 1),
            author="author1",
            change_type="major",
            description="Initial release"
        )

        record2 = ChangeRecord(
            version=TemplateVersion(1, 0, 1),
            timestamp=datetime(2025, 1, 2),
            author="author2",
            change_type="patch",
            description="Bug fix"
        )

        history.append(record1)
        history.append(record2)

        assert len(history) == 2
        assert history[0].version.patch == 0
        assert history[1].version.patch == 1

    def test_change_history_get_changes_for_version(self):
        """Test retrieving changes for specific version."""
        from azlin.templates.versioning import ChangeHistory, ChangeRecord, TemplateVersion

        history = ChangeHistory()

        v1 = TemplateVersion(1, 0, 0)
        v2 = TemplateVersion(1, 0, 1)

        history.append(ChangeRecord(v1, datetime.now(), "author1", "major", "Initial"))
        history.append(ChangeRecord(v2, datetime.now(), "author2", "patch", "Fix"))
        history.append(ChangeRecord(v2, datetime.now(), "author3", "patch", "Another fix"))

        v2_changes = history.get_changes_for_version(v2)

        assert len(v2_changes) == 2
        assert all(c.version == v2 for c in v2_changes)

    def test_change_history_get_latest(self):
        """Test retrieving latest change from history."""
        from azlin.templates.versioning import ChangeHistory, ChangeRecord, TemplateVersion

        history = ChangeHistory()

        history.append(ChangeRecord(
            TemplateVersion(1, 0, 0),
            datetime(2025, 1, 1),
            "author1",
            "major",
            "Initial"
        ))
        history.append(ChangeRecord(
            TemplateVersion(1, 0, 1),
            datetime(2025, 1, 2),
            "author2",
            "patch",
            "Fix"
        ))

        latest = history.get_latest()

        assert latest.version.patch == 1
        assert latest.author == "author2"

    def test_change_history_empty(self):
        """Test change history operations on empty history."""
        from azlin.templates.versioning import ChangeHistory

        history = ChangeHistory()

        assert len(history) == 0
        assert history.get_latest() is None

    def test_change_history_serialization(self):
        """Test serializing change history to JSON."""
        from azlin.templates.versioning import ChangeHistory, ChangeRecord, TemplateVersion

        history = ChangeHistory()
        history.append(ChangeRecord(
            TemplateVersion(1, 0, 0),
            datetime(2025, 1, 1, 12, 0, 0),
            "author1",
            "major",
            "Initial release"
        ))

        data = history.to_dict()

        assert "changes" in data
        assert len(data["changes"]) == 1
        assert data["changes"][0]["version"] == "1.0.0"


class TestVersionedTemplate:
    """Test versioned template integration."""

    def test_versioned_template_creation(self):
        """Test creating a versioned template."""
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 0, 0),
            description="Basic VM",
            author="test",
            created_at=datetime.now()
        )

        template = VersionedTemplate(
            metadata=metadata,
            content={"resources": [{"type": "Microsoft.Compute/virtualMachines"}]}
        )

        assert template.metadata.name == "vm-basic"
        assert "resources" in template.content

    def test_versioned_template_update_version(self):
        """Test updating template version with change tracking."""
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 0, 0),
            description="Basic VM",
            author="test",
            created_at=datetime.now()
        )

        template = VersionedTemplate(
            metadata=metadata,
            content={"resources": []}
        )

        template.update_version(
            new_version=TemplateVersion(1, 0, 1),
            author="updater",
            change_type="patch",
            description="Fixed bug"
        )

        assert template.metadata.version.patch == 1
        assert len(template.change_history) == 1
        assert template.change_history[0].description == "Fixed bug"

    def test_versioned_template_validation(self):
        """Test template validation before version update."""
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        metadata = TemplateMetadata(
            name="vm-basic",
            version=TemplateVersion(1, 0, 0),
            description="Basic VM",
            author="test",
            created_at=datetime.now()
        )

        template = VersionedTemplate(
            metadata=metadata,
            content={"resources": []}
        )

        # Should not allow downgrade
        with pytest.raises(ValueError, match="Cannot downgrade"):
            template.update_version(
                new_version=TemplateVersion(0, 9, 0),
                author="test",
                change_type="major",
                description="Downgrade"
            )
