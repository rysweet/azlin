"""Documentation consistency tests for the azlin repo.

These tests codify the contract that user-facing documentation must agree with
the *authoritative* values defined in the Rust source code. They are written
TDD-style: the version-drift assertions below FAIL when docs assert a stale
default (e.g. Ubuntu 24.04 default, Node.js 20, Python 3.11 in the dev-tool
list) and PASS once the docs are aligned with code.

Authoritative sources (single source of truth):
  * rust/crates/azlin-core/src/models.rs   -> default VM image + shorthands
  * rust/crates/azlin-azure/src/cloud_init.rs -> installed dev-tool versions

Run with:  pytest scripts/test_docs_consistency.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

MODELS_RS = REPO_ROOT / "rust" / "crates" / "azlin-core" / "src" / "models.rs"
CLOUD_INIT_RS = REPO_ROOT / "rust" / "crates" / "azlin-azure" / "src" / "cloud_init.rs"

# Doc roots that contain user-facing assertions about current behaviour.
DOC_GLOBS = ["README.md", "docs/**/*.md", "docs-site/**/*.md"]

# Files/areas that are historical, illustrative, or auto-generated context and
# therefore intentionally excluded from "current default" assertions.
EXCLUDE_SUBSTRINGS = (
    "CHANGELOG",
    "MIGRATION",
    "RUST_MIGRATION_ASSESSMENT",
    "DESIGN_UPDATE_COMMAND",
    "/pwa/",
    "node_modules",
)


# --------------------------------------------------------------------------- #
# Authoritative value extraction (parsed from code, never hard-coded twice).
# --------------------------------------------------------------------------- #
def _read(path: Path) -> str:
    assert path.exists(), f"Authoritative source missing: {path}"
    return path.read_text(encoding="utf-8")


def authoritative_default_image() -> str:
    """Return the default Ubuntu offer string, e.g. 'ubuntu-26_04-lts'."""
    text = _read(MODELS_RS)
    # The Default impl sets `offer: "ubuntu-XX_YY-lts".into(),`
    m = re.search(r'offer:\s*"(ubuntu-[\d_]+(?:-lts)?)"\s*\.into\(\)', text)
    assert m, "Could not parse default VM image offer from models.rs"
    return m.group(1)


def authoritative_default_ubuntu_version() -> str:
    """Return the human-facing default Ubuntu version, e.g. '26.04'."""
    offer = authoritative_default_image()  # ubuntu-26_04-lts
    m = re.search(r"ubuntu-(\d+)_(\d+)", offer)
    assert m, f"Unexpected offer format: {offer}"
    return f"{m.group(1)}.{m.group(2)}"


def authoritative_node_major() -> str:
    """Return the installed Node.js major version, e.g. '24'."""
    text = _read(CLOUD_INIT_RS)
    m = re.search(r"nodesource\.com/setup_(\d+)\.x", text)
    assert m, "Could not parse Node.js version from cloud_init.rs"
    return m.group(1)


def authoritative_go_version() -> str:
    """Return the installed Go version, e.g. '1.26.4'."""
    text = _read(CLOUD_INIT_RS)
    m = re.search(r"go(\d+\.\d+\.\d+)\.linux", text)
    assert m, "Could not parse Go version from cloud_init.rs"
    return m.group(1)


def authoritative_dotnet_channel() -> str:
    """Return the installed .NET channel, e.g. '10.0'."""
    text = _read(CLOUD_INIT_RS)
    m = re.search(r"--channel\s+(\d+\.\d+)", text)
    assert m, "Could not parse .NET channel from cloud_init.rs"
    return m.group(1)


def authoritative_python_minor() -> str:
    """Return the installed Python version on the VM, e.g. '3.14'."""
    text = _read(CLOUD_INIT_RS)
    m = re.search(r"python(3\.\d+)\s+--version", text)
    assert m, "Could not parse Python version from cloud_init.rs"
    return m.group(1)


# --------------------------------------------------------------------------- #
# Doc collection helpers.
# --------------------------------------------------------------------------- #
def _iter_doc_files():
    seen = set()
    for pattern in DOC_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            posix = path.as_posix()
            if any(sub in posix for sub in EXCLUDE_SUBSTRINGS):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _doc_lines():
    for path in _iter_doc_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            yield path, lineno, line


# --------------------------------------------------------------------------- #
# Tests: authoritative extraction sanity.
# --------------------------------------------------------------------------- #
class TestAuthoritativeValues:
    def test_default_image_is_ubuntu_26_04(self):
        assert authoritative_default_image() == "ubuntu-26_04-lts"
        assert authoritative_default_ubuntu_version() == "26.04"

    def test_toolchain_versions(self):
        assert authoritative_node_major() == "24"
        assert authoritative_go_version() == "1.26.4"
        assert authoritative_dotnet_channel() == "10.0"
        assert authoritative_python_minor() == "3.14"


# --------------------------------------------------------------------------- #
# Tests: docs must not assert a stale *default* OS.
# --------------------------------------------------------------------------- #
class TestDefaultOsDrift:
    # A line that pairs the word "default" with a concrete Ubuntu version is an
    # assertion about the default OS. If that version isn't the authoritative
    # one, it's drift.
    _DEFAULT_OS_RE = re.compile(
        r"default[^.\n]{0,60}?ubuntu[^.\n]{0,20}?(\d{2}\.\d{2})"
        r"|ubuntu[^.\n]{0,20}?(\d{2}\.\d{2})[^.\n]{0,40}?default",
        re.IGNORECASE,
    )

    def test_no_stale_default_os_assertion(self):
        expected = authoritative_default_ubuntu_version()
        offenders = []
        for path, lineno, line in _doc_lines():
            m = self._DEFAULT_OS_RE.search(line)
            if not m:
                continue
            version = m.group(1) or m.group(2)
            if version != expected:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
                )
        assert not offenders, (
            f"Docs assert a stale default OS (expected Ubuntu {expected}):\n"
            + "\n".join(offenders)
        )


# --------------------------------------------------------------------------- #
# Tests: the dev-tool example listings that mirror the installed toolchain must
# use the authoritative versions (these are the lines fixed in this task).
# --------------------------------------------------------------------------- #
class TestToolListDrift:
    """Doc references to the installed toolchain must reflect the authoritative
    versions, not stale ones."""

    _NODE_RE = re.compile(r"node\.?js?\s+(\d{2})", re.IGNORECASE)
    # Python version with an optional trailing '+' (prerequisite phrasing).
    _PY_RE = re.compile(r"python\s+3\.(\d+)(\+?)", re.IGNORECASE)

    def test_installed_node_version_is_current(self):
        """Any concrete 'Node.js NN' assertion must match the installed major.

        azlin is a Rust binary with no Node prerequisite, so every Node.js
        version mention describes the VM-installed toolchain (Node 24 LTS).
        """
        node_major = authoritative_node_major()
        offenders = []
        for path, lineno, line in _doc_lines():
            m = self._NODE_RE.search(line)
            if m and m.group(1) != node_major:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno} "
                    f"(Node {m.group(1)} != {node_major}): {line.strip()}"
                )
        assert not offenders, (
            f"Docs reference a stale Node.js version (installed: {node_major}):\n"
            + "\n".join(offenders)
        )

    def test_installed_python_version_is_current(self):
        """A bare 'Python 3.NN' (no '+') describes the installed VM Python and
        must match 3.14. Prerequisite phrasing ('3.11+', '3.10+') and historical
        snapshot labels ('Pre-Python 3.13') are intentionally allowed.
        """
        py_minor = authoritative_python_minor().split(".")[1]  # '14'
        offenders = []
        for path, lineno, line in _doc_lines():
            low = line.lower()
            if "pre-python" in low:  # historical annotation
                continue
            m = self._PY_RE.search(line)
            if not m:
                continue
            minor, plus = m.group(1), m.group(2)
            if plus == "+":  # prerequisite / minimum-version phrasing
                continue
            if minor != py_minor:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{lineno} "
                    f"(Python 3.{minor} != 3.{py_minor}): {line.strip()}"
                )
        assert not offenders, (
            f"Docs assert a stale installed Python version (3.{py_minor}):\n"
            + "\n".join(offenders)
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
