/// Validate a mount-point path is safe (no shell metacharacters, no traversal).
pub fn validate_mount_path(path: &str) -> Result<(), String> {
    if path.is_empty() {
        return Err("Mount path must not be empty".into());
    }
    if !path.starts_with('/') {
        return Err(format!("Mount path '{}' must be absolute", path));
    }
    // Reject shell metacharacters
    let bad_chars = [
        ';', '|', '&', '$', '`', '(', ')', '{', '}', '<', '>', '!', '\n', '\0',
    ];
    for c in bad_chars {
        if path.contains(c) {
            return Err(format!(
                "Mount path '{}' contains dangerous character '{}'",
                path, c
            ));
        }
    }
    // Reject traversal
    if path.contains("/../") || path.ends_with("/..") || path == ".." {
        return Err(format!("Mount path '{}' contains path traversal", path));
    }
    Ok(())
}

/// The Azure-stable device path for a data disk at `lun`.
///
/// `/dev/sdc` and friends are assigned in attach order and change across
/// reboots; `/dev/disk/azure/scsi1/lunN` is the symlink Azure's udev rules
/// maintain and is the only name that means the same disk twice.
pub fn azure_lun_device(lun: u32) -> String {
    format!("/dev/disk/azure/scsi1/lun{}", lun)
}

/// The script that formats (only if unformatted) and mounts a data disk.
///
/// `azlin disk add --mount` attached the disk and stopped; the flag was
/// accepted and discarded (#1089), so the disk arrived raw and the user had to
/// find it themselves.
///
/// Two properties matter more than brevity here:
///
/// * **It never reformats.** `blkid` decides. Running `azlin disk add --mount`
///   twice against the same LUN must not destroy the filesystem the first run
///   created, and a `mkfs` that runs unconditionally is a data-loss bug that
///   only shows up the second time.
/// * **It mounts by UUID in fstab**, not by the `/dev/sd*` name, which Azure
///   reassigns in attach order across reboots. Persisting the wrong name is
///   how a VM comes back with someone else's disk on the mount point.
///
/// `nofail` keeps a missing disk from blocking boot: a VM that will not come
/// up is a worse outcome than a missing mount.
pub fn build_disk_mount_script(lun: u32, mount_path: &str) -> String {
    let device = azure_lun_device(lun);
    format!(
        "set -e\n\
         DEV={device}\n\
         for _ in $(seq 1 30); do [ -e \"$DEV\" ] && break; sleep 1; done\n\
         if [ ! -e \"$DEV\" ]; then echo \"azlin: {device} never appeared\" >&2; exit 1; fi\n\
         if ! sudo blkid \"$DEV\" >/dev/null 2>&1; then\n\
         echo 'azlin: formatting (no filesystem found)'\n\
         sudo mkfs.ext4 -F \"$DEV\"\n\
         else echo 'azlin: filesystem already present, not reformatting'; fi\n\
         sudo mkdir -p {mount_path}\n\
         sudo mount \"$DEV\" {mount_path}\n\
         UUID=$(sudo blkid -s UUID -o value \"$DEV\")\n\
         if ! grep -q \"$UUID\" /etc/fstab; then\n\
         echo \"UUID=$UUID {mount_path} ext4 defaults,nofail 0 2\" | sudo tee -a /etc/fstab >/dev/null\n\
         fi\n\
         echo 'azlin: mounted'\n"
    )
}

#[cfg(test)]
mod mount_script_tests {
    use super::*;

    #[test]
    fn the_device_is_the_stable_azure_symlink() {
        // `/dev/sdc` is assigned in attach order and means a different disk
        // after a reboot.
        assert_eq!(azure_lun_device(3), "/dev/disk/azure/scsi1/lun3");
    }

    /// Running `disk add --mount` twice must not destroy the filesystem the
    /// first run created.
    #[test]
    fn the_script_never_reformats_unconditionally() {
        let script = build_disk_mount_script(0, "/data");
        assert!(script.contains("blkid"), "{script}");
        let mkfs_line = script
            .lines()
            .find(|l| l.contains("mkfs"))
            .expect("a format step");
        assert!(
            mkfs_line.trim().starts_with("sudo mkfs"),
            "mkfs must be inside the blkid guard: {script}"
        );
        assert!(
            script.contains("not reformatting"),
            "and must say when it skipped: {script}"
        );
    }

    /// fstab by UUID, not by `/dev/sd*`: Azure reassigns those across reboots,
    /// and persisting one is how a VM comes back with another disk mounted
    /// where this one was.
    #[test]
    fn fstab_uses_the_uuid_and_does_not_block_boot() {
        let script = build_disk_mount_script(1, "/data");
        assert!(script.contains("blkid -s UUID"), "{script}");
        assert!(script.contains("UUID=$UUID /data ext4"), "{script}");
        assert!(
            script.contains("nofail"),
            "a missing disk must not wedge boot: {script}"
        );
        assert!(!script.contains("/dev/sd"), "{script}");
    }

    /// A second run must not append a duplicate fstab entry.
    #[test]
    fn fstab_is_not_appended_twice() {
        let script = build_disk_mount_script(1, "/data");
        assert!(script.contains("grep -q \"$UUID\" /etc/fstab"), "{script}");
    }

    /// The device symlink appears asynchronously after the attach returns.
    #[test]
    fn the_script_waits_for_the_device() {
        let script = build_disk_mount_script(2, "/data");
        assert!(script.contains("seq 1 30"), "{script}");
        assert!(script.contains("never appeared"), "{script}");
    }

    #[test]
    fn the_mount_path_is_validated_before_it_reaches_a_shell() {
        assert!(validate_mount_path("/data").is_ok());
        assert!(validate_mount_path("/data; rm -rf /").is_err());
        assert!(validate_mount_path("relative").is_err());
        assert!(validate_mount_path("/a/../../etc").is_err());
    }
}
