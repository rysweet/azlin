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

What it catches, precisely: a citation to a symbol that no longer exists,
whether renamed or deleted. What it does NOT catch: a citation to a symbol that
exists but is the wrong one — swap two test names past each other and every
reference still resolves while every one of them lies. Proving that a named
test asserts a named thing means parsing the test, which is a different and
much larger tool. "Renamed or deleted" is the common failure; "swapped" is not.

Only backticked identifiers that look like Rust items are checked, and only
when they carry an underscore — English words in backticks (`--yes`, `region`,
`Absent`) are not symbols and are skipped. A symbol counts as existing if it
appears anywhere under `rust/crates/`, which is deliberately loose: the goal is
to catch a rename or a deletion, not to police visibility.

Scope. The check originally ran on one document, which is why #1128 shipped a
CHANGELOG entry citing a `proc_route` function that has never existed under any
name — the file naming the symbol was not one of the files being checked. The
scope is now every document that describes Rust internals: `CHANGELOG.md`, the
reference and feature docs, and the bastion and `azlin vm` pages of the docs
site. `STALE_DOCS` below carries the handful that predate the Python-to-Rust
migration and cite code that no longer exists in any language; that list is a
ratchet, not an escape hatch — the checker fails if an entry on it starts
passing, so a doc that gets fixed cannot quietly stay exempt.

Usage: ./scripts/check_doc_code_references.py [doc ...]
Exit codes: 0 = every reference resolves, 1 = at least one dangles.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_SRC = REPO_ROOT / "rust" / "crates"

# Every document that describes Rust internals. Globs, expanded at run time so a
# new feature doc is covered the day it lands rather than the day somebody
# remembers to add it here.
CHECKED_GLOBS = [
    "CHANGELOG.md",
    "docs/CONTEXT_MANAGEMENT.md",
    "docs/reference/*.md",
    "docs/features/*.md",
    "docs-site/bastion/*.md",
    "docs-site/commands/vm/*.md",
]

# Documents inside CHECKED_GLOBS that cite code deleted in the Python-to-Rust
# migration. Their citations do not resolve because the functions are gone, not
# because they were renamed, so there is nothing to update the reference to —
# each needs a rewrite against the Rust implementation. The reason is mandatory
# and the exemption is checked in both directions: `check_stale_docs_still_fail`
# fails the run if a listed document starts resolving cleanly, so this list
# cannot outlive the problem it describes.
STALE_DOCS = {
    "docs/reference/azure-cli-detection.md": (
        "cites `get_linux_cli_path` and `safe_run` from the deleted Python CLI "
        "detection module; needs a rewrite against rust/crates/azlin-azure"
    ),
    "docs/reference/cli-python-parity.md": (
        "a Python-vs-Rust parity table that names Python-side enum variants "
        "(`linux_gnome`, `linux_xterm`); it documents the migration itself"
    ),
    "docs/features/incremental-cache-refresh.md": (
        "cites Python test names (`test_refresh_expired_vms` and siblings) for "
        "a feature since reimplemented in Rust"
    ),
    "docs/features/vm-lifecycle-automation.md": (
        "cites `on_start`/`on_stop`/`on_restart`/`on_destroy`/`on_healthy` as "
        "Rust items; they are hook keys in a planned config schema"
    ),
    "docs-site/bastion/setup.md": (
        "cites `detect_bastion_for_vm`, `list_bastions` and their Python "
        "acceptance tests; needs a rewrite against the Rust bastion path"
    ),
}

_unexplained_docs = [d for d, reason in STALE_DOCS.items() if not reason.strip()]
if _unexplained_docs:
    raise SystemExit(
        f"error: STALE_DOCS entries {_unexplained_docs} have no reason. Every "
        "exemption needs one, or this list becomes the place a stale document "
        "goes to hide."
    )

# A Rust item name: lowercase, underscore-separated, at least two segments.
# `--no-bastion`, `Key=Value` and `Absent` are all correctly excluded.
SYMBOL = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")

# Tokens that match the Rust-item shape but are not Rust items: Azure field
# names, resource-tag keys, prose.
#
# The reason is mandatory and is enforced below. An append-only allowlist is
# how a gate stops being a gate: the cheapest way to make this script green is
# to add a line, and without a reason nothing distinguishes "this is an Azure
# JSON field" from "this used to exist and somebody silenced the alarm". The
# flag-wiring ledger in `rust/crates/xtask/unwired-flags-allowlist.txt` made
# the same rule for the same reason.
NOT_SYMBOLS = {
    "azlin_session": "an Azure resource-tag key, not a Rust item",
    "ip_tagged": "part of the NAT public IP name suffix",
    "public_ip": "an Azure API field name",
    "nat_gateway": "an Azure API field name and an `az` flag",
    "natgateway_id": "an Azure API field name",
    "cargo_test": "prose about the `cargo test` command",
}

_unexplained = [t for t, reason in NOT_SYMBOLS.items() if not reason.strip()]
if _unexplained:
    raise SystemExit(
        f"error: NOT_SYMBOLS entries {_unexplained} have no reason. Every "
        "exemption needs one, or this list becomes the place a dangling "
        "citation goes to hide."
    )


def backticked(text: str) -> list[str]:
    """Every single-backtick span in the document, in order of appearance."""
    without_fences = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.findall(r"`([^`\n]+)`", without_fences)


def in_scope_text(doc: Path) -> str:
    """The part of `doc` whose citations are expected to describe current code.

    A changelog is append-only history: an entry describing a release from two
    years ago names the code that shipped in it, and rewriting that to match
    today's symbols would make the history a lie to satisfy a linter. Only the
    unreleased section — the part still being written, and the part that shipped
    `proc_route` — is checked.
    """
    text = doc.read_text()
    if doc.name != "CHANGELOG.md":
        return text
    headings = [m.start() for m in re.finditer(r"^## ", text, flags=re.M)]
    return text[: headings[1]] if len(headings) > 1 else text


def candidate_symbols(doc: Path) -> list[str]:
    seen: dict[str, None] = {}
    for span in backticked(in_scope_text(doc)):
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


def default_docs() -> list[str]:
    """Every document in scope, deduplicated and in a stable order."""
    seen: dict[str, None] = {}
    for pattern in CHECKED_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if path.is_file():
                seen.setdefault(str(path.relative_to(REPO_ROOT)), None)
    return list(seen)


def dangling_in(rel: str) -> tuple[int, list[str]]:
    """(symbols examined, symbols that resolve nowhere) for one document."""
    symbols = candidate_symbols(REPO_ROOT / rel)
    return len(symbols), [s for s in symbols if not exists_in_rust(s)]


def check_stale_docs_still_fail(docs: list[str]) -> int:
    """Fail when an exempted document no longer needs its exemption.

    Without this the ratchet only turns one way: a doc gets fixed, nobody
    removes its entry, and the next citation it grows is exempt for a reason
    that stopped being true.
    """
    failures = 0
    for rel in sorted(STALE_DOCS):
        if rel not in docs:
            continue
        _, missing = dangling_in(rel)
        if not missing:
            print(
                f"error: {rel} is listed in STALE_DOCS but every reference in "
                f"it now resolves. Delete its entry — an exemption that is no "
                f"longer needed exempts the next mistake instead.",
                file=sys.stderr,
            )
            failures += 1
    return failures


def main(argv: list[str]) -> int:
    explicit = argv[1:]
    docs = explicit or default_docs()
    failures = 0
    examined = 0
    for rel in docs:
        doc = REPO_ROOT / rel
        if not doc.is_file():
            print(f"error: no such document: {rel}", file=sys.stderr)
            return 1
        count, missing = dangling_in(rel)
        examined += count
        if rel in STALE_DOCS and not explicit:
            print(f"{rel}: skipped — {STALE_DOCS[rel]}")
            continue
        for s in missing:
            print(
                f"error: {rel} refers to `{s}`, which does not exist under "
                f"rust/crates/. Either it was renamed or removed — update the "
                f"document, or add it to NOT_SYMBOLS if it is not a Rust item.",
                file=sys.stderr,
            )
        failures += len(missing)
        if count:
            print(f"{rel}: {count - len(missing)}/{count} references resolve")

    # Per-run, not per-document: most pages in scope name no Rust items at all,
    # and that is normal. A run that finds none anywhere is not — it means the
    # extraction above has drifted and this script is passing vacuously.
    if examined == 0:
        print(
            "error: no document named a Rust symbol — the extraction in this "
            "script has drifted from the documents it checks",
            file=sys.stderr,
        )
        return 1

    if not explicit:
        failures += check_stale_docs_still_fail(docs)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
