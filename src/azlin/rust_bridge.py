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

import copy
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

GITHUB_REPO = "rysweet/azlin"
MANAGED_BIN_DIR = Path.home() / ".azlin" / "bin"
MANAGED_BIN = MANAGED_BIN_DIR / "azlin"

# Computed once at import time; used to select tar extraction strategy
_PY312_PLUS = sys.version_info >= (3, 12)


class SecurityError(Exception):
    """Raised when a security violation is detected during binary installation."""


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
    """Check if a binary is the Rust azlin (has update command)."""
    try:
        result = subprocess.run(
            [str(path), "update", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "update" in result.stdout.lower()
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
        if (
            candidate.exists()
            and os.access(candidate, os.X_OK)
            and _is_rust_binary(candidate)
        ):
            return str(candidate)
    return None


def _is_release_binary_member(name: str) -> bool:
    """Return True if the tar member name corresponds to the azlin binary.

    Pure predicate — no I/O.
    """
    return name == "azlin" or name.endswith("/azlin")


def _validate_release_member(member: tarfile.TarInfo) -> None:
    """Raise SecurityError if a tar member is unsafe to extract.

    Checks performed:
    - Absolute path (e.g. /etc/cron.d/evil)
    - Parent-directory traversal (e.g. ../../usr/bin/evil)
    - Non-regular-file on Python < 3.12 (symlinks, device files, hard links)

    On Python >= 3.12 filter='data' handles non-regular-file filtering at
    extraction time, so only path checks are required here.
    """
    path = PurePosixPath(member.name)

    if path.is_absolute():
        raise SecurityError(f"Absolute path in archive: {member.name!r}")

    if ".." in path.parts:
        raise SecurityError(f"Path traversal in archive: {member.name!r}")

    if not _PY312_PLUS:
        # filter='data' is unavailable before 3.12 — check member type manually
        if not member.isfile():
            raise SecurityError(
                f"Non-regular-file in archive: {member.name!r} (type={member.type})"
            )


def _extract_release_binary(tmp_path: Path, destination: Path) -> None:
    """Extract only the azlin binary from a release tarball.

    Validates every member before extraction and normalises the output
    filename to 'azlin' regardless of the member's name in the archive.

    Raises:
        SecurityError: If any tar member fails validation or the binary is
            absent from the archive.
    """
    with tarfile.open(tmp_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not _is_release_binary_member(member.name):
                continue

            _validate_release_member(member)

            # Normalise name: always write to destination/azlin regardless of
            # the member's original name inside the archive (defence-in-depth).
            safe_member = copy.copy(member)
            safe_member.name = "azlin"

            if _PY312_PLUS:
                tar.extract(safe_member, path=str(destination), filter="data")
            else:
                tar.extract(safe_member, path=str(destination))

            return  # Successfully extracted exactly one binary — done

    raise SecurityError("azlin binary not found in archive")


def _download_from_release() -> str | None:
    """Download pre-built binary from GitHub Releases."""
    suffix = _platform_suffix()
    if not suffix:
        return None

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    try:
        req = urllib.request.Request(
            api_url, headers={"Accept": "application/vnd.github+json"}
        )  # noqa: S310
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            releases = json.loads(resp.read())
    except (urllib.error.URLError, OSError):
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
    sys.stderr.write(
        f"azlin: installing Rust binary v{version} from GitHub Releases...\n"
    )
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        urllib.request.urlretrieve(download_url, str(tmp_path))  # noqa: S310  # nosec B310

        # SecurityError propagates uncaught — installation is aborted loudly
        _extract_release_binary(tmp_path, MANAGED_BIN_DIR)

        if MANAGED_BIN.exists():
            MANAGED_BIN.chmod(
                MANAGED_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )
            sys.stderr.write(f"azlin: installed to {MANAGED_BIN}\n")
            return str(MANAGED_BIN)
    except (urllib.error.URLError, OSError) as e:
        sys.stderr.write(f"azlin: download failed: {e}\n")
    finally:
        # Always clean up the temp file — even if SecurityError is raised
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

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
