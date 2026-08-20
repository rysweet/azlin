#!/usr/bin/env python3
"""Fail on a run of spaces inside a Rust string literal, mid-sentence.

Why this exists
---------------
A multi-line Rust string literal ends its lines with `\\`, which strips the
newline *and* the following indentation:

    "Would run '{}' across fleet in '{}' on {} \\
     (timeout {}s)"

Drop the backslash — or generate the source with a tool whose own line
continuation eats the newline but keeps the indentation — and the literal
silently carries the indentation instead:

    "Would run '{}' across fleet in '{}' on {}                          (timeout {}s)"

`cargo fmt` does not touch the inside of string literals, `clippy` has no
opinion, and the code compiles. The only signal is the output, which nobody
reads character by character. This has happened twice in the #1089 series:
once in `azlin fleet run --dry-run` and once in the `--auth-profile` override
notice. The first was caught by reading the output; the second by a test that
happened to assert on the exact wording.

What counts as a hit
--------------------
A run of six or more spaces, between two sentence characters, in the part of
a literal **before its first `\n`**.

Both exclusions are load-bearing, and the first version of this check without
them produced sixteen hits, every one of them wrong:

* **Before the first `\n`.** Indented content after a newline is the normal
  way to embed an SSH config block, a cloud-init document or an aligned help
  listing, and this codebase does all three. A lost line continuation, by
  contrast, splices indentation into a running sentence with no newline in
  front of it.
* **Six, not three.** Deliberate mid-sentence spacing is one or two; a test
  fixture like `"az   vm   list"` is three. A lost continuation carries the
  source's indentation, which inside a function body is eight or more.

Alignment padding is excluded by the character classes: it follows a
separator (`:`, `|`, a flag name), never a letter mid-sentence.

What this does not catch
------------------------
A lost continuation whose indentation is under six spaces — a `const` at top
level, say. The threshold is what keeps the false-positive rate at zero on this
tree, and a gate people turn off catches nothing at all; but the blind spot is
real and is stated here rather than left to be found.

It also reads no Rust grammar. Lines that are entirely a `//` comment are
skipped so a comment quoting garbled output does not trip it, but a string
literal inside a trailing comment on a code line is still fair game.

Usage: ./scripts/check_string_continuations.py [path ...]
Exit codes: 0 = clean, 1 = at least one garbled literal.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATHS = ["rust/crates"]

# A double-quoted Rust string literal on one line, escapes included.
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"')

# Six or more spaces with sentence text on both sides.
#
# `}` on the left and `(` on the right matter: the fleet dry-run banner broke
# as `on {}` + spaces + `(timeout`, so a class covering only letters would have
# missed the very case this exists for. Alignment padding is still excluded
# because it follows a separator — `:`, `|`, a flag name — and none of those
# are in the left class.
GARBLED = re.compile(r"""[A-Za-z0-9,\)\}\.\?!;']      +[A-Za-z0-9\(\{]""")


def hits(line: str) -> list[str]:
    # A line that is entirely a comment may legitimately quote garbled output —
    # this file's own tests do. Anything else, including a trailing comment on a
    # code line, is still scanned.
    if line.lstrip().startswith("//"):
        return []
    found = []
    for literal in STRING.findall(line):
        # Only the part before the first embedded newline: indentation *after*
        # a `\n` is how an SSH config block or a cloud-init document is written,
        # and there is nothing wrong with it.
        head = literal.split("\\n", 1)[0]
        if GARBLED.search(head):
            found.append(literal)
    return found


def main(argv: list[str]) -> int:
    paths = argv[1:] or DEFAULT_PATHS
    failures = 0
    scanned = 0
    for rel in paths:
        root = REPO_ROOT / rel
        files = sorted(root.rglob("*.rs")) if root.is_dir() else [root]
        for path in files:
            if "target" in path.parts:
                continue
            scanned += 1
            for number, line in enumerate(
                path.read_text(errors="replace").splitlines(), start=1
            ):
                for literal in hits(line):
                    rel_path = path.relative_to(REPO_ROOT)
                    print(
                        f"error: {rel_path}:{number}: a run of spaces inside a string "
                        f"literal, mid-sentence. This is almost always a lost `\\` line "
                        f"continuation — the indentation ended up in the string.\n"
                        f"    {literal.strip()}",
                        file=sys.stderr,
                    )
                    failures += 1
    if scanned == 0:
        print("error: scanned no files; the paths given do not exist", file=sys.stderr)
        return 1
    print(f"checked {scanned} file(s) for garbled string literals")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
