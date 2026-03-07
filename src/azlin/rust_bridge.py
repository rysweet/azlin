"""Bridge module: detects and delegates to the Rust azlin binary.

When installed via uvx/pip, the Python 'azlin' command lands here first.
If a Rust binary is available (or can be downloaded), we exec it directly.
Otherwise we fall back to the Python CLI.

The Rust binary location priority:
  1. ~/.azlin/bin/azlin          (managed install)
  2. azlin on PATH               (cargo install / system package)
"""

import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

GITHUB_REPO = "rysweet/azlin"
RUST_VERSION_PREFIX = "azlin "  # `azlin --version` outputs "azlin 2.3.0"
MANAGED_BIN_DIR = Path.home() / ".azlin" / "bin"
MANAGED_BIN = MANAGED_BIN_DIR / "azlin"


def _platform_suffix() -> str | None:
    """Map current platform to GitHub Release asset suffix."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return "linux-x86_64"
        if machine in ("aarch64", "arm64"):
            return "linux-aarch64"
    elif system == "darwin":
        if machine in ("x86_64", "amd64"):
            return "macos-x86_64"
        if machine in ("aarch64", "arm64"):
            return "macos-aarch64"
    elif system == "windows":
        return "windows-x86_64"
    return None


def _find_rust_binary() -> str | None:
    """Find an existing Rust azlin binary. Returns path or None."""
    # 1. Managed install location
    if MANAGED_BIN.exists() and os.access(MANAGED_BIN, os.X_OK):
        return str(MANAGED_BIN)
    # 2. Check well-known locations for Rust binary (outside venvs)
    candidates = [
        Path.home() / ".cargo" / "bin" / "azlin",
        Path("/usr/local/bin/azlin"),
        Path("/usr/bin/azlin"),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            try:
                result = subprocess.run(
                    [str(candidate), "self-update", "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Rust binary has self-update; Python does not
                if result.returncode == 0 and "self-update" in result.stdout.lower():
                    return str(candidate)
            except (subprocess.TimeoutExpired, OSError):
                continue
    return None


def _get_latest_release_url() -> tuple[str, str] | None:
    """Query GitHub API for the latest Rust release asset URL.

    Returns (download_url, version) or None.
    """
    suffix = _platform_suffix()
    if not suffix:
        return None
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json

            releases = json.loads(resp.read())
        for release in releases:
            tag = release.get("tag_name", "")
            if "-rust" not in tag:
                continue
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if suffix in name and name.endswith(".tar.gz"):
                    version = tag.replace("v", "").replace("-rust", "")
                    return asset["browser_download_url"], version
    except Exception:
        pass
    return None


def _download_and_install(url: str) -> str | None:
    """Download a tar.gz release asset and install the binary to ~/.azlin/bin/."""
    import tarfile
    import tempfile

    MANAGED_BIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        sys.stderr.write(f"Downloading Rust azlin from {url}...\n")
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            urllib.request.urlretrieve(url, tmp.name)
            tmp_path = tmp.name

        with tarfile.open(tmp_path, "r:gz") as tar:
            # Find the azlin binary in the archive
            for member in tar.getmembers():
                if member.name.endswith("/azlin") or member.name == "azlin":
                    member.name = "azlin"
                    tar.extract(member, path=str(MANAGED_BIN_DIR))
                    break

        os.unlink(tmp_path)

        if MANAGED_BIN.exists():
            MANAGED_BIN.chmod(MANAGED_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            sys.stderr.write(f"Installed Rust azlin to {MANAGED_BIN}\n")
            return str(MANAGED_BIN)
    except Exception as e:
        sys.stderr.write(f"Failed to download Rust binary: {e}\n")
    return None


def _try_cargo_install() -> str | None:
    """Try to build and install via cargo if Rust toolchain is available."""
    cargo = shutil.which("cargo")
    if not cargo:
        return None
    sys.stderr.write(
        "azlin: No pre-built binary found. Building from source with cargo...\n"
    )
    try:
        result = subprocess.run(
            [
                cargo,
                "install",
                "--git",
                f"https://github.com/{GITHUB_REPO}",
                "--bin",
                "azlin",
                "--force",
            ],
            timeout=600,
        )
        if result.returncode == 0:
            cargo_bin = Path.home() / ".cargo" / "bin" / "azlin"
            if cargo_bin.exists():
                sys.stderr.write(f"Built and installed azlin to {cargo_bin}\n")
                return str(cargo_bin)
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"cargo install failed: {e}\n")
    return None


def _exec_rust(binary: str, args: list[str]) -> None:
    """Replace this process with the Rust binary (Unix exec)."""
    if platform.system() == "Windows":
        # Windows doesn't have exec; use subprocess
        result = subprocess.run([binary] + args)
        sys.exit(result.returncode)
    else:
        os.execvp(binary, [binary] + args)


def entry() -> None:
    """Main entry point: prefer Rust binary, fall back to Python CLI."""
    args = sys.argv[1:]

    # Escape hatch: --python-fallback forces Python CLI
    if "--python-fallback" in args:
        args.remove("--python-fallback")
        sys.argv = [sys.argv[0]] + args
        from azlin.cli import main

        main()
        return

    # Try to find existing Rust binary
    rust_bin = _find_rust_binary()

    if not rust_bin:
        # No Rust binary found — try to download
        release_info = _get_latest_release_url()
        if release_info:
            url, version = release_info
            sys.stderr.write(
                f"azlin: Rust binary v{version} available. "
                f"Migrating from Python to Rust (75-85x faster)...\n"
            )
            rust_bin = _download_and_install(url)

    if not rust_bin:
        # Try cargo install as last resort (if cargo is available)
        rust_bin = _try_cargo_install()

    if rust_bin:
        _exec_rust(rust_bin, args)
        # exec doesn't return on Unix; on Windows we already called sys.exit
    else:
        # No Rust binary available — run Python CLI as fallback
        from azlin.cli import main

        main()
