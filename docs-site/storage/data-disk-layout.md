# Data Disk Layout

How azlin lays out the `/home` and `/tmp` data disks it attaches to a VM, what
the layout looks like from inside the VM, and how provisioning records whether
it succeeded.

Read this when you need to verify a VM by hand, write tooling against the
layout, or understand what [`azlin disk check`](../commands/disk/check.md) is
comparing against.

## The two roles

`azlin new` attaches at most two data disks. Each has a fixed role, and the role
determines its LUN, its filesystem label, and where it ends up:

| Role   | LUN                        | Disk name      | Label        | Backing mount   | Bind target     |
| ------ | -------------------------- | -------------- | ------------ | --------------- | --------------- |
| `home` | 0                          | `<vm>_home`    | `azlin-home` | `/mnt/home-data` | `/home/<user>`  |
| `tmp`  | 1 (0 if there is no home disk) | `<vm>_tmp` | `azlin-tmp`  | `/mnt/tmp-data`  | `/tmp`          |

LUN order is attach order. With `--no-home-disk --tmp-disk-size 64`, the tmp
disk is the only data disk and takes LUN 0.

## The disk is not mounted on `/home` — it is bind-mounted

This is the single most common misreading of the layout, and it is why a naive
`findmnt /home` check reports a correctly provisioned VM as broken.

The data disk is mounted at a **backing** path, and a **bind mount** exposes one
subdirectory of it at the user-facing path:

```
/dev/disk/azure/scsi1/lun0  ──mount──▶  /mnt/home-data
                                        └── azureuser  ──bind──▶  /home/azureuser

/dev/disk/azure/scsi1/lun1  ──mount──▶  /mnt/tmp-data
                                        └── tmp        ──bind──▶  /tmp
```

Nothing is ever mounted directly on `/home` or on `/tmp`. A healthy VM has
**four** mounts for two disks: two ext4 mounts and two binds.

The devices are addressed by their Azure udev symlinks, never by `/dev/sdX`.
`/dev/sdb` is assigned in attach order and can mean a different disk after a
reboot; `/dev/disk/azure/scsi1/lun0` means the same disk every time.

## What a healthy VM looks like

```bash
azlin connect dev
findmnt -rno SOURCE,TARGET,FSTYPE | grep -E '/mnt/(home|tmp)-data|/home/|^/tmp'
```

```
/dev/sdb        /mnt/home-data      ext4
/dev/sdb[/azureuser] /home/azureuser ext4
/dev/sdc        /mnt/tmp-data       ext4
/dev/sdc[/tmp]  /tmp                ext4
```

The `[/subdir]` suffix is how `findmnt` renders a bind mount. Its presence is
the proof that the bind half of the layout is in place.

## fstab entries

Provisioning appends four lines — two ext4 mounts keyed by UUID, two binds:

```
UUID=8f3c1a02-... /mnt/home-data ext4 defaults,nofail 0 2
/mnt/home-data/azureuser /home/azureuser none bind,nofail 0 0
UUID=b71d4e55-... /mnt/tmp-data ext4 defaults,nofail 0 2
/mnt/tmp-data/tmp /tmp none bind,nofail 0 0
```

Three properties are load-bearing:

- **UUIDs, not device names.** A `/dev/sdb` entry in fstab survives until the
  first reboot that reorders the SCSI bus, and then mounts the wrong disk on the
  right path.
- **`nofail`, on all four lines.** A missing data disk must not stop the VM from
  booting. A VM that will not come up is a worse failure than a VM with one
  directory on the OS disk. It matters *more* on the bind lines than on the ext4
  ones: systemd's fstab generator gives a bind mount a hard `RequiresMountsFor`
  on its source, so a bind without `nofail` takes `local-fs.target` down when
  the backing disk is absent and the VM boots to emergency mode with no SSH —
  defeating the `nofail` on the ext4 line above it.
- **`defaults,nofail` and nothing else on the ext4 lines.** In particular
  **never `mode=`**. `mode=1777` is a tmpfs option; ext4 rejects the mount
  outright, and combined with `nofail` the rejection is silent — the boot
  succeeds and `/tmp` quietly stays on the OS disk. Every producer of an fstab
  line in azlin — cloud-init, `azlin disk repair`, and `azlin disk add --mount`
  — goes through one function, which takes no options argument at all. There is
  nowhere for a stray option to enter, and a test asserts that no ext4 line it
  emits contains `mode=`. That structural guarantee is what protects against
  this class; `mount -a` during a repair does **not**, because both paths are
  already mounted by then and it skips them. A reboot is still the only
  end-to-end proof.

### `/tmp` gets its sticky bit from the backing directory

The sticky bit is a `chmod 1777`, not a mount option — and it is applied to the
**backing directory** `/mnt/tmp-data/tmp`, not to `/tmp`:

```bash
chmod 1777 /mnt/tmp-data/tmp     # survives reboots
chmod 1777 /tmp                  # only until the next boot
```

Boot mounts the backing directory over `/tmp`, so `/tmp` shows whatever mode
that directory carries. On a running VM both commands reach the same inode
through the bind, so chmodding `/tmp` looks like it worked — and it did, for
now. But if the backing directory itself was never chmodded, the next boot
brings `/tmp` up with the mode that directory actually has, and `/tmp` is
unwritable for non-root users. Anything that repairs `/tmp` by hand must chmod
the backing directory; chmodding `/tmp` alone is the failure that reappears one
reboot later.

## Formatting: which paths are guarded

`mkfs` runs from three places in azlin, and they do **not** all guard against an
existing filesystem. The difference is deliberate, and assuming otherwise is how
data gets destroyed:

| Path | Guard | Why |
| ---- | ----- | --- |
| cloud-init, at first boot | **none** — `mkfs.ext4 -F` runs unconditionally | The disks were created blank by the same `azlin new` invocation, moments earlier. There is nothing to protect, and a guard would silently skip a disk that a previous failed boot had partially formatted. |
| [`azlin disk repair`](../commands/disk/repair.md) | `blkid`, and `--force` to override | Runs on a live VM, days or months later. A filesystem found here may hold data the repair cannot see. |
| [`azlin disk add --mount`](../commands/disk/add.md) | `blkid`, no override | The disk may be a re-attached one that already holds a filesystem. |

The `blkid` guard **fails closed**. `blkid` reports "no filesystem found" as
exit status 2; only that status permits a format. Any other non-zero status —
`blkid` absent from the image, `sudo` denied, an I/O error on the device — stops
the script instead. The distinction matters because those are the same
conditions under which the *probe* is most likely to have misread the disk as
blank, so the guard and the classification it is supposed to be independent of
would otherwise fail together.

For the same reason the probe reports whether it could answer the filesystem
question at all. A disk with no `fstype` on a VM where neither `lsblk` nor
`sudo -n blkid` could run is reported `unknown`, not `raw` — `raw` is the stage a
repair formats without `--force`.

The consequence worth remembering: **never re-run cloud-init's disk block by
hand on a VM that has been used.** It is the one unguarded `mkfs` in azlin, and
it is safe only in the context it was written for — a VM that has existed for
about ninety seconds. To fix a VM that is already running, use `azlin disk
repair`, which is guarded.

## Provisioning order and failure isolation

Data disk setup runs **before** `apt-get update` and every other
network-dependent step in cloud-init.

The ordering is not cosmetic. Disk setup needs only `udevadm`, `mkfs.ext4`,
`blkid` and `mount`, all present in the Azure Ubuntu base image, and no network
at all. Package installation needs the archive to be reachable, which on a
bastion-only VM with no outbound route it is not. Sequencing the step that
cannot fail for network reasons behind the step that can is what left VMs with
attached, unformatted disks for weeks (issue #1131).

Ordering alone is not enough, because it only protects whatever happens to be
first. Each optional section is therefore wrapped so its failure cannot abort
the script:

```sh
# ---- section: apt-install ----
rc=0
(
  apt-get install -y -qq ripgrep fd-find tree ...
) || rc=$?
azlin_record apt-install "$rc"
```

The script keeps `set -euo pipefail` as its default, so critical work still
fails fast at the first error. What the wrapper changes is the *blast radius*:
the subshell still inherits `set -e` and still stops at its first failing
command — which is what the home block's rollback trap depends on — but the
`|| rc=$?` keeps that failure from ending the script. A missing `tree` package
can no longer prevent a filesystem from being created.

## The provisioning ledger

Suppressing failures without recording them would be worse than the original
bug, so every section writes its outcome to a ledger:

**`/var/lib/azlin/provisioning.tsv`** — append-only, one tab-separated line per
section, written as each section finishes:

```
disk-home	ok	0
disk-tmp	ok	0
apt-update	failed	100
apt-install	failed	100
setup-github-cli	skipped	skipped
```

Section names are a contract, not a convention: `azlin disk check` prints them
back to you, and support instructions are written against them. The emitted set
is `disk-home`, `disk-tmp`, `apt-update`, `apt-upgrade`, `apt-install`, and
`setup-<tool>` for each toolchain (`setup-python314`, `setup-github-cli`,
`setup-azure-cli`, `setup-rust`, `setup-go`, `setup-dotnet`, `setup-verify`, and
so on) — asserted by a test over the generated cloud-init script, so adding a
section whose name does not fit this shape fails that test rather than silently
drifting from this page.

`disk-home` and `disk-tmp` are absent on a VM created with no data disks; every
other section is always emitted.

Status is `ok`, `failed`, or `skipped`. The same lines appear in
`/var/log/cloud-init-output.log` as
`[AZLIN] section=<name> status=<status> rc=<rc>`.

`skipped` has exactly one cause: the package archive is unreachable, so the
`setup-*` sections that fetch from the network are not attempted. The gate needs
**two** signals, not one — `apt-update` *and* `apt-install` both failing:

- `apt-get update` alone fails whenever any configured source is unreachable,
  including a single broken PPA on an otherwise healthy machine.
- `apt-get install` alone fails when one package name is missing from a
  perfectly reachable archive — which is what Ubuntu 26.04 did to `tree`.

Either signal alone would misfire, and misfiring here is expensive in both
directions: skip too eagerly and a working VM loses its toolchains; skip too
reluctantly and a bastion-only VM spends its whole provisioning window running
twenty `curl` calls into their individual timeouts, which is how the #1131 VM
spent its. Sections that need no network — `setup-bashrc`, `setup-tmux-conf`,
`setup-path-links` — are never skipped.

`skipped` is not `failed`: the run that produced it is already `degraded`
because the apt sections failed, and marking twenty downstream sections `failed`
as well would bury the one line that says what actually went wrong.

Two files are written at the end, from an `EXIT` trap set in the preamble — so
even a failure outside any section reaches a terminal state:

| File | Meaning |
| ---- | ------- |
| `/var/lib/azlin/provisioning-complete` | Cloud-init finished. Always written, on every path. |
| `/var/lib/azlin/provisioning-status`   | `ok` or `degraded`, derived from the ledger. |

Splitting them this way keeps the sentinel's existing meaning for readiness
checks while making "finished" and "finished correctly" separately answerable. A
VM whose disk sections failed reaches a terminal state — it does not sit in
"provisioning" forever — and it reports `degraded` rather than healthy.

`azlin new` reads both files when it waits for the VM: a `degraded` status
prints a warning naming the failed sections instead of "Cloud-init provisioning
complete." It names the sections whose status is `failed` — not the ones that
are merely "not `ok`", which would include every `skipped` section and bury the
line that says what actually went wrong. All three readers of the ledger — that
warning, the storage probe, and cloud-init's own `EXIT` trap — select rows by
the same test. The sentinel alone can no longer mean success, because it is now
written on every path — reading it as success is how a VM with unformatted data
disks came back from `azlin new` looking like a clean create.

The script itself exits `0` even from a degraded run, deliberately. A non-zero
exit produces one `Failed to run module scripts_user` line at the bottom of
`/var/log/cloud-init-output.log` — which is precisely the channel that failed to
tell anyone about #1131 for weeks. `provisioning-status`, the `Storage` column
in `azlin list --with-health`, and `azlin disk check` are the channels that
someone actually reads.

The same trap prints a storage summary, so the log records what the VM came up
with rather than only what went wrong:

```
[AZLIN] storage: /mnt/home-data mounted, fstab=yes
[AZLIN] storage: /mnt/tmp-data absent
[AZLIN] provisioning finished: status=degraded
```

`fstab=no` on a mounted backing path is worth reading twice: the mount is live
now and will not come back after a reboot.

## Resuming an interrupted repair

`azlin disk repair` copies `/home/<user>` onto the data disk before it switches
the bind. If that copy is interrupted — Ctrl-C, a dropped SSH session, a reboot
— the VM is left with the disk formatted, the backing mounted, the bind never
made, and the destination half populated. The probe reads that as
`backing-mounted`, which is exactly what a correctly provisioned VM whose bind
was lost also looks like. The two are indistinguishable from the outside.

So the copy leaves a record of itself, on the data disk and outside the bind
source:

**`<backing>/.azlin-copy-<user>`** — `in-progress` from before the first byte is
written, `complete` only after the copy has been verified.

| Destination state | What repair does |
| ----------------- | ---------------- |
| empty | copy, verify, mark `complete` |
| marked `in-progress` | **resume**: copy again, verify, mark `complete` |
| marked `complete` | nothing — an earlier run already verified it |
| populated, no marker | nothing — this is data repair did not put there |

The last row is the original rule and it has not changed; it is now applied only
to the case where it is correct. The row above it is the one that mattered:
without the marker, a resumed repair skipped the copy *and with it the count
check and the `rsync -n` pass*, bound the partial directory over `/home/<user>`,
and reported success. If `.ssh/authorized_keys` was among the files not yet
copied, the operator could not log in to check — sshd reads `~` through the new
bind.

The marker lives in the backing mount's root rather than inside
`<backing>/<user>`, for two reasons: it never appears in the user's home, and it
is not one more entry on the destination side of the count the copy is verified
against.

The window between `mv /home/<user> /home/<user>.old` and a verified bind is
covered by a `trap … EXIT HUP INT TERM`. In that window the home directory is a
name that resolves to nothing, and a dropped SSH session delivers SIGHUP into
precisely it. The trap is cleared once the bind is verified — after that, the
original is *supposed* to stay at `.old`.

## Provisioning stages

`azlin disk check` reports how far each disk got. The stages are ordered: each
one implies every earlier one succeeded.

| Stage            | Meaning | Holds data? |
| ---------------- | ------- | ----------- |
| `absent`         | The LUN has no block device. The disk is not attached. | no |
| `raw`            | Attached, no filesystem. `mkfs` never ran. | no |
| `formatted`      | Has a filesystem, but the backing path is not mounted. | **yes** |
| `backing-mounted`| Backing path mounted, bind missing. `/home/<user>` is still the OS disk. | **yes** |
| `healthy`        | Backing mount and bind both in place. | yes |

The distinction matters for repair: only `formatted` and later can contain data,
so only those require `--force` before any `mkfs`. `raw` — the #1131 case — is
safe to format without one.

## Related

- [`azlin disk check`](../commands/disk/check.md) — report a VM's layout against this contract
- [`azlin health` and `azlin list --with-health`](../commands/disk/check.md#storage-in-the-health-surfaces) — the same verdict, per VM, in a `Storage` column
- [`azlin disk repair`](../commands/disk/repair.md) — bring a VM up to it
- [Data disks are not mounted](../troubleshooting/data-disks-not-mounted.md) — diagnosing the #1131 symptom
- [Creating VMs](../vm-lifecycle/creating.md) — `--home-disk-size`, `--tmp-disk-size`, `--no-home-disk`
