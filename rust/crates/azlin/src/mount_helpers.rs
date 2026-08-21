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
///
/// The guard and the fstab line both come from `azlin_azure::disk_layout`,
/// shared with `azlin disk repair` and (for the fstab line) with the cloud-init
/// generator. One `mode=` in the wrong place cost a manual repair a whole cycle
/// to find (#1131); there is one function that can make that mistake now.
pub fn build_disk_mount_script(lun: u32, mount_path: &str) -> Result<String, String> {
    // Validated here as well as at the call site. The path is interpolated into a
    // shell script two modules away from where it is checked, so a second caller
    // would inherit that guarantee by convention rather than by construction — and
    // shell injection is not a property to hold by convention.
    validate_mount_path(mount_path)?;
    let device = azure_lun_device(lun);
    let format_step = azlin_azure::disk_layout::blkid_guarded_mkfs("DEV", None, "sudo ");
    let fstab =
        azlin_azure::disk_layout::fstab_line(&azlin_azure::disk_layout::FstabSpec::Ext4ByUuid {
            uuid_expr: "$UUID".to_string(),
            target: mount_path.to_string(),
        });
    Ok(format!(
        "set -e\n\
         DEV={device}\n\
         for _ in $(seq 1 30); do [ -e \"$DEV\" ] && break; sleep 1; done\n\
         if [ ! -e \"$DEV\" ]; then echo \"azlin: {device} never appeared\" >&2; exit 1; fi\n\
         {format_step}\n\
         sudo mkdir -p {mount_path}\n\
         sudo mount \"$DEV\" {mount_path}\n\
         echo 'azlin: step=mounted'\n\
         UUID=$(sudo blkid -s UUID -o value \"$DEV\")\n\
         if ! grep -q \"$UUID\" /etc/fstab; then\n\
         echo \"{fstab}\" | sudo tee -a /etc/fstab >/dev/null\n\
         fi\n\
         echo 'azlin: step=persisted'\n"
    ))
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
        let script = build_disk_mount_script(0, "/data").unwrap();
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
        let script = build_disk_mount_script(1, "/data").unwrap();
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
        let script = build_disk_mount_script(1, "/data").unwrap();
        assert!(script.contains("grep -q \"$UUID\" /etc/fstab"), "{script}");
    }

    /// The device symlink appears asynchronously after the attach returns.
    #[test]
    fn the_script_waits_for_the_device() {
        let script = build_disk_mount_script(2, "/data").unwrap();
        assert!(script.contains("seq 1 30"), "{script}");
        assert!(script.contains("never appeared"), "{script}");
    }

    /// The builder refuses a path the validator rejects, so the guarantee is
    /// local to the function that does the interpolating rather than held by
    /// convention at the call site.
    #[test]
    fn the_builder_refuses_a_path_it_would_have_to_interpolate_unsafely() {
        assert!(build_disk_mount_script(0, "/data; rm -rf /").is_err());
        assert!(build_disk_mount_script(0, "relative").is_err());
        assert!(build_disk_mount_script(0, "/data").is_ok());
    }

    #[test]
    fn the_mount_path_is_validated_before_it_reaches_a_shell() {
        assert!(validate_mount_path("/data").is_ok());
        assert!(validate_mount_path("/data; rm -rf /").is_err());
        assert!(validate_mount_path("relative").is_err());
        assert!(validate_mount_path("/a/../../etc").is_err());
    }
}
