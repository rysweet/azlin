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
         will report the pool as enabled with fewer runners than requested.",
        failed.len(),
        total,
        pool,
        failed.join(", "),
        pool
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
    }

    #[test]
    fn the_egress_note_says_where_outbound_goes() {
        let note = egress_note("westus2");
        assert!(note.contains("without a public IP"), "{}", note);
        assert!(note.contains("NAT gateway"), "{}", note);
        assert!(note.contains("westus2"), "{}", note);
    }
}
