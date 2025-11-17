"""Context selection module for multi-context operations.

This module provides pattern-based context selection for querying multiple
Azure contexts simultaneously. It supports glob patterns and filters contexts
from the configured context list.

Features:
- Pattern matching with glob syntax (e.g., "prod*", "dev-*", "*-test")
- --all-contexts flag to select all defined contexts
- Validation and error handling for no contexts found
- Integration with ContextManager

Architecture:
- ContextSelector class with select_contexts() method
- Reuses Context and ContextManager from context_manager.py
- Pattern matching via fnmatch (consistent with batch_executor.py)

Example Usage:
    >>> selector = ContextSelector(config_path="~/.azlin/config.toml")
    >>> contexts = selector.select_contexts(pattern="prod*")
    >>> contexts = selector.select_all_contexts()
"""

import fnmatch
import logging
from pathlib import Path

from azlin.context_manager import Context, ContextConfig, ContextError, ContextManager

logger = logging.getLogger(__name__)


class ContextSelectorError(Exception):
    """Raised when context selection fails."""

    pass


class ContextSelector:
    """Select contexts based on patterns or flags.

    This class provides methods to select one or more contexts from the
    configuration file using patterns or selection flags.

    Philosophy:
    - Fail-fast: Raise errors immediately if no contexts match
    - Explicit: Require either pattern or all_contexts flag
    - Consistent: Use fnmatch for pattern matching (same as BatchSelector)
    """

    def __init__(self, config_path: str | None = None):
        """Initialize context selector.

        Args:
            config_path: Optional path to config file (uses default if None)
        """
        self.config_path = config_path

    def select_contexts(
        self, pattern: str | None = None, all_contexts: bool = False
    ) -> list[Context]:
        """Select contexts based on pattern or flag.

        Exactly one of pattern or all_contexts must be provided.

        Args:
            pattern: Glob pattern for context names (e.g., "prod*", "dev-*")
            all_contexts: If True, select all defined contexts

        Returns:
            List of matching Context objects (sorted by name)

        Raises:
            ContextSelectorError: If no contexts match or invalid arguments

        Example:
            >>> selector = ContextSelector()
            >>> contexts = selector.select_contexts(pattern="prod*")
            >>> contexts = selector.select_contexts(all_contexts=True)
        """
        # Validate arguments
        if pattern and all_contexts:
            raise ContextSelectorError(
                "Cannot specify both pattern and all_contexts. Choose one."
            )

        if not pattern and not all_contexts:
            raise ContextSelectorError(
                "Must specify either pattern or all_contexts=True"
            )

        # Load context configuration
        try:
            config = ContextManager.load(custom_path=self.config_path)
        except ContextError as e:
            raise ContextSelectorError(f"Failed to load context config: {e}") from e

        # Check if any contexts are defined
        if not config.contexts:
            raise ContextSelectorError(
                "No contexts defined in configuration. "
                "Use 'azlin context set' to create contexts first."
            )

        # Select contexts based on arguments
        if all_contexts:
            selected = list(config.contexts.values())
            logger.debug(f"Selected all {len(selected)} contexts")
        else:
            # Pattern matching
            selected = self._select_by_pattern(config, pattern)
            logger.debug(f"Pattern '{pattern}' matched {len(selected)} contexts")

        # Sort by name for consistent output
        selected.sort(key=lambda c: c.name)

        return selected

    def select_all_contexts(self) -> list[Context]:
        """Select all defined contexts.

        Convenience method for select_contexts(all_contexts=True).

        Returns:
            List of all Context objects (sorted by name)

        Raises:
            ContextSelectorError: If no contexts are defined
        """
        return self.select_contexts(all_contexts=True)

    def select_by_pattern(self, pattern: str) -> list[Context]:
        """Select contexts matching a pattern.

        Convenience method for select_contexts(pattern=pattern).

        Args:
            pattern: Glob pattern for context names

        Returns:
            List of matching Context objects (sorted by name)

        Raises:
            ContextSelectorError: If no contexts match
        """
        return self.select_contexts(pattern=pattern)

    def _select_by_pattern(self, config: ContextConfig, pattern: str | None) -> list[Context]:
        """Select contexts matching a glob pattern.

        Args:
            config: Context configuration
            pattern: Glob pattern for context names

        Returns:
            List of matching Context objects

        Raises:
            ContextSelectorError: If no contexts match the pattern
        """
        if not pattern:
            raise ContextSelectorError("Pattern cannot be empty")

        matched = []
        for name, context in config.contexts.items():
            if fnmatch.fnmatch(name, pattern):
                matched.append(context)

        if not matched:
            available = list(config.contexts.keys())
            raise ContextSelectorError(
                f"No contexts match pattern '{pattern}'.\n"
                f"Available contexts: {', '.join(available)}"
            )

        return matched

    def get_current_context(self) -> Context | None:
        """Get the currently active context.

        Returns:
            Current Context object or None if not set

        Raises:
            ContextSelectorError: If config loading fails
        """
        try:
            config = ContextManager.load(custom_path=self.config_path)
            return config.get_current_context()
        except ContextError as e:
            raise ContextSelectorError(f"Failed to load context config: {e}") from e

    def list_available_contexts(self) -> list[str]:
        """List all available context names.

        Returns:
            List of context names (sorted)

        Raises:
            ContextSelectorError: If config loading fails
        """
        try:
            config = ContextManager.load(custom_path=self.config_path)
            return sorted(config.contexts.keys())
        except ContextError as e:
            raise ContextSelectorError(f"Failed to load context config: {e}") from e


__all__ = ["ContextSelector", "ContextSelectorError"]
