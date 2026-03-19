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
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Literal


class SecurityError(Exception):
    """Raised when a security integrity check fails (e.g. checksum mismatch)."""


GITHUB_REPO = "rysweet/azlin"
MANAGED_BIN_DIR = Path.home() / ".azlin" / "bin"
MANAGED_BIN = MANAGED_BIN_DIR / "azlin"
_PY312_PLUS = sys.version_info >= (3, 12)
_DATA_FILTER: Literal["data"] = "data"


def _is_release_binary_member(name: str) -> bool:
    """Return whether an archive member is the azlin binary payload."""
    return name == "azlin" or name.endswith("/azlin")


def _validate_release_member(member: tarfile.TarInfo) -> None:
    """Validate a release archive member before extraction."""
    member_path = PurePosixPath(member.name)
    if member_path.is_absolute() or "\\" in member.name:
        raise SecurityError(f"Unsafe archive member rejected: {member.name!r}")
    if any(part == ".." for part in member_path.parts):
        raise SecurityError(f"Path traversal member rejected: {member.name!r}")
    if not _PY312_PLUS and not member.isfile():
        raise SecurityError(
            f"Non-regular archive member rejected on Python <3.12: {member.name!r}"
        )


def _extract_release_binary(archive_path: Path, destination: Path) -> None:
    """Extract the azlin binary from a downloaded release archive."""
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not _is_release_binary_member(member.name):
                continue

            _validate_release_member(member)
            extracted_member = copy.copy(member)
            extracted_member.name = "azlin"

            if _PY312_PLUS:
                tar.extract(
                    extracted_member,
                    path=str(destination),
                    filter=_DATA_FILTER,
                )
            else:
                tar.extract(extracted_member, path=str(destination))
            return

    raise SecurityError("Downloaded archive did not contain an azlin binary")


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


def _download_from_release() -> str | None:
    """Download pre-built binary from GitHub Releases.

    Security measures:
    - Member allowlist: only the tar member whose bare name is exactly "azlin" is extracted.
    - Path traversal and non-file members are rejected before extraction.
    - filter='data' (Python >=3.12) blocks symlinks, device nodes, and unsafe metadata.
    """
    suffix = _platform_suffix()
    if not suffix:
        return None

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    try:
        req = urllib.request.Request(
            api_url, headers={"Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            releases = json.loads(resp.read())
    except Exception:
        return None

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

    MANAGED_BIN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    sys.stderr.write(
        f"azlin: installing Rust binary v{version} from GitHub Releases...\n"
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".tar.gz", dir=MANAGED_BIN_DIR, delete=False
        ) as tmp:
            tmp_path = Path(tmp.name)

        urllib.request.urlretrieve(download_url, str(tmp_path))  # nosec B310
        _extract_release_binary(tmp_path, MANAGED_BIN_DIR)

        if MANAGED_BIN.exists():
            MANAGED_BIN.chmod(
                MANAGED_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
            )
            sys.stderr.write(f"azlin: installed to {MANAGED_BIN}\n")
            return str(MANAGED_BIN)
    except SecurityError:
        sys.stderr.write("azlin: download aborted — archive integrity check failed.\n")
    except Exception as e:
        sys.stderr.write(f"azlin: download failed: {e}\n")
    finally:
        if tmp_path is not None:
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
    """Replace this process with the Rust binary.

    On POSIX, uses os.execvp so the Rust process inherits the PID.
    On Windows, subprocess.run is used as execvp is unavailable.
    argv passthrough is intentional: azlin is a CLI passthrough tool
    and there is no untrusted input to sanitise.
    """
    if platform.system() == "Windows":
        result = subprocess.run([binary, *args])
        sys.exit(result.returncode)
    else:
        os.execvp(binary, [binary, *args])  # noqa: S606


def entry() -> None:
    """Find or install the Rust binary and exec it. No fallback."""
    args = sys.argv[1:]

    rust_bin = _find_rust_binary()

    if not rust_bin:
        rust_bin = _download_from_release()

    if not rust_bin:
        rust_bin = _build_from_source()

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
