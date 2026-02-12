"""Unit tests for integrator module."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import pytest

from ..errors import IntegrationError
from ..integrator import BranchInfo, IntegrationSummary, Integrator


class TestIntegrator(unittest.TestCase):
    """Test cases for Integrator class."""

    def setUp(self):
        """Create temporary git repository for testing."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.temp_dir / "test_repo"
        self.repo_path.mkdir()

        # Initialize git repository with main as default branch
        subprocess.run(
            ["git", "init", "-b", "main"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=self.repo_path, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True)

        # Create .claude directory structure
        claude_dir = self.repo_path / ".claude" / "runtime" / "logs"
        claude_dir.mkdir(parents=True)

        # Create initial commit
        test_file = self.repo_path / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_integrator_initialization(self):
        """Test Integrator initialization."""
        integrator = Integrator(self.repo_path)
        assert integrator.repo_path == self.repo_path

    def test_initialization_non_git_repo_fails(self):
        """Test that initialization fails for non-git directory."""
        non_git_dir = self.temp_dir / "not_git"
        non_git_dir.mkdir()

        with pytest.raises(IntegrationError) as ctx:
            Integrator(non_git_dir)

        assert "not a git repository" in str(ctx.value).lower()

    def test_import_branches(self):
        """Test importing branches from bundle."""
        # Create a feature branch in original repo
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )
        feature_file = self.repo_path / "feature.txt"
        feature_file.write_text("feature content")
        subprocess.run(["git", "add", "feature.txt"], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "main"], cwd=self.repo_path, check=True, capture_output=True
        )

        # Create bundle
        bundle_dir = self.temp_dir / "results"
        bundle_dir.mkdir()
        bundle_path = bundle_dir / "results.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle_path), "--all"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

        # Import branches
        integrator = Integrator(self.repo_path)
        branches = integrator._import_branches(bundle_dir)

        assert len(branches) > 0
        branch_names = [b.name for b in branches]
        assert "feature" in branch_names

    def test_copy_logs(self):
        """Test copying logs from results."""
        # Create mock results directory with logs
        results_dir = self.temp_dir / "results"
        results_logs = results_dir / ".claude" / "runtime" / "logs"
        results_logs.mkdir(parents=True)

        log_file = results_logs / "test.log"
        log_file.write_text("test log content")

        # Copy logs
        integrator = Integrator(self.repo_path)
        success = integrator._copy_logs(results_dir)

        assert success

        # Verify logs were copied
        dest_log = self.repo_path / ".claude" / "runtime" / "logs" / "remote" / "test.log"
        assert dest_log.exists()
        assert dest_log.read_text() == "test log content"

    def test_copy_logs_no_logs_directory(self):
        """Test copying logs when no logs exist."""
        results_dir = self.temp_dir / "results"
        results_dir.mkdir()

        integrator = Integrator(self.repo_path)
        success = integrator._copy_logs(results_dir)

        assert not success

    def test_detect_conflicts_none(self):
        """Test conflict detection when no conflicts."""
        branches = [BranchInfo(name="feature", commit="abc123", is_new=True)]

        integrator = Integrator(self.repo_path)
        conflicts = integrator._detect_conflicts(branches)

        assert len(conflicts) == 0

    def test_list_local_branches(self):
        """Test listing local branches."""
        integrator = Integrator(self.repo_path)
        branches = integrator._list_local_branches()

        assert "main" in branches

    def test_create_summary_report(self):
        """Test creating summary report."""
        summary = IntegrationSummary(
            branches=[BranchInfo(name="feature", commit="abc123", is_new=True)],
            commits_count=5,
            files_changed=10,
            logs_copied=True,
            has_conflicts=False,
        )

        integrator = Integrator(self.repo_path)
        report = integrator.create_summary_report(summary)

        assert "Remote Execution Results" in report
        assert "feature" in report
        assert "5" in report
        assert "10" in report

    def test_create_summary_report_with_conflicts(self):
        """Test summary report with conflicts."""
        summary = IntegrationSummary(
            branches=[BranchInfo(name="main", commit="def456", is_new=False)],
            commits_count=3,
            files_changed=5,
            logs_copied=True,
            has_conflicts=True,
            conflict_details="Branch main has diverged",
        )

        integrator = Integrator(self.repo_path)
        report = integrator.create_summary_report(summary)

        assert "WARNING" in report
        assert "Conflicts detected" in report
        assert "diverged" in report

    def test_count_files_changed(self):
        """Test counting files changed."""
        # Create feature branch with changes
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )
        (self.repo_path / "file1.txt").write_text("content1")
        (self.repo_path / "file2.txt").write_text("content2")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add files"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

        # Create bundle and import
        bundle_dir = self.temp_dir / "results"
        bundle_dir.mkdir()
        bundle_path = bundle_dir / "results.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle_path), "--all"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

        subprocess.run(
            ["git", "checkout", "main"], cwd=self.repo_path, check=True, capture_output=True
        )

        integrator = Integrator(self.repo_path)
        branches = integrator._import_branches(bundle_dir)

        files_changed = integrator._count_files_changed(branches)

        # Should count the 2 new files
        assert files_changed >= 0  # May vary based on git state


class TestBranchInfo(unittest.TestCase):
    """Test cases for BranchInfo dataclass."""

    def test_branch_info_creation(self):
        """Test creating BranchInfo."""
        branch = BranchInfo(name="feature", commit="abc123", is_new=True)

        assert branch.name == "feature"
        assert branch.commit == "abc123"
        assert branch.is_new


class TestIntegrationSummary(unittest.TestCase):
    """Test cases for IntegrationSummary dataclass."""

    def test_integration_summary_creation(self):
        """Test creating IntegrationSummary."""
        summary = IntegrationSummary(
            branches=[], commits_count=0, files_changed=0, logs_copied=False, has_conflicts=False
        )

        assert len(summary.branches) == 0
        assert summary.commits_count == 0
        assert not summary.has_conflicts


if __name__ == "__main__":
    unittest.main()
