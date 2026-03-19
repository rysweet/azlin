"""Targeted tests for rust_bridge security hardening."""

from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from azlin import rust_bridge


def _make_archive(
    member_name: str = "azlin",
    *,
    member_type: bytes = tarfile.REGTYPE,
    link_target: str = "",
) -> bytes:
    """Build a minimal tar.gz archive for extraction tests."""
    payload = b"#!/bin/sh\necho azlin\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member_name)
        info.type = member_type
        info.mode = 0o755
        info.size = 0 if member_type == tarfile.SYMTYPE else len(payload)
        if member_type == tarfile.SYMTYPE:
            info.linkname = link_target
            tar.addfile(info)
        else:
            tar.addfile(info, io.BytesIO(payload))
    buffer.seek(0)
    return buffer.read()


class TestExtractReleaseBinary(unittest.TestCase):
    def _write_archive(self, tar_bytes: bytes) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp.write(tar_bytes)
        tmp.close()
        return Path(tmp.name)

    def test_uses_data_filter_on_python_312_plus(self) -> None:
        archive_path = self._write_archive(_make_archive())
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with mock.patch.object(rust_bridge, "_PY312_PLUS", True):
                    with mock.patch("tarfile.TarFile.extract") as extract_mock:
                        rust_bridge._extract_release_binary(archive_path, Path(tmpdir))

                extract_mock.assert_called_once()
                self.assertEqual(extract_mock.call_args.kwargs["filter"], "data")
        finally:
            archive_path.unlink(missing_ok=True)

    def test_rejects_path_traversal_member_on_older_python(self) -> None:
        archive_path = self._write_archive(_make_archive("../../azlin"))
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with mock.patch.object(rust_bridge, "_PY312_PLUS", False):
                    with self.assertRaises(rust_bridge.SecurityError):
                        rust_bridge._extract_release_binary(archive_path, Path(tmpdir))
        finally:
            archive_path.unlink(missing_ok=True)

    def test_rejects_symlink_member_on_older_python(self) -> None:
        archive_path = self._write_archive(
            _make_archive(
                member_name="azlin",
                member_type=tarfile.SYMTYPE,
                link_target="/etc/passwd",
            )
        )
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with mock.patch.object(rust_bridge, "_PY312_PLUS", False):
                    with self.assertRaises(rust_bridge.SecurityError):
                        rust_bridge._extract_release_binary(archive_path, Path(tmpdir))
        finally:
            archive_path.unlink(missing_ok=True)


class TestExecRust(unittest.TestCase):
    def test_execvp_passthrough_is_intentional(self) -> None:
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("os.execvp") as execvp_mock:
                rust_bridge._exec_rust("/tmp/azlin", ["--foo", "bar baz"])

        execvp_mock.assert_called_once_with(
            "/tmp/azlin",
            ["/tmp/azlin", "--foo", "bar baz"],
        )


if __name__ == "__main__":
    unittest.main()
