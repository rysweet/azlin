"""Template management module.

This module handles VM configuration template storage, retrieval, and management.
Templates are stored as YAML files in ~/.azlin/templates/.

Security:
- Template name validation (no path traversal)
- File permissions: 0644 for template files
- Directory permissions: 0755 for templates directory
- YAML content validation
- Input sanitization

Template Structure:
    name: VM template name (alphanumeric, hyphens, underscores)
    description: Human-readable description
    vm_size: Azure VM size (e.g., Standard_B2s)
    region: Azure region (e.g., eastus)
    cloud_init: Optional cloud-init script
    custom_metadata: Optional metadata dictionary
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise ImportError("PyYAML not available. Install with: pip install pyyaml")

logger = logging.getLogger(__name__)


class TemplateError(Exception):
    """Raised when template operations fail."""

    pass


@dataclass
class VMTemplateConfig:
    """VM template configuration."""

    name: str
    description: str
    vm_size: str
    region: str
    cloud_init: str | None = None
    custom_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert template to dictionary for YAML serialization.

        Returns:
            Dictionary representation of template
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VMTemplateConfig":
        """Create template from dictionary.

        Args:
            data: Dictionary with template fields

        Returns:
            VMTemplateConfig instance

        Raises:
            TemplateError: If required fields are missing
        """
        required_fields = ["name", "description", "vm_size", "region"]
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            raise TemplateError(f"Missing required field: {', '.join(missing_fields)}")

        return cls(
            name=data["name"],
            description=data["description"],
            vm_size=data["vm_size"],
            region=data["region"],
            cloud_init=data.get("cloud_init"),
            custom_metadata=data.get("custom_metadata", {}),
        )

    def validate(self) -> None:
        """Validate template fields.

        Raises:
            TemplateError: If validation fails
        """
        if not self.name or not self.name.strip():
            raise TemplateError("Template name cannot be empty")

        if not self.description or not self.description.strip():
            raise TemplateError("Template description cannot be empty")

        if not self.vm_size or not self.vm_size.strip():
            raise TemplateError("VM size cannot be empty")

        if not self.region or not self.region.strip():
            raise TemplateError("Region cannot be empty")


class TemplateManager:
    """Manage VM configuration templates.

    Templates are stored as YAML files in ~/.azlin/templates/.
    """

    TEMPLATES_DIR = Path.home() / ".azlin" / "templates"
    MAX_NAME_LENGTH = 128
    NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

    @classmethod
    def ensure_templates_dir(cls) -> Path:
        """Ensure templates directory exists with proper permissions.

        Returns:
            Path to templates directory

        Raises:
            TemplateError: If directory creation fails
        """
        try:
            cls.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
            # Set directory permissions to 0755
            cls.TEMPLATES_DIR.chmod(0o755)
            return cls.TEMPLATES_DIR
        except Exception as e:
            raise TemplateError(f"Failed to create templates directory: {e}")

    @classmethod
    def validate_template_name(cls, name: str) -> bool:
        """Validate template name.

        Template names must:
        - Start with alphanumeric character
        - Contain only alphanumeric, hyphens, and underscores
        - Not contain path separators
        - Be <= MAX_NAME_LENGTH characters

        Args:
            name: Template name to validate

        Returns:
            True if valid, False otherwise
        """
        if not name or len(name) > cls.MAX_NAME_LENGTH:
            return False

        # Check for path traversal attempts
        if "/" in name or "\\" in name or ".." in name:
            return False

        # Check pattern
        return bool(cls.NAME_PATTERN.match(name))

    @classmethod
    def get_template_path(cls, name: str) -> Path:
        """Get path to template file.

        Args:
            name: Template name

        Returns:
            Path to template file
        """
        return cls.TEMPLATES_DIR / f"{name}.yaml"

    @classmethod
    def create_template(cls, template: VMTemplateConfig) -> None:
        """Create a new template.

        Args:
            template: Template configuration

        Raises:
            TemplateError: If template creation fails
        """
        # Validate template
        template.validate()

        # Validate name
        if not cls.validate_template_name(template.name):
            raise TemplateError(f"Invalid template name: {template.name}")

        if len(template.name) > cls.MAX_NAME_LENGTH:
            raise TemplateError(f"Template name too long (max {cls.MAX_NAME_LENGTH} characters)")

        # Ensure directory exists
        cls.ensure_templates_dir()

        # Check if template already exists
        template_path = cls.get_template_path(template.name)
        if template_path.exists():
            raise TemplateError(f"Template '{template.name}' already exists")

        # Write template to file
        try:
            with open(template_path, "w") as f:
                yaml.dump(template.to_dict(), f, default_flow_style=False, sort_keys=False)

            # Set file permissions to 0644
            template_path.chmod(0o644)

            logger.info(f"Created template: {template.name}")

        except Exception as e:
            raise TemplateError(f"Failed to create template: {e}")

    @classmethod
    def list_templates(cls) -> list[VMTemplateConfig]:
        """List all available templates.

        Returns:
            List of templates, sorted alphabetically by name

        Note:
            Corrupted YAML files are silently skipped and logged
        """
        # Ensure directory exists
        if not cls.TEMPLATES_DIR.exists():
            return []

        templates = []

        # Read all .yaml files
        for template_file in cls.TEMPLATES_DIR.glob("*.yaml"):
            try:
                with open(template_file) as f:
                    data = yaml.safe_load(f)

                if data:
                    template = VMTemplateConfig.from_dict(data)
                    templates.append(template)

            except Exception as e:
                logger.warning(f"Skipping corrupted template file {template_file.name}: {e}")
                continue

        # Sort alphabetically by name
        templates.sort(key=lambda t: t.name)

        return templates

    @classmethod
    def get_template(cls, name: str) -> VMTemplateConfig:
        """Retrieve a template by name.

        Args:
            name: Template name

        Returns:
            Template configuration

        Raises:
            TemplateError: If template not found or invalid
        """
        template_path = cls.get_template_path(name)

        if not template_path.exists():
            raise TemplateError(f"Template '{name}' not found")

        try:
            with open(template_path) as f:
                data = yaml.safe_load(f)

            return VMTemplateConfig.from_dict(data)

        except Exception as e:
            raise TemplateError(f"Failed to load template '{name}': {e}")

    @classmethod
    def delete_template(cls, name: str) -> None:
        """Delete a template.

        Args:
            name: Template name

        Raises:
            TemplateError: If template not found or deletion fails
        """
        template_path = cls.get_template_path(name)

        if not template_path.exists():
            raise TemplateError(f"Template '{name}' not found")

        try:
            template_path.unlink()
            logger.info(f"Deleted template: {name}")

        except Exception as e:
            raise TemplateError(f"Failed to delete template '{name}': {e}")

    @classmethod
    def export_template(cls, name: str, output_path: Path) -> None:
        """Export a template to a file.

        Args:
            name: Template name
            output_path: Path to export file

        Raises:
            TemplateError: If template not found or export fails
        """
        template = cls.get_template(name)

        try:
            output_path = Path(output_path).expanduser().resolve()

            with open(output_path, "w") as f:
                yaml.dump(template.to_dict(), f, default_flow_style=False, sort_keys=False)

            # Set file permissions to 0644
            output_path.chmod(0o644)

            logger.info(f"Exported template '{name}' to {output_path}")

        except Exception as e:
            raise TemplateError(f"Failed to export template: {e}")

    @classmethod
    def import_template(cls, input_path: Path) -> VMTemplateConfig:
        """Import a template from a file.

        Args:
            input_path: Path to import file

        Returns:
            Imported template

        Raises:
            TemplateError: If import fails or file is invalid
        """
        try:
            input_path = Path(input_path).expanduser().resolve()

            if not input_path.exists():
                raise TemplateError(f"Import file not found: {input_path}")

            with open(input_path) as f:
                data = yaml.safe_load(f)

            if not data:
                raise TemplateError("Invalid YAML: file is empty")

            template = VMTemplateConfig.from_dict(data)

            # Validate and create template
            cls.create_template(template)

            logger.info(f"Imported template '{template.name}' from {input_path}")

            return template

        except yaml.YAMLError as e:
            raise TemplateError(f"Invalid YAML: {e}")
        except TemplateError:
            raise
        except Exception as e:
            raise TemplateError(f"Failed to import template: {e}")


__all__ = ["TemplateError", "TemplateManager", "VMTemplateConfig"]
