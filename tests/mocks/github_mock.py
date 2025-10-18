"""
Mock GitHub CLI and API for testing.

This module provides mocks for GitHub CLI (gh) and GitHub API
interactions without making actual network requests.
"""

from typing import Any
from unittest.mock import Mock


class MockGitHubCLI:
    """Mock GitHub CLI (gh) for testing."""

    def __init__(self, authenticated: bool = True, username: str = "testuser"):
        self.authenticated = authenticated
        self.username = username
        self.auth_calls: list[str] = []
        self.repo_calls: list[str] = []

    def auth_status(self) -> Mock:
        """Mock 'gh auth status' command."""
        self.auth_calls.append("auth status")

        if self.authenticated:
            return Mock(
                returncode=0,
                stdout=f"✓ Logged in to github.com as {self.username}\n✓ Git operations for github.com configured",
                stderr="",
            )

        return Mock(
            returncode=1,
            stdout="",
            stderr="You are not logged into any GitHub hosts. Run gh auth login to authenticate.",
        )

    def auth_login(self, protocol: str = "https") -> Mock:
        """Mock 'gh auth login' command."""
        self.auth_calls.append(f"auth login --web --git-protocol {protocol}")

        if not self.authenticated:
            self.authenticated = True

        return Mock(returncode=0, stdout=f"✓ Logged in as {self.username}", stderr="")

    def repo_clone(self, repo_url: str, directory: str | None = None) -> Mock:
        """Mock 'gh repo clone' command."""
        clone_cmd = f"repo clone {repo_url}"
        if directory:
            clone_cmd += f" {directory}"
        self.repo_calls.append(clone_cmd)

        if not self.authenticated:
            return Mock(returncode=1, stdout="", stderr="authentication required")

        return Mock(
            returncode=0, stdout=f"Cloning into '{repo_url.split('/')[-1]}'...\nDone.", stderr=""
        )

    def repo_view(self, repo: str | None = None) -> Mock:
        """Mock 'gh repo view' command."""
        view_cmd = f"repo view {repo}" if repo else "repo view"
        self.repo_calls.append(view_cmd)

        if not self.authenticated:
            return Mock(returncode=1, stderr="authentication required")

        return Mock(
            returncode=0, stdout="name: test-repo\nowner: testuser\nprivate: false", stderr=""
        )

    def handle_command(self, cmd: list[str], **kwargs) -> Mock:
        """Handle arbitrary gh CLI commands."""
        cmd_str = " ".join(cmd)

        if "auth status" in cmd_str:
            return self.auth_status()
        if "auth login" in cmd_str:
            protocol = "https"
            if "--git-protocol" in cmd:
                idx = cmd.index("--git-protocol")
                if idx + 1 < len(cmd):
                    protocol = cmd[idx + 1]
            return self.auth_login(protocol)
        if "repo clone" in cmd_str:
            repo_url = None
            directory = None
            for _i, arg in enumerate(cmd):
                if (
                    not arg.startswith("-")
                    and "gh" not in arg
                    and "repo" not in arg
                    and "clone" not in arg
                ):
                    if repo_url is None:
                        repo_url = arg
                    else:
                        directory = arg
            return self.repo_clone(repo_url or "", directory)
        if "repo view" in cmd_str:
            repo = None
            for arg in cmd:
                if (
                    not arg.startswith("-")
                    and "gh" not in arg
                    and "repo" not in arg
                    and "view" not in arg
                ):
                    repo = arg
                    break
            return self.repo_view(repo)

        return Mock(returncode=0, stdout="", stderr="")


class MockGitHubAPI:
    """Mock GitHub REST API for testing."""

    def __init__(self):
        self.repos: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}

    def create_repo(
        self, owner: str, name: str, private: bool = False, description: str = ""
    ) -> dict[str, Any]:
        """Create a mock repository."""
        repo_id = f"{owner}/{name}"
        self.repos[repo_id] = {
            "id": len(self.repos) + 1,
            "owner": {"login": owner},
            "name": name,
            "full_name": repo_id,
            "private": private,
            "description": description,
            "html_url": f"https://github.com/{repo_id}",
            "clone_url": f"https://github.com/{repo_id}.git",
            "ssh_url": f"git@github.com:{repo_id}.git",
            "default_branch": "main",
        }
        return self.repos[repo_id]

    def get_repo(self, owner: str, name: str) -> dict[str, Any] | None:
        """Get a repository by owner and name."""
        repo_id = f"{owner}/{name}"
        return self.repos.get(repo_id)

    def repo_exists(self, owner: str, name: str) -> bool:
        """Check if repository exists."""
        return f"{owner}/{name}" in self.repos

    def create_user(self, login: str, name: str = "") -> dict[str, Any]:
        """Create a mock user."""
        self.users[login] = {
            "id": len(self.users) + 1,
            "login": login,
            "name": name or login,
            "html_url": f"https://github.com/{login}",
        }
        return self.users[login]

    def get_user(self, login: str) -> dict[str, Any] | None:
        """Get a user by login."""
        return self.users.get(login)


class GitHubMockFactory:
    """Factory for creating various GitHub mock scenarios."""

    @staticmethod
    def create_authenticated_scenario() -> tuple[MockGitHubCLI, MockGitHubAPI]:
        """Create scenario where user is authenticated with repos available."""
        cli = MockGitHubCLI(authenticated=True, username="testuser")
        api = MockGitHubAPI()

        # Create some test repos
        api.create_user("testuser", "Test User")
        api.create_repo("testuser", "dotfiles", private=False, description="My dotfiles")
        api.create_repo("testuser", "private-repo", private=True, description="Private project")

        return cli, api

    @staticmethod
    def create_unauthenticated_scenario() -> tuple[MockGitHubCLI, MockGitHubAPI]:
        """Create scenario where user is not authenticated."""
        cli = MockGitHubCLI(authenticated=False)
        api = MockGitHubAPI()
        return cli, api

    @staticmethod
    def create_repo_not_found_scenario() -> tuple[MockGitHubCLI, MockGitHubAPI]:
        """Create scenario where repository doesn't exist."""
        cli = MockGitHubCLI(authenticated=True, username="testuser")
        api = MockGitHubAPI()
        api.create_user("testuser", "Test User")
        # Don't create any repos
        return cli, api


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_mock_gh_subprocess_handler(cli: MockGitHubCLI):
    """Create a subprocess handler for gh CLI commands.

    Args:
        cli: MockGitHubCLI instance to use

    Returns:
        Function that can be used as subprocess.run side_effect
    """

    def handler(cmd: list[str], **kwargs):
        if isinstance(cmd, list) and cmd and "gh" in cmd[0]:
            return cli.handle_command(cmd, **kwargs)
        return Mock(returncode=1, stderr="command not found")

    return handler
