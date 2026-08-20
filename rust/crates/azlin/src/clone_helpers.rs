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

/// Warn when a clone is being sent to a different region than its source.
///
/// Returns `None` when the regions match. A cross-region clone copies the
/// snapshot across regions, which costs egress and can fail on snapshot types
/// Azure will not copy — worth saying before it runs rather than explaining
/// afterwards.
pub fn cross_region_note(source_location: &str, target_location: &str) -> Option<String> {
    if source_location.eq_ignore_ascii_case(target_location) {
        return None;
    }
    Some(format!(
        "Cloning from {} into {}: the snapshot is copied across regions, which incurs \
         egress and is not supported for every snapshot type.",
        source_location, target_location
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
    fn a_cross_region_clone_says_what_it_will_cost() {
        let note = cross_region_note("westus2", "eastus").unwrap();
        assert!(note.contains("westus2"), "{note}");
        assert!(note.contains("eastus"), "{note}");
        assert!(note.contains("egress"), "{note}");
    }
}
