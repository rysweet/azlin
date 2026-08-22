# azlin disk repair

Bring a VM's data disks up to azlin's intended layout in place — format, copy,
bind-mount, and persist to fstab — without reprovisioning the VM.

Use it when [`azlin disk check`](check.md) reports `degraded`.

## Usage

```bash
azlin disk repair VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - VM name or session name (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group (default: configured resource group) |
| `--dry-run` | Print the plan and the exact script, then exit without touching the VM |
| `--force` | Permit `mkfs` on a disk that already holds a filesystem. Required for any disk at stage `formatted` or later; refused otherwise. This is a permission, not a confirmation |
| `--yes` | Skip the confirmation prompt shown before a `--force` reformat |
| `-h, --help` | Show help message |

`--force` and `--yes` are two different things, and on this command only.
Everywhere else in azlin `--force` means "do not ask me"; here it means "you may
run `mkfs` over a filesystem", and the question about doing so is still asked.
Collapsing them would make the flag that permits the reformat also the flag that
skips the question about it, which is how `azlin disk repair --force <typo>`
becomes unrecoverable. In a non-TTY — cron, CI, a piped shell — `--yes` is
required rather than assumed.

## What it does

Repair starts from the stage each disk is actually at and runs only the steps
that are missing. It is idempotent by construction, not by a pile of guards:

| Stage at start | Steps performed |
| -------------- | --------------- |
| `absent` | None. Repair stops and tells you the LUN has no device — that is an Azure attach problem, not a filesystem one |
| `raw` | `mkfs` → mount backing → copy → verify → bind → fstab → `mount -a` verify |
| `formatted` | **Refused** without `--force`: there is a filesystem here that repair cannot read, because it is not mounted. With `--force`: `mkfs` → mount backing → copy → verify → bind → fstab → verify |
| `backing-mounted` | copy → verify → bind → fstab → verify |
| `healthy` | None. Reported as a no-op |

Running `azlin disk repair` twice is safe: the second run finds every disk
`healthy` and does nothing.

## Safety properties

These are the reasons this command can be pointed at a VM that has data on it.

- **It will not format a disk that holds a filesystem.** The `mkfs` step sits
  behind a `blkid` guard — literally the same function `azlin disk add --mount`
  uses. A disk at stage `formatted` is refused outright with an explanatory
  message unless you pass `--force`, which is the only route to reformatting.

    The guard **fails closed**. `blkid` spells "no filesystem here" as exit
    status 2, and only that status permits a format. Any other failure — `blkid`
    missing from the image, `sudo` denied, an I/O error on the device — stops
    the repair with a message rather than formatting a disk whose contents
    nobody could read.

    `backing-mounted` is not refused, and the distinction is the point: at that
    stage the filesystem *is* mounted, so its contents are visible and the only
    missing step is the bind. At `formatted` the filesystem is not mounted, so
    whatever it holds is exactly what repair cannot see.
- **The copy is verified before the bind is switched.** Until the verification
  passes, the original directory is retained as `/home/<user>.old` and the bind
  is not made. Which verification runs depends on what the VM has:
    - **`rsync` present** — copy with `rsync -aAXH`; verify that file counts
      match *and* that a `rsync -n -aAXH` pass reports no differences.
    - **`rsync` absent** — copy with `cp -a`; verify that file counts match.

    The fallback is not hypothetical. Repair exists for VMs where the
    `apt-install` section failed, so it must assume the package set is
    incomplete; `cp -a` is in coreutils and always present. Repair prints which
    mode it used, because the weaker verify is a real difference: matching
    counts prove nothing was dropped, but unlike the `rsync -n` pass they do not
    prove that contents, ACLs, and xattrs came across intact. If that matters,
    install `rsync` on the VM and re-run — a repair that already reached
    `healthy` re-runs as a no-op.
- **An interrupted copy is resumed, not mistaken for a finished one.** The copy
  writes `in-progress` to a marker on the data disk before it starts and
  promotes it to `complete` only after the verification passes. A repair
  interrupted mid-copy — Ctrl-C, a dropped SSH session, a reboot — leaves the VM
  at stage `backing-mounted` with a half-populated destination, which is
  indistinguishable on the wire from a VM whose bind was simply lost. The marker
  is what tells them apart: the first is resumed and re-verified, the second is
  left alone. Without it the re-run skipped the copy *and* the verification and
  bound a partial home over the real one.

    Data that this repair did not put there is still never copied over. That
    rule has not changed; it is now applied only where it is correct.
- **Failure rolls back.** If the bind mount does not come up, the trap restores
  the original directory. The trap is armed *before* the rename and cleared only
  once the bind is verified, so an interruption anywhere in that window — a
  SIGHUP from a dropped session lands squarely in it — restores the original
  too. A failed repair leaves the VM as it was, on the OS disk, not with an
  empty home directory.
- **fstab is verified, not assumed.** After writing the entries, repair runs
  `mount -a` and re-checks the mount table. "Persisted to fstab" is never
  reported for an entry that does not actually mount. This is what catches a
  malformed option before the next reboot does — see
  [why `mode=` never appears on an ext4 line](../../storage/data-disk-layout.md#fstab-entries).
- **It never runs implicitly.** `azlin disk check` reports the verdict and
  prints the suggested command; `azlin list --with-health` reports the verdict in
  its `Storage` column. Nothing formats a disk as a side effect of a status
  query.

## Examples

### Repairing the #1131 case

Both disks attached and raw; everything running on the OS disk.

```bash
azlin disk repair dev
```

**Output:**
```
VM: dev  (rg: rysweet-linux-vm-pool)

Plan:
  home  0    /dev/sdb  1000G  raw    -> healthy
  tmp   1    /dev/sdc  200G   raw    -> healthy

  home  formatting (no filesystem found)
  home  mounted /dev/sdb on /mnt/home-data
  home  copied with rsync -aAXH
  home  verified 48213 entries, rsync dry run clean
  home  bound /mnt/home-data/azureuser onto /home/azureuser, original kept at /home/azureuser.old
  home  /etc/fstab entries written; verified as far as is possible without a reboot
  tmp   formatting (no filesystem found)
  tmp   mounted /dev/sdc on /mnt/tmp-data
  tmp   bound /mnt/tmp-data/tmp onto /tmp
  tmp   /etc/fstab entries written; verified as far as is possible without a reboot

Storage: ok

Note: open shells and tmux sessions still hold the old directories. Reconnect
      to see the new mounts:  azlin connect dev
Note: the previous contents of the repaired home directory were kept alongside
      it as `<path>.old` and still occupy the OS disk. Remove them once you have
      confirmed the new mount.
```

### Previewing without touching the VM

```bash
azlin disk repair dev --dry-run
```

Prints the same plan followed by the exact shell script that would run, and
exits. Nothing is executed on the VM. Use this when you want to read the
commands before letting them run, or to hand them to someone else.

### A disk that already has a filesystem

```bash
azlin disk repair archive-vm
```

**Output:**
```
VM: archive-vm  (rg: azlin-rg)

  home: refusing to format the home disk at LUN 0: it already has a filesystem,
  which may hold data this repair cannot see because it is not mounted. Inspect
  it first, then re-run with --force if it should be reformatted anyway.

Error: nothing could be repaired on 'archive-vm'
```

Inspect it before deciding:

```bash
azlin connect archive-vm
sudo mkdir -p /mnt/inspect
sudo mount /dev/disk/azure/scsi1/lun0 /mnt/inspect
```

Exit code `1`.

Re-running with `--force` names the disks it would reformat and asks before
doing anything:

```bash
azlin disk repair archive-vm --force
```

**Output:**
```
VM: archive-vm  (rg: azlin-rg)

Plan:
  home  0    /dev/sdb  1000G  formatted  -> healthy

  --force will run mkfs.ext4 over the existing filesystem on the home disk at LUN 0 (/dev/sdb).
  Anything on it that is not already on another disk is lost.
? Reformat and continue? (y/N)
```

Add `--yes` to skip that question — which is required, not optional, when stdin
is not a terminal.

### A VM that is already fine

```bash
azlin disk repair build-vm
```

**Output:**
```
VM: build-vm  (rg: azlin-rg)
Storage: ok — nothing to repair.

  home  LUN 0  healthy
  tmp   LUN 1  healthy
```

Exit code `0`.

## After a repair

- **Reconnect.** Processes with open file handles — your tmux session, a running
  build — keep the old inodes on the OS disk until they exit. `azlin connect`
  gives you a shell on the new mount. Repair does not kill sessions.
- **Verify across a reboot** if the VM can afford one. The fstab entries are
  verified with `mount -a` during the repair, which is the same code path a
  boot takes, but a reboot is the only end-to-end proof.
- **`/tmp` keeps its sticky bit across reboots** because repair sets `1777` on
  the backing directory `/mnt/tmp-data/tmp`, not on `/tmp`. A boot mounts the
  backing directory over `/tmp`, so `/tmp` shows whatever mode that directory
  has; a `chmod 1777 /tmp` applied afterwards is only cosmetic and is lost at
  the next boot.
- **Reclaim the retained copy.** Repair renames the original directory to
  `/home/<user>.old` rather than deleting it, so it still occupies the OS disk.
  That copy is your rollback; remove it once you are satisfied. See
  [Reclaim the retained copy](../../troubleshooting/data-disks-not-mounted.md#4-reclaim-the-retained-copy).

## Related

- [`azlin disk check`](check.md) - the read-only half
- [Data Disk Layout](../../storage/data-disk-layout.md) - the layout this restores
- [Data disks are not mounted](../../troubleshooting/data-disks-not-mounted.md) - the full walkthrough, including the manual fallback
