"""MS Learn documentation search client.

This module provides intelligent search of Microsoft Learn documentation:
- Search MS Learn for error codes and troubleshooting guides
- Cache results locally with TTL
- Extract relevant documentation sections
- Rank results by relevance
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """MS Learn search result."""

    title: str
    url: str
    summary: str | None
    relevance_score: float
    cached: bool = False


class MSLearnClient:
    """Client for searching MS Learn documentation.

    Provides intelligent search with caching for Azure documentation:
    1. Search MS Learn for error codes and issues
    2. Filter to troubleshooting and error documentation
    3. Rank by relevance
    4. Cache results locally (7-day TTL)

    Example:
        >>> client = MSLearnClient()
        >>> results = client.search("QuotaExceeded", "virtualMachines")
        >>> for result in results[:3]:
        ...     print(result.title, result.url)
    """

    def __init__(self, cache_dir: Path | None = None, cache_ttl_days: int = 7):
        """Initialize MS Learn client.

        Args:
            cache_dir: Directory for caching search results
            cache_ttl_days: Cache time-to-live in days
        """
        self.cache_dir = cache_dir or Path.home() / ".azlin" / "docs_cache"
        self.cache_ttl_seconds = cache_ttl_days * 24 * 3600
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def search(
        self,
        error_code: str,
        resource_type: str | None = None,
        max_results: int = 3,
    ) -> list[SearchResult]:
        """Search MS Learn for relevant documentation.

        Args:
            error_code: Error code or issue keyword
            resource_type: Azure resource type (optional)
            max_results: Maximum results to return

        Returns:
            List of search results, ranked by relevance

        Example:
            >>> client = MSLearnClient()
            >>> results = client.search("InvalidParameter", "virtualMachines", max_results=5)
        """
        # Check cache first
        cache_key = self._get_cache_key(error_code, resource_type)
        cached_results = self._load_from_cache(cache_key)
        if cached_results:
            logger.info("Using cached MS Learn results for %s", error_code)
            return cached_results[:max_results]

        # Search MS Learn (in real implementation, would use API or scraping)
        results = self._search_ms_learn(error_code, resource_type)

        # Filter to troubleshooting/error docs
        results = self._filter_troubleshooting_docs(results)

        # Rank by relevance
        results = self._rank_by_relevance(results, error_code, resource_type)

        # Cache results
        self._save_to_cache(cache_key, results)

        return results[:max_results]

    def _search_ms_learn(
        self,
        error_code: str,
        resource_type: str | None,
    ) -> list[SearchResult]:
        """Search MS Learn documentation.

        In production, this would:
        1. Query MS Learn API or search endpoint
        2. Parse HTML results
        3. Extract title, URL, summary

        For now, returns simulated results based on patterns.

        Args:
            error_code: Error code to search
            resource_type: Resource type

        Returns:
            List of search results
        """
        # Build search query
        query_parts = [error_code]
        if resource_type:
            query_parts.append(resource_type)
        query_parts.append("Azure troubleshooting")

        query = " ".join(query_parts)
        quote_plus(query)

        # Simulate search results based on common Azure error patterns
        results = []

        # Pattern-based documentation links (real implementation would fetch these)
        doc_templates = self._get_doc_templates(error_code, resource_type)

        for template in doc_templates:
            result = SearchResult(
                title=template["title"],
                url=template["url"],
                summary=template["summary"],
                relevance_score=0.0,  # Will be calculated in ranking
            )
            results.append(result)

        return results

    def _get_doc_templates(
        self,
        error_code: str,
        resource_type: str | None,
    ) -> list[dict[str, str]]:
        """Get documentation templates based on error patterns.

        Args:
            error_code: Error code
            resource_type: Resource type

        Returns:
            List of doc templates
        """
        templates = []

        # Quota errors
        if "quota" in error_code.lower():
            templates.extend(
                [
                    {
                        "title": "Resolve errors for resource quotas",
                        "url": "https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-resource-quota",
                        "summary": "Learn how to resolve Azure resource quota errors and request quota increases.",
                    },
                    {
                        "title": "Azure subscription and service limits",
                        "url": "https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits",
                        "summary": "View default quotas and limits for Azure resources.",
                    },
                ]
            )

        # Permission errors
        elif "permission" in error_code.lower() or "authorization" in error_code.lower():
            templates.extend(
                [
                    {
                        "title": "Troubleshoot Azure RBAC",
                        "url": "https://learn.microsoft.com/en-us/azure/role-based-access-control/troubleshooting",
                        "summary": "Troubleshoot Azure role-based access control (RBAC) issues.",
                    },
                    {
                        "title": "Resolve authorization errors",
                        "url": "https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-authorization-failed",
                        "summary": "Learn how to resolve authorization and permission errors in Azure.",
                    },
                ]
            )

        # Resource not found errors
        elif "notfound" in error_code.lower() or "not found" in error_code.lower():
            templates.extend(
                [
                    {
                        "title": "Resolve resource not found errors",
                        "url": "https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-not-found",
                        "summary": "Troubleshoot errors when Azure resources cannot be found.",
                    },
                ]
            )

        # Network errors
        elif "network" in error_code.lower() or "timeout" in error_code.lower():
            templates.extend(
                [
                    {
                        "title": "Troubleshoot Azure network issues",
                        "url": "https://learn.microsoft.com/en-us/azure/networking/troubleshoot-network-issues",
                        "summary": "Diagnose and resolve Azure networking and connectivity issues.",
                    },
                ]
            )

        # VM-specific errors
        if resource_type and ("vm" in resource_type.lower() or "virtual" in resource_type.lower()):
            templates.extend(
                [
                    {
                        "title": "Troubleshoot Azure VM deployment",
                        "url": "https://learn.microsoft.com/en-us/azure/virtual-machines/troubleshooting/",
                        "summary": "Troubleshoot common Azure virtual machine deployment and runtime issues.",
                    },
                ]
            )

        # Generic Azure troubleshooting
        if not templates:
            templates.extend(
                [
                    {
                        "title": "Azure troubleshooting documentation",
                        "url": "https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/",
                        "summary": "General Azure troubleshooting guides and error resolution.",
                    },
                ]
            )

        return templates

    def _filter_troubleshooting_docs(self, results: list[SearchResult]) -> list[SearchResult]:
        """Filter to troubleshooting and error documentation.

        Args:
            results: Search results

        Returns:
            Filtered results
        """
        troubleshooting_keywords = [
            "troubleshoot",
            "error",
            "resolve",
            "fix",
            "issue",
            "problem",
            "diagnose",
        ]

        filtered = []
        for result in results:
            title_lower = result.title.lower()
            url_lower = result.url.lower()

            # Check if title or URL contains troubleshooting keywords
            if any(
                keyword in title_lower or keyword in url_lower
                for keyword in troubleshooting_keywords
            ):
                filtered.append(result)

        return filtered or results  # Return all if none match

    def _rank_by_relevance(
        self,
        results: list[SearchResult],
        error_code: str,
        resource_type: str | None,
    ) -> list[SearchResult]:
        """Rank results by relevance score.

        Args:
            results: Search results
            error_code: Error code being searched
            resource_type: Resource type

        Returns:
            Results sorted by relevance (highest first)
        """
        error_lower = error_code.lower()
        resource_lower = (resource_type or "").lower()

        for result in results:
            score = 0.0

            title_lower = result.title.lower()
            url_lower = result.url.lower()
            summary_lower = (result.summary or "").lower()

            # Exact error code match in title (highest score)
            if error_lower in title_lower:
                score += 10.0

            # Error code in URL or summary
            if error_lower in url_lower:
                score += 5.0
            if error_lower in summary_lower:
                score += 3.0

            # Resource type match
            if resource_lower and resource_lower in title_lower:
                score += 5.0
            if resource_lower and resource_lower in url_lower:
                score += 3.0

            # Prioritize "troubleshoot" and "error" docs
            if "troubleshoot" in title_lower:
                score += 2.0
            if "error" in title_lower:
                score += 2.0

            result.relevance_score = score

        # Sort by relevance (highest first)
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    def _get_cache_key(self, error_code: str, resource_type: str | None) -> str:
        """Generate cache key from search parameters.

        Args:
            error_code: Error code
            resource_type: Resource type

        Returns:
            Cache key string
        """
        parts = [error_code.lower()]
        if resource_type:
            parts.append(resource_type.lower())

        # Sanitize for filename
        key = "_".join(parts)
        key = re.sub(r"[^\w\-]", "_", key)
        return f"{key}.json"

    def _load_from_cache(self, cache_key: str) -> list[SearchResult] | None:
        """Load search results from cache if not expired.

        Args:
            cache_key: Cache key

        Returns:
            Cached results or None if not found/expired
        """
        cache_file = self.cache_dir / cache_key

        if not cache_file.exists():
            return None

        try:
            # Check if cache is expired
            file_age = time.time() - cache_file.stat().st_mtime
            if file_age > self.cache_ttl_seconds:
                logger.debug("Cache expired for %s", cache_key)
                cache_file.unlink()
                return None

            # Load cache
            data = json.loads(cache_file.read_text())
            return [
                SearchResult(
                    title=item["title"],
                    url=item["url"],
                    summary=item.get("summary"),
                    relevance_score=item["relevance_score"],
                    cached=True,
                )
                for item in data
            ]

        except Exception:
            logger.warning("Failed to load cache for %s", cache_key)
            return None

    def _save_to_cache(self, cache_key: str, results: list[SearchResult]) -> None:
        """Save search results to cache.

        Args:
            cache_key: Cache key
            results: Results to cache
        """
        cache_file = self.cache_dir / cache_key

        try:
            data = [
                {
                    "title": result.title,
                    "url": result.url,
                    "summary": result.summary,
                    "relevance_score": result.relevance_score,
                }
                for result in results
            ]

            cache_file.write_text(json.dumps(data, indent=2))
            cache_file.chmod(0o600)

        except Exception:
            logger.exception("Failed to save cache for %s", cache_key)
