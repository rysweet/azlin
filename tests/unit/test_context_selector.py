"""Unit tests for ContextSelector module.

Tests pattern-based context selection with glob patterns and error handling.
Follows testing pyramid: 100% unit tests (no I/O, pure logic).

Test Coverage:
- Context selection by pattern matching
- Context selection with all_contexts flag
- Validation and error handling
- Edge cases: empty patterns, no contexts defined, no matches
- Sorting and consistency
"""

import pytest
from unittest.mock import Mock, patch

from azlin.context_selector import ContextSelector, ContextSelectorError
from azlin.context_manager import Context, ContextConfig, ContextError


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_contexts():
    """Create sample contexts for testing."""
    return {
        "production": Context(
            name="production",
            subscription_id="12345678-1234-1234-1234-123456789001",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        "staging": Context(
            name="staging",
            subscription_id="12345678-1234-1234-1234-123456789002",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        "development": Context(
            name="development",
            subscription_id="12345678-1234-1234-1234-123456789003",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        "prod-backup": Context(
            name="prod-backup",
            subscription_id="12345678-1234-1234-1234-123456789004",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
        "dev-backup": Context(
            name="dev-backup",
            subscription_id="12345678-1234-1234-1234-123456789005",
            tenant_id="87654321-4321-4321-4321-210987654321",
        ),
    }


@pytest.fixture
def mock_config(sample_contexts):
    """Create mock ContextConfig with sample contexts."""
    config = Mock(spec=ContextConfig)
    config.contexts = sample_contexts
    config.get_current_context.return_value = sample_contexts["production"]
    return config


@pytest.fixture
def selector():
    """Create ContextSelector instance."""
    return ContextSelector()


# =============================================================================
# TESTS: Pattern Matching
# =============================================================================


class TestPatternMatching:
    """Test glob pattern matching for context selection."""

    def test_select_by_exact_pattern(self, selector, mock_config):
        """Test selecting context with exact name match."""
        with patch.object(selector, "select_contexts") as mock_select:
            mock_select.return_value = [mock_config.contexts["production"]]
            result = selector.select_contexts(pattern="production")
            assert len(result) == 1
            assert result[0].name == "production"

    def test_select_by_prefix_pattern(self, selector, sample_contexts):
        """Test selecting contexts with prefix pattern."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="prod*")
            assert len(result) == 2
            assert all(c.name.startswith("prod") for c in result)

    def test_select_by_suffix_pattern(self, selector, sample_contexts):
        """Test selecting contexts with suffix pattern."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="*-backup")
            assert len(result) == 2
            assert all(c.name.endswith("-backup") for c in result)

    def test_select_by_wildcard_pattern(self, selector, sample_contexts):
        """Test selecting contexts with full wildcard pattern."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="*")
            assert len(result) == 5
            names = [c.name for c in result]
            assert "production" in names
            assert "staging" in names
            assert "development" in names

    def test_select_by_question_mark_pattern(self, selector, sample_contexts):
        """Test selecting contexts with ? single character wildcard."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="staging")
            assert len(result) == 1
            assert result[0].name == "staging"

    def test_select_by_complex_pattern(self, selector, sample_contexts):
        """Test selecting contexts with complex pattern."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="*dev*")
            names = [c.name for c in result]
            assert "development" in names
            assert "dev-backup" in names
            assert len(result) == 2

    def test_pattern_matching_is_case_sensitive(self, selector, sample_contexts):
        """Test that pattern matching is case-sensitive."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            with pytest.raises(ContextSelectorError, match="No contexts match"):
                selector.select_contexts(pattern="PRODUCTION")

    def test_pattern_matching_is_sorted(self, selector, sample_contexts):
        """Test that results are sorted by name."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="*")
            names = [c.name for c in result]
            assert names == sorted(names)


# =============================================================================
# TESTS: All Contexts Selection
# =============================================================================


class TestAllContextsSelection:
    """Test selecting all defined contexts."""

    def test_select_all_contexts(self, selector, sample_contexts):
        """Test selecting all defined contexts."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(all_contexts=True)
            assert len(result) == 5
            names = {c.name for c in result}
            assert names == set(sample_contexts.keys())

    def test_select_all_contexts_convenience_method(self, selector, sample_contexts):
        """Test select_all_contexts convenience method."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_all_contexts()
            assert len(result) == 5

    def test_select_all_contexts_returns_sorted(self, selector, sample_contexts):
        """Test that all contexts are sorted by name."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_all_contexts()
            names = [c.name for c in result]
            assert names == sorted(names)


# =============================================================================
# TESTS: Argument Validation
# =============================================================================


class TestArgumentValidation:
    """Test validation of selection arguments."""

    def test_both_pattern_and_all_contexts_raises_error(self, selector):
        """Test that specifying both pattern and all_contexts raises error."""
        with pytest.raises(
            ContextSelectorError, match="Cannot specify both pattern and all_contexts"
        ):
            selector.select_contexts(pattern="prod*", all_contexts=True)

    def test_neither_pattern_nor_all_contexts_raises_error(self, selector):
        """Test that specifying neither argument raises error."""
        with pytest.raises(
            ContextSelectorError, match="Must specify either pattern or all_contexts"
        ):
            selector.select_contexts()

    def test_empty_pattern_raises_error(self, selector, sample_contexts):
        """Test that empty pattern is treated as falsy (no pattern/all_contexts)."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            # Empty string pattern is falsy, so it should be caught by the
            # "Must specify either pattern or all_contexts" check
            with pytest.raises(ContextSelectorError, match="Must specify either pattern or all_contexts"):
                selector.select_contexts(pattern="")


# =============================================================================
# TESTS: Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling for edge cases."""

    def test_no_contexts_defined(self, selector):
        """Test error when no contexts are defined."""
        config = Mock(spec=ContextConfig)
        config.contexts = {}

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            with pytest.raises(ContextSelectorError, match="No contexts defined"):
                selector.select_contexts(all_contexts=True)

    def test_no_contexts_match_pattern(self, selector, sample_contexts):
        """Test error when pattern matches no contexts."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            with pytest.raises(ContextSelectorError, match="No contexts match pattern"):
                selector.select_contexts(pattern="nonexistent*")

    def test_no_contexts_match_pattern_shows_available(self, selector, sample_contexts):
        """Test that error message shows available contexts."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            try:
                selector.select_contexts(pattern="xyz*")
                pytest.fail("Should have raised error")
            except ContextSelectorError as e:
                error_msg = str(e)
                assert "Available contexts" in error_msg
                assert "production" in error_msg

    def test_context_manager_load_error(self, selector):
        """Test error when ContextManager.load fails."""
        with patch(
            "azlin.context_selector.ContextManager.load",
            side_effect=ContextError("Config not found"),
        ):
            with pytest.raises(ContextSelectorError, match="Failed to load context config"):
                selector.select_contexts(all_contexts=True)

    def test_custom_config_path(self, selector, sample_contexts):
        """Test using custom config path."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts
        custom_path = "/custom/path/config.toml"

        selector_with_path = ContextSelector(config_path=custom_path)

        with patch("azlin.context_selector.ContextManager.load", return_value=config) as mock_load:
            result = selector_with_path.select_contexts(pattern="production")
            mock_load.assert_called_once_with(custom_path=custom_path)


# =============================================================================
# TESTS: Convenience Methods
# =============================================================================


class TestConvenienceMethods:
    """Test convenience wrapper methods."""

    def test_select_by_pattern_method(self, selector, sample_contexts):
        """Test select_by_pattern convenience method."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_by_pattern("prod*")
            assert len(result) == 2
            assert all(c.name.startswith("prod") for c in result)

    def test_select_by_pattern_no_matches(self, selector, sample_contexts):
        """Test select_by_pattern with no matches."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            with pytest.raises(ContextSelectorError, match="No contexts match"):
                selector.select_by_pattern("nonexistent*")

    def test_get_current_context(self, selector, sample_contexts):
        """Test getting current context."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts
        config.get_current_context.return_value = sample_contexts["production"]

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.get_current_context()
            assert result.name == "production"

    def test_get_current_context_none(self, selector, sample_contexts):
        """Test getting current context when not set."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts
        config.get_current_context.return_value = None

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.get_current_context()
            assert result is None

    def test_get_current_context_error(self, selector):
        """Test error getting current context."""
        with patch(
            "azlin.context_selector.ContextManager.load",
            side_effect=ContextError("Config not found"),
        ):
            with pytest.raises(ContextSelectorError, match="Failed to load context config"):
                selector.get_current_context()

    def test_list_available_contexts(self, selector, sample_contexts):
        """Test listing available context names."""
        config = Mock(spec=ContextConfig)
        config.contexts = sample_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.list_available_contexts()
            assert len(result) == 5
            assert result == sorted(sample_contexts.keys())

    def test_list_available_contexts_empty(self, selector):
        """Test listing contexts when none defined."""
        config = Mock(spec=ContextConfig)
        config.contexts = {}

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.list_available_contexts()
            assert result == []

    def test_list_available_contexts_error(self, selector):
        """Test error listing available contexts."""
        with patch(
            "azlin.context_selector.ContextManager.load",
            side_effect=ContextError("Config not found"),
        ):
            with pytest.raises(ContextSelectorError, match="Failed to load context config"):
                selector.list_available_contexts()


# =============================================================================
# TESTS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_context(self, selector):
        """Test selecting from single context."""
        single_context = {
            "production": Context(
                name="production",
                subscription_id="12345678-1234-1234-1234-123456789001",
                tenant_id="87654321-4321-4321-4321-210987654321",
            )
        }
        config = Mock(spec=ContextConfig)
        config.contexts = single_context

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(all_contexts=True)
            assert len(result) == 1
            assert result[0].name == "production"

    def test_many_contexts(self, selector):
        """Test selecting from many contexts."""
        many_contexts = {
            f"context-{i:02d}": Context(
                name=f"context-{i:02d}",
                subscription_id="12345678-1234-1234-1234-123456789001",
                tenant_id="87654321-4321-4321-4321-210987654321",
            )
            for i in range(20)
        }
        config = Mock(spec=ContextConfig)
        config.contexts = many_contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(all_contexts=True)
            assert len(result) == 20

    def test_context_names_with_special_chars(self, selector):
        """Test contexts with underscores and hyphens."""
        contexts = {
            "prod_env": Context(
                name="prod_env",
                subscription_id="12345678-1234-1234-1234-123456789001",
                tenant_id="87654321-4321-4321-4321-210987654321",
            ),
            "dev-env": Context(
                name="dev-env",
                subscription_id="12345678-1234-1234-1234-123456789002",
                tenant_id="87654321-4321-4321-4321-210987654321",
            ),
        }
        config = Mock(spec=ContextConfig)
        config.contexts = contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="*_*")
            assert len(result) == 1
            assert result[0].name == "prod_env"

    def test_numeric_context_names(self, selector):
        """Test contexts with numeric names."""
        contexts = {
            "1": Context(
                name="1",
                subscription_id="12345678-1234-1234-1234-123456789001",
                tenant_id="87654321-4321-4321-4321-210987654321",
            ),
            "2": Context(
                name="2",
                subscription_id="12345678-1234-1234-1234-123456789002",
                tenant_id="87654321-4321-4321-4321-210987654321",
            ),
        }
        config = Mock(spec=ContextConfig)
        config.contexts = contexts

        with patch("azlin.context_selector.ContextManager.load", return_value=config):
            result = selector.select_contexts(pattern="1")
            assert len(result) == 1
            assert result[0].name == "1"
