//! Argument construction for `azlin clone`, and the three flags it discarded.
//!
//! `--session-prefix`, `--vm-size` and `--region` all reached `--help` and none
//! reached the handler (#1089). Two of them advertise a default the code did
//! not implement either:
//!
//! * `--vm-size` says "default: same as source". `az vm create --attach-os-disk`
//!   with no `--size` uses **Azure's** default SKU, not the source VM's, so a
//!   clone of a `Standard_D8s_v5` came back as whatever Azure picks — quietly,
//!   at a different price, with different performance.
//! * `--region` says "default: same as source", which the code did do.
//! * `--session-prefix` set nothing, so clones carried no `azlin-session` tag
//!   at all and did not appear as a session in `azlin list`.
//!
//! Everything here is pure argv construction so the shapes can be asserted
//! offline, the same way `nat_helpers` does it. A wrong `--size` is a billing
//! difference and a wrong `--location` is a cross-region copy, so both are
//! pinned verbatim rather than by `contains`.

/// The name a clone gets. `index` is zero-based; the name is one-based.
pub fn clone_name(source_vm: &str, index: u32) -> String {
    format!("{}-clone-{}", source_vm, index + 1)
}

/// The `azlin-session` tag value for one clone.
///
/// Without a prefix the clone's own name is the session, which matches what a
/// single `azlin new` does. With a prefix, the clones form one numbered group,
/// so `azlin clone web --num-replicas 3 --session-prefix canary` produces
/// `canary-1`, `canary-2`, `canary-3` rather than three unrelated sessions.
///
/// A single clone with a prefix takes the prefix unnumbered: `-1` on a group of
/// one is noise.
pub fn clone_session_tag(prefix: Option<&str>, source_vm: &str, index: u32, total: u32) -> String {
    match prefix.map(str::trim).filter(|p| !p.is_empty()) {
        Some(p) if total > 1 => format!("{}-{}", p, index + 1),
        Some(p) => p.to_string(),
        None => clone_name(source_vm, index),
    }
}

/// `az disk create` for one clone's OS disk.
///
/// `--location` is explicit. Without it the disk inherits the resource group's
/// location, which is not necessarily the region the clone is going to — and
/// with `--region` now honoured, "not necessarily" became "often not".
pub fn build_clone_disk_args(
    resource_group: &str,
    disk_name: &str,
    snapshot_name: &str,
    location: &str,
) -> Vec<String> {
    [
        "disk",
        "create",
        "--resource-group",
        resource_group,
        "--name",
        disk_name,
        "--source",
        snapshot_name,
        "--location",
        location,
        "--output",
        "json",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect()
}

/// `az vm create` for one clone.
///
/// `size` is the resolved SKU — the flag's value, or the source VM's own size
/// when it was not given. It is never omitted: leaving `--size` off is what
/// made `--vm-size`'s documented default ("same as source") untrue.
///
/// `is_bastion` mirrors the source's shape: a source with no public IP produces
/// a clone with none, routed through the region's bastion VNet. A clone that
/// silently gained a public IP would be a different security posture from the
/// VM it was cloned from.
pub fn build_clone_vm_args(
    resource_group: &str,
    clone_name: &str,
    disk_name: &str,
    location: &str,
    size: &str,
    session_tag: &str,
    is_bastion: bool,
) -> Vec<String> {
    let mut args: Vec<String> = [
        "vm",
        "create",
        "--resource-group",
        resource_group,
        "--name",
        clone_name,
        "--attach-os-disk",
        disk_name,
        "--os-type",
        "Linux",
        "--location",
        location,
        "--size",
        size,
        "--tags",
        // One `argv` element: `az` takes `key=value` pairs, and splitting on
        // the `=` would make the tag two malformed arguments.
        &format!("azlin-session={}", session_tag),
        "--output",
        "json",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    if is_bastion {
        for arg in [
            "--public-ip-address",
            "",
            "--subnet",
            "default",
            "--vnet-name",
            &format!("azlin-bastion-{}-vnet", location),
        ] {
            args.push(arg.to_string());
        }
    }
    args
}

/// Is this clone crossing a region boundary?
pub fn is_cross_region(source_location: &str, target_location: &str) -> bool {
    !source_location.eq_ignore_ascii_case(target_location)
}

/// Warn when a clone is being sent to a different region than its source.
///
/// Returns `None` when the regions match. Azure only copies a snapshot across
/// regions when it is **incremental** and referenced by its full resource id,
/// so azlin asks for both — but support still varies by disk type and by
/// region pair, and a refusal arrives as an Azure error after the snapshot has
/// been created and is billing. Saying that up front beats explaining it
/// afterwards.
pub fn cross_region_note(source_location: &str, target_location: &str) -> Option<String> {
    if !is_cross_region(source_location, target_location) {
        return None;
    }
    Some(format!(
        "Cloning from {} into {}: the snapshot is created incremental and copied across \
         regions, which incurs egress. Azure does not support this for every disk type or \
         region pair; if it refuses, the snapshot has already been created and is billing.",
        source_location, target_location
    ))
}

/// `az snapshot create` for the clone source.
///
/// `--incremental` only when the clone is crossing regions: it is what makes
/// the cross-region copy possible at all, and it is not free to ask for
/// otherwise — incremental snapshots have different billing and different
/// restore behaviour from full ones, so a same-region clone should not
/// silently start producing them.
pub fn build_snapshot_args(
    resource_group: &str,
    snapshot_name: &str,
    disk_id: &str,
    source_location: &str,
    cross_region: bool,
) -> Vec<String> {
    let mut args: Vec<String> = [
        "snapshot",
        "create",
        "--resource-group",
        resource_group,
        "--source",
        disk_id,
        "--name",
        snapshot_name,
        "--location",
        source_location,
        "--output",
        "json",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    if cross_region {
        args.push("--incremental".to_string());
    }
    args
}

/// The snapshot's resource id, from `az snapshot create`'s JSON.
///
/// The id rather than the name, because `az disk create --source` only accepts
/// a bare name for a snapshot in the same region: a cross-region copy needs
/// the full id. Falling back to the name would work within a region and fail
/// across one, which is the harder failure to diagnose.
pub fn snapshot_id_from_create(stdout: &[u8]) -> Option<String> {
    serde_json::from_slice::<serde_json::Value>(stdout)
        .ok()?
        .get("id")?
        .as_str()
        .map(str::to_string)
}

/// The message for clones that failed, or `None` when they all succeeded.
///
/// The loop reported each failure and returned success, so
/// `azlin clone web --num-replicas 3` with three failures exited 0 having
/// created a snapshot that bills. Naming the snapshot matters: it is the
/// resource left behind, and nothing else in the output says it is still
/// there.
pub fn clone_failure_message(
    failed: &[String],
    total: u32,
    snapshot_name: &str,
    resource_group: &str,
) -> Option<String> {
    if failed.is_empty() {
        return None;
    }
    Some(format!(
        "{} of {} clone(s) failed: {}. Snapshot '{}' was created and is still billing; \
         delete it with `az snapshot delete --resource-group {} --name {}` if you are not \
         retrying.",
        failed.len(),
        total,
        failed.join(", "),
        snapshot_name,
        resource_group,
        snapshot_name
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sv(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn clone_names_are_one_based() {
        assert_eq!(clone_name("web", 0), "web-clone-1");
        assert_eq!(clone_name("web", 2), "web-clone-3");
    }

    // ── `--session-prefix` ───────────────────────────────────────────

    /// Without a prefix the clone's own name is the session, matching what a
    /// single `azlin new` does. Before, clones carried no session tag at all.
    #[test]
    fn without_a_prefix_the_clone_name_is_the_session() {
        assert_eq!(clone_session_tag(None, "web", 0, 3), "web-clone-1");
    }

    #[test]
    fn a_prefix_numbers_the_group() {
        assert_eq!(clone_session_tag(Some("canary"), "web", 0, 3), "canary-1");
        assert_eq!(clone_session_tag(Some("canary"), "web", 2, 3), "canary-3");
    }

    /// `-1` on a group of one is noise.
    #[test]
    fn a_single_clone_takes_the_prefix_unnumbered() {
        assert_eq!(clone_session_tag(Some("canary"), "web", 0, 1), "canary");
    }

    /// A blank prefix is not a prefix. `--session-prefix ""` would otherwise
    /// produce sessions called `-1`.
    #[test]
    fn a_blank_prefix_falls_back_to_the_clone_name() {
        assert_eq!(clone_session_tag(Some("   "), "web", 0, 2), "web-clone-1");
    }

    // ── argv shapes ──────────────────────────────────────────────────

    #[test]
    fn disk_args_are_verbatim_and_carry_the_location() {
        assert_eq!(
            build_clone_disk_args("rg", "web-clone-1_OsDisk", "snap", "westus2"),
            sv(&[
                "disk",
                "create",
                "--resource-group",
                "rg",
                "--name",
                "web-clone-1_OsDisk",
                "--source",
                "snap",
                "--location",
                "westus2",
                "--output",
                "json",
            ])
        );
    }

    /// The size is never omitted: leaving `--size` off is what made
    /// `--vm-size`'s documented default ("same as source") untrue, because
    /// `az` then picks its own.
    #[test]
    fn vm_args_always_carry_a_size() {
        let args = build_clone_vm_args(
            "rg",
            "web-clone-1",
            "web-clone-1_OsDisk",
            "westus2",
            "Standard_D8s_v5",
            "web-clone-1",
            false,
        );
        let i = args.iter().position(|a| a == "--size").expect("a --size");
        assert_eq!(args[i + 1], "Standard_D8s_v5");
    }

    /// The tag is one argv element. Splitting on the `=` makes it two
    /// malformed arguments and `az` rejects them.
    #[test]
    fn the_session_tag_is_a_single_argv_element() {
        let args = build_clone_vm_args(
            "rg",
            "web-clone-1",
            "disk",
            "westus2",
            "Standard_D2s_v5",
            "canary-1",
            false,
        );
        let i = args.iter().position(|a| a == "--tags").expect("--tags");
        assert_eq!(args[i + 1], "azlin-session=canary-1");
        assert_eq!(
            args.iter().filter(|a| a.contains("azlin-session")).count(),
            1
        );
    }

    /// A source with no public IP produces a clone with none. A clone that
    /// silently gained one would be a different security posture from the VM
    /// it was cloned from.
    #[test]
    fn a_bastion_source_produces_a_bastion_clone() {
        let args = build_clone_vm_args(
            "rg",
            "web-clone-1",
            "disk",
            "westus2",
            "Standard_D2s_v5",
            "s",
            true,
        );
        let i = args
            .iter()
            .position(|a| a == "--public-ip-address")
            .expect("--public-ip-address");
        assert_eq!(args[i + 1], "", "an empty value is how `az` is told 'none'");
        assert!(args.contains(&"azlin-bastion-westus2-vnet".to_string()));
        assert!(args.contains(&"default".to_string()));
    }

    #[test]
    fn a_public_source_produces_no_bastion_arguments() {
        let args = build_clone_vm_args(
            "rg",
            "web-clone-1",
            "disk",
            "westus2",
            "Standard_D2s_v5",
            "s",
            false,
        );
        assert!(!args.iter().any(|a| a == "--public-ip-address"));
        assert!(!args.iter().any(|a| a == "--vnet-name"));
    }

    /// The VNet follows the *target* region, not the source's. A clone sent
    /// elsewhere with `--region` must not be pointed at a VNet in the region
    /// it came from.
    #[test]
    fn the_bastion_vnet_follows_the_target_region() {
        let args = build_clone_vm_args(
            "rg",
            "web-clone-1",
            "disk",
            "eastus",
            "Standard_D2s_v5",
            "s",
            true,
        );
        assert!(args.contains(&"azlin-bastion-eastus-vnet".to_string()));
    }

    // ── cross-region ─────────────────────────────────────────────────

    #[test]
    fn a_same_region_clone_says_nothing() {
        assert_eq!(cross_region_note("westus2", "westus2"), None);
        // Azure region names are case-insensitive.
        assert_eq!(cross_region_note("WestUS2", "westus2"), None);
    }

    #[test]
    fn a_cross_region_clone_says_what_it_will_cost_and_what_may_fail() {
        let note = cross_region_note("westus2", "eastus").unwrap();
        assert!(note.contains("westus2"), "{note}");
        assert!(note.contains("eastus"), "{note}");
        assert!(note.contains("egress"), "{note}");
        // Azure does not support this for every disk type, and the refusal
        // arrives after the snapshot has been created and is billing.
        assert!(note.contains("billing"), "{note}");
    }

    // ── snapshot ─────────────────────────────────────────────────────

    /// `--incremental` is what makes a cross-region copy possible at all, and
    /// is not asked for otherwise: incremental snapshots bill and restore
    /// differently, so a same-region clone must not silently start producing
    /// them.
    #[test]
    fn incremental_is_asked_for_only_when_crossing_regions() {
        let same = build_snapshot_args("rg", "snap", "/disk/id", "westus2", false);
        assert!(!same.contains(&"--incremental".to_string()), "{same:?}");
        let cross = build_snapshot_args("rg", "snap", "/disk/id", "westus2", true);
        assert!(cross.contains(&"--incremental".to_string()), "{cross:?}");
        // Either way the snapshot lives with its source disk.
        for args in [same, cross] {
            let i = args.iter().position(|a| a == "--location").unwrap();
            assert_eq!(args[i + 1], "westus2");
        }
    }

    /// `az disk create --source` accepts a bare snapshot name only within one
    /// region. Falling back to the name would work in-region and fail across
    /// one, which is the harder failure to diagnose.
    #[test]
    fn the_snapshot_id_is_read_from_the_create_output() {
        let json = br#"{"id":"/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap","name":"snap"}"#;
        assert_eq!(
            snapshot_id_from_create(json).as_deref(),
            Some("/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/snapshots/snap")
        );
        assert_eq!(snapshot_id_from_create(b"not json"), None);
        assert_eq!(snapshot_id_from_create(br#"{"name":"snap"}"#), None);
    }

    // ── failures ─────────────────────────────────────────────────────

    #[test]
    fn all_clones_succeeding_reports_nothing() {
        assert_eq!(clone_failure_message(&[], 3, "snap", "rg"), None);
    }

    /// The loop used to report each failure and return success, so three
    /// failed clones exited 0 having created a snapshot that bills.
    #[test]
    fn failed_clones_name_the_snapshot_left_behind() {
        let msg = clone_failure_message(
            &["web-clone-1".to_string(), "web-clone-3".to_string()],
            3,
            "web_clone_snap_1",
            "rg",
        )
        .unwrap();
        assert!(msg.starts_with("2 of 3"), "{msg}");
        assert!(msg.contains("web-clone-1, web-clone-3"), "{msg}");
        assert!(msg.contains("still billing"), "{msg}");
        assert!(msg.contains("az snapshot delete"), "{msg}");
    }
}
