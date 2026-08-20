#!/usr/bin/env python3
"""Tests for scripts/check_doc_code_references.py.

The checker exists to stop a reference doc from citing a Rust symbol that no
longer exists. A checker that cannot fail would be worse than no checker, so
these drive it against fixture documents rather than only against the real one.

Usage: ./scripts/test_check_doc_code_references.py
Exit codes: 0 = all pass, 1 = a failure.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_doc_code_references.py"

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")
        if detail:
            print(f"      {detail}")


def run_on(body: str) -> subprocess.CompletedProcess:
    """Write `body` as a doc under the repo and run the checker on it."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", dir=REPO_ROOT / "docs", delete=False
    ) as fh:
        fh.write(body)
        path = Path(fh.name)
    try:
        return subprocess.run(
            [sys.executable, str(CHECKER), str(path.relative_to(REPO_ROOT))],
            capture_output=True,
            text=True,
        )
    finally:
        path.unlink()


print("=== check_doc_code_references.py ===\n")

print("1. A dangling reference fails")
r = run_on("See `parse_subnet_nat_status` and `this_symbol_does_not_exist_anywhere`.\n")
check("exit code is non-zero", r.returncode != 0, r.stdout + r.stderr)
check(
    "the missing symbol is named",
    "this_symbol_does_not_exist_anywhere" in r.stderr,
    r.stderr,
)
check(
    "the existing symbol is not reported",
    "parse_subnet_nat_status`, which does not exist" not in r.stderr,
    r.stderr,
)
print()

print("2. Real references pass")
r = run_on("`parse_subnet_nat_status` and `plan_nat_provisioning` are real.\n")
check("exit code is zero", r.returncode == 0, r.stdout + r.stderr)
print()

print("3. Prose in backticks is not treated as a symbol")
# A checker that flagged these would be turned off within a week. The real
# symbol is there so the "names nothing" guard does not fire instead and mask
# what this case is actually testing.
r = run_on(
    "Pass `--no-bastion`, set `Key=Value`, expect `Absent` or `Ok`, "
    "and see `parse_subnet_nat_status`.\n"
)
check("exit code is zero", r.returncode == 0, r.stdout + r.stderr)
check(
    "none of the prose tokens is reported as missing",
    "does not exist" not in r.stderr,
    r.stderr,
)
print()

print("4. Fenced code blocks are not scanned")
# Signatures inside ```rust blocks name types and parameters that are not
# items to look up; the doc's prose citations are what matter.
r = run_on(
    "Prose cites `parse_subnet_nat_status`.\n\n"
    "```rust\nfn no_such_function_at_all(x: u32) -> u32 { x }\n```\n"
)
check("exit code is zero", r.returncode == 0, r.stdout + r.stderr)
print()

print("5. A document naming no symbols is an error, not a pass")
# Silently passing would mean the extraction had drifted and nobody noticed.
r = run_on("This document cites nothing at all.\n")
check("exit code is non-zero", r.returncode != 0, r.stdout + r.stderr)
check("the reason is stated", "names no Rust symbols" in r.stderr, r.stderr)
print()

print("6. Every exemption carries a reason")
# An append-only allowlist with no reason field is where a dangling citation
# goes to hide.
r = subprocess.run(
    [sys.executable, "-c",
     "import importlib.util, sys;"
     "spec = importlib.util.spec_from_file_location('c', sys.argv[1]);"
     "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
     "print(all(v.strip() for v in m.NOT_SYMBOLS.values()))",
     str(CHECKER)],
    capture_output=True,
    text=True,
)
check("NOT_SYMBOLS has no blank reasons", r.stdout.strip() == "True", r.stdout + r.stderr)
print()

print("7. The real document")
r = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
check(
    "every reference in nat-gateway-provisioning.md resolves",
    r.returncode == 0,
    r.stdout + r.stderr,
)
print()

print(f"=== {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
