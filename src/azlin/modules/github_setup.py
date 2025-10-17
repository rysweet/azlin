"""
GitHub Setup Handler Module

Handle GitHub authentication and repository cloning on remote VM.

Security Requirements:
- No credential storage
- URL validation (HTTPS only)
- Safe subprocess execution
- gh CLI delegation for auth
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from .ssh_connector import SSHConfig, SSHConnector

logger = logging.getLogger(__name__)


@dataclass
class GitHubConfig:
    """GitHub setup configuration."""

    repo_url: str
    clone_path: Optional[str] = None  # Remote path, default: ~/repo-name


@dataclass
class RepoDetails:
    """Repository clone details."""

    clone_path: str
    repo_name: str
    repo_owner: str


class GitHubSetupError(Exception):
    """Raised when GitHub setup fails."""

    pass


class GitHubSetupHandler:
    """
    Handle GitHub authentication and repo cloning on VM.

    Security:
    - Validates GitHub URLs (HTTPS only)
    - Uses gh CLI for authentication
    - No credential handling
    """

    @classmethod
    def setup_github_on_vm(
        cls, ssh_config: SSHConfig, repo_url: str, clone_path: Optional[str] = None
    ) -> RepoDetails:
        """
        Run GitHub authentication and clone repository on VM.

        Args:
            ssh_config: SSH configuration for VM
            repo_url: GitHub repository URL (HTTPS)
            clone_path: Optional custom clone path on VM

        Returns:
            RepoDetails: Information about cloned repository

        Raises:
            GitHubSetupError: If setup fails

        Security:
        - Validates repo URL before any operations
        - Uses gh CLI for authentication
        - Executes commands via SSH

        Example:
            >>> ssh_config = SSHConfig(...)
            >>> details = GitHubSetupHandler.setup_github_on_vm(
            ...     ssh_config,
            ...     "https://github.com/owner/repo"
            ... )
            >>> print(details.clone_path)
            /home/azureuser/repo
        """
        # Validate URL
        valid, message = cls.validate_repo_url(repo_url)
        if not valid:
            raise GitHubSetupError(f"Invalid repository URL: {message}")

        # Parse repo details
        owner, repo_name = cls._parse_repo_url(repo_url)

        # Determine clone path
        if clone_path is None:
            clone_path = f"/home/{ssh_config.user}/{repo_name}"

        logger.info(f"Setting up GitHub on VM for {owner}/{repo_name}")

        # Generate setup script
        script = cls.generate_setup_script(repo_url, clone_path)

        # Execute setup script on VM
        try:
            logger.info("Running GitHub authentication on VM...")
            output = SSHConnector.execute_remote_command(
                ssh_config,
                script,
                timeout=300,  # 5 minutes for gh auth (may require user interaction)
            )

            logger.debug(f"GitHub setup output: {output}")

            logger.info(f"Repository cloned to {clone_path}")

            return RepoDetails(clone_path=clone_path, repo_name=repo_name, repo_owner=owner)

        except Exception as e:
            raise GitHubSetupError(f"GitHub setup failed: {e}")

    @classmethod
    def generate_setup_script(cls, repo_url: str, clone_path: str) -> str:
        """
        Generate bash script for GitHub setup on VM.

        Args:
            repo_url: GitHub repository URL
            clone_path: Path where to clone repository

        Returns:
            str: Bash script content

        Security:
        - Uses quoted variables
        - Validates inputs before generation
        - No credential exposure

        Example:
            >>> script = GitHubSetupHandler.generate_setup_script(
            ...     "https://github.com/owner/repo",
            ...     "/home/user/repo"
            ... )
        """
        import shlex

        # Quote parameters safely
        safe_url = shlex.quote(repo_url)
        safe_path = shlex.quote(clone_path)

        # Generate script
        script_lines = [
            "set -e",  # Exit on error
            "",
            "# GitHub CLI authentication",
            "if ! gh auth status >/dev/null 2>&1; then",
            "  echo 'Starting GitHub authentication...'",
            "  gh auth login --web --git-protocol https",
            "fi",
            "",
            "# Clone repository",
            f"if [ ! -d {safe_path} ]; then",
            "  echo 'Cloning repository...'",
            f"  git clone {safe_url} {safe_path}",
            "else",
            f"  echo 'Repository already cloned at {safe_path}'",
            "fi",
            "",
            "# Navigate to repository",
            f"cd {safe_path}",
            "",
            "# Configure git",
            "git config pull.rebase false",
            "",
            "echo 'GitHub setup complete'",
        ]

        return "\n".join(script_lines)

    @classmethod
    def validate_repo_url(cls, repo_url: str) -> tuple[bool, str]:
        """
        Validate GitHub repository URL.

        Args:
            repo_url: URL to validate

        Returns:
            tuple: (is_valid, message)

        Security:
        - HTTPS only (no HTTP, git://, etc.)
        - GitHub.com only
        - Valid path format
        - No command injection characters

        Example:
            >>> valid, msg = GitHubSetupHandler.validate_repo_url(
            ...     "https://github.com/owner/repo"
            ... )
            >>> if not valid:
            ...     print(msg)
        """
        if not repo_url:
            return False, "URL cannot be empty"

        if len(repo_url) > 2048:
            return False, "URL too long"

        # Check for dangerous characters
        dangerous_chars = ["&", "|", ";", "`", "$", "\n", "\r"]
        for char in dangerous_chars:
            if char in repo_url:
                return False, f"URL contains invalid character: {char}"

        # Parse URL
        try:
            parsed = urlparse(repo_url)
        except Exception:
            return False, "Invalid URL format"

        # Must be HTTPS
        if parsed.scheme != "https":
            return False, f"Only HTTPS URLs are supported (got: {parsed.scheme}://)"

        # Must be GitHub
        hostname = parsed.netloc.lower()
        if hostname not in ["github.com", "www.github.com"]:
            return False, f"Only GitHub.com URLs are supported (got: {hostname})"

        # Parse path: /owner/repo or /owner/repo.git
        path = parsed.path.strip("/")
        if not path:
            return False, "Invalid URL: missing repository path"

        parts = path.split("/")
        if len(parts) < 2:
            return False, "Invalid URL: expected format https://github.com/owner/repo"

        owner, repo = parts[0], parts[1]

        # Remove .git suffix if present
        repo = repo.removesuffix(".git")

        # Validate owner name (GitHub allows alphanumeric, hyphen)
        if not re.match(r"^[a-zA-Z0-9_-]+$", owner):
            return False, f"Invalid owner name: {owner}"

        if len(owner) > 39:  # GitHub username max length
            return False, f"Owner name too long: {owner}"

        # Validate repo name
        if not re.match(r"^[a-zA-Z0-9._-]+$", repo):
            return False, f"Invalid repository name: {repo}"

        if len(repo) > 100:  # GitHub repo name max length
            return False, f"Repository name too long: {repo}"

        return True, "Valid"

    @classmethod
    def _parse_repo_url(cls, repo_url: str) -> tuple[str, str]:
        """
        Parse owner and repository name from URL.

        Args:
            repo_url: GitHub repository URL

        Returns:
            tuple: (owner, repo_name)

        Raises:
            ValueError: If URL cannot be parsed

        Example:
            >>> owner, repo = GitHubSetupHandler._parse_repo_url(
            ...     "https://github.com/microsoft/vscode"
            ... )
            >>> print(owner, repo)
            microsoft vscode
        """
        parsed = urlparse(repo_url)
        path = parsed.path.strip("/")

        parts = path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Cannot parse repository URL: {repo_url}")

        owner = parts[0]
        repo = parts[1].removesuffix(".git")

        return owner, repo


# Convenience functions for CLI use
def setup_github(
    ssh_config: SSHConfig, repo_url: str, clone_path: Optional[str] = None
) -> RepoDetails:
    """
    Setup GitHub on VM (convenience function).

    Args:
        ssh_config: SSH configuration
        repo_url: GitHub repository URL
        clone_path: Optional clone path

    Returns:
        RepoDetails: Clone details

    Example:
        >>> from azlin.modules.github_setup import setup_github
        >>> details = setup_github(ssh_config, "https://github.com/owner/repo")
    """
    return GitHubSetupHandler.setup_github_on_vm(ssh_config, repo_url, clone_path)


def validate_github_url(repo_url: str) -> bool:
    """
    Validate GitHub URL (convenience function).

    Args:
        repo_url: URL to validate

    Returns:
        bool: True if valid

    Example:
        >>> from azlin.modules.github_setup import validate_github_url
        >>> if validate_github_url("https://github.com/owner/repo"):
        ...     print("Valid")
    """
    valid, _ = GitHubSetupHandler.validate_repo_url(repo_url)
    return valid
