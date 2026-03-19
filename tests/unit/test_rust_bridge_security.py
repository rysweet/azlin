"""Security tests for rust_bridge.py — binary bootstrapper.

These tests verify that the tar-extraction path cannot be exploited via:
  - Path traversal members (../../etc/passwd)
  - Absolute-path members (/etc/cron.d/evil)
  - Symlink members (on Python < 3.12)
  - Device-file members (on Python < 3.12)
  - Archives that contain no azlin binary

Design spec refs:
    SEC-R-01  Validate all tar members before extraction (CRITICAL)
    SEC-R-02  filter='data' on Python >= 3.12 (HIGH)
    SEC-R-03  Normalise extracted member name to "azlin" (HIGH)
    SEC-R-04  Skip-all-but-one; never extractall() (HIGH)
    SEC-R-06  Temp file cleanup in finally block (LOW)
    SEC-R-07  SecurityError NOT caught by download handler (LOW)
"""

import io
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.rust_bridge import (
    SecurityError,
    _extract_release_binary,
    _is_release_binary_member,
    _validate_release_member,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tarball(members: list[tuple[str, bytes, str]]) -> Path:
    """Write an in-memory tar.gz to a temp file and return its path.

    Each element of *members* is (name, content_bytes, type) where type is
    one of: 'file', 'symlink', 'hardlink'.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content, member_type in members:
            info = tarfile.TarInfo(name=name)
            if member_type == "file":
                info.type = tarfile.REGTYPE
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            elif member_type == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "target"
                tar.addfile(info)
            elif member_type == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = "target"
                tar.addfile(info)
    buf.seek(0)

    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    tmp.write(buf.read())
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _make_info(name: str, member_type: str = "file") -> tarfile.TarInfo:
    """Return a TarInfo with the given name and type."""
    info = tarfile.TarInfo(name=name)
    if member_type == "file":
        info.type = tarfile.REGTYPE
    elif member_type == "symlink":
        info.type = tarfile.SYMTYPE
        info.linkname = "target"
    elif member_type == "hardlink":
        info.type = tarfile.LNKTYPE
        info.linkname = "target"
    elif member_type == "device":
        info.type = tarfile.CHRTYPE
    return info


# ---------------------------------------------------------------------------
# SEC-R-01 / _validate_release_member: path traversal & type checks
# ---------------------------------------------------------------------------


class TestValidateReleaseMember:
    """Unit tests for _validate_release_member()."""

    def test_valid_regular_file_passes(self):
        """A plain regular file with a safe relative name is accepted."""
        info = _make_info("azlin-v1.0/azlin", member_type="file")
        # Should not raise
        _validate_release_member(info)

    def test_rejects_absolute_path_member(self):
        """A member with an absolute path is rejected with SecurityError."""
        info = _make_info("/etc/cron.d/evil", member_type="file")
        with pytest.raises(SecurityError, match="Absolute path"):
            _validate_release_member(info)

    def test_rejects_path_traversal_member(self):
        """A member with '..' in its path is rejected with SecurityError."""
        info = _make_info("../../etc/passwd", member_type="file")
        with pytest.raises(SecurityError, match="Path traversal"):
            _validate_release_member(info)

    def test_rejects_path_traversal_nested(self):
        """Traversal nested inside a subdirectory is also rejected."""
        info = _make_info("legitimate/../../etc/shadow", member_type="file")
        with pytest.raises(SecurityError, match="Path traversal"):
            _validate_release_member(info)

    def test_allows_dotdot_in_filename_component(self):
        """'foo..bar' (dotdot inside a component) is NOT traversal — allowed."""
        info = _make_info("foo..bar/azlin", member_type="file")
        # Should not raise — 'foo..bar' is not the same as '..'
        _validate_release_member(info)

    @pytest.mark.skipif(
        sys.version_info >= (3, 12),
        reason="filter='data' handles this on Python 3.12+",
    )
    def test_rejects_symlink_member_on_older_python(self):
        """On Python < 3.12 a symlink member is rejected with SecurityError."""
        info = _make_info("azlin", member_type="symlink")
        with pytest.raises(SecurityError, match="Non-regular-file"):
            _validate_release_member(info)

    @pytest.mark.skipif(
        sys.version_info >= (3, 12),
        reason="filter='data' handles this on Python 3.12+",
    )
    def test_rejects_hardlink_member_on_older_python(self):
        """On Python < 3.12 a hard-link member is rejected with SecurityError."""
        info = _make_info("azlin", member_type="hardlink")
        with pytest.raises(SecurityError, match="Non-regular-file"):
            _validate_release_member(info)

    @pytest.mark.skipif(
        sys.version_info >= (3, 12),
        reason="filter='data' handles this on Python 3.12+",
    )
    def test_rejects_device_file_on_older_python(self):
        """On Python < 3.12 a device-file member is rejected with SecurityError."""
        info = _make_info("azlin", member_type="device")
        with pytest.raises(SecurityError, match="Non-regular-file"):
            _validate_release_member(info)


# ---------------------------------------------------------------------------
# _is_release_binary_member: predicate
# ---------------------------------------------------------------------------


class TestIsReleaseBinaryMember:
    def test_exact_name(self):
        assert _is_release_binary_member("azlin") is True

    def test_path_ending_in_azlin(self):
        assert _is_release_binary_member("dist/azlin") is True

    def test_version_dir_ending_in_azlin(self):
        assert _is_release_binary_member("azlin-1.2.3/azlin") is True

    def test_does_not_match_different_binary(self):
        assert _is_release_binary_member("azlinx") is False

    def test_does_not_match_partial_suffix(self):
        assert _is_release_binary_member("src/azlin.sh") is False


# ---------------------------------------------------------------------------
# SEC-R-04 / _extract_release_binary: no binary in archive
# ---------------------------------------------------------------------------


class TestExtractReleaseBinary:
    def test_raises_when_no_binary_in_archive(self, tmp_path):
        """An archive with no azlin binary raises SecurityError."""
        tarball = _make_tarball([("README.txt", b"hello", "file")])
        try:
            with pytest.raises(SecurityError, match="azlin binary not found"):
                _extract_release_binary(tarball, tmp_path)
        finally:
            tarball.unlink(missing_ok=True)

    def test_extracts_binary_to_normalised_name(self, tmp_path):
        """The binary is always written as 'azlin', regardless of member name."""
        content = b"fake-binary-content"
        tarball = _make_tarball([("dist/v1.2.3/azlin", content, "file")])
        try:
            _extract_release_binary(tarball, tmp_path)
            output = tmp_path / "azlin"
            assert output.exists(), "azlin binary should be extracted"
            assert output.read_bytes() == content
        finally:
            tarball.unlink(missing_ok=True)

    def test_rejects_traversal_member_named_like_binary(self, tmp_path):
        """A member like '../../azlin' is rejected even though it ends with /azlin."""
        tarball = _make_tarball([("../../azlin", b"evil", "file")])
        try:
            with pytest.raises(SecurityError, match="Path traversal"):
                _extract_release_binary(tarball, tmp_path)
        finally:
            tarball.unlink(missing_ok=True)

    @pytest.mark.skipif(
        sys.version_info >= (3, 12),
        reason="filter='data' handles symlinks on Python 3.12+",
    )
    def test_rejects_symlink_named_like_binary(self, tmp_path):
        """A symlink member named 'azlin' is rejected on Python < 3.12."""
        tarball = _make_tarball([("azlin", b"", "symlink")])
        try:
            with pytest.raises(SecurityError, match="Non-regular-file"):
                _extract_release_binary(tarball, tmp_path)
        finally:
            tarball.unlink(missing_ok=True)

    @pytest.mark.skipif(
        sys.version_info < (3, 12),
        reason="filter='data' only available on Python 3.12+",
    )
    def test_uses_data_filter_on_python_312_plus(self, tmp_path):
        """On Python >= 3.12 tar.extract() is called with filter='data'."""
        content = b"fake-binary-content"
        tarball = _make_tarball([("azlin", content, "file")])
        try:
            with patch("azlin.rust_bridge._PY312_PLUS", True):
                with patch("tarfile.TarFile.extract") as mock_extract:
                    _extract_release_binary(tarball, tmp_path)
                    _, kwargs = mock_extract.call_args
                    assert kwargs.get("filter") == "data", (
                        "filter='data' must be passed to tar.extract() on Python 3.12+"
                    )
        finally:
            tarball.unlink(missing_ok=True)

    def test_only_binary_member_extracted(self, tmp_path):
        """Only the binary member is extracted; other members are skipped."""
        content = b"fake-binary-content"
        tarball = _make_tarball(
            [
                ("README.txt", b"ignore me", "file"),
                ("azlin", content, "file"),
                ("LICENSE", b"also ignore", "file"),
            ]
        )
        try:
            _extract_release_binary(tarball, tmp_path)
            assert (tmp_path / "azlin").exists()
            assert not (tmp_path / "README.txt").exists()
            assert not (tmp_path / "LICENSE").exists()
        finally:
            tarball.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# SEC-R-06 / _download_from_release: temp file cleanup
# ---------------------------------------------------------------------------


class TestTempFileCleanup:
    """Verify that temp files are always cleaned up, even on extraction failure."""

    def test_temp_file_cleaned_up_on_security_error(self, tmp_path, monkeypatch):
        """If SecurityError is raised during extraction, the temp file is removed."""
        import azlin.rust_bridge as rb

        captured_tmp: list[Path] = []

        original_mktemp = tempfile.NamedTemporaryFile

        def tracking_mktemp(*args, **kwargs):
            f = original_mktemp(*args, **kwargs)
            captured_tmp.append(Path(f.name))
            return f

        monkeypatch.setattr(tempfile, "NamedTemporaryFile", tracking_mktemp)

        # Simulate a SecurityError during extraction
        def bad_extract(tmp_path, destination):
            raise SecurityError("simulated traversal attack")

        monkeypatch.setattr(rb, "_extract_release_binary", bad_extract)
        monkeypatch.setattr(rb, "MANAGED_BIN_DIR", tmp_path)
        monkeypatch.setattr(rb, "MANAGED_BIN", tmp_path / "azlin")

        # Provide a fake release list and download URL
        fake_releases = [
            {
                "tag_name": "v0.1.0-rust",
                "assets": [
                    {
                        "name": f"azlin-{rb._platform_suffix() or 'linux-x86_64'}.tar.gz",
                        "browser_download_url": "http://example.com/azlin.tar.gz",
                    }
                ],
            }
        ]

        with patch("azlin.rust_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = (
                __import__("json").dumps(fake_releases).encode()
            )
            mock_urlopen.return_value = mock_resp

            with patch("azlin.rust_bridge.urllib.request.urlretrieve"):
                # SecurityError should propagate (not be caught)
                with pytest.raises(SecurityError):
                    rb._download_from_release()

        # The temp file must have been deleted despite the SecurityError
        for tmp in captured_tmp:
            assert not tmp.exists(), (
                f"Temp file {tmp} was not cleaned up after SecurityError"
            )


# ---------------------------------------------------------------------------
# SEC-R-07: SecurityError NOT swallowed by the download handler
# ---------------------------------------------------------------------------


class TestSecurityErrorPropagation:
    """SecurityError must propagate out of _download_from_release() uncaught."""

    def test_security_error_propagates_from_download_handler(
        self, tmp_path, monkeypatch
    ):
        """_download_from_release() must NOT catch SecurityError."""
        import azlin.rust_bridge as rb

        monkeypatch.setattr(rb, "MANAGED_BIN_DIR", tmp_path)
        monkeypatch.setattr(rb, "MANAGED_BIN", tmp_path / "azlin")

        def evil_extract(tmp_path, destination):
            raise SecurityError("path traversal detected")

        monkeypatch.setattr(rb, "_extract_release_binary", evil_extract)

        fake_releases = [
            {
                "tag_name": "v0.1.0-rust",
                "assets": [
                    {
                        "name": f"azlin-{rb._platform_suffix() or 'linux-x86_64'}.tar.gz",
                        "browser_download_url": "http://example.com/azlin.tar.gz",
                    }
                ],
            }
        ]

        with patch("azlin.rust_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = (
                __import__("json").dumps(fake_releases).encode()
            )
            mock_urlopen.return_value = mock_resp

            with patch("azlin.rust_bridge.urllib.request.urlretrieve"):
                with pytest.raises(SecurityError, match="path traversal detected"):
                    rb._download_from_release()
