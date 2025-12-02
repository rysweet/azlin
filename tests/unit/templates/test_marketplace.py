"""Unit tests for template marketplace and registry.

Test coverage: Template marketplace/sharing (registry, discovery)

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import pytest
from pathlib import Path
from datetime import datetime


class TestTemplateRegistry:
    """Test template registry core functionality."""

    def test_registry_initialization(self):
        """Test creating a template registry."""
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()

        assert registry is not None
        assert registry.count() == 0

    def test_registry_register_template(self):
        """Test registering a new template."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

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

        registry.register(template)

        assert registry.count() == 1
        assert registry.exists("vm-basic")

    def test_registry_register_duplicate_name(self):
        """Test registering template with duplicate name raises error."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template1 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        template2 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",  # Same name
                version=TemplateVersion(2, 0, 0),
                description="Different template",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(template2)

    def test_registry_get_template(self):
        """Test retrieving template by name."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": []}
        )

        registry.register(template)
        retrieved = registry.get("vm-basic")

        assert retrieved is not None
        assert retrieved.metadata.name == "vm-basic"

    def test_registry_get_nonexistent_template(self):
        """Test retrieving nonexistent template returns None."""
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()
        retrieved = registry.get("nonexistent")

        assert retrieved is None

    def test_registry_update_template_version(self):
        """Test updating template to new version."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template_v1 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        template_v2 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(2, 0, 0),
                description="Basic VM v2",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template_v1)
        registry.update_version("vm-basic", template_v2)

        retrieved = registry.get("vm-basic")
        assert retrieved.metadata.version.major == 2

    def test_registry_list_all_templates(self):
        """Test listing all registered templates."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        for i in range(3):
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name=f"template-{i}",
                    version=TemplateVersion(1, 0, 0),
                    description=f"Template {i}",
                    author="test",
                    created_at=datetime.now()
                ),
                content={}
            )
            registry.register(template)

        all_templates = registry.list_all()

        assert len(all_templates) == 3
        assert "template-0" in [t.metadata.name for t in all_templates]


class TestTemplateDiscovery:
    """Test template discovery and search functionality."""

    def test_search_by_name(self):
        """Test searching templates by name."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        templates = [
            ("vm-basic", "Basic VM"),
            ("vm-advanced", "Advanced VM"),
            ("storage-basic", "Basic Storage")
        ]

        for name, desc in templates:
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name=name,
                    version=TemplateVersion(1, 0, 0),
                    description=desc,
                    author="test",
                    created_at=datetime.now()
                ),
                content={}
            )
            registry.register(template)

        results = registry.search(name_pattern="vm-*")

        assert len(results) == 2
        assert all("vm-" in t.metadata.name for t in results)

    def test_search_by_tag(self):
        """Test searching templates by tag."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template1 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now(),
                tags=["compute", "vm", "basic"]
            ),
            content={}
        )

        template2 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="storage-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic Storage",
                author="test",
                created_at=datetime.now(),
                tags=["storage", "basic"]
            ),
            content={}
        )

        registry.register(template1)
        registry.register(template2)

        results = registry.search(tags=["compute"])

        assert len(results) == 1
        assert results[0].metadata.name == "vm-basic"

    def test_search_by_author(self):
        """Test searching templates by author."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        authors = ["author1", "author2", "author1"]
        for i, author in enumerate(authors):
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name=f"template-{i}",
                    version=TemplateVersion(1, 0, 0),
                    description=f"Template {i}",
                    author=author,
                    created_at=datetime.now()
                ),
                content={}
            )
            registry.register(template)

        results = registry.search(author="author1")

        assert len(results) == 2
        assert all(t.metadata.author == "author1" for t in results)

    def test_search_multiple_criteria(self):
        """Test searching with multiple criteria."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="alice",
                created_at=datetime.now(),
                tags=["compute", "basic"]
            ),
            content={}
        )
        registry.register(template)

        # Should match
        results = registry.search(author="alice", tags=["compute"])
        assert len(results) == 1

        # Should not match (wrong author)
        results = registry.search(author="bob", tags=["compute"])
        assert len(results) == 0

    def test_search_empty_results(self):
        """Test search with no matching templates."""
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()

        results = registry.search(name_pattern="nonexistent-*")

        assert len(results) == 0
        assert isinstance(results, list)


class TestTemplateSharing:
    """Test template sharing and export/import functionality."""

    def test_export_template_to_file(self):
        """Test exporting template to file."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion
        import tempfile

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": []}
        )

        # Register the template before exporting
        registry.register(template)

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "vm-basic.json"
            registry.export_template("vm-basic", export_path)

            assert export_path.exists()
            assert export_path.stat().st_size > 0

    def test_import_template_from_file(self):
        """Test importing template from file."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            import_path = Path(tmpdir) / "vm-basic.json"

            # Create a template file
            template_data = {
                "metadata": {
                    "name": "vm-basic",
                    "version": "1.0.0",
                    "description": "Basic VM",
                    "author": "test",
                    "created_at": datetime.now().isoformat()
                },
                "content": {"resources": []}
            }

            import_path.write_text(json.dumps(template_data))

            registry = TemplateRegistry()
            registry.import_template(import_path)

            assert registry.exists("vm-basic")
            template = registry.get("vm-basic")
            assert template.metadata.version.major == 1

    def test_import_invalid_template_file(self):
        """Test importing invalid template file raises error."""
        from azlin.templates.marketplace import TemplateRegistry
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.json"
            invalid_path.write_text("not valid json")

            registry = TemplateRegistry()

            with pytest.raises(ValueError, match="Invalid template"):
                registry.import_template(invalid_path)

    def test_export_nonexistent_template(self):
        """Test exporting nonexistent template raises error."""
        from azlin.templates.marketplace import TemplateRegistry
        import tempfile

        registry = TemplateRegistry()

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "nonexistent.json"

            with pytest.raises(ValueError, match="not found"):
                registry.export_template("nonexistent", export_path)


class TestTemplateRating:
    """Test template rating and popularity tracking."""

    def test_rate_template(self):
        """Test rating a template."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template)
        registry.rate_template("vm-basic", user_id="user1", rating=5)

        stats = registry.get_rating_stats("vm-basic")
        assert stats["average"] == 5.0
        assert stats["count"] == 1

    def test_multiple_ratings_average(self):
        """Test average rating calculation with multiple ratings."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template)
        registry.rate_template("vm-basic", "user1", 5)
        registry.rate_template("vm-basic", "user2", 3)
        registry.rate_template("vm-basic", "user3", 4)

        stats = registry.get_rating_stats("vm-basic")
        assert stats["average"] == 4.0
        assert stats["count"] == 3

    def test_rate_invalid_value(self):
        """Test rating with invalid value raises error."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template)

        with pytest.raises(ValueError, match="Rating must be between"):
            registry.rate_template("vm-basic", "user1", 6)

        with pytest.raises(ValueError, match="Rating must be between"):
            registry.rate_template("vm-basic", "user1", 0)

    def test_user_can_update_rating(self):
        """Test user can update their rating."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-basic",
                version=TemplateVersion(1, 0, 0),
                description="Basic VM",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        registry.register(template)
        registry.rate_template("vm-basic", "user1", 3)
        registry.rate_template("vm-basic", "user1", 5)  # Update

        stats = registry.get_rating_stats("vm-basic")
        assert stats["average"] == 5.0
        assert stats["count"] == 1  # Still one rating

    def test_get_top_rated_templates(self):
        """Test getting top-rated templates."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        for i, avg_rating in enumerate([3, 5, 4]):
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name=f"template-{i}",
                    version=TemplateVersion(1, 0, 0),
                    description=f"Template {i}",
                    author="test",
                    created_at=datetime.now()
                ),
                content={}
            )
            registry.register(template)
            registry.rate_template(f"template-{i}", "user1", avg_rating)

        top_rated = registry.get_top_rated(limit=2)

        assert len(top_rated) == 2
        assert top_rated[0].metadata.name == "template-1"  # Rating 5
        assert top_rated[1].metadata.name == "template-2"  # Rating 4
