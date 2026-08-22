//! The three properties the one-sweep collector has to keep, and that a merge
//! is most likely to take away.
//!
//! `collect_health_and_storage` was written on a branch cut before three
//! sibling fixes landed on main: the routing precondition guard (#1132), the
//! caller-lent bastion map (#1142), and the `enrichment.health` gate. Landing
//! it conflicted in exactly those three places, and in every one of them the
//! incoming side was the older, weaker behaviour. Taking it would have
//! compiled, would have passed every test that existed, and would have
//! silently reverted three fixes.
//!
//! Nothing pinned any of the three. That is the whole reason they were
//! losable. These tests are the pin.

use crate::{collect_health_metrics_with, RoutedExec};

/// One file of this crate's source.
///
/// Two of the properties below are statements about what the code does *not*
/// do -- ask Azure a question it was lent the answer to, or restate a
/// threshold that is already computed elsewhere. Neither is observable without
/// a network and a subscription, and a property that can only be checked by
/// reading the code is still worth checking mechanically: the alternative is
/// trusting whoever resolves this conflict next to recognise what they are
/// looking at, which is precisely what failed.
fn source(file: &str) -> String {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("src")
        .join(file);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
}

/// The body of a top-level `fn`, from its signature to the closing brace in
/// column zero.
///
/// The signature is matched at the start of a line, so a doc comment or a call
/// site that happens to quote it cannot be mistaken for the definition -- both
/// of these functions are named in prose elsewhere in their own file.
fn function_body(file: &str, signature: &str) -> String {
    let text = source(file);
    let anchored = format!("\n{signature}");
    let start = text
        .find(&anchored)
        .unwrap_or_else(|| panic!("{file} no longer defines `{signature}`"))
        + 1;
    let rest = &text[start..];
    let end = rest
        .find("\n}\n")
        .unwrap_or_else(|| panic!("no closing brace for `{signature}` in {file}"));
    rest[..end].to_string()
}

// ---------------------------------------------------------------------------
// Routing precondition (#1132)
// ---------------------------------------------------------------------------

#[test]
fn a_route_with_neither_a_tunnel_nor_an_address_is_unroutable() {
    // The exact case the guard exists for. Without it the direct branch
    // flattens the address with `unwrap_or_default()` and runs `ssh user@`:
    // a guaranteed transport failure, recorded as this VM's health.
    assert!(RoutedExec::new("", "azureuser", None).is_unroutable());
}

#[test]
fn an_address_alone_is_enough_to_be_routable() {
    assert!(!RoutedExec::new("10.0.0.4", "azureuser", None).is_unroutable());
    assert!(!RoutedExec::new("fd00::4", "azureuser", None).is_unroutable());
}

#[test]
fn a_tunnel_alone_is_enough_to_be_routable() {
    // A bastion-only VM with no private IP recorded is reachable through its
    // tunnel. Treating "no address" as "unroutable" is the older bug.
    let bastion = Some((
        "bastion-eastus",
        "rg-a",
        "/subscriptions/s/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/web-01",
        None,
    ));
    assert!(!RoutedExec::new("", "azureuser", bastion).is_unroutable());
}

#[test]
fn the_guard_is_on_the_entry_point_the_sweep_actually_calls() {
    // `collect_health_metrics` delegates to `collect_health_metrics_with`, so
    // a guard placed only on the former leaves the shared-executor path -- the
    // newer one, and the one the fleet sweep uses -- unguarded. Placement is
    // the whole of this fix; the predicate above is the easy half.
    let body = function_body("main.rs", "pub(crate) fn collect_health_metrics_with(");
    assert!(
        body.contains("is_unroutable()"),
        "the routing precondition is not checked on the shared-executor path:\n{body}"
    );
}

#[test]
fn a_stopped_vm_is_not_probed_at_all() {
    // Unrelated to routing, and the one early return that is observable
    // without a network: it must keep coming first.
    let metrics = collect_health_metrics_with(
        &RoutedExec::new("10.0.0.4", "azureuser", None),
        "web-01",
        "VM deallocated",
    );
    assert_eq!(metrics.vm_name, "web-01");
    assert_eq!(metrics.power_state, "VM deallocated");
    assert_eq!(metrics.cpu_percent, None);
    assert_eq!(metrics.mem_percent, None);
    assert_eq!(metrics.disk_percent, None);
    assert_eq!(metrics.error_count, None);
}

// ---------------------------------------------------------------------------
// Caller-lent bastion routing (#1142)
// ---------------------------------------------------------------------------

#[test]
fn the_sweep_is_lent_its_bastion_map_and_never_rediscovers_one() {
    // The sweep exists to stop paying `az network bastion list` per resource
    // group. Rediscovering inside it reinstates that cost in the one function
    // written to remove it -- and discards the lookup warnings, which main
    // hands back to the caller to print, so a failed lookup would have
    // nowhere left to report itself.
    let body = function_body(
        "cmd_list_data.rs",
        "pub(crate) fn collect_health_and_storage(",
    );
    assert!(
        body.contains("bastion_map: &BastionMap"),
        "the sweep no longer takes a lent bastion map:\n{body}"
    );
    assert!(
        !body.contains("discover_bastions"),
        "the sweep rediscovers bastion routing it was lent:\n{body}"
    );
}

// ---------------------------------------------------------------------------
// The subscription gate
// ---------------------------------------------------------------------------

#[test]
fn the_sweep_takes_the_shared_enrichment_gate_and_not_a_second_copy_of_it() {
    // Health, tmux, procs and storage are all subscription-scoped: each probes
    // through an ARM id built from the queried subscription. `enrichment.health`
    // already means "health was asked for and this listing can attribute it".
    // Restating that threshold as `with_health && !cross_subscription` is
    // exactly how `--show-procs` drifted out of sync with its own note.
    //
    // Only the condition is read. Slicing to the end of the enclosing function
    // would drag in the whole of `dispatch` and report it on failure.
    const BINDING: &str = "let (health_data, storage_data) = if ";
    let text = source("cmd_list.rs");
    let start = text
        .find(BINDING)
        .unwrap_or_else(|| panic!("cmd_list.rs no longer binds the sweep's two maps together"))
        + BINDING.len();
    let rest = &text[start..];
    let condition = rest[..rest
        .find('{')
        .unwrap_or_else(|| panic!("no block after `{BINDING}`"))]
        .trim();

    assert_eq!(
        condition, "enrichment.health",
        "the health/storage sweep is gated on a second copy of the threshold"
    );
}
