# Doc-Code Reference Check

How azlin keeps prose from citing code that does not exist: what the check
covers, how a symbol is recognised, the two exemption lists and the rules that
keep them from becoming hiding places, and what to do when it fails.

The check is implemented by `scripts/check_doc_code_references.py` and runs in
CI from `.github/workflows/doc-validation.yml`.

For the narrative on why documentation drift is treated as a defect rather than
an untidiness, see
[Documentation Sync](../contributing/documentation-sync.md).

## What this file is, and is not

This file states the **contract**: what is in scope, what counts as a citation,
and what each failure means. It does not reproduce the script's internals —
those live in the script, are asserted by `scripts/test_check_doc_code_references.py`,
and a second copy here would drift exactly the way this check exists to prevent.

Run the tests to read the current behaviour:

```bash
python scripts/test_check_doc_code_references.py
```

## The problem it solves

A changelog entry shipped describing a routing function named "proc\_route" —
a name no symbol in this repository has ever had, under any language. It passed
every gate, because the check ran on exactly one document and `CHANGELOG.md`
was not it.

The function it meant is `probe_route`, which returns `ProbeRoute::Bastion`,
`ProbeRoute::Direct` or `ProbeRoute::Unreachable`. A reader who went looking for
the name the changelog gave them found nothing and had no way to tell whether
the feature or the name was wrong.

> The name in the paragraph above is deliberately written with an escaped
> underscore rather than in backticks. Backticking it would make this document
> fail the very check it documents — which is the check working.

## What counts as a citation

A citation is a **single-backtick span** whose content matches the shape of a
Rust item name: lowercase, underscore-separated, at least two segments.

| Written in a doc | Treated as a citation? | Why |
|---|---|---|
| `` `sanitize_remote_text` `` | Yes | Matches the shape |
| `` `csv_field` `` | Yes | Matches the shape |
| `` `resolve_enrichment()` `` | Yes — as `resolve_enrichment` | A trailing call is stripped |
| `` `--show-procs` `` | No | Leading dash |
| `` `ProbeRoute` `` | No | Not lowercase |
| `` `az network bastion list` `` | No | Contains spaces |
| Anything inside a triple-backtick fence | No | Those fences are removed before extraction. Four-space indented blocks are **not** removed |

A citation resolves when its text appears **anywhere** under `rust/crates/` in a
`.rs` file. That is deliberately loose. The goal is to catch a rename or a
deletion, not to police visibility or to verify that the citation is about the
right thing — a check that tried to do the latter would be a type system, and
this is a grep.

**Consequence worth knowing:** a symbol that exists but is documented
*incorrectly* still passes. This check bounds one failure mode — dangling names
— and makes no claim about the rest.

**And it does not bound even that one completely.** The match is a fixed
*substring*, not a whole-word one, so a citation that is a prefix of some other
surviving symbol resolves against it. A document citing `discover_bastions`
passes on `discover_bastions_async` long after `discover_bastions` itself is
gone. Renaming by *extending* a name — appending a suffix such as "_async" is
the common shape — is therefore the rename this check is least able to see.
Tightening the match to
a word boundary would catch it, at the cost of failing citations that name a
method through its type or a macro-generated item.

## Scope

Every document that describes Rust internals is checked. The scope is a list of
globs, expanded at run time so a new feature doc is covered the day it lands
rather than the day somebody remembers to register it:

```
CHANGELOG.md
docs/CONTEXT_MANAGEMENT.md
docs/reference/*.md
docs/features/*.md
docs-site/bastion/*.md
docs-site/commands/vm/*.md
```

**Adding a file to `docs/reference/` or `docs/features/` puts it in scope
immediately.** No registration step exists, and that is the point.

### The changelog is checked from the top only

For `CHANGELOG.md`, only the text above the *second* `## ` heading is
examined — in practice, the `## [Unreleased]` section.

Released sections are history. An entry describing a release from two years ago
names the code that shipped in it, and rewriting that entry so a linter goes
green would make the record a lie in exchange for a green tick. The unreleased
section is the part still being written, and it is the part that shipped the
bad name.

## The two exemption lists

Both lists require a written reason for every entry, enforced at import time:
the script raises rather than running if any reason is blank. An append-only
allowlist with no reason field is how a gate stops being a gate — the cheapest
way to make a check green is to add a line, and without a reason nothing
distinguishes "this is an Azure JSON field" from "this used to exist and
somebody silenced the alarm".

### `NOT_SYMBOLS` — token level

Tokens that match the Rust-item shape but are not Rust items: Azure API field
names, resource-tag keys, and prose. `azlin_session` is a resource-tag key;
`public_ip` and `nat_gateway` are Azure API field names.

Add an entry here when a token is *permanently* not a Rust symbol.

### `STALE_DOCS` — document level

Whole documents whose dangling citations cannot be fixed by correcting a name.
Most entries cite code deleted in the Python-to-Rust migration: the functions
are gone, so there is nothing to update the reference *to*, and the document
needs a rewrite against the Rust implementation. Not all of them — one entry
backticks hook keys from a planned config schema, names that were never Rust
items in any language.

Add an entry here only for a document that is wrong throughout, and say in its
reason which case it is.

### The ratchet turns one way

`STALE_DOCS` is checked **in both directions**. If a listed document starts
resolving cleanly, the run fails and tells you to delete its entry.

Without that, the list only ever grows: a doc gets fixed, nobody removes its
line, and the next dangling citation that document grows is exempt for a reason
that stopped being true. The list cannot outlive the problem it describes.

## The vacuous-pass guard

The run fails if **no checked document named a Rust symbol**. Symbols in
`STALE_DOCS` documents do not count towards it: a default run skips those
documents, so their citations cannot satisfy the guard on their own.

This is evaluated per run, not per document. Many pages in scope name no Rust
items at all, and that is normal — a how-to about `--show-all-vms` should not
have to cite an internal function to satisfy a linter. But a run that finds a
citation nowhere means the extraction has drifted from the documents, and the
check is passing because it stopped looking rather than because everything
resolves.

## Running it

```bash
# Every document in scope. This is what CI runs.
python scripts/check_doc_code_references.py

# One or more specific documents.
python scripts/check_doc_code_references.py docs/features/tmux-session-status.md
```

| Exit code | Meaning |
|---|---|
| `0` | Every citation in every checked document resolves |
| `1` | At least one citation dangles, an exemption is stale, a named document is missing, or no checked document named a symbol |

Passing paths explicitly changes two behaviours, so that you can inspect a
document the default run skips:

- `STALE_DOCS` entries are **checked**, not skipped.
- The `STALE_DOCS` ratchet is **not** evaluated.

The vacuous-pass guard still applies, and it is scoped to the documents you
named. Running the checker on a single in-scope document that cites no Rust
symbol therefore exits 1 with the "no document named a Rust symbol" error —
there, it means only that none of the named documents cited one, which is not a
defect in that document.

Output on a passing run is one line per document that was skipped or that cited
at least one symbol: its path, then either the resolved-over-total ratio or
`skipped` followed by that document's exemption reason verbatim. A document
that was checked and cited nothing prints no line at all, so silence means
"checked, cited nothing" rather than "not in scope".

The ratios are deliberately not reproduced here — they move whenever any checked
document is edited, and a hand-copied number going stale is the failure this
gate exists to catch. Run the checker for current counts.

## When it fails

### A citation does not resolve

```
error: docs/features/tmux-session-status.md refers to `proc_route`, which does
not exist under rust/crates/. Either it was renamed or removed — update the
document, or add it to NOT_SYMBOLS if it is not a Rust item.
```

The name is wrong, or the code was renamed or deleted. In order of preference:

1. **Fix the citation.** Find the real name and use it. Most failures are this.
2. **Unbacktick it.** If it is prose rather than a symbol, it should not be in
   backticks. Straight quotes are not citations.
3. **Move it into a fenced block.** Illustrative snippets belong in fences —
   but it must be a triple-backtick fence. A four-space indented block is not
   stripped, so a citation inside one is still extracted and still has to
   resolve.
4. **Add it to `NOT_SYMBOLS` with a reason.** Only if it is permanently not a
   Rust symbol.

Do not add a document to `STALE_DOCS` to clear a single dangling citation. That
list is for documents needing a full rewrite, and using it as a mute button is
what its reason field exists to make visible.

### An exemption is no longer needed

```
error: docs-site/bastion/setup.md is listed in STALE_DOCS but every reference in
it now resolves. Delete its entry — an exemption that is no longer needed
exempts the next mistake instead.
```

Delete the entry. The document was rewritten; the exemption is now cover for
whatever it grows next.

### Nothing was found anywhere

```
error: no document named a Rust symbol — the extraction in this script has
drifted from the documents it checks
```

On a default run, the extraction is broken or scope has collapsed. Do not
silence this by adding a citation somewhere — check that the globs still match
real files and that the symbol pattern still matches real names.

When paths were passed explicitly it means only that none of those documents
cited a symbol; re-run without arguments before treating it as a defect.

## CI wiring

`.github/workflows/doc-validation.yml` runs the checker's own tests first, then
the checker. It triggers on changes to the documents in scope — including
`CHANGELOG.md` and `docs-site/**/*.md` — and to the checker itself.

Running the tests before the check is not ceremony. The check is a grep with a
regex and two allowlists; if the extraction silently stops matching, the check
passes on everything. The tests pin that the scope is more than one document,
that `CHANGELOG.md` is in it, and that `docs-site/` is in it.

## Related

- [Documentation Sync](../contributing/documentation-sync.md) — the wider
  documentation-consistency gate
- [NAT Gateway Provisioning](./nat-gateway-provisioning.md) — the reference doc
  this check was originally written for
- [Tmux Session Status](../features/tmux-session-status.md) — a feature doc in
  scope, and a worked example of citing Rust internals accurately
