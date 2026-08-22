# Filter Disclosure in `azlin list`

`azlin list` hides VMs that are not running. It now says so.

Every invocation that drops rows — because of the default running-only filter,
`--tag`, or `--vm-pattern` — reports how many rows it dropped and how to get
them back.

## The problem this solves

`azlin list` defaults to showing running VMs only. That default is correct: a
day-to-day listing should show the machines you can connect to right now.

The defect was that the filter was *silent*. A resource group with six VMs —
two running, three deallocated, one stopped — printed:

```
Total: 2 VMs | 2 running
```

Nothing in that output indicated four more VMs existed. Deallocated VMs keep
their attached managed disks, and those disks bill at full rate whether or not
the VM ever runs again. An operator reading the default listing had no way to
learn, from the listing itself, that they were paying for machines the tool had
decided not to mention. The counts were not wrong; they were incomplete in a way
the reader could not detect.

The fix is disclosure, not a changed default. Running-only is still the default.

## What changes, and when

This is the invariant to build and test against. It is **not** "nothing changes
when nothing was hidden" — that is true of only one of the three formats.

| Surface | When rows *were* dropped | When nothing was dropped |
| ------- | ------------------------ | ------------------------ |
| **Table body** | Unchanged | Unchanged |
| **Table `Total:` footer** | Clauses appended after ` \| ` | Unchanged |
| **Table remedy line** | Added below the footer | Absent |
| **Table hints block** | Reworded, one new entry | **Reworded, one new entry** |
| **JSON stdout** | `{"filters": …, "vms": […]}` | **`{"filters": …, "vms": […]}`** |
| **JSON stderr** | The disclosure lines | Silent |
| **CSV stdout** | Byte-identical to before | Byte-identical to before |
| **CSV stderr** | The disclosure lines | Silent |

Two consequences that are easy to get backwards:

- **The JSON shape changes unconditionally.** `filters` is always present with
  all three keys even when every count is zero. Do not write a test asserting
  that `azlin list --all -o json` still emits a bare array — it does not.
- **The table is not byte-identical either**, because the hints block gained an
  `--all` entry and reworded `-a`. The hints block renders whenever
  `cfg.show_all_vms` is false, and `show_all_vms` is the `-a` cross-resource-group
  flag — *not* `--all`. So a plain `azlin list` and an `azlin list --all` both
  render the new hints.

**CSV stdout is the only surface that still matches the previous release
byte for byte.** That is the one anything already parsing `azlin list` depends
on. Note the "stdout" — the guarantee does not survive `2>&1`. `azlin list -o
csv > out.csv 2>&1` merges the disclosure into the file and yields two records
that are not VMs. That shape is not hypothetical: `rust/scripts/capture_golden.sh`
used it and had to be changed. Redirect stdout alone, or send stderr to
`/dev/null`.

## What the table shows

The counts extend the `Total:` summary footer, and a remedy line follows it,
before the hints block:

```
└─────────────┴────────────────────────┴────────────────┴─────────┴───────────────────┴────────────────┴─────┴────────┘

Total: 2 VMs | 2 running | 4 hidden (stopped/deallocated)
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.

Hints:
  azlin list --all  Include stopped/deallocated VMs
  azlin list -a     Scan all resource groups (not the same as --all)
  azlin list -w     Wide mode (show VM Name, SKU columns)
  azlin list -r     Restore all tmux sessions in new terminal window
  azlin list -q     Show quota usage (slower)
  azlin list -v     Verbose mode (show tunnel/SSH details)
```

The summary line keeps the `bold()` it has always had; the remedy line is dim.
As with every other coloured line in `azlin list`, the ANSI codes are emitted
unconditionally and wrap each line whole, so the message text stays contiguous
and `grep hidden` matches captured output without stripping escapes first.

### The count clauses

The counts extend the existing ` | `-separated summary rather than starting a
new line. That footer is the line an operator actually reads, and it is the line
that lied: `Total: 2 VMs | 2 running` was true and useless.

One clause per filter stage that removed something, in the order the stages ran,
and only when that counter is nonzero:

| Counter              | Clause                             |
| -------------------- | ---------------------------------- |
| `dropped_by_tag`     | `{n} excluded by --tag`            |
| `dropped_by_pattern` | `{n} excluded by --vm-pattern`     |
| `hidden_not_running` | `{n} hidden (stopped/deallocated)` |

`hidden` for `hidden_not_running` and `excluded` for the other two is
deliberate. The running filter removes rows nobody asked it to remove — that is
the incident. `--tag` and `--vm-pattern` remove rows you typed a flag to remove,
which is a different thing and should not read as an alarm.

When every counter is zero the suffix is empty and the footer is byte-identical
to what it printed before.

### The remedy line

```
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

This exact string is a test assertion target. It is ASCII-only — no em-dash, no
backticks, straight single quotes around the command — so it survives a
non-UTF-8 terminal and a naive `grep -F`.

It appears **only when `hidden_not_running` is greater than zero**. A run where
`--tag` dropped rows but the running filter did not has nothing to reveal with
`--all`, so it gets the count clauses and no remedy — pointing at `--all` there
would be wrong advice.

### The disclosure never names a VM

The disclosure is counts. It never prints a hidden VM's name, tag value, IP, or
the pattern you supplied.

That is a deliberate boundary, not an oversight. `--tag` and `--vm-pattern` are
how you *narrow* a listing before pasting it into an issue or a chat channel.
Echoing the excluded names back into the footer would undo the narrowing and
silently change the sensitivity class of output that operators routinely share.
To see the names, run the listing that includes them.

## Examples

### Stopped VMs are hidden

```bash
azlin list
```

```
Total: 2 VMs | 2 running | 4 hidden (stopped/deallocated)
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

### A pattern matched nothing

```bash
azlin list --vm-pattern "staging-"
```

```
Total: 0 VMs | 0 running | 6 excluded by --vm-pattern
```

The table still renders with headers and an empty body. Previously an empty
table was indistinguishable from an empty resource group; now the footer says
which filter emptied it — here the pattern matched none of the six VMs, so it
took all of them.

Note what is *absent*: no `hidden` clause and no `--all` remedy. Nothing was
hidden from this listing by the running-only default, because the pattern had
already removed everything before that stage ran. Advising `--all` here would be
wrong — it would drop your pattern and show you a different question's answer.

### Several filters at once

```bash
azlin list --tag env=dev --vm-pattern "dev"
```

```
Total: 1 VMs | 1 running | 1 excluded by --tag | 2 excluded by --vm-pattern | 2 hidden (stopped/deallocated)
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

Clauses appear in the order the stages ran. Against the six-VM pool: `--tag`
took `ia2` (the only `env=prod` machine), `--vm-pattern` took the two survivors
whose names do not contain `dev`, and the running-only default then took
`deva2` and `deva3` from the three that were left.

The `2 hidden` is the number that matters, and it is the number `--all` would
add back to *this* listing — not the four non-running VMs in the resource group,
two of which this query excluded anyway. That is the whole reason the running
filter runs last.

A filter that removed nothing contributes no clause:

```bash
azlin list --tag env=prod --vm-pattern "web-"
```

```
Total: 0 VMs | 0 running | 5 excluded by --tag | 1 excluded by --vm-pattern
```

Here `--tag` took five of the six and `--vm-pattern` took the one that was left,
so the running-only default had nothing to consider — no `hidden` clause, and no
remedy line, because `--all` would not bring back a single row either filter
removed.

### Nothing was hidden

```bash
azlin list --all
```

```
Total: 6 VMs | 2 running
```

No count clauses, no remedy line, nothing on stderr — the footer is exactly
what it was before. A tool that prints a scary line when nothing is wrong
teaches people to skip the footer.

Note the scope of that silence: it covers the **disclosure lines** only. The
hints block below still renders with its new `--all` entry, and `-o json` still
emits the `filters` envelope with three zeroes. See
[What changes, and when](#what-changes-and-when).

## Revealing the hidden VMs

```bash
azlin list --all              # include stopped and deallocated VMs
azlin list --include-stopped  # alias for --all
```

**`-a` is a different flag.** `-a` / `--show-all-vms` scans *all resource
groups*; it does not include stopped VMs. Passing `-a` when you meant `--all`
gives you a wider, still running-only listing — the same blind spot in a new
place. The hints block spells both out, and `-a`'s description now reads
`Scan all resource groups (not the same as --all)` for exactly this reason.

| Flag | Effect |
| ---- | ------ |
| `--all`, `--include-stopped` | Include stopped/deallocated VMs in the current resource group |
| `-a`, `--show-all-vms` | Scan every resource group (running-only unless combined with `--all`) |
| `--all -a` | Every VM in every resource group |

## Machine-readable output

### JSON

> **Breaking change.** `azlin -o json list` used to print a bare array of VM
> objects. It now prints an object with the array under `vms`. Update
> `jq '.[]'` to `jq '.vms[]'`.

```bash
azlin -o json list
```

```json
{
  "filters": {
    "dropped_by_pattern": 0,
    "dropped_by_tag": 0,
    "hidden_not_running": 4
  },
  "vms": [
    {
      "cpu": "4",
      "ip": "10.0.0.4 (Bast)",
      "location": "westus2",
      "mem": "16 GB",
      "name": "azt1",
      "os": "Ubuntu 24.04",
      "os_offer": "ubuntu-24_04-lts",
      "power_state": "Running",
      "private_ip": "10.0.0.4",
      "public_ip": null,
      "resource_group": "rysweet-linux-vm-pool",
      "session": "-",
      "tmux_sessions": ["main"],
      "vm_size": "Standard_D4s_v3"
    }
  ]
}
```

Per-VM objects are unchanged — same keys, same types, same values. Only the
top-level shape moved.

Keys serialise in **alphabetical order**. That is not a style choice: the
workspace depends on `serde_json` without the `preserve_order` feature, so
objects are backed by a `BTreeMap` and sort their keys. Any test that pins the
exact JSON text must expect alphabetical order.

`filters` is **always present with all three keys**, including when every count
is zero:

```json
{
  "filters": {
    "dropped_by_pattern": 0,
    "dropped_by_tag": 0,
    "hidden_not_running": 0
  },
  "vms": []
}
```

This is a deliberate divergence from the "print nothing when nothing was hidden"
rule, which governs the human-readable disclosure lines only. A key that appears
only sometimes forces every consumer to distinguish `null` from `0`, and that
distinction is a defect generator. Machines get a stable schema; humans get
silence.

No human-readable prose is ever written into the JSON payload. The disclosure
still reaches a human running `-o json` at a terminal, via **stderr**:

```bash
azlin -o json list > vms.json
```

```
Note: 4 hidden (stopped/deallocated).
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

stdout stays a clean payload for `jq`; stderr carries the sentence. Nothing is
written to stderr when all counters are zero — the envelope on stdout is the
machine-readable answer either way.

That guarantee required fixing three older call sites that wrote to stdout
without checking the output format:

- the `── context: … ──` banner on `--all-contexts`;
- the `vCPU Quota:` heading and `az vm list-usage` table on `--quota`;
- the `Restoring tmux sessions...`, `Opening tab:` and `Session restore
  initiated.` narration on `--restore`.

Before this change `azlin -o json list --quota` emitted a valid JSON document
followed by an ASCII table, which `jq` rejects. All three now follow the same
rule and go to stderr whenever the format is not `Table`.

**Only the narration moved, never the behaviour.** `azlin -o json list --restore`
still opens a terminal tab per session — the restore is the side effect you asked
for, and suppressing it because you also asked for JSON would be a different bug.
What changed is that its progress lines no longer land in the middle of your
payload.

### CSV

CSV stdout is untouched: same header row, same data rows, no trailer, no comment
line. Anything that parses `azlin -o csv list` today keeps parsing it.

When at least one counter is nonzero, the disclosure goes to **stderr** — the
same lines the JSON run emits there:

```bash
azlin -o csv list > vms.csv
```

```
Note: 4 hidden (stopped/deallocated).
Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.
```

Nothing is written to stderr when all counters are zero.

CSV has no metadata channel. A comment line breaks Python's `csv` module, a
summary row corrupts the body, and an extra column disappears exactly when the
result set is empty — the case that matters most. stderr is the established
out-of-band channel for `azlin list`; the tmux tunnel warnings already use it
for the same reason.

Unlike JSON, CSV has no in-band place to put the numbers, so **stderr is the
only channel a CSV consumer has**. If you want them as data rather than prose,
run the same query with `-o json` and read `.filters` — that is the schema
contract. Scraping the English sentence will break on the next wording change.

One asymmetry is intentional: the JSON `filters` block is a *schema contract*,
so it is unconditional even when every count is zero; the stderr lines are a
*diagnostic event*, so they fire only when there is something to report.

## What the counters mean

```rust
pub struct FilterCounts {
    pub hidden_not_running: usize,
    pub dropped_by_tag: usize,
    pub dropped_by_pattern: usize,
}
```

Filters run in a fixed order: **tag → pattern → running** (`list_helpers.rs`,
`apply_filters`). Each counter records how many VMs *that stage* removed, from
whatever survived the previous stages. They are stage-local deltas, not
independent "would have been dropped" figures.

Every stage is an independent `Vec::retain`, so the order does not change *which*
VMs survive — only which stage is credited with removing them. The running filter
runs **last** on purpose. That scopes `hidden_not_running` to the query you
actually typed: `azlin list --vm-pattern dev` tells you how many *dev* machines
are hidden, not how many machines are hidden in the resource group. Since
`hidden_not_running` is what triggers the `--all` advice, group-wide counting
made that advice wrong in the common case — in a 100-VM group with 90 stopped,
`--vm-pattern dev` would have reported "90 hidden" and pointed at a command that
discards your pattern.

Consider three VMs: `web-1` (Running, `env=prod`), `web-2` (Deallocated,
`env=prod`), `db-1` (Deallocated, `env=dev`). Running `azlin list --tag env=dev`
reports:

- `dropped_by_tag: 2` — `web-1` and `web-2` are `env=prod`, removed first
- `dropped_by_pattern: 0` — no pattern was given
- `hidden_not_running: 1` — only `db-1` reached the running stage, and it is
  Deallocated

`web-2` is counted once, under `dropped_by_tag`, even though the running filter
would also have removed it. The counters sum to the number of rows removed, and
never double-count.

The `hidden_not_running: 1` is the useful number here: it says one of *your*
`env=dev` machines is hidden and billing, which is exactly what `--all` would
add back to this listing.

A stage that does not run reports `0`. `--all` therefore always reports
`hidden_not_running: 0`, because the running filter did not execute.

### `hidden_not_running` is not `total − running`

It is tempting to derive the hidden count from the summary line and delete the
counter. That is wrong in both directions:

- `filter_running` keeps `Running` **and** `Starting`. The
  `Total: N VMs | M running` footer counts `Running` only. A VM mid-boot makes
  `M < N` with nothing hidden.
- With `--all`, no filtering happened at all, so `total − running` counts VMs
  that are present in the output.

The counters come from the filter itself, which is the only place that knows
what it removed.

## Deliberately out of scope

The cost signal here is one clause: *hidden VMs still bill for attached
storage*. It is accurate for both hidden states — a deallocated VM bills for
disks, a stopped-but-allocated VM bills for compute as well — and it costs one
string.

A stronger signal is not part of this feature: no per-VM deallocation age, no
attached-disk capacity or price estimate, no cost column, no `--stale` threshold.
Those need disk SKU lookups and pricing data, which is a separate design with its
own Azure API surface and its own failure modes. It is tracked in
[#1144](https://github.com/rysweet/azlin/issues/1144) rather than bolted onto a
display fix.

One known inconsistency is also left alone: under `--all-contexts`, the
per-context headers (`── context: X … — N VMs ──`) count VMs *before* filtering,
so they can disagree with the post-filter footer. Reconciling them requires
filtering per-context, which changes aggregation order. It is tracked in the same
issue, [#1144](https://github.com/rysweet/azlin/issues/1144).

`azlin cleanup` is unaffected. Disks attached to a deallocated VM have a
populated `managedBy` field, so they are not orphans and cleanup is right to
leave them. The problem was never that cleanup missed them — it was that you
could not see the VMs holding them.

## Scripting recipes

Alert when anything is hidden:

```bash
hidden=$(azlin -o json list | jq '.filters.hidden_not_running')
if [ "$hidden" -gt 0 ]; then
  echo "warning: $hidden VM(s) are stopped or deallocated and still billing for disks"
  azlin -o json list --all \
    | jq -r '.vms[] | select(.power_state != "Running") | "\(.name)\t\(.power_state)\t\(.vm_size)"'
fi
```

Fail a CI check when a pattern matches nothing, instead of silently succeeding on
an empty list:

```bash
azlin -o json list --vm-pattern "$PREFIX" \
  | jq -e '(.vms | length) > 0' > /dev/null \
  || { echo "no VM matched $PREFIX"; exit 1; }
```

Check only that the result set is non-empty. Do **not** also assert
`.filters.dropped_by_pattern == 0` — a legitimate narrowing run reports a nonzero
`dropped_by_pattern` precisely because the pattern did its job. A pattern that
keeps 2 of 5 VMs reports `dropped_by_pattern: 3`, and the check would fail a
build that matched exactly what it was asked to match.

Keep the CSV body and the disclosure in separate files:

```bash
azlin -o csv list > vms.csv 2> filters.txt
```

### Migrating from the bare JSON array

| Before | After |
| ------ | ----- |
| `jq '.[]'` | `jq '.vms[]'` |
| `jq -r '.[].name'` | `jq -r '.vms[].name'` |
| `jq 'length'` | `jq '.vms \| length'` |
| `jq '[.[] \| select(.power_state=="Running")]'` | `jq '[.vms[] \| select(.power_state=="Running")]'` |

How each unmigrated form fails — these differ, and the quiet one is the
dangerous one:

- **`jq 'length'` returns `2`** and exits `0`. That is the envelope's key count,
  not a VM count. It is a plausible-looking wrong number that no exit status will
  catch, and it is the single most important reason to audit scripts rather than
  wait for them to break.
- **`jq -r '.[].name'` writes `Cannot index array with string "name"` to
  stderr, prints `null` to stdout, and exits `5`.** In a pipeline without
  `set -o pipefail` the nonzero status is discarded and the caller sees the
  string `null` as if it were a VM name.
- **`jq '.[]'` succeeds** and iterates the envelope's two *values* — first the
  `filters` object, then the whole `vms` array as a single item. Downstream
  field access then misbehaves rather than erroring cleanly.

## Related documentation

- [Listing VMs](listing.md) — the task-level guide to `azlin list`
- [`azlin list` command reference](../commands/vm/list.md) — every flag
- [Start/Stop](start-stop.md) — how to deallocate the VMs this disclosure surfaces
