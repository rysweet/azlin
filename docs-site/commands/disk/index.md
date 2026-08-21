# Disk Commands

Manage the data disks attached to an azlin VM: add one, verify the ones that are
already there, and repair a VM whose disks were attached but never set up.

## Commands

| Command | Description |
| ------- | ----------- |
| [`azlin disk add`](add.md) | Attach a new data disk to a VM, optionally formatting and mounting it |
| [`azlin disk check`](check.md) | Report whether a VM's data disks match azlin's intended layout |
| [`azlin disk repair`](repair.md) | Bring a VM's data disks up to that layout in place |

## Quick Start

```bash
# Is this VM's storage set up the way azlin intended?
azlin disk check dev

# Fix it without reprovisioning
azlin disk repair dev

# Attach an extra 500 GB disk and mount it at /data
azlin disk add dev --size 500 --mount /data
```

## The disks azlin creates for you

`azlin new` already attaches up to two data disks — a 100 GB `/home` disk by
default, and a `/tmp` disk when you pass `--tmp-disk-size`. Those are set up by
cloud-init at first boot and need no `disk` command.

`azlin disk check` and `azlin disk repair` exist for when that setup did not
happen. The layout they verify and restore is described in
[Data Disk Layout](../../storage/data-disk-layout.md) — read that first if you
are diagnosing by hand, because the disks are bind-mounted rather than mounted
directly on `/home` and `/tmp`, and a check written against the obvious layout
reports healthy VMs as broken.

## Scope

These commands operate on **azlin's own data disks**, addressed by LUN and role.
For shared network storage across VMs, see
[Storage Commands](../storage/index.md).

## Related

- [Data Disk Layout](../../storage/data-disk-layout.md) — the layout, fstab entries, and provisioning ledger
- [Data disks are not mounted](../../troubleshooting/data-disks-not-mounted.md) — troubleshooting guide
- [`azlin new`](../vm/new.md) — `--home-disk-size`, `--tmp-disk-size`, `--no-home-disk`
