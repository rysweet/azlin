"""Migration entry point: finds or installs the Rust azlin binary and execs it.

The Python azlin package exists only to bootstrap the Rust binary.
There is NO fallback to Python. If the Rust binary cannot be found or
installed, this exits with an error telling the user how to fix it.

Search order:
  1. ~/.azlin/bin/azlin          (managed install from GitHub Releases)
  2. ~/.cargo/bin/azlin           (cargo install)
  3. /usr/local/bin/azlin         (system package)

If none found, attempts (in order):
  1. Download from GitHub Releases
  2. Build from source via cargo
  3. Exit with error
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


def _is_rust_binary(path: Path) -> bool:
    """Check if a binary is the Rust azlin (has self-update command)."""
    try:
        result = subprocess.run(
            [str(path), "self-update", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "self-update" in result.stdout.lower()
    except (subprocess.TimeoutExpired, OSError):
        return False


def _find_rust_binary() -> str | None:
    """Find an existing Rust azlin binary. Returns path or None."""
    candidates = [
        MANAGED_BIN,
        Path.home() / ".cargo" / "bin" / "azlin",
        Path("/usr/local/bin/azlin"),
        Path("/usr/bin/azlin"),
    ]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK) and _is_rust_binary(candidate):
            return str(candidate)
    return None


def _download_from_release() -> str | None:
    """Download pre-built binary from GitHub Releases."""
    import tarfile
    import tempfile

    suffix = _platform_suffix()
    if not suffix:
        return None

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    try:
        req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            import json

            releases = json.loads(resp.read())
    except Exception:
        return None

    # Find the latest Rust release asset for this platform
    download_url = None
    version = None
    for release in releases:
        tag = release.get("tag_name", "")
        if "-rust" not in tag:
            continue
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if suffix in name and name.endswith(".tar.gz"):
                download_url = asset["browser_download_url"]
                version = tag.replace("v", "").replace("-rust", "")
                break
        if download_url:
            break

    if not download_url:
        return None

    # Download and extract
    MANAGED_BIN_DIR.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"azlin: installing Rust binary v{version} from GitHub Releases...\n")
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            urllib.request.urlretrieve(download_url, tmp.name)  # noqa: S310
            tmp_path = tmp.name

        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/azlin") or member.name == "azlin":
                    member.name = "azlin"
                    tar.extract(member, path=str(MANAGED_BIN_DIR))
                    break

        os.unlink(tmp_path)

        if MANAGED_BIN.exists():
            MANAGED_BIN.chmod(
                MANAGED_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )
            sys.stderr.write(f"azlin: installed to {MANAGED_BIN}\n")
            return str(MANAGED_BIN)
    except Exception as e:
        sys.stderr.write(f"azlin: download failed: {e}\n")
    return None


def _build_from_source() -> str | None:
    """Build from source via cargo install."""
    cargo = shutil.which("cargo")
    if not cargo:
        return None

    sys.stderr.write("azlin: building from source with cargo (this takes ~60s)...\n")
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
                sys.stderr.write(f"azlin: built and installed to {cargo_bin}\n")
                return str(cargo_bin)
    except (subprocess.TimeoutExpired, OSError) as e:
        sys.stderr.write(f"azlin: cargo install failed: {e}\n")
    return None


def _exec_rust(binary: str, args: list[str]) -> None:
    """Replace this process with the Rust binary."""
    if platform.system() == "Windows":
        result = subprocess.run([binary, *args])
        sys.exit(result.returncode)
    else:
        os.execvp(binary, [binary, *args])  # noqa: S606


def entry() -> None:
    """Find or install the Rust binary and exec it. No fallback."""
    args = sys.argv[1:]

    # 1. Try to find existing Rust binary
    rust_bin = _find_rust_binary()

    # 2. Try to download from GitHub Releases
    if not rust_bin:
        rust_bin = _download_from_release()

    # 3. Try to build from source
    if not rust_bin:
        rust_bin = _build_from_source()

    # 4. No options left — fail with clear instructions
    if not rust_bin:
        sys.stderr.write(
            "\n"
            "ERROR: Could not find or install the azlin Rust binary.\n"
            "\n"
            "Install manually with one of:\n"
            "\n"
            "  # Option 1: cargo (requires Rust toolchain)\n"
            "  cargo install --git https://github.com/rysweet/azlin --bin azlin\n"
            "\n"
            "  # Option 2: download pre-built binary\n"
            "  curl -sL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-x86_64.tar.gz | tar xz\n"
            "  sudo mv azlin /usr/local/bin/\n"
            "\n"
        )
        sys.exit(1)

    _exec_rust(rust_bin, args)
