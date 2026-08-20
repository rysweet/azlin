#!/usr/bin/env python3
"""Fail when a reference doc names a Rust symbol that does not exist.

Issue #1103 removed the verbatim `az` argument vectors and error-message text
from `docs/reference/nat-gateway-provisioning.md`, because a second copy of
something the tests already assert has no mechanism keeping it honest — that
file drifted three times inside one pull request.

What replaced the copies is a set of pointers: "the argv is asserted by
`test_build_attach_natgw_args_verbatim`". Pointers rot too, and a dangling one
is worse than a stale copy: it reads as a citation and leads nowhere. This is
the mechanism.

Only backticked identifiers that look like Rust items are checked, and only
when they carry an underscore — English words in backticks (`--yes`, `region`,
`Absent`) are not symbols and are skipped. A symbol counts as existing if it
appears anywhere under `rust/crates/`, which is deliberately loose: the goal is
to catch a rename or a deletion, not to police visibility.

Usage: ./scripts/check_doc_code_references.py [doc ...]
Exit codes: 0 = every reference resolves, 1 = at least one dangles.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_SRC = REPO_ROOT / "rust" / "crates"

DEFAULT_DOCS = ["docs/reference/nat-gateway-provisioning.md"]

# A Rust item name: lowercase, underscore-separated, at least two segments.
# `--no-bastion`, `Key=Value` and `Absent` are all correctly excluded.
SYMBOL = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

# Words that match the shape but are prose, config keys or file names rather
# than Rust items. Kept explicit so the list is reviewable.
NOT_SYMBOLS = {
    "azlin_session",
    "ip_tagged",
    "public_ip",
    "nat_gateway",
    "natgateway_id",
    "cargo_test",
}


def backticked(text: str) -> list[str]:
    """Every single-backtick span in the document, in order of appearance."""
    without_fences = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.findall(r"`([^`\n]+)`", without_fences)


def candidate_symbols(doc: Path) -> list[str]:
    seen: dict[str, None] = {}
    for span in backticked(doc.read_text()):
        token = span.strip()
        # `foo()` and `foo(a, b)` both name `foo`.
        token = token.split("(")[0].strip()
        if SYMBOL.match(token) and token not in NOT_SYMBOLS:
            seen.setdefault(token, None)
    return list(seen)


def exists_in_rust(symbol: str) -> bool:
    result = subprocess.run(
        ["grep", "-rqF", symbol, str(RUST_SRC), "--include=*.rs"],
        capture_output=True,
    )
    return result.returncode == 0


def main(argv: list[str]) -> int:
    docs = argv[1:] or DEFAULT_DOCS
    failures = 0
    for rel in docs:
        doc = REPO_ROOT / rel
        if not doc.is_file():
            print(f"error: no such document: {rel}", file=sys.stderr)
            return 1
        symbols = candidate_symbols(doc)
        if not symbols:
            print(f"error: {rel} names no Rust symbols at all — the extraction "
                  f"in this script has drifted from the document", file=sys.stderr)
            return 1
        missing = [s for s in symbols if not exists_in_rust(s)]
        for s in missing:
            print(
                f"error: {rel} refers to `{s}`, which does not exist under "
                f"rust/crates/. Either it was renamed or removed — update the "
                f"document, or add it to NOT_SYMBOLS if it is not a Rust item.",
                file=sys.stderr,
            )
        failures += len(missing)
        print(f"{rel}: {len(symbols) - len(missing)}/{len(symbols)} references resolve")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
