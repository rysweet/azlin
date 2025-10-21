"""Tests for MS Learn client module."""

import json
import time
from pathlib import Path

import pytest

from azlin.agentic.ms_learn_client import MSLearnClient, SearchResult


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "docs_cache"
    cache_dir.mkdir()
    return cache_dir


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a search result."""
        result = SearchResult(
            title="Test Document",
            url="https://example.com",
            summary="Test summary",
            relevance_score=0.95,
        )

        assert result.title == "Test Document"
        assert result.url == "https://example.com"
        assert result.summary == "Test summary"
        assert result.relevance_score == 0.95
        assert result.cached is False


class TestMSLearnClient:
    """Test MSLearnClient class."""

    def test_initialization(self, temp_cache_dir):
        """Test client initialization."""
        client = MSLearnClient(cache_dir=temp_cache_dir, cache_ttl_days=7)

        assert client.cache_dir == temp_cache_dir
        assert client.cache_ttl_seconds == 7 * 24 * 3600
        assert temp_cache_dir.exists()

    def test_search_quota_exceeded(self, temp_cache_dir):
        """Test searching for quota exceeded errors."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        results = client.search("QuotaExceeded", max_results=3)

        assert len(results) > 0
        assert len(results) <= 3
        # Should return quota-related docs
        assert any("quota" in r.title.lower() for r in results)

    def test_search_permission_error(self, temp_cache_dir):
        """Test searching for permission errors."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        results = client.search("AuthorizationFailed", max_results=3)

        assert len(results) > 0
        # Should return auth/permission-related docs
        assert any("authorization" in r.title.lower() or "rbac" in r.title.lower() for r in results)

    def test_search_with_resource_type(self, temp_cache_dir):
        """Test search with resource type."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        results = client.search("QuotaExceeded", resource_type="virtualMachines", max_results=3)

        assert len(results) > 0
        # Results should be relevant to VMs or general quota issues
        assert any("virtual" in r.title.lower() or "quota" in r.title.lower() for r in results)

    def test_search_caching(self, temp_cache_dir):
        """Test that search results are cached."""
        client = MSLearnClient(cache_dir=temp_cache_dir, cache_ttl_days=1)

        # First search
        results1 = client.search("QuotaExceeded", max_results=3)
        assert len(results1) > 0
        assert not results1[0].cached

        # Second search (should use cache)
        results2 = client.search("QuotaExceeded", max_results=3)
        assert len(results2) > 0
        assert results2[0].cached

        # Results should be identical
        assert len(results1) == len(results2)
        assert results1[0].title == results2[0].title

    def test_cache_expiration(self, temp_cache_dir):
        """Test that cache expires after TTL."""
        # Use very short TTL for testing (1 second = 1/86400 days)
        client = MSLearnClient(cache_dir=temp_cache_dir, cache_ttl_days=1 / 86400)

        # First search
        results1 = client.search("QuotaExceeded")
        assert not results1[0].cached

        # Wait for cache to expire
        time.sleep(1.1)

        # Second search (cache should be expired)
        results2 = client.search("QuotaExceeded")
        assert not results2[0].cached

    def test_filter_troubleshooting_docs(self, temp_cache_dir):
        """Test filtering to troubleshooting docs."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        # Create mixed results
        results = [
            SearchResult("Troubleshoot VM Issues", "https://example.com/troubleshoot", None, 0.0),
            SearchResult("VM Overview", "https://example.com/overview", None, 0.0),
            SearchResult("Resolve Error Codes", "https://example.com/errors", None, 0.0),
            SearchResult("Getting Started", "https://example.com/start", None, 0.0),
        ]

        filtered = client._filter_troubleshooting_docs(results)

        # Should prioritize troubleshooting/error docs
        assert len(filtered) >= 2
        assert any("troubleshoot" in r.title.lower() or "error" in r.title.lower() for r in filtered)

    def test_rank_by_relevance(self, temp_cache_dir):
        """Test relevance ranking."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        # Create results with varying relevance
        results = [
            SearchResult("General Azure Docs", "https://example.com/general", None, 0.0),
            SearchResult("QuotaExceeded Error", "https://example.com/quota-error", "Details about quota", 0.0),
            SearchResult("Troubleshoot Quotas", "https://example.com/troubleshoot-quota", "Quota troubleshooting", 0.0),
        ]

        ranked = client._rank_by_relevance(results, "QuotaExceeded", "virtualMachines")

        # Higher relevance should come first
        assert ranked[0].relevance_score > 0
        # Exact match in title should score highest
        assert "QuotaExceeded" in ranked[0].title or "Quota" in ranked[0].title

    def test_get_cache_key(self, temp_cache_dir):
        """Test cache key generation."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        key1 = client._get_cache_key("QuotaExceeded", "virtualMachines")
        key2 = client._get_cache_key("quotaexceeded", "virtualmachines")

        # Should be normalized (lowercase)
        assert key1 == key2
        assert key1.endswith(".json")

    def test_cache_key_sanitization(self, temp_cache_dir):
        """Test that cache keys are sanitized for filesystem."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        # Use characters that need sanitization
        key = client._get_cache_key("Error/Code:123", "Microsoft.Compute")

        # Should not contain invalid filesystem characters
        assert "/" not in key
        assert ":" not in key
        assert key.endswith(".json")

    def test_search_returns_max_results(self, temp_cache_dir):
        """Test that search respects max_results parameter."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        results_3 = client.search("QuotaExceeded", max_results=3)
        results_1 = client.search("AuthorizationFailed", max_results=1)

        assert len(results_3) <= 3
        assert len(results_1) <= 1

    def test_doc_templates_for_different_errors(self, temp_cache_dir):
        """Test that different error types return relevant doc templates."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        error_types = [
            ("QuotaExceeded", "quota"),
            ("AuthorizationFailed", "authorization"),
            ("ResourceNotFound", "not found"),
            ("NetworkError", "network"),
        ]

        for error_code, expected_keyword in error_types:
            templates = client._get_doc_templates(error_code, None)
            assert len(templates) > 0
            # Check that at least one template is relevant
            assert any(
                expected_keyword in template["title"].lower() or expected_keyword in template["url"].lower()
                for template in templates
            )

    def test_vm_specific_docs(self, temp_cache_dir):
        """Test that VM-specific errors include VM documentation."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        templates = client._get_doc_templates("SomeError", "virtualMachines")

        # Should include VM-specific docs
        assert any("vm" in template["title"].lower() or "virtual" in template["title"].lower() for template in templates)

    def test_fallback_to_generic_docs(self, temp_cache_dir):
        """Test fallback to generic docs for unknown errors."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        templates = client._get_doc_templates("UnknownError123", None)

        # Should return at least generic Azure troubleshooting docs
        assert len(templates) > 0
        assert any("troubleshoot" in template["title"].lower() for template in templates)

    def test_cache_permissions(self, temp_cache_dir):
        """Test that cached files have proper permissions."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        # Perform search to create cache
        client.search("QuotaExceeded")

        # Find cache file
        cache_files = list(temp_cache_dir.glob("*.json"))
        assert len(cache_files) > 0

        # Check permissions (0600 = owner read/write only)
        cache_file = cache_files[0]
        mode = cache_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_relevance_scoring_components(self, temp_cache_dir):
        """Test that relevance scoring considers multiple factors."""
        client = MSLearnClient(cache_dir=temp_cache_dir)

        results = [
            SearchResult(
                "QuotaExceeded troubleshoot",
                "https://example.com/quota-exceeded",
                "Details about QuotaExceeded error",
                0.0,
            ),
            SearchResult("Random doc", "https://example.com/random", "Random content", 0.0),
        ]

        ranked = client._rank_by_relevance(results, "QuotaExceeded", None)

        # First result should score much higher
        assert ranked[0].relevance_score > ranked[1].relevance_score
        # Score should consider title, URL, and summary
        assert ranked[0].relevance_score > 10.0  # Multiple matching factors
