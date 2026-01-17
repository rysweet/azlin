"""Tests for audit_key_operations.py script - WORKING IMPLEMENTATIONS"""

import subprocess
import tempfile
from pathlib import Path


class TestAuditScript:
    """Test the audit_key_operations.py script."""

    def test_detects_unsafe_redirect_pattern(self):
        """Test detects unsafe > authorized_keys pattern."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import subprocess
# UNSAFE: Replaces authorized_keys
subprocess.run("echo 'key' > ~/.ssh/authorized_keys", shell=True)
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1  # Should fail
            assert str(temp_file.name) in result.stdout
        finally:
            temp_file.unlink()

    def test_allows_safe_append_pattern(self):
        """Test allows safe >> authorized_keys pattern."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import subprocess
# SAFE: Appends to authorized_keys
subprocess.run("echo 'key' >> ~/.ssh/authorized_keys", shell=True)
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0  # Should pass
            assert "PASSED" in result.stdout
        finally:
            temp_file.unlink()

    def test_exit_code_zero_when_all_safe(self):
        """Test exits with code 0 when all patterns are safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file1.py").write_text(
                "subprocess.run('echo key >> authorized_keys', shell=True)"
            )

            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", tmpdir],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

    def test_exit_code_one_when_unsafe_found(self):
        """Test exits with code 1 when unsafe patterns found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "unsafe.py").write_text(
                "subprocess.run('echo key > authorized_keys', shell=True)"
            )

            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", tmpdir],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1

    def test_ignores_comments(self):
        """Test ignores patterns in comments."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
# This comment mentions: echo key > authorized_keys (UNSAFE in real code)
# But the actual code is safe:
subprocess.run("echo key >> authorized_keys", shell=True)
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0  # Should pass
        finally:
            temp_file.unlink()

    def test_reports_line_numbers(self):
        """Test reports exact line numbers of violations."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""# Line 1
# Line 2
# Line 3
subprocess.run("echo key > authorized_keys", shell=True)  # Line 4
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert ":4" in result.stdout or "line 4" in result.stdout.lower()
        finally:
            temp_file.unlink()

    def test_detects_unsafe_in_shell_script(self):
        """Test detects unsafe patterns in .sh files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("""#!/bin/bash
# UNSAFE: Direct overwrite
cat key.pub > ~/.ssh/authorized_keys
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
        finally:
            temp_file.unlink()

    def test_allows_tee_append(self):
        """Test allows safe tee -a pattern."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write("""#!/bin/bash
# SAFE: tee -a appends
cat key.pub | tee -a ~/.ssh/authorized_keys
""")
            temp_file = Path(f.name)

        try:
            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", str(temp_file.parent)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
        finally:
            temp_file.unlink()

    def test_recursive_directory_scan(self):
        """Test recursively scans subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            (subdir / "nested.py").write_text(
                "subprocess.run('echo key > authorized_keys', shell=True)"
            )

            result = subprocess.run(
                ["python3", "scripts/audit_key_operations.py", tmpdir],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1  # Should find violation in nested file
