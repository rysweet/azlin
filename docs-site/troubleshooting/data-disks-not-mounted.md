# Data disks are not mounted

**Symptom:** the VM is out of disk space while `az disk list` shows one or two
azlin data disks attached to it. `/home` and `/tmp` are ordinary directories on
the small OS disk; the data disks have no filesystem at all.

```
$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        29G   28G  830M  98% /

$ lsblk
sda      30G  disk
├─sda1   29G  part /
sdb    1000G  disk          <- attached, empty, billed
sdc     200G  disk          <- attached, empty, billed
```

`azlin list` shows the VM `running`, and until you look at `df` nothing tells
you the storage provisioning never happened.

## 1. Confirm it in one command

```bash
azlin disk check dev
```

```
VM: dev  (rg: rysweet-linux-vm-pool)
Storage: degraded

  ROLE  LUN  DEVICE      SIZE     STAGE
  home  0    /dev/sdb    1000G    raw
        no filesystem on the device; /home/<user> is on the OS disk
  tmp   1    /dev/sdc    200G     raw
        no filesystem on the device; /tmp is on the OS disk
```

`raw` is the diagnosis: the disk is attached and has never been formatted.

To sweep a fleet — the disks are named `<vm>_home` and `<vm>_tmp`, so a VM in
this state is rarely the only one:

```bash
azlin list --with-health
```

The `Storage` column reports `ok`, `degraded`, or `--` per VM. `--` means the
probe could not run; it is not a pass.

## 2. Why it happens

On VMs provisioned before this was fixed, cloud-init ran under
`set -euo pipefail` with `apt-get update`/`upgrade`/`install` **before** the disk
setup block. On a bastion-only VM with no outbound route, apt cannot reach the
Ubuntu archive:

```
W: Failed to fetch http://azure.archive.ubuntu.com/ubuntu/dists/... Unable to connect
E: Package 'docker.io' has no installation candidate
cc_scripts_user.py[WARNING]: Failed to run module scripts_user
```

`apt-get install` exited non-zero, `set -e` ended the script, and every line
after it — including all of the disk formatting and mounting — never ran. The
disk block's own retry loop, subshell isolation, and rollback trap were all
intact and all unreachable.

Two changes fixed it for VMs created since:

- disk setup now runs **before** any network-dependent step, because it needs no
  network at all
- each optional section is wrapped so its failure is recorded rather than fatal,
  and the result is written to a
  [provisioning ledger](../storage/data-disk-layout.md#the-provisioning-ledger)

Neither change reaches back to a VM that is already running. That is what
`azlin disk repair` is for.

You can confirm the original cause on the VM itself:

```bash
azlin connect dev
grep -E 'Unable to connect|has no installation candidate|Failed to run module' \
  /var/log/cloud-init-output.log | head
```

On a VM new enough to have the ledger, read that instead — it names the failed
sections directly:

```bash
cat /var/lib/azlin/provisioning.tsv
```

## 3. Repair it

```bash
azlin disk repair dev
```

Repair formats each `raw` disk, copies the existing contents onto it, verifies
the copy, bind-mounts it into place, writes the fstab entries, and runs
`mount -a` to confirm the entries actually mount. It refuses to format a disk
that already holds a filesystem unless you pass `--force`.

Preview first if you would rather read the commands:

```bash
azlin disk repair dev --dry-run
```

Then verify:

```bash
azlin disk check dev     # Storage: ok
azlin connect dev        # reconnect: your old shell still holds the old inodes
df -h / /home /tmp
```

```
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        29G  5.1G   23G  19% /
/dev/sdb        984G  2.1G  916G   1% /home/azureuser
/dev/sdc        196G   28K  186G   1% /tmp
```

## 4. Reclaim the retained copy

Repair does not delete the directory it copied. It renames it to
`/home/<user>.old` and bind-mounts the data disk over a fresh `/home/<user>`, so
the original is still there, on the OS disk, as your rollback.

That is why `/` is not much emptier immediately after a repair: the space is
still held by `.old`. Once you have confirmed the new mount holds everything you
need, reclaim it:

```bash
azlin connect dev
sudo du -sh /home/azureuser.old      # what you are about to delete
sudo rm -rf /home/azureuser.old
df -h /
```

Repair renames rather than shadows on purpose. A directory bind-mounted over in
place is still reachable — through `mount --bind / /mnt/rootfs` — but only if
you remember to do it, and a plain `rm -rf /home/<user>/*` at that point deletes
the copy on the data disk instead of the one on the OS disk. `.old` is visible,
nameable, and cannot be confused with the live directory.

Cloud-init's own home block removes `.old` as soon as it has verified the bind,
and that asymmetry is deliberate: at first boot the directory it moved is a
ninety-second-old skeleton, and there is nothing to roll back to.

## 5. Manual repair, if you cannot run `azlin disk repair`

The steps below are what the command automates. Run them on the VM as root.

```bash
# 1. Identify the disks by LUN, not by /dev/sdX
HOME_DEV=$(readlink -f /dev/disk/azure/scsi1/lun0)
TMP_DEV=$(readlink -f /dev/disk/azure/scsi1/lun1)

# 2. Format -- but only if blkid finds nothing. Any output from blkid means the
#    disk is NOT raw: stop and find out what is on it before going further.
#    (Cloud-init's own disk block runs mkfs.ext4 -F unguarded, which is safe
#    only on a brand-new VM. Do not copy that line onto a VM in use.)
blkid "$HOME_DEV" || mkfs.ext4 -F -L azlin-home "$HOME_DEV"
blkid "$TMP_DEV"  || mkfs.ext4 -F -L azlin-tmp  "$TMP_DEV"

# 3. Mount the backing paths
mkdir -p /mnt/home-data /mnt/tmp-data
mount "$HOME_DEV" /mnt/home-data
mount "$TMP_DEV" /mnt/tmp-data
# This chmod is the one that matters: /tmp inherits the backing directory's
# mode at every boot. The chmod in step 5 only fixes the running system.
mkdir -p /mnt/tmp-data/tmp && chmod 1777 /mnt/tmp-data/tmp

# 4. Copy home, then VERIFY before switching anything
rsync -aAXH /home/azureuser/ /mnt/home-data/azureuser/
find /home/azureuser -xdev | wc -l
find /mnt/home-data/azureuser -xdev | wc -l      # must match
rsync -n -aAXH /home/azureuser/ /mnt/home-data/azureuser/   # must print nothing

# 5. Bind into place
mount --bind /mnt/home-data/azureuser /home/azureuser
mount --bind /mnt/tmp-data/tmp /tmp
chmod 1777 /tmp        # cosmetic if step 3 was done; harmless either way

# 6. Persist -- UUIDs for the ext4 mounts, paths for the binds
HOME_UUID=$(blkid -s UUID -o value "$HOME_DEV")
TMP_UUID=$(blkid -s UUID -o value "$TMP_DEV")
cat >> /etc/fstab <<EOF
UUID=$HOME_UUID /mnt/home-data ext4 defaults,nofail 0 2
/mnt/home-data/azureuser /home/azureuser none bind,nofail 0 0
UUID=$TMP_UUID /mnt/tmp-data ext4 defaults,nofail 0 2
/mnt/tmp-data/tmp /tmp none bind,nofail 0 0
EOF

# 7. Prove the entries mount, now -- not at the next reboot
umount /tmp /home/azureuser /mnt/tmp-data /mnt/home-data
mount -a
findmnt /home/azureuser && findmnt /tmp
```

### If `rsync` is not installed

This VM is broken *because* `apt-get install` failed, so do not assume the
package set is complete. If step 4's `rsync` is not found, use coreutils:

```bash
cp -a /home/azureuser/. /mnt/home-data/azureuser/
find /home/azureuser -xdev | wc -l
find /mnt/home-data/azureuser -xdev | wc -l      # must match before step 5
```

`cp -a` preserves mode, ownership, timestamps, symlinks and ACLs, which covers
a home directory. What you lose is the verification, not the copy: the file
counts prove nothing was dropped, but there is no equivalent of the `rsync -n`
pass to prove every file's *contents* came across. Before deleting anything in
[step 4 above](#4-reclaim-the-retained-copy), spot-check what you would miss —
`~/.ssh`, credentials, anything not reproducible:

```bash
diff -r /home/azureuser/.ssh /mnt/home-data/azureuser/.ssh
```

Installing `rsync` first is better if the VM can reach the archive at all.

### Do not put `mode=1777` in an fstab entry for `/tmp`

`mode=` is a **tmpfs** option. ext4 rejects it, the mount fails, and because the
entry also carries `nofail` the failure is silent: the boot succeeds and `/tmp`
stays on the OS disk, looking exactly like the problem you were fixing.

```
# WRONG -- fails silently at boot
UUID=... /tmp ext4 defaults,nofail,mode=1777 0 2

# RIGHT -- the sticky bit is a chmod, not a mount option
UUID=... /mnt/tmp-data ext4 defaults,nofail 0 2
/mnt/tmp-data/tmp /tmp none bind,nofail 0 0
```

Step 7 above exists to catch exactly this: if `mount -a` does not bring the
entry up now, it will not bring it up at boot either.

## 6. Preventing it on new VMs

Nothing to configure. VMs created with a current azlin set the disks up before
any network step, record the outcome, and report `degraded` in
`azlin disk check` and the `Storage` column of `azlin list --with-health` if anything went
wrong. A `raw` disk cannot go unnoticed for weeks again.

## Related

- [Data Disk Layout](../storage/data-disk-layout.md) - the layout, fstab rules, and provisioning ledger
- [`azlin disk check`](../commands/disk/check.md) - the read-only diagnosis
- [`azlin disk repair`](../commands/disk/repair.md) - the automated fix
