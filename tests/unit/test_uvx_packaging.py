"""Test uvx packaging and entry point configuration.

This module tests that azlin is correctly packaged for uvx usage.
"""

import subprocess
from pathlib import Path

import pytest


class TestUvxPackaging:
    """Test uvx packaging configuration."""

    def test_pyproject_has_entry_point(self):
        """Test that pyproject.toml has the correct entry point configured.

        This is required for uvx to work properly.
        """
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        assert pyproject_path.exists(), "pyproject.toml not found"

        content = pyproject_path.read_text()

        # Should have [project.scripts] section
        assert "[project.scripts]" in content, "Missing [project.scripts] section"

        # Should have azlin entry point
        assert "azlin = " in content, "Missing azlin entry point"
        assert "azlin.cli:main" in content, "Entry point doesn't point to cli:main"

    def test_pyproject_has_required_metadata(self):
        """Test that pyproject.toml has required metadata for packaging."""
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        content = pyproject_path.read_text()

        # Required fields for proper packaging
        assert 'name = "azlin"' in content
        assert "version = " in content
        assert "description = " in content
        assert "requires-python = " in content

    def test_build_system_configured(self):
        """Test that build system is configured."""
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        content = pyproject_path.read_text()

        # Should have build-system section
        assert "[build-system]" in content
        assert "requires = " in content
        assert "build-backend = " in content

    def test_package_importable(self):
        """Test that azlin package can be imported."""
        import azlin

        # Package should be importable
        assert azlin is not None

        # Should have cli module
        from azlin import cli

        assert cli is not None
        assert hasattr(cli, "main")

    def test_cli_entry_point_callable(self):
        """Test that the CLI entry point is callable."""
        from azlin.cli import main

        # Should be callable
        assert callable(main)

    @pytest.mark.integration
    def test_uvx_local_execution(self, tmp_path):
        """Test that uvx can execute azlin from local directory.

        This is an integration test that requires uv/uvx to be installed.
        """
        from unittest.mock import patch

        # Get repo root (2 levels up from this test file)
        repo_root = Path(__file__).parents[2]

        # Ensure subprocess.run is NOT mocked for this integration test
        # Use stopall() to clear any existing patches
        patch.stopall()

        # Try to run azlin --help via uvx from local directory
        result = subprocess.run(
            ["uvx", "--from", str(repo_root), "azlin", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should succeed
        assert result.returncode == 0, f"uvx failed: {result.stderr}"

        # Should show help text
        assert "azlin" in result.stdout.lower()
        assert "usage" in result.stdout.lower() or "options" in result.stdout.lower()

    def test_package_structure(self):
        """Test that package structure is correct for uvx."""
        repo_root = Path(__file__).parents[2]

        # Should have src/azlin directory
        azlin_dir = repo_root / "src" / "azlin"
        assert azlin_dir.exists(), "src/azlin directory not found"
        assert azlin_dir.is_dir()

        # Should have __init__.py
        init_file = azlin_dir / "__init__.py"
        assert init_file.exists(), "src/azlin/__init__.py not found"

        # Should have cli.py
        cli_file = azlin_dir / "cli.py"
        assert cli_file.exists(), "src/azlin/cli.py not found"

    def test_dependencies_listed(self):
        """Test that all dependencies are listed in pyproject.toml."""
        pyproject_path = Path(__file__).parents[2] / "pyproject.toml"
        content = pyproject_path.read_text()

        # Should have dependencies section
        assert "dependencies = [" in content

        # Should have click dependency (used by CLI)
        assert "click" in content.lower()


class TestUvxDocumentation:
    """Test that uvx usage is documented."""

    def test_readme_mentions_uvx(self):
        """Test that README.md documents uvx usage."""
        readme_path = Path(__file__).parents[2] / "README.md"
        assert readme_path.exists(), "README.md not found"

        content = readme_path.read_text()

        # Should mention uvx
        assert "uvx" in content.lower(), "README doesn't mention uvx"

        # Should show git+https usage
        assert "git+https://github.com/rysweet/azlin" in content, (
            "README doesn't show uvx git+ usage"
        )

    def test_readme_has_uvx_examples(self):
        """Test that README has uvx usage examples."""
        readme_path = Path(__file__).parents[2] / "README.md"
        content = readme_path.read_text()

        # Should have example commands
        assert "uvx --from git+https://github.com/rysweet/azlin azlin" in content, (
            "README missing uvx example commands"
        )
