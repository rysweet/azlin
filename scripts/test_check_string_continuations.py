#!/usr/bin/env python3
"""Tests for scripts/check_string_continuations.py.

The check is a heuristic, so what matters is both directions: it has to catch
the two real cases that occurred in the #1089 series, and it has to stay quiet
on the patterns this codebase legitimately contains. A checker with false
positives gets deleted; a checker with false negatives is decoration.

Usage: ./scripts/test_check_string_continuations.py
Exit codes: 0 = all pass, 1 = a failure.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_string_continuations.py"

spec = importlib.util.spec_from_file_location("checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

PASS = 0
FAIL = 0


def expect(name: str, line: str, should_hit: bool) -> None:
    global PASS, FAIL
    got = bool(checker.hits(line))
    if got == should_hit:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        verb = "missed" if should_hit else "flagged"
        print(f"  ❌ {name} — {verb}: {line.strip()[:100]}")


print("=== check_string_continuations.py ===\n")

print("1. The two that actually happened")
# azlin fleet run --dry-run, before the fix.
expect(
    "the fleet dry-run banner",
    r'''        "Would run '{}' across fleet in '{}' on {}                          (timeout {}s)",''',
    True,
)
# The --auth-profile override notice, before the fix.
expect(
    "the auth-profile notice",
    r'''        "Note: this switches the Azure CLI to subscription {id} and leaves it          there."''',
    True,
)
print()

print("2. What the same code looks like once it is right")
expect(
    "a correct continuation leaves one space",
    r'''        "Would run '{}' across fleet in '{}' on {} (timeout {}s)",''',
    False,
)
expect(
    "the continuation line itself",
    r'''         (timeout {}s, {} parallel worker(s))",''',
    False,
)
print()

print("3. Patterns this codebase legitimately contains")
expect(
    "an SSH config block after a newline",
    r'''    "\n# Added by azlin\nHost {}\n    HostName 127.0.0.1\n    Port {}\n"''',
    False,
)
expect(
    "an aligned help listing after a newline",
    r'''    "\n  azlin list -a        Show all VMs across all resource groups"''',
    False,
)
expect(
    "column padding after a label",
    r'''    out.push_str(&format!("Name:               {}\n", vm.name));''',
    False,
)
expect(
    "a test fixture with deliberate extra spaces",
    r'''    let argv = "az   vm   list";''',
    False,
)
expect(
    "a cloud-init document",
    r'''    "runcmd:\n  - |\n    echo one\n    echo two\n"''',
    False,
)
expect("a format spec, not literal spaces", r'''    format!("{:>20}", name)''', False)
print()

print("4. A comment quoting garbled output is not a hit")
# This file's own docstrings and comments quote the broken literals; a checker
# that flagged them would fail on itself.
expect(
    "a full-line comment",
    '    // it printed "on {}                          (timeout)" before the fix',
    False,
)
print()

print("5. The real tree")
rc = checker.main([str(CHECKER)])
if rc == 0:
    PASS += 1
    print("  ✅ rust/crates is clean")
else:
    FAIL += 1
    print("  ❌ rust/crates has garbled literals")
print()

print(f"=== {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
