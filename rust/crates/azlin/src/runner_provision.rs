//! Where `azlin github-runner enable`'s VMs come from.
//!
//! The handler hand-rolled its own `az vm create` argv, which meant it
//! inherited Azure's defaults — and Azure's default is a **public IP**. Every
//! runner the command has ever created is exposed to the internet, and the
//! command reported `Provisioned VM 'azlin-runner-ci-1'` without mentioning it
//! (#1123).
//!
//! Every other creation path in this repository is explicit about that and
//! defaults the other way: `VmManager::create_vm` disables the public IP and
//! joins the bastion VNet unless asked otherwise, and `clone_helpers` and
//! `bastion_helpers` do the same. The fix is not to add a flag to the
//! hand-rolled argv — it is to stop hand-rolling it, so this path inherits
//! every correction the shared one gets.
//!
//! A runner still needs *outbound* connectivity to reach github.com, which a
//! bastion does not provide: a bastion is inbound only. That is what the NAT
//! gateway is for, and why enabling a pool now ensures both.

use std::collections::HashMap;

/// One runner VM's name in a pool.
///
/// Unchanged from the hand-rolled version — existing pools must keep resolving
/// to the same VMs, or `github-runner disable` stops finding them.
pub fn runner_vm_name(pool: &str, index: u32) -> String {
    format!("azlin-runner-{}-{}", pool, index + 1)
}

/// The tags a runner VM carries, so `disable` and `status` can find it.
///
/// The hand-rolled argv passed these as one space-separated `--tags` string.
/// Structured here because `CreateVmParams` takes a map, and because a repo
/// name containing a space silently produced two tags before.
pub fn runner_tags(pool: &str, repo: &str) -> HashMap<String, String> {
    let mut tags = HashMap::new();
    tags.insert("azlin-runner".to_string(), "true".to_string());
    tags.insert("pool".to_string(), pool.to_string());
    tags.insert("repo".to_string(), repo.to_string());
    tags
}

/// The image runner VMs are created from.
///
/// The hand-rolled argv passed `--image Ubuntu2204`. Going through the shared
/// creation path made it tempting to take `VmImage::default()`, which is now
/// 26.04 — a four-release jump on a machine that runs CI, applied silently to
/// any pool that gets re-enabled. This command has no `--image` flag, so the
/// user has no way to ask for either; preserving what the command has always
/// created is the only choice that surprises nobody.
pub fn runner_image() -> Result<azlin_core::models::VmImage, String> {
    azlin_core::models::VmImage::from_image_spec("22.04-lts")
}

/// Refuse to re-enable a pool into a different region than the one it lives in.
///
/// The region is new here — the old code had none — and it is read from
/// `default_region` at enable time. Change that default, re-run `enable` for an
/// existing pool, and the second run creates VMs with the same names in a
/// different region of the same resource group: a name collision at best, two
/// half-pools at worst, with the TOML file recording whichever ran last.
pub fn region_conflict(recorded: Option<&str>, requested: &str, pool: &str) -> Option<String> {
    let recorded = recorded?;
    if recorded.eq_ignore_ascii_case(requested.trim()) {
        return None;
    }
    Some(format!(
        "Pool '{}' already exists in region '{}', and this run would create runners in '{}'. \
         Two regions cannot share one pool: the VM names would collide. Run \
         `azlin github-runner disable {}` first, or set default_region back to '{}'.",
        pool, recorded, requested, pool, recorded
    ))
}

/// What to say when some runners in a pool did not come up.
///
/// The loop used to print each failure and return `Ok(())`, so
/// `azlin github-runner enable --count 5` with five failures exited 0 — the
/// same shape fixed in #1105, #1110 and #1118. Returns `None` when every VM
/// came up.
pub fn runner_failure_message(failed: &[String], total: u32, pool: &str) -> Option<String> {
    if failed.is_empty() {
        return None;
    }
    Some(format!(
        "{} of {} runner VM(s) in pool '{}' could not be provisioned: {}. \
         The pool configuration was still written, so `azlin github-runner status {}` \
         will report the pool as enabled with fewer runners than requested. Re-running \
         `azlin github-runner enable` for this pool is safe: the runners that came up are \
         left alone, and the bastion and NAT gateway are only created if missing.",
        failed.len(),
        total,
        pool,
        failed.join(", "),
        pool
    ))
}

/// What to ask before creating regional infrastructure for a runner pool.
///
/// `azlin new` asks before creating a bastion or a NAT gateway, because both
/// carry a monthly bill. Enabling a pool went straight to creating them: the
/// ensure functions were reused and the gate around them was left behind in
/// `cmd_vm_ops`. This command is not interactive, which is a reason it cannot
/// prompt casually — not a reason it may provision without consent.
///
/// Returns `None` when both already exist, so a second pool in a region that
/// is already set up asks nothing.
pub fn confirm_infrastructure_prompt(
    region: &str,
    needs_bastion: bool,
    needs_nat: bool,
) -> Option<String> {
    let what = match (needs_bastion, needs_nat) {
        (true, true) => "a bastion host and a NAT gateway",
        (true, false) => "a bastion host",
        (false, true) => "a NAT gateway",
        (false, false) => return None,
    };
    Some(format!(
        "Runner pools need private VMs with outbound access, which requires {} in {}. \
         Both are billed monthly for as long as they exist, and are shared with every other \
         azlin VM in that region. Create {}?",
        what, region, what
    ))
}

/// What to tell the user before provisioning starts.
///
/// Says the thing the old output never did: these VMs have no public IP, and
/// they reach the internet through the region's NAT gateway.
pub fn egress_note(region: &str) -> String {
    format!(
        "Runners are created without a public IP, on the bastion VNet in {}. \
         Outbound access (github.com, package registries) goes through the region's \
         NAT gateway, which is provisioned if it is missing.",
        region
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vm_names_are_unchanged_so_existing_pools_still_resolve() {
        // `github-runner disable` finds VMs by this name. Changing the scheme
        // would strand every pool created before this change.
        assert_eq!(runner_vm_name("ci", 0), "azlin-runner-ci-1");
        assert_eq!(runner_vm_name("ci", 4), "azlin-runner-ci-5");
    }

    #[test]
    fn tags_are_structured_so_a_repo_name_with_a_space_stays_one_tag() {
        let tags = runner_tags("ci", "my org/my repo");
        assert_eq!(tags.get("azlin-runner").map(String::as_str), Some("true"));
        assert_eq!(tags.get("pool").map(String::as_str), Some("ci"));
        assert_eq!(
            tags.get("repo").map(String::as_str),
            Some("my org/my repo"),
            "the old space-separated --tags string split this into two tags"
        );
        assert_eq!(tags.len(), 3);
    }

    #[test]
    fn the_image_is_the_one_this_command_has_always_created() {
        // Not `VmImage::default()`: that is 26.04 now, and a pool re-enabled
        // after this change would come back four releases newer without
        // anything saying so.
        let image = runner_image().unwrap();
        assert_eq!(image.offer, "ubuntu-22_04-lts", "{}", image);
        assert_eq!(image.publisher, "Canonical");
    }

    #[test]
    fn re_enabling_a_pool_in_a_different_region_is_refused() {
        assert_eq!(region_conflict(None, "westus2", "ci"), None);
        assert_eq!(region_conflict(Some("westus2"), "westus2", "ci"), None);
        assert_eq!(region_conflict(Some("westus2"), "  WestUS2 ", "ci"), None);

        let msg = region_conflict(Some("westus2"), "eastus", "ci").unwrap();
        assert!(msg.contains("westus2") && msg.contains("eastus"), "{}", msg);
        assert!(msg.contains("names would collide"), "{}", msg);
        assert!(
            msg.contains("disable ci"),
            "the way out must be in the message: {}",
            msg
        );
    }

    #[test]
    fn every_runner_coming_up_reports_nothing() {
        assert_eq!(runner_failure_message(&[], 3, "ci"), None);
    }

    #[test]
    fn failed_runners_are_named_and_the_half_pool_is_admitted() {
        let msg = runner_failure_message(&["azlin-runner-ci-2".to_string()], 3, "ci").unwrap();
        assert!(msg.contains("1 of 3"), "{}", msg);
        assert!(msg.contains("azlin-runner-ci-2"), "{}", msg);
        assert!(
            msg.contains("fewer runners than requested"),
            "the config file was still written, and status will disagree: {}",
            msg
        );
        assert!(
            msg.contains("Re-running") && msg.contains("is safe"),
            "a command that provisions infrastructure must say whether re-running doubles it: {}",
            msg
        );
    }

    #[test]
    fn nothing_is_asked_when_the_region_is_already_set_up() {
        assert_eq!(confirm_infrastructure_prompt("westus2", false, false), None);
    }

    #[test]
    fn the_prompt_names_what_will_be_created_and_that_it_is_billed() {
        let both = confirm_infrastructure_prompt("westus2", true, true).unwrap();
        assert!(both.contains("bastion host and a NAT gateway"), "{}", both);
        assert!(both.contains("billed monthly"), "{}", both);
        assert!(both.contains("westus2"), "{}", both);

        // Only the missing half is offered, so a region with a bastion and no
        // gateway does not read as though both are about to be created.
        let nat_only = confirm_infrastructure_prompt("westus2", false, true).unwrap();
        assert!(nat_only.contains("a NAT gateway"), "{}", nat_only);
        assert!(!nat_only.contains("bastion"), "{}", nat_only);
    }

    #[test]
    fn the_egress_note_says_where_outbound_goes() {
        let note = egress_note("westus2");
        assert!(note.contains("without a public IP"), "{}", note);
        assert!(note.contains("NAT gateway"), "{}", note);
        assert!(note.contains("westus2"), "{}", note);
    }
}
