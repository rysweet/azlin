"""Documentation validation for generated CLI docs.

This module validates generated documentation against quality standards.
It checks for placeholder text, required sections, and formatting issues.

Philosophy:
- Regex-based validation (fast)
- Standard library only
- Self-contained and regeneratable
"""

import re
from pathlib import Path

from .models import ValidationResult


class SyncValidator:
    """Validates generated CLI documentation.

    This class checks generated markdown files for common issues like
    placeholder text, missing sections, and formatting problems.
    """

    # Placeholder patterns to detect
    PLACEHOLDER_PATTERNS = [
        r"\[TODO:.*?\]",
        r"\[PLACEHOLDER.*?\]",
        r"TBD",
        r"Coming soon",
        r"To be implemented",
        r"Lorem ipsum",
    ]

    # Required sections for complete documentation
    REQUIRED_SECTIONS = [
        "# azlin",  # Must have main heading
        "## Usage",  # Must have usage section
    ]

    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a single documentation file.

        Args:
            file_path: Path to markdown file to validate

        Returns:
            ValidationResult with errors and warnings

        Example:
            >>> validator = SyncValidator()
            >>> result = validator.validate_file("docs/commands/mount.md")
            >>> if not result.is_valid:
            ...     print(result.errors)
        """
        path = Path(file_path)
        errors = []
        warnings = []

        # Check file exists
        if not path.exists():
            errors.append(f"File does not exist: {file_path}")
            return ValidationResult(
                is_valid=False, file_path=file_path, errors=errors, warnings=warnings
            )

        # Read content
        try:
            content = path.read_text()
        except Exception as e:
            errors.append(f"Failed to read file: {e}")
            return ValidationResult(
                is_valid=False, file_path=file_path, errors=errors, warnings=warnings
            )

        # Check for placeholder text
        placeholder_errors = self._check_placeholders(content)
        errors.extend(placeholder_errors)

        # Check for required sections
        section_errors = self._check_required_sections(content)
        errors.extend(section_errors)

        # Check formatting
        format_warnings = self._check_formatting(content)
        warnings.extend(format_warnings)

        # Check for empty sections
        empty_warnings = self._check_empty_sections(content)
        warnings.extend(empty_warnings)

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            file_path=file_path,
            errors=errors,
            warnings=warnings,
        )

    def validate_directory(self, dir_path: str) -> list[ValidationResult]:
        """Validate all markdown files in a directory.

        Args:
            dir_path: Path to directory containing markdown files

        Returns:
            List of ValidationResult objects, one per file

        Example:
            >>> validator = SyncValidator()
            >>> results = validator.validate_directory("docs/commands/")
            >>> failed = [r for r in results if not r.is_valid]
            >>> print(f"{len(failed)} files failed validation")
        """
        directory = Path(dir_path)
        results = []

        if not directory.exists():
            return results

        for md_file in directory.glob("**/*.md"):
            result = self.validate_file(str(md_file))
            results.append(result)

        return results

    def _check_placeholders(self, content: str) -> list[str]:
        """Check for placeholder text in content."""
        errors = []

        for pattern in self.PLACEHOLDER_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                errors.append(f"Found placeholder text: {matches[0]}")

        return errors

    def _check_required_sections(self, content: str) -> list[str]:
        """Check that all required sections are present."""
        return [
            f"Missing required section: {section}"
            for section in self.REQUIRED_SECTIONS
            if section not in content
        ]

    def _check_formatting(self, content: str) -> list[str]:
        """Check for formatting issues."""
        warnings = []

        # Check for broken markdown links
        broken_links = re.findall(r"\[([^\]]+)\]\(\)", content)
        if broken_links:
            warnings.append(f"Found broken links: {broken_links[:3]}")

        # Check for unclosed code blocks
        code_blocks = content.count("```")
        if code_blocks % 2 != 0:
            warnings.append("Unclosed code block detected")

        return warnings

    def _check_empty_sections(self, content: str) -> list[str]:
        """Check for sections with no content."""
        warnings = []

        # Pattern: section heading followed by another heading or end of file
        empty_section_pattern = r"^(#{1,6}\s+.+)$\s*^(#{1,6}\s+|$)"
        matches = re.finditer(empty_section_pattern, content, re.MULTILINE)

        for match in matches:
            section_name = match.group(1).strip()
            warnings.append(f"Empty section: {section_name}")

        return warnings


__all__ = ["SyncValidator"]
