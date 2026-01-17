"""Azure DevOps CLI tools for common workflows.

This package provides command-line tools for working with Azure DevOps:
- auth_check: Verify authentication and configuration
- format_html: Convert markdown to Azure DevOps HTML
- create_work_item: Create work items with formatted descriptions
- link_parent: Link work items to parent items
- query_wiql: Execute WIQL queries
- list_types: List work item types and fields
"""

__version__ = "0.1.0"
__all__ = [
    "auth_check",
    "create_work_item",
    "format_html",
    "link_parent",
    "list_types",
    "query_wiql",
]
