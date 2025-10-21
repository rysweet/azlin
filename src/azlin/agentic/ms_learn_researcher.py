"""Microsoft Learn documentation researcher.

Phase 6 Implementation (not yet implemented).

Researches Azure documentation for:
- Best practices
- Configuration examples
- API references
- Troubleshooting guides
"""

from typing import Any

from azlin.agentic.types import Intent


class MSLearnResearcher:
    """Researches Microsoft Learn documentation.

    Phase 6 will implement:
    - Search MS Learn docs
    - Extract relevant examples
    - Parse code snippets
    - Generate documentation summaries

    Example (when implemented):
        >>> researcher = MSLearnResearcher()
        >>> intent = Intent(intent="provision_aks", ...)
        >>> docs = researcher.research(intent)
        >>> for doc in docs:
        ...     print(f"Found: {doc['title']}")
        ...     print(f"URL: {doc['url']}")
    """

    def research(
        self,
        intent: Intent,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Research documentation for intent.

        TODO Phase 6:
        - Query MS Learn search API
        - Filter relevant results
        - Extract code examples
        - Return structured documentation

        Args:
            intent: Parsed intent
            max_results: Maximum number of results

        Returns:
            List of documentation entries with title, url, summary, examples

        Raises:
            NotImplementedError: Phase 6 not yet implemented
        """
        raise NotImplementedError("Phase 6 - MS Learn research not yet implemented")

    def find_examples(
        self,
        resource_type: str,
        language: str = "python",
    ) -> list[dict[str, Any]]:
        """Find code examples for resource type.

        TODO Phase 6:
        - Search for code examples
        - Filter by language
        - Parse and validate examples
        - Return structured examples

        Args:
            resource_type: Azure resource type (e.g., "vm", "aks")
            language: Programming language filter

        Returns:
            List of code examples

        Raises:
            NotImplementedError: Phase 6 not yet implemented
        """
        raise NotImplementedError("Phase 6 - example search not yet implemented")

    def get_best_practices(
        self,
        intent: Intent,
    ) -> list[str]:
        """Get best practices for intent.

        TODO Phase 6:
        - Extract best practices from docs
        - Rank by relevance
        - Return as bullet points

        Args:
            intent: Parsed intent

        Returns:
            List of best practice strings

        Raises:
            NotImplementedError: Phase 6 not yet implemented
        """
        raise NotImplementedError("Phase 6 - best practices extraction not yet implemented")
