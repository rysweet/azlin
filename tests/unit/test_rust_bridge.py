"""Tests for rust_bridge.py security hardening — Issue #876.

These tests define the contract for the new security components:

    SecurityError          — typed exception for tar extraction failures
    _PY312_PLUS            — module-level bool constant
    _is_release_binary_member — pure predicate: is this the azlin binary?
    _validate_release_member  — guard: raises SecurityError on unsafe members
    _extract_release_binary   — orchestrator: safe extraction to dest dir

All four tests will FAIL until the implementation adds those symbols.
They will PASS once the security hardening in PR #885 is merged.

Design spec references:
    SEC-R-01  path traversal via PurePosixPath.parts
    SEC-R-02  _PY312_PLUS uses tuple comparison sys.version_info >= (3, 12)
    SEC-R-03  copy.copy(member) before renaming to avoid mutating TarFile internals
    SEC-R-04  extractall() must never appear; use member-level extract
"""

import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# These imports will raise ImportError until the implementation is done.
# That is intentional: every test in this class is a FAILING test until
# the security hardening (Issue #876) has been implemented.
# ---------------------------------------------------------------------------
from azlin.rust_bridge import (  # noqa: E402 — must be after conftest path setup
    SecurityError,
    _PY312_PLUS,
    _extract_release_binary,
    _validate_release_member,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tar_gz(members: list[tuple[str, int, bytes]]) -> bytes:
    """Build an in-memory .tar.gz with the given (name, type, content) tuples."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, tar_type, content in members:
            info = tarfile.TarInfo(name=name)
            info.type = tar_type
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _make_tar_gz_file(tmp_path: Path, members: list[tuple[str, int, bytes]]) -> Path:
    """Write a .tar.gz to *tmp_path* and return its path."""
    data = _make_tar_gz(members)
    p = tmp_path / "release.tar.gz"
    p.write_bytes(data)
    return p


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestExtractReleaseBinary:
    """4 targeted unit tests covering the new security helpers (Issue #876)."""

    # ------------------------------------------------------------------
    # Test 1: filter='data' is passed to tarfile.extract on Python 3.12+
    # ------------------------------------------------------------------

    def test_filter_data_used_on_python_312_plus(self, tmp_path: Path) -> None:
        """On Python 3.12+, _extract_release_binary must call tar.extract with
        filter='data' to leverage the security filter introduced in CPython 3.12.

        On Python < 3.12, the filter keyword is not supported and must be omitted.

        Spec ref: SEC-R-02 (_PY312_PLUS), design component _extract_release_binary.
        """
        content = b"#!/bin/sh\necho azlin"
        tar_path = _make_tar_gz_file(
            tmp_path,
            [("azlin", tarfile.REGTYPE, content)],
        )

        if _PY312_PLUS:
            # Patch tarfile.TarFile.extract so we can inspect kwargs.
            # The real extraction is NOT performed; we only verify the call.
            with patch("tarfile.TarFile.extract") as mock_extract:
                _extract_release_binary(str(tar_path), tmp_path / "dest")

            assert mock_extract.called, (
                "_extract_release_binary must call tar.extract()"
            )
            filter_values = [
                c.kwargs.get("filter") for c in mock_extract.call_args_list
            ]
            assert "data" in filter_values, (
                "On Python 3.12+, extract() must be called with filter='data'. "
                f"Actual filter values seen: {filter_values}"
            )
        else:
            # On < 3.12: extraction must succeed without the filter kwarg.
            dest = tmp_path / "dest"
            _extract_release_binary(str(tar_path), dest)
            assert (dest / "azlin").exists(), (
                "Binary must be extracted to dest directory"
            )

    # ------------------------------------------------------------------
    # Test 2: path traversal entries are rejected
    # ------------------------------------------------------------------

    def test_path_traversal_rejected(self) -> None:
        """_validate_release_member must raise SecurityError for any member whose
        PurePosixPath.parts contain '..', blocking directory traversal attacks.

        The check must use pathlib.PurePosixPath(name).parts, NOT a naive string
        contains, so that names like 'foo..bar' are NOT falsely rejected.

        Spec ref: SEC-R-01.
        """
        from pathlib import PurePosixPath

        traversal_names = [
            "../etc/passwd",
            "subdir/../../etc/shadow",
            "./../../root/.ssh/authorized_keys",
            "../azlin",  # looks like a binary name but traverses up
        ]
        safe_name = "foo..bar"  # dots-in-name must NOT be rejected

        for name in traversal_names:
            # Verify the name actually has '..' in its PurePosixPath parts
            assert ".." in PurePosixPath(name).parts, (
                f"Test fixture error: '{name}' should contain '..' parts"
            )
            member = tarfile.TarInfo(name=name)
            member.type = tarfile.REGTYPE
            with pytest.raises(SecurityError):
                _validate_release_member(member)

        # Sanity check: a name with '..' in the *text* but not in *parts*
        # must NOT raise SecurityError (it's a valid leaf name).
        assert ".." not in PurePosixPath(safe_name).parts
        safe_member = tarfile.TarInfo(name=safe_name)
        safe_member.type = tarfile.REGTYPE
        # Should not raise:
        _validate_release_member(safe_member)

    # ------------------------------------------------------------------
    # Test 3: symlink members are rejected on Python < 3.12
    # ------------------------------------------------------------------

    def test_symlink_rejected_on_pre_312(self) -> None:
        """On Python < 3.12, _validate_release_member must raise SecurityError
        for symlink (SYMTYPE) and hard-link (LNKTYPE) members, because
        filter='data' is not available to handle them at the tarfile level.

        On Python 3.12+, filter='data' provides this guarantee at extraction
        time, so _validate_release_member may (but need not) reject them here;
        the important invariant is that filter='data' is used (Test 1).

        Spec ref: SEC-R-01 (non-regular-file members), SEC-R-02.
        """
        symlink_member = tarfile.TarInfo(name="azlin")
        symlink_member.type = tarfile.SYMTYPE
        symlink_member.linkname = "/usr/bin/malicious"

        hardlink_member = tarfile.TarInfo(name="azlin")
        hardlink_member.type = tarfile.LNKTYPE
        hardlink_member.linkname = "/etc/passwd"

        if not _PY312_PLUS:
            # Pre-3.12: guard must reject symlinks and hard links
            with pytest.raises(SecurityError):
                _validate_release_member(symlink_member)
            with pytest.raises(SecurityError):
                _validate_release_member(hardlink_member)
        else:
            # 3.12+: filter='data' handles this at extraction; the predicate
            # may choose to reject early (defensive), but Test 1 already covers
            # the filter='data' requirement.  We just document the 3.12+ branch.
            pytest.skip(
                "On Python 3.12+ symlink rejection is handled by filter='data' "
                "(see test_filter_data_used_on_python_312_plus)"
            )

    # ------------------------------------------------------------------
    # Test 4: SecurityError raised when no azlin binary is found in archive
    # ------------------------------------------------------------------

    def test_security_error_raised_when_no_binary_in_archive(
        self, tmp_path: Path
    ) -> None:
        """_extract_release_binary must raise SecurityError when the archive
        contains no member matching the azlin binary predicate.

        This prevents silent installation failures where a release asset is
        downloaded but the binary is absent (e.g., wrong platform tarball,
        corrupted or tampered archive).

        Spec ref: design component _extract_release_binary (raises SecurityError
        when no binary found after iterating all members).
        """
        # Archive with only a README — no 'azlin' binary
        tar_path = _make_tar_gz_file(
            tmp_path,
            [
                ("README.md", tarfile.REGTYPE, b"# azlin\n"),
                ("CHANGELOG.md", tarfile.REGTYPE, b"## v1.0\n"),
            ],
        )

        dest = tmp_path / "dest"
        with pytest.raises(SecurityError):
            _extract_release_binary(str(tar_path), dest)

        # Destination directory must NOT be left with partial content
        # (the binary should not exist even if extraction started)
        assert not (dest / "azlin").exists(), (
            "azlin binary must not exist in dest when SecurityError is raised"
        )
