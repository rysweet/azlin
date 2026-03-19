"""Test configuration and path setup.

Adds the repository root to sys.path so that both
`azlin` (src/azlin/) and `scripts` are importable
during pytest collection and execution.
"""

import sys
from pathlib import Path

# Repository root: tests/ is one level below the root
REPO_ROOT = Path(__file__).parent.parent

# src/azlin must be on the path for `import azlin`
_src = str(REPO_ROOT / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# Repo root must be on the path for `import scripts.cli_documentation`
_root = str(REPO_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)
