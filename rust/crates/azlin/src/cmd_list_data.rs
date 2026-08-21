//! Data collection helpers for the list command (tmux, latency, health, procs).

use super::*;
use azlin_core::models::VmInfo;
use std::collections::HashMap;

/// Maximum number of tmux sessions to restore per VM to prevent resource exhaustion.
pub(crate) const MAX_SESSIONS_PER_VM: usize = 20;

/// Resolve SSH key path from the shared azlin private-key priority list.
fn resolve_ssh_key() -> Option<std::path::PathBuf> {
    let ssh_dir = dirs::home_dir()?.join(".ssh");
    crate::key_helpers::find_preferred_private_key(&ssh_dir)
}

/// The ssh options every probe in this module shares: connect timeout, batch
/// mode, and the identity file when there is one.
///
/// Route-specific options stay at the call site — direct probes add
/// `StrictHostKeyChecking=accept-new`, bastion probes add
/// [`crate::bastion_tunnel::bastion_loopback_ssh_opts`] and `-p <port>` — but
/// three call sites had each spelled this common tail by hand, and each spelled
/// the identity fallback `key.to_str().unwrap_or("")`. That hands ssh an empty
/// `-i` argument rather than omitting the flag, so a key path that is not valid
/// UTF-8 makes ssh fail on a missing identity file and the probe reports the VM
/// as unreachable. Omitting `-i` is the honest degradation: it is exactly the
/// state `resolve_ssh_key` returning `None` already produces.
fn probe_ssh_opts(connect_timeout: u64, ssh_key: Option<&std::path::Path>) -> Vec<String> {
    let mut opts = vec![
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
    ];
    if let Some(key) = ssh_key.and_then(|k| k.to_str()) {
        opts.push("-i".to_string());
        opts.push(key.to_string());
    }
    opts
}

/// Result of resolving a bare identifier against known tmux session names
/// across all running VMs in a resource group.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum SessionLookup {
    /// Exactly one running VM has a tmux session with this name.
    Found { vm_name: String },
    /// No running VM has a tmux session with this name.
    NotFound,
    /// More than one running VM has a tmux session with this name; caller
    /// should ask the user to disambiguate with `vm:session` notation.
    Ambiguous { vm_names: Vec<String> },
}

/// Search all running VMs in `rg` for a tmux session named `session_name`.
///
/// Used by `azlin connect <name>` to fall back to session-name resolution
/// when `<name>` does not match any VM hostname: if exactly one running VM
/// has a matching tmux session, callers can connect to `vm_name:session_name`.
pub(crate) async fn find_vm_by_tmux_session(
    vms: &[VmInfo],
    subscription_id: &str,
    connect_timeout: u64,
    session_name: &str,
    verbose: bool,
) -> SessionLookup {
    // Bastion routing is discovered from the VM list, so no output-format flag
    // is required. This caller runs one collector, so it owns the map for the
    // length of that one call.
    let bastion_map = discover_bastions_async(vms).await;
    let tmux_sessions =
        collect_tmux_sessions(vms, &bastion_map, verbose, subscription_id, connect_timeout).await;
    match_session_in_map(&tmux_sessions, session_name)
}

/// Pure matching logic for [`find_vm_by_tmux_session`], split out so it can
/// be unit tested without spawning real SSH/az processes.
pub(crate) fn match_session_in_map(
    tmux_sessions: &HashMap<String, Vec<String>>,
    session_name: &str,
) -> SessionLookup {
    let mut matches: Vec<String> = Vec::new();
    for (vm_name, sessions) in tmux_sessions {
        let has_match = sessions
            .iter()
            .any(|raw| parse_session_name(raw).as_deref() == Some(session_name));
        if has_match {
            matches.push(vm_name.clone());
        }
    }
    matches.sort();

    match matches.len() {
        0 => SessionLookup::NotFound,
        1 => SessionLookup::Found {
            vm_name: matches.remove(0),
        },
        _ => SessionLookup::Ambiguous { vm_names: matches },
    }
}

/// A bastion is scoped to a resource group *and* a region, so a VM may only be
/// tunnelled through a bastion that shares both. Keying discovery by region
/// alone would let a VM in `rg-b` be routed through a bastion that only exists
/// in `rg-a`, where the tunnel open would fail (or, worse, succeed against a
/// peered network the operator did not intend).
pub(crate) type BastionMap = HashMap<(String, String), String>;

/// Upper bound on bastion tunnels opened for a single listing.
///
/// Each tunnel is a sequential Azure round trip plus a long-lived local
/// listener, so a very wide listing would otherwise stall for minutes and leak
/// file descriptors. VMs beyond the cap are *counted*, never silently dropped —
/// see [`PlannedTunnels::skipped`].
pub(crate) const MAX_BASTION_TUNNELS_PER_RUN: usize = 32;

/// Upper bound on a single piece of text read off a remote host before it is
/// handed to the renderer.
pub(crate) const MAX_REMOTE_TEXT_LEN: usize = 512;

/// Build the ARM resource id for a VM.
///
/// Every id in this module goes through here so the id a tunnel is *opened*
/// against cannot drift from the id used to look its port back up, nor from
/// the key the tunnel registry stores under.
pub(crate) fn build_vm_resource_id(
    subscription_id: &str,
    resource_group: &str,
    name: &str,
) -> String {
    format!(
        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
        subscription_id, resource_group, name
    )
}

/// The `BastionMap` key for a (resource group, region) pair.
///
/// The two sides of this map come from two different `az` commands: the entry
/// is inserted with the *bastion's* location as `az network bastion list`
/// reports it, and looked up with the *VM's* location as the VM listing
/// reports it. Azure resource group names are case-insensitive and region
/// names are returned in more than one casing, so comparing the raw strings
/// makes a bastion vanish from the map on a casing difference alone — and a
/// VM with no bastion in the map silently reports zero sessions, which is the
/// #1127 symptom arriving through the key instead of through the port.
pub(crate) fn bastion_key(resource_group: &str, location: &str) -> (String, String) {
    (
        resource_group.to_ascii_lowercase(),
        location.to_ascii_lowercase(),
    )
}

/// One bastion tunnel that must be opened before the tmux probes can run.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BastionTunnelPlan {
    pub vm_name: String,
    pub bastion_name: String,
    pub resource_group: String,
    pub vm_resource_id: String,
}

/// The outcome of [`plan_bastion_tunnels`]: the tunnels to open, plus how many
/// VMs were left out by [`MAX_BASTION_TUNNELS_PER_RUN`] so the caller can say
/// so rather than quietly returning a short list.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct PlannedTunnels {
    pub plans: Vec<BastionTunnelPlan>,
    pub skipped: usize,
}

/// Decide which bastion tunnels the probes need — one per bastion-only VM.
///
/// A bastion tunnel is bound to ONE target VM: it is opened against that VM's
/// resource id. An earlier version opened a single tunnel per *bastion* and
/// shared its port across every VM in that region, so all probes landed on
/// whichever VM was reached first and the rest reported zero tmux sessions
/// even when they had some (#1127).
///
/// Deduplication is by resource id, not by name: Azure permits the same VM
/// name in two resource groups of one subscription, and those are two
/// different VMs needing two different tunnels.
pub(crate) fn plan_bastion_tunnels(
    vms: &[VmInfo],
    bastion_map: &BastionMap,
    subscription_id: &str,
) -> PlannedTunnels {
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut plans = Vec::new();
    let mut skipped = 0usize;

    for vm in vms {
        let ProbeRoute::Bastion { target, .. } = probe_route(vm, bastion_map, subscription_id)
        else {
            continue;
        };
        if !seen.insert(target.vm_resource_id.clone()) {
            continue; // The same VM must not get two tunnels.
        }
        if plans.len() >= MAX_BASTION_TUNNELS_PER_RUN {
            skipped += 1;
            continue;
        }
        plans.push(target);
    }

    PlannedTunnels { plans, skipped }
}

/// Which resource groups need an `az network bastion list` call.
///
/// Discovery used to run against a single resource group — the one passed on
/// the command line — so a listing that spanned resource groups skipped the
/// bastions of every other one. That is the same first-one-wins defect as
/// #1127, one call frame higher. Returns a deduplicated, sorted list so the
/// number of `az` calls is bounded by the resource groups that actually have a
/// bastion-only VM, and is zero when nothing is private.
pub(crate) fn resource_groups_needing_bastion_lookup(vms: &[VmInfo]) -> Vec<String> {
    let mut rgs: Vec<String> = vms
        .iter()
        .filter(|vm| {
            vm.power_state == azlin_core::models::PowerState::Running && vm.public_ip.is_none()
        })
        .map(|vm| vm.resource_group.clone())
        .collect();
    rgs.sort();
    rgs.dedup();
    rgs
}

/// Every resource group the listing covers, deduplicated and sorted.
///
/// The "Azure Bastion Hosts" table used to be built from
/// `all_vms.first()`'s resource group, so a listing spanning resource groups
/// displayed only the bastions of whichever VM happened to sort first and
/// silently omitted the rest — the same first-one-wins omission as #1127,
/// in the display path rather than the routing path.
///
/// Unlike [`resource_groups_needing_bastion_lookup`] this is not filtered by
/// power state or public IP: the table documents the bastions in the scope the
/// user asked about, which does not depend on whether a VM happens to be
/// running right now.
pub(crate) fn resource_groups_in_listing(vms: &[VmInfo]) -> Vec<String> {
    let mut rgs: Vec<String> = vms
        .iter()
        .filter(|vm| !vm.resource_group.is_empty())
        .map(|vm| vm.resource_group.clone())
        .collect();
    rgs.sort();
    rgs.dedup();
    rgs
}

/// Whether a bastion name/location pair read back from `az` is safe to use.
///
/// These strings come from outside the process and go straight into an
/// argument vector, so a name beginning with `-` would be parsed as a flag.
pub(crate) fn valid_bastion_coordinates(name: &str, location: &str) -> bool {
    !name.is_empty()
        && !location.is_empty()
        && !name.starts_with('-')
        && !location.starts_with('-')
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
        && location.chars().all(|c| c.is_ascii_alphanumeric())
}

/// Discover bastions for every resource group that has a bastion-only VM.
///
/// Blocking `az` calls: one `az network bastion list` per resource group that
/// needs routing. Private on purpose — [`discover_bastions_async`] is the only
/// stud this module offers, because every caller in the crate is async and
/// calling this one directly from a runtime thread would stall the concurrent
/// SSH probes `collect_tmux_sessions` spawns in its `JoinSet`. An exported
/// blocking twin would be an invitation to exactly that mistake.
///
/// The result belongs to the *caller*, not to each collector. Discovery is a
/// pure function of `vms`, and a single `azlin vm list --with-health
/// --show-procs` runs three collectors over one VM list: when each discovered
/// routing for itself the command spent three `az` invocations per resource
/// group to compute the same map three times, and the operator watched three
/// spinners re-derive one answer. Every collector now borrows a map the caller
/// discovered once.
fn discover_bastions(vms: &[VmInfo]) -> BastionMap {
    let mut map = BastionMap::new();
    for rg in resource_groups_needing_bastion_lookup(vms) {
        let found = match crate::list_helpers::detect_bastion_hosts(&rg) {
            Ok(found) => found,
            // Swallowing this reproduces the very bug this module was fixed
            // for: with no bastion in the map every bastion-only VM in `rg`
            // falls back to its own private IP, which the operator usually
            // cannot route to, and reports zero sessions as if it had none.
            Err(e) => {
                eprintln!("{}", bastion_lookup_failure_warning(&rg, &e.to_string()));
                continue;
            }
        };
        for warning in insert_bastions_for_group(&mut map, &rg, found) {
            eprintln!("{}", warning);
        }
    }
    map
}

/// [`discover_bastions`] for async callers, run off the runtime.
///
/// The single entry point for anyone holding a VM list and about to run one or
/// more collectors over it. It exists so that hoisting discovery out of the
/// collectors did not leave three callers each hand-rolling the same
/// `spawn_blocking` and the same failure message.
pub(crate) async fn discover_bastions_async(vms: &[VmInfo]) -> BastionMap {
    let owned: Vec<VmInfo> = vms.to_vec();
    match tokio::task::spawn_blocking(move || discover_bastions(&owned)).await {
        Ok(map) => map,
        // An empty map here is not "no bastions exist" — it is "we never found
        // out". Every bastion-only VM would report zero sessions with nothing
        // on screen to distinguish that from genuinely having none.
        Err(e) => {
            eprintln!(
                "Warning: bastion discovery did not complete ({}); VMs reachable only \
                 through a bastion will show no tmux sessions, health or process data.",
                e
            );
            BastionMap::new()
        }
    }
}

/// Fold one resource group's `az network bastion list` result into `map`,
/// returning any warnings the caller should print.
///
/// Split out of [`discover_bastions`] so the selection rule is testable
/// without `az`: the rule is the whole point, and an untested tie-break is how
/// #1127 shipped in the first place.
///
/// A resource group may hold several virtual networks and therefore several
/// bastions in one region. A plain `insert` lets whichever bastion `az` listed
/// last win silently, so the route a VM gets depends on Azure's listing order
/// — and a bastion that cannot see the VM yields an empty row that reads as
/// "nothing to report". The first entry wins deterministically instead, and
/// the one that was passed over is named.
pub(crate) fn insert_bastions_for_group(
    map: &mut BastionMap,
    resource_group: &str,
    found: Vec<(String, String, String)>,
) -> Vec<String> {
    let mut warnings = Vec::new();
    for (name, location, _sku) in found {
        if !valid_bastion_coordinates(&name, &location) {
            continue;
        }
        match map.entry(bastion_key(resource_group, &location)) {
            std::collections::hash_map::Entry::Vacant(slot) => {
                slot.insert(name);
            }
            std::collections::hash_map::Entry::Occupied(slot) => {
                if slot.get() != &name {
                    // `valid_bastion_coordinates` already allowlists `name` and
                    // `location`, but the resource group reaches here straight
                    // from the caller having passed no validator at all, and a
                    // warning is not a safer place to print an escape sequence
                    // than a table cell is. Sanitizing all four keeps that rule
                    // true of this line without depending on which argument
                    // happens to have been checked upstream.
                    let (rg, loc) = (
                        sanitize_remote_text(resource_group),
                        sanitize_remote_text(&location),
                    );
                    let (kept, ignored) = (
                        sanitize_remote_text(slot.get()),
                        sanitize_remote_text(&name),
                    );
                    warnings.push(format!(
                        "Warning: resource group {} has more than one bastion in {}; using {} \
                         and ignoring {}. VMs reachable only through {} will show no tmux, \
                         health or process data.",
                        rg, loc, kept, ignored, ignored
                    ));
                }
            }
        }
    }
    warnings
}

/// How a VM should be reached for an SSH probe.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ProbeRoute {
    /// Reachable at this address without a tunnel.
    Direct { host: String },
    /// Bastion-only: open `target`'s tunnel. `fallback_host` is the VM's
    /// private IP when it has one, which may still be routable for an operator
    /// on a VPN or peered network if the tunnel cannot be opened.
    Bastion {
        target: BastionTunnelPlan,
        fallback_host: Option<String>,
    },
    /// Not running, or no address and no bastion.
    Unreachable,
}

/// Decide how to reach `vm` for an SSH probe.
///
/// The single routing decision shared by every collector in this module.
/// `collect_procs` used to inline `public_ip.or(private_ip)`, which SSH'd a
/// bastion-only VM at its own private IP — unroutable from the operator's
/// machine — so the VM silently reported no processes at all: the same
/// user-visible defect class as #1127.
pub(crate) fn probe_route(
    vm: &VmInfo,
    bastion_map: &BastionMap,
    subscription_id: &str,
) -> ProbeRoute {
    if vm.power_state != azlin_core::models::PowerState::Running {
        return ProbeRoute::Unreachable;
    }
    if let Some(ip) = vm.public_ip.as_deref() {
        // A reachable public IP is never routed through a bastion.
        return ProbeRoute::Direct {
            host: ip.to_string(),
        };
    }
    let key = bastion_key(&vm.resource_group, &vm.location);
    if let Some(bastion_name) = bastion_map.get(&key) {
        return ProbeRoute::Bastion {
            target: BastionTunnelPlan {
                vm_name: vm.name.clone(),
                bastion_name: bastion_name.clone(),
                resource_group: vm.resource_group.clone(),
                vm_resource_id: build_vm_resource_id(subscription_id, &vm.resource_group, &vm.name),
            },
            fallback_host: vm.private_ip.clone(),
        };
    }
    // No bastion for this VM: the private IP may still be routable over a VPN
    // or peering, so keep trying it rather than declaring the VM unreachable.
    match vm.private_ip.as_deref() {
        Some(ip) => ProbeRoute::Direct {
            host: ip.to_string(),
        },
        None => ProbeRoute::Unreachable,
    }
}

/// The directly routable address to retry at when a bastion attempt fails.
///
/// `ProbeRoute::Bastion::fallback_host` documents this degradation path, but
/// until now no collector read the field: a bastion transport failure dropped
/// the VM outright. That is strictly less available than the code this routing
/// replaced, which SSH'd the private IP directly and succeeds for an operator
/// on a VPN or peered network.
///
/// Empty and whitespace-only strings are rejected because the health collector
/// flattens `Option<String>` with `unwrap_or_default()`, so "no address" and
/// `""` arrive here as the same thing; `ssh user@` is not a probe.
pub(crate) fn direct_fallback_host(fallback_host: Option<&str>) -> Option<&str> {
    fallback_host.filter(|h| !h.trim().is_empty())
}

/// The address to time for the Latency column, or `None`.
///
/// Deliberately never a tunnel: timing a bastion tunnel measures the tunnel
/// and the local listener, not the host, which would silently change what the
/// column means. A VM with no directly routable address is omitted instead.
pub(crate) fn latency_probe_host(vm: &VmInfo) -> Option<String> {
    if vm.power_state != azlin_core::models::PowerState::Running {
        return None;
    }
    vm.public_ip
        .as_deref()
        .or(vm.private_ip.as_deref())
        .map(|s| s.to_string())
}

/// The warning printed when a resource group's bastion lookup fails.
///
/// Without a bastion in the map every bastion-only VM in that resource group
/// silently degrades to its private IP and reports nothing, which is
/// indistinguishable from having nothing to report.
///
/// Both interpolations are sanitized. The resource group name is chosen by
/// whoever created it, and `az` quotes the names it was given back into its own
/// error text, so an escape sequence in either reaches the terminal through a
/// message the operator has no reason to distrust. Taking the first line alone
/// stops a fabricated *second* warning; it does nothing about a cursor-movement
/// sequence rewriting the one line we do print.
pub(crate) fn bastion_lookup_failure_warning(resource_group: &str, error: &str) -> String {
    let first_line = error.lines().next().unwrap_or("").trim();
    format!(
        "Warning: could not list bastion hosts in resource group {}: {}. \
         VMs there that are only reachable through a bastion will show no tmux, \
         health or process data.",
        sanitize_remote_text(resource_group),
        sanitize_remote_text(first_line)
    )
}

/// The warning printed when a bastion tunnel cannot be opened.
///
/// A failed tunnel drops the VM from the results entirely, which is
/// indistinguishable from "this VM has no sessions" unless we say so — and
/// saying so only under `--verbose` means the default path degrades silently.
/// It goes to stderr, so JSON and CSV consumers are unaffected.
/// The VM name, the bastion name and the error text are all sanitized: the
/// first two are Azure resource names an operator (or anyone with write access
/// to the subscription) chooses, and the third routinely quotes them back.
pub(crate) fn tunnel_failure_warning(vm_name: &str, bastion_name: &str, error: &str) -> String {
    let first_line = error.lines().next().unwrap_or("").trim();
    format!(
        "Warning: could not open a bastion tunnel to {} via {} ({}); its sessions will not be listed.",
        sanitize_remote_text(vm_name),
        sanitize_remote_text(bastion_name),
        sanitize_remote_text(first_line)
    )
}

/// VM names that appear more than once in this listing.
///
/// Tunnels are correctly separated by resource id, but the maps handed to the
/// renderer are still keyed by VM name. Rendering one VM's sessions against a
/// same-named VM's row is worse than a blank cell, so colliding names have
/// their enrichment withheld.
pub(crate) fn colliding_vm_names(vms: &[VmInfo]) -> std::collections::HashSet<String> {
    let mut counts: HashMap<&str, usize> = HashMap::new();
    for vm in vms {
        *counts.entry(vm.name.as_str()).or_insert(0) += 1;
    }
    counts
        .into_iter()
        .filter(|(_, n)| *n > 1)
        .map(|(name, _)| name.to_string())
        .collect()
}

/// The warning printed once when some VM names collide.
fn collision_warning(colliding: &std::collections::HashSet<String>) -> String {
    let mut names: Vec<String> = colliding.iter().map(|s| sanitize_remote_text(s)).collect();
    names.sort();
    format!(
        "Warning: VM name(s) {} appear in more than one resource group; \
         their tmux/health/process columns are withheld to avoid attributing \
         one VM's data to another.",
        names.join(", ")
    )
}

/// Make text this machine did not author safe to print in a single line.
///
/// Session and process names come from the listed hosts — the least observed
/// machines in a fleet — and land directly in the operator's terminal, so
/// control characters are stripped and the length is capped.
///
/// The same treatment applies to Azure-supplied strings: resource, VM and
/// bastion names are chosen by whoever created them, and `az` error text quotes
/// them back. A warning is not a safer place to print an escape sequence than a
/// table cell is.
///
/// Newlines are stripped along with every other control character: each caller
/// already reduces its remote output to one line per cell, and a surviving
/// newline would let a listed host end the row and print rows of its own
/// invention, which an operator cannot distinguish from real VMs.
pub(crate) fn sanitize_remote_text(raw: &str) -> String {
    raw.chars()
        .filter(|c| !c.is_control() && !is_bidi_or_invisible(*c))
        .take(MAX_REMOTE_TEXT_LEN)
        .collect()
}

/// Characters that break a line, reorder it, or hide part of it without being
/// control characters.
///
/// `char::is_control` is exactly the `Cc` category. That is wider than it looks
/// — it covers `U+0080`–`U+009F`, so the 8-bit CSI is already handled — but it
/// is also narrower than the guarantee above needs, in two ways:
///
/// * **`Zl`/`Zp`.** `U+2028 LINE SEPARATOR` and `U+2029 PARAGRAPH SEPARATOR`
///   are not `Cc`, yet terminals and downstream text consumers break a line on
///   them. Letting them through defeats the newline rule stated one doc comment
///   up, so they are stripped for that rule's sake.
/// * **`Cf`.** `U+202E RIGHT-TO-LEFT OVERRIDE` and its relatives reverse the
///   rendering of everything after them, so a process name can make one VM's
///   row read as another's (the "Trojan Source" class); `U+00AD SOFT HYPHEN`,
///   the word joiners and the tag block hide or fabricate text just as
///   effectively while occupying no column.
///
/// The ranges below are the `Cf` block plus the two separators, listed
/// explicitly rather than pulled from a Unicode-tables dependency: the set is
/// small, fixed, and cheaper to audit here than to trust to a transitive crate.
fn is_bidi_or_invisible(c: char) -> bool {
    matches!(c,
        '\u{00AD}'                  // soft hyphen
        | '\u{061C}'                // arabic letter mark
        | '\u{180E}'                // mongolian vowel separator
        | '\u{200B}'..='\u{200F}'   // zero-width spaces, LRM/RLM
        | '\u{2028}'..='\u{2029}'   // line and paragraph separators (Zl/Zp)
        | '\u{202A}'..='\u{202E}'   // embedding and override
        | '\u{2060}'..='\u{2064}'   // word joiner, invisible operators
        | '\u{2066}'..='\u{206F}'   // isolates and deprecated formatting
        | '\u{FEFF}'                // zero-width no-break space / BOM
        | '\u{FFF9}'..='\u{FFFB}'   // interlinear annotation
        | '\u{110BD}' | '\u{110CD}' // kaithi number signs
        | '\u{13430}'..='\u{1343F}' // egyptian hieroglyph format controls
        | '\u{1BCA0}'..='\u{1BCA3}' // shorthand format controls
        | '\u{1D173}'..='\u{1D17A}' // musical format controls
        | '\u{E0000}'..='\u{E007F}' // tag block (invisible ASCII mirror)
    )
}

/// Collect tmux sessions for all running VMs via SSH (direct or bastion).
///
/// SSH probes run concurrently (up to the JoinSet's natural fan-out) using
/// `tokio::process::Command` to avoid blocking the async runtime. Bastion
/// tunnels are pre-created sequentially because tunnel creation mutates a
/// shared registry file.
///
/// Bastion routing is supplied by the caller via [`discover_bastions_async`],
/// which runs whenever at least one running VM has no public IP (i.e. is
/// bastion-only), regardless of output format. It was once gated on
/// `is_table_output`, so tmux sessions were never collected for private VMs in
/// JSON/CSV output modes.
pub(crate) async fn collect_tmux_sessions(
    vms: &[VmInfo],
    bastion_map: &BastionMap,
    verbose: bool,
    subscription_id: &str,
    connect_timeout: u64,
) -> HashMap<String, Vec<String>> {
    let ssh_key = resolve_ssh_key();

    // Same-named VMs in different resource groups cannot be told apart in a
    // name-keyed result map, so they are not probed at all.
    let colliding = colliding_vm_names(vms);
    if !colliding.is_empty() {
        eprintln!("{}", collision_warning(&colliding));
    }

    // Pre-create bastion tunnels before the concurrent SSH probes, because
    // tunnel creation mutates a shared registry file and must stay sequential.
    //
    // Colliding VMs are removed *before* planning, not skipped afterwards.
    // Planning over them would let VMs that are never going to be probed
    // consume slots under MAX_BASTION_TUNNELS_PER_RUN, pushing real VMs past
    // the cap, and would count them in the "skipped" total reported to the
    // operator -- a number they cannot act on.
    let probe_vms: Vec<VmInfo> = vms
        .iter()
        .filter(|vm| !colliding.contains(&vm.name))
        .cloned()
        .collect();
    let planned = plan_bastion_tunnels(&probe_vms, bastion_map, subscription_id);
    if planned.skipped > 0 {
        eprintln!(
            "Warning: {} bastion-only VM(s) beyond the limit of {} tunnels per run were not probed; \
             narrow the listing (for example with --resource-group) to see their sessions.",
            planned.skipped, MAX_BASTION_TUNNELS_PER_RUN
        );
    }

    // Keyed by VM resource id — the id the tunnel was actually opened against.
    // Keying by bastion name is the #1127 bug itself; keying by VM name still
    // collides for same-named VMs in two resource groups.
    let mut bastion_ports: HashMap<String, u16> = HashMap::new();
    for plan in &planned.plans {
        match crate::bastion_tunnel::get_or_create_tunnel(
            &plan.bastion_name,
            &plan.resource_group,
            &plan.vm_resource_id,
        )
        .await
        {
            Ok(port) => {
                bastion_ports.insert(plan.vm_resource_id.clone(), port);
            }
            Err(e) => {
                eprintln!(
                    "{}",
                    tunnel_failure_warning(&plan.vm_name, &plan.bastion_name, &e.to_string())
                );
                if verbose {
                    // `{:#}` prints the whole anyhow chain, which is the point
                    // of the verbose line — but it is also the one path that
                    // reaches the terminal without passing through
                    // `tunnel_failure_warning`, so it sanitizes for itself.
                    eprintln!(
                        "[VERBOSE] tunnel error for {}: {}",
                        sanitize_remote_text(&plan.vm_name),
                        sanitize_remote_text(&format!("{:#}", e))
                    );
                }
            }
        }
    }

    // Build SSH tasks for all running VMs, then execute concurrently
    let tmux_cmd =
        "tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null || true";
    let mut join_set = tokio::task::JoinSet::new();

    for vm in vms {
        if colliding.contains(&vm.name) {
            continue;
        }
        let route = probe_route(vm, bastion_map, subscription_id);
        // A tunnel that failed to open is not the end of the road. The VM's
        // private IP is routable for an operator on a VPN or peered network,
        // and a listed session beats a blank cell that reads as "no sessions"
        // — which is the #1127 symptom this module exists to remove. Demote
        // such a plan to a direct probe instead of dropping the VM.
        let route = match route {
            ProbeRoute::Bastion {
                target,
                fallback_host,
            } if !bastion_ports.contains_key(&target.vm_resource_id) => {
                match direct_fallback_host(fallback_host.as_deref()) {
                    Some(host) => ProbeRoute::Direct {
                        host: host.to_string(),
                    },
                    // Nothing left to try. The warning was already printed
                    // when the tunnel failed, so do not repeat it here.
                    None => continue,
                }
            }
            other => other,
        };
        let user = vm
            .admin_username
            .as_deref()
            .unwrap_or(DEFAULT_ADMIN_USERNAME)
            .to_string();
        let vm_name = vm.name.clone();
        let ssh_key = ssh_key.clone();
        let tmux_cmd = tmux_cmd.to_string();
        let common_opts = probe_ssh_opts(connect_timeout, ssh_key.as_deref());

        match route {
            ProbeRoute::Direct { host } => {
                join_set.spawn(async move {
                    let mut cmd = tokio::process::Command::new("ssh");
                    cmd.args(["-o", "StrictHostKeyChecking=accept-new"]);
                    cmd.args(&common_opts);
                    cmd.arg(format!("{}@{}", user, host));
                    cmd.arg(&tmux_cmd);
                    cmd.stdout(std::process::Stdio::piped())
                        .stderr(std::process::Stdio::piped());
                    (vm_name, cmd.output().await)
                });
            }
            ProbeRoute::Bastion { target, .. } => {
                let Some(&port) = bastion_ports.get(&target.vm_resource_id) else {
                    // Unreachable: a plan with no port was demoted above.
                    continue;
                };
                join_set.spawn(async move {
                    let mut cmd = tokio::process::Command::new("ssh");
                    cmd.args(crate::bastion_tunnel::bastion_loopback_ssh_opts());
                    cmd.args(["-p", &port.to_string()]);
                    cmd.args(&common_opts);
                    cmd.arg(format!("{}@127.0.0.1", user));
                    cmd.arg(&tmux_cmd);
                    cmd.stdout(std::process::Stdio::piped())
                        .stderr(std::process::Stdio::piped());
                    (vm_name, cmd.output().await)
                });
            }
            ProbeRoute::Unreachable => {
                if verbose {
                    eprintln!(
                        "[VERBOSE] {} has no reachable address and no bastion in {}/{}; skipping tmux collection",
                        sanitize_remote_text(&vm.name),
                        sanitize_remote_text(&vm.resource_group),
                        sanitize_remote_text(&vm.location)
                    );
                }
            }
        }
    }

    // Collect results
    let mut tmux_sessions: HashMap<String, Vec<String>> = HashMap::new();
    while let Some(result) = join_set.join_next().await {
        // A probe that never answered is not the same as a VM with no
        // sessions, but both render as a blank cell. The distinction is only
        // ever interesting when someone is already asking why a row is empty,
        // so it is reported under --verbose: warning by default would fire for
        // every VM an operator legitimately cannot SSH to.
        let (vm_name, out) = match result {
            Ok((vm_name, Ok(out))) => (vm_name, out),
            Ok((vm_name, Err(e))) => {
                if verbose {
                    eprintln!(
                        "[VERBOSE] {} -> tmux probe could not be run ({}); reporting no sessions",
                        vm_name, e
                    );
                }
                continue;
            }
            Err(e) => {
                if verbose {
                    eprintln!(
                        "[VERBOSE] a tmux probe task did not complete ({}); that VM reports no sessions",
                        e
                    );
                }
                continue;
            }
        };
        if !out.status.success() {
            if verbose {
                // The probe's stderr is remote-controlled -- a listed host's
                // SSH banner or MOTD lands here -- and this prints straight to
                // the operator's terminal, so it goes through the same filter
                // as anything else read off a host.
                eprintln!(
                    "[VERBOSE] {} -> tmux probe exited {} ({}); reporting no sessions",
                    vm_name,
                    out.status.code().unwrap_or(-1),
                    sanitize_remote_text(String::from_utf8_lossy(&out.stderr).trim())
                );
            }
            continue;
        }

        let all: Vec<String> = String::from_utf8_lossy(&out.stdout)
            .lines()
            .filter(|l| !l.is_empty() && !l.starts_with('{'))
            .map(sanitize_remote_text)
            .filter(|l| !l.is_empty())
            .collect();
        // A cap that drops sessions without saying so reads as "this VM has 20
        // sessions", which is the same confidently-wrong answer the tunnel bug
        // gave. The tunnel cap already reports what it skipped; so does this
        // one.
        let dropped = all.len().saturating_sub(MAX_SESSIONS_PER_VM);
        let sessions: Vec<String> = all.into_iter().take(MAX_SESSIONS_PER_VM).collect();
        if dropped > 0 {
            // On the default path and remotely triggerable: a compromised VM
            // opens enough sessions to force this line, so the name it prints
            // is attacker-chosen input reaching an operator's terminal.
            eprintln!(
                "Warning: {} has more than {} tmux sessions; {} are not shown.",
                sanitize_remote_text(&vm_name),
                MAX_SESSIONS_PER_VM,
                dropped
            );
        }
        if verbose {
            eprintln!(
                "[VERBOSE] {} -> {} sessions",
                sanitize_remote_text(&vm_name),
                sessions.len()
            );
        }
        if !sessions.is_empty() {
            tmux_sessions.insert(vm_name, sessions);
        }
    }
    tmux_sessions
}

/// Collect latency measurements for running VMs via TCP connect.
///
/// Only directly routable addresses are timed — see [`latency_probe_host`].
pub(crate) fn collect_latencies(vms: &[VmInfo]) -> HashMap<String, u64> {
    let colliding = colliding_vm_names(vms);
    let mut latencies = HashMap::new();
    for vm in vms {
        if colliding.contains(&vm.name) {
            continue;
        }
        let Some(ip) = latency_probe_host(vm) else {
            continue;
        };
        // Parsed as an address, not as `"{ip}:22"` text: an IPv6 address needs
        // brackets in that form, so the textual parse failed and the VM was
        // dropped from the Latency column entirely.
        let Ok(parsed) = ip.parse::<std::net::IpAddr>() else {
            continue;
        };
        let addr = std::net::SocketAddr::new(parsed, 22);
        let start = std::time::Instant::now();
        if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok() {
            latencies.insert(vm.name.clone(), start.elapsed().as_millis() as u64);
        }
    }
    latencies
}

/// Collect detailed health metrics (CPU, Mem, Disk, Agent) for running VMs via SSH.
pub(crate) fn collect_health_data(
    vms: &[VmInfo],
    bastion_map: &BastionMap,
    subscription_id: &str,
) -> HashMap<String, crate::HealthMetrics> {
    let mut health_data = HashMap::new();
    let ssh_key_path = resolve_ssh_key();
    let colliding = colliding_vm_names(vms);

    for vm in vms {
        if colliding.contains(&vm.name) {
            continue;
        }
        let state = vm.power_state.to_string();
        let user = vm
            .admin_username
            .as_deref()
            .unwrap_or(DEFAULT_ADMIN_USERNAME);

        // A bastion-only VM with no recorded private IP is still reachable
        // through its tunnel; it used to be skipped for having no address.
        let (ip, bastion_info_owned) = match probe_route(vm, bastion_map, subscription_id) {
            ProbeRoute::Direct { host } => (host, None),
            ProbeRoute::Bastion {
                target,
                fallback_host,
            } => (
                fallback_host.unwrap_or_default(),
                Some((
                    target.bastion_name,
                    target.resource_group,
                    target.vm_resource_id,
                    ssh_key_path.clone(),
                )),
            ),
            ProbeRoute::Unreachable => continue,
        };

        let bastion_ref = bastion_info_owned
            .as_ref()
            .map(|(bn, rg_b, rid, key)| (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref()));

        let metrics = crate::collect_health_metrics(&vm.name, &ip, user, &state, bastion_ref);
        health_data.insert(vm.name.clone(), metrics);
    }
    health_data
}

/// Collect top process data for running VMs.
///
/// Bastion-only VMs are routed through their own tunnel. They were previously
/// SSH'd at their own private IP, which is unroutable from the operator's
/// machine, so they silently reported no processes at all.
pub(crate) fn collect_procs(
    vms: &[VmInfo],
    bastion_map: &BastionMap,
    connect_timeout: u64,
    subscription_id: &str,
) -> HashMap<String, String> {
    const PROC_CMD: &str =
        "ps aux --sort=-%mem | head -6 | tail -5 | awk '{print $11}' | tr '\\n' ', '";

    let mut proc_data = HashMap::new();
    let ssh_key_path = resolve_ssh_key();
    let colliding = colliding_vm_names(vms);

    for vm in vms {
        if colliding.contains(&vm.name) {
            continue;
        }
        let user = vm
            .admin_username
            .as_deref()
            .unwrap_or(DEFAULT_ADMIN_USERNAME);

        // One SSH probe at a directly routable address. Shared by the direct
        // route and by the bastion route's fallback so the two cannot drift
        // into spelling the same probe differently.
        let direct_probe = |host: &str| -> Option<String> {
            let mut cmd = std::process::Command::new("ssh");
            cmd.args(["-o", "StrictHostKeyChecking=accept-new"]);
            cmd.args(probe_ssh_opts(connect_timeout, ssh_key_path.as_deref()));
            cmd.arg(format!("{}@{}", user, host)).arg(PROC_CMD);
            match cmd.output() {
                Ok(out) if out.status.success() => {
                    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
                }
                _ => None,
            }
        };

        let procs = match probe_route(vm, bastion_map, subscription_id) {
            ProbeRoute::Direct { host } => match direct_probe(&host) {
                Some(out) => out,
                None => continue,
            },
            ProbeRoute::Bastion {
                target,
                fallback_host,
            } => {
                match crate::bastion_ssh_exec(
                    &target.bastion_name,
                    &target.resource_group,
                    &target.vm_resource_id,
                    user,
                    ssh_key_path.as_deref(),
                    PROC_CMD,
                    crate::BASTION_EXEC_TIMEOUT_SECS,
                ) {
                    Ok((0, stdout, _)) => stdout.trim().to_string(),
                    // The command reached the VM and failed there. Retrying at
                    // the private IP would either fail the same way or, far
                    // worse, succeed against a different host and report its
                    // processes under this VM's name.
                    Ok(_) => continue,
                    Err(e) => {
                        // Transport failure: the bastion never carried the
                        // command. Before this routing existed, collect_procs
                        // SSH'd the private IP directly, which works for an
                        // operator on a VPN or peered network. Keeping that as
                        // the fallback makes the new routing strictly more
                        // available than what it replaced, never less.
                        match direct_fallback_host(fallback_host.as_deref()).and_then(direct_probe)
                        {
                            Some(out) => out,
                            None => {
                                eprintln!(
                                    "{}",
                                    tunnel_failure_warning(
                                        &target.vm_name,
                                        &target.bastion_name,
                                        &e.to_string()
                                    )
                                );
                                continue;
                            }
                        }
                    }
                }
            }
            ProbeRoute::Unreachable => continue,
        };

        proc_data.insert(vm.name.clone(), sanitize_remote_text(&procs));
    }
    proc_data
}

/// Parse a raw tmux session string (e.g. `"main:1"`) into a validated session name.
///
/// Splits on `:` to strip the `attached` count suffix, trims whitespace, then validates
/// the name against the alphanumeric + `_` + `-` allowlist.  Returns `None` when the
/// name is empty, exceeds 128 characters, or contains any disallowed character.
pub(crate) fn parse_session_name(raw: &str) -> Option<String> {
    let name = raw.split(':').next().unwrap_or("").trim().to_string();
    if name.is_empty() || name.len() > 128 {
        return None;
    }
    if !name
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return None;
    }
    Some(name)
}

/// Validate a VM name before using it in process arguments.
///
/// Allowlist permits alphanumeric characters, underscores, hyphens, and dots (dots are
/// required for Azure FQDNs) and rejects everything else, preventing argument injection.
pub(crate) fn is_valid_restore_vm_name(name: &str) -> bool {
    if name.is_empty() || name.len() > 256 {
        return false;
    }
    name.chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.')
}

/// Build the Windows Terminal argument list for restoring a single tmux session.
///
/// When `wsl_distro` is non-empty, the command is wrapped in `bash -lc '...'`
/// so the user's login shell environment (PATH, SSH_AUTH_SOCK, etc.) is loaded.
/// Without that wrapper, `wsl.exe -d <distro> -- <binary>` runs outside any
/// shell, so tools like `ssh` and `az` may not be found.
///
/// `restore_mode` controls window placement:
/// - `Tab` → `wt.exe -w 0 new-tab ...` (reuse existing window)
/// - `Window` → `wt.exe -w new new-tab ...` (new window per session)
/// - `Auto` is resolved by the caller before reaching here; treated as `Tab`.
pub(crate) fn build_wt_restore_args(
    wsl_distro: &str,
    self_exe: &str,
    vm_name: &str,
    session: &str,
    restore_mode: &azlin_core::RestoreMode,
) -> Vec<String> {
    let mut args: Vec<String> = match restore_mode {
        azlin_core::RestoreMode::Window => vec!["-w".into(), "new".into(), "new-tab".into()],
        _ => vec!["-w".into(), "0".into(), "new-tab".into()],
    };
    if !wsl_distro.is_empty() {
        let inner_cmd = format!(
            "exec {} connect {} --tmux-session {}",
            crate::dispatch_helpers::shell_escape(self_exe),
            crate::dispatch_helpers::shell_escape(vm_name),
            crate::dispatch_helpers::shell_escape(session),
        );
        args.extend_from_slice(&[
            "wsl.exe".into(),
            "-d".into(),
            wsl_distro.into(),
            "--".into(),
            "bash".into(),
            "-lc".into(),
            inner_cmd,
        ]);
    } else {
        args.extend_from_slice(&[
            self_exe.into(),
            "connect".into(),
            vm_name.into(),
            "--tmux-session".into(),
            session.into(),
        ]);
    }
    args
}

/// Restore tmux sessions by connecting to each VM.
///
/// `multi_tab` is the inverse of `--no-multi-tab`: when false no terminal is
/// spawned at all and the `azlin connect` commands are printed instead, so the
/// user stays in the tab they are already in.
pub(crate) fn restore_tmux_sessions(tmux_sessions: &HashMap<String, Vec<String>>, multi_tab: bool) {
    println!("\nRestoring tmux sessions...");

    let plan = crate::restore_helpers::plan_restore(tmux_sessions);
    for warning in &plan.warnings {
        eprintln!("  Warning: {}", warning);
    }

    // In test builds, skip spawning real terminal processes to avoid
    // opening windows on the developer's screen during cargo test.
    if cfg!(test) || std::env::var("AZLIN_TEST_MODE").is_ok() {
        for target in &plan.targets {
            println!(
                "  [dry-run] Would connect to {} (session: {})",
                target.vm, target.session
            );
        }
        return;
    }

    let detected_wt = std::env::var("WT_SESSION").is_ok();

    // Load config for restore_mode preference. `--no-multi-tab` (multi_tab =
    // false) overrides it: each session gets its own window instead of a tab in
    // the current one.
    let config = crate::dispatch_helpers::load_user_config();
    let restore_mode =
        &crate::restore_helpers::effective_restore_mode(&config.restore_mode, multi_tab);

    // If restore_mode is explicitly set to tab or window, force wt.exe usage
    // — but only when we're in WSL where wt.exe is actually available.
    let in_wsl = std::env::var("WSL_DISTRO_NAME").is_ok_and(|v| !v.is_empty());
    let force_wt = in_wsl
        && matches!(
            restore_mode,
            azlin_core::RestoreMode::Tab | azlin_core::RestoreMode::Window
        );
    let use_wt = detected_wt || force_wt;
    let use_macos = cfg!(target_os = "macos") && !use_wt;

    // Resolve the current executable path so we can re-invoke ourselves
    // in new terminal tabs. Using bare "azlin" fails when installed via
    // uvx or cargo install since it may not be in PATH for new shells.
    let self_exe = std::env::current_exe()
        .ok()
        .and_then(|p| p.to_str().map(|s| s.to_string()))
        .unwrap_or_else(|| "azlin".to_string());

    // Detect which macOS terminal emulator is running (if on macOS).
    let macos_terminal = if use_macos {
        detect_macos_terminal()
    } else {
        MacTerminal::Unknown
    };

    for target in &plan.targets {
        let vm_name = &target.vm;
        let session = &target.session;
        if use_wt {
            println!("  Opening tab: {} (session: {})", vm_name, session);
            let wsl_distro = std::env::var("WSL_DISTRO_NAME").unwrap_or_else(|_| "".to_string());
            let wt_args =
                build_wt_restore_args(&wsl_distro, &self_exe, vm_name, session, restore_mode);
            let wt_str_args: Vec<&str> = wt_args.iter().map(|s| s.as_str()).collect();
            match std::process::Command::new("wt.exe")
                .args(&wt_str_args)
                .stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .spawn()
                .and_then(|child| child.wait_with_output())
            {
                Ok(output) if !output.status.success() => {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    eprintln!(
                        "  Warning: wt.exe failed for {} (exit {}): {}",
                        vm_name,
                        output.status.code().unwrap_or(-1),
                        stderr.trim()
                    );
                }
                Err(e) => {
                    eprintln!("  Warning: failed to open tab for {}: {}", vm_name, e);
                }
                _ => {}
            }
            // Windows Terminal silently drops new-tab commands when
            // many are issued simultaneously. A small delay between
            // spawns prevents lost tabs.
            std::thread::sleep(std::time::Duration::from_millis(500));
        } else if use_macos {
            println!("  Opening window: {} (session: {})", vm_name, session);
            let connect_cmd = escape_for_applescript(&format!(
                "{} connect {} --tmux-session {}",
                self_exe, vm_name, session
            ));
            if let Err(e) = open_macos_terminal(&macos_terminal, &connect_cmd) {
                eprintln!("  Warning: failed to open window for {}: {}", vm_name, e);
            }
        } else {
            // On Linux without Windows Terminal, open a terminal emulator.
            let connect_cmd = format!(
                "{} connect {} --tmux-session {}",
                crate::dispatch_helpers::shell_escape(&self_exe),
                crate::dispatch_helpers::shell_escape(vm_name),
                crate::dispatch_helpers::shell_escape(session),
            );
            if let Some(term) = detect_linux_terminal() {
                println!("  Opening terminal: {} (session: {})", vm_name, session);
                if let Err(e) = open_linux_terminal(&term, &connect_cmd) {
                    eprintln!("  Warning: failed to open terminal for {}: {}", vm_name, e);
                }
            } else {
                eprintln!(
                    "  No terminal emulator detected for {}. Run manually:",
                    vm_name
                );
                eprintln!("    azlin connect {} --tmux-session {}", vm_name, session);
                eprintln!("  Tip: set AZLIN_TERMINAL=<your-terminal> to enable auto-restore.");
            }
        }
    }
    println!("Session restore initiated.");
}

/// Supported macOS terminal emulators.
#[derive(Debug, PartialEq)]
enum MacTerminal {
    TerminalApp,
    ITerm2,
    Unknown,
}

/// Detect which macOS terminal emulator is running.
fn detect_macos_terminal() -> MacTerminal {
    // TERM_PROGRAM is set by most macOS terminal emulators.
    match std::env::var("TERM_PROGRAM").as_deref() {
        Ok("Apple_Terminal") => MacTerminal::TerminalApp,
        Ok("iTerm.app") => MacTerminal::ITerm2,
        _ => MacTerminal::Unknown,
    }
}

/// Escape a string for safe embedding in AppleScript double-quoted strings.
/// Handles `\` and `"` which are the two special characters in AppleScript strings.
fn escape_for_applescript(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

/// Open a new macOS terminal window running the given command string.
/// The command string must already be escaped via `escape_for_applescript`.
fn open_macos_terminal(terminal: &MacTerminal, command: &str) -> Result<(), String> {
    match terminal {
        MacTerminal::ITerm2 => {
            // iTerm2: create a new window (or tab in existing window).
            // Check for existing windows first to avoid errors.
            let script = format!(
                r#"tell application "iTerm2"
    if (count of windows) = 0 then
        create window with default profile
        tell current session of current window
            write text "{cmd}"
        end tell
    else
        tell current window
            create tab with default profile
            tell current session
                write text "{cmd}"
            end tell
        end tell
    end if
end tell"#,
                cmd = command
            );
            run_osascript(&script)
        }
        MacTerminal::TerminalApp | MacTerminal::Unknown => {
            // Terminal.app: `do script` opens a new window.
            // For Unknown, fall back to Terminal.app since it's always available on macOS.
            let script = format!(
                r#"tell application "Terminal"
    activate
    do script "{}"
end tell"#,
                command
            );
            run_osascript(&script)
        }
    }
}

/// Execute an AppleScript via osascript.
fn run_osascript(script: &str) -> Result<(), String> {
    let result = std::process::Command::new("osascript")
        .args(["-e", script])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .output();
    match result {
        Ok(output) if output.status.success() => Ok(()),
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            Err(format!("osascript failed: {}", stderr.trim()))
        }
        Err(e) => Err(format!("failed to run osascript: {}", e)),
    }
}

// ── Linux terminal support ──────────────────────────────────────────────

/// Supported Linux terminal emulators.
#[derive(Debug, PartialEq)]
enum LinuxTerminal {
    Custom(String),
    GnomeTerminal,
    Xfce4Terminal,
    Konsole,
    Xterm,
}

/// Detect an available Linux terminal emulator.
///
/// Checks `AZLIN_TERMINAL` env var first (user override, like `$EDITOR`),
/// then probes known emulators via `which`.
fn detect_linux_terminal() -> Option<LinuxTerminal> {
    if let Ok(custom) = std::env::var("AZLIN_TERMINAL") {
        if !custom.is_empty() {
            // Reject values containing shell metacharacters to prevent injection.
            if custom.contains([';', '&', '|', '$', '`', '\n', '(', ')']) {
                eprintln!(
                    "  Warning: AZLIN_TERMINAL contains shell metacharacters, ignoring: {}",
                    custom
                );
            } else if which_exists(&custom) {
                return Some(LinuxTerminal::Custom(custom));
            } else {
                eprintln!(
                    "  Warning: AZLIN_TERMINAL binary not found on PATH: {}",
                    custom
                );
            }
        }
    }
    let candidates = [
        ("gnome-terminal", LinuxTerminal::GnomeTerminal),
        ("xfce4-terminal", LinuxTerminal::Xfce4Terminal),
        ("konsole", LinuxTerminal::Konsole),
        ("xterm", LinuxTerminal::Xterm),
    ];
    for (bin, variant) in candidates {
        if which_exists(bin) {
            return Some(variant);
        }
    }
    None
}

/// Check if a binary exists on PATH.
fn which_exists(name: &str) -> bool {
    std::process::Command::new("which")
        .arg(name)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Open a new Linux terminal window running the given shell command string.
fn open_linux_terminal(terminal: &LinuxTerminal, command: &str) -> Result<(), String> {
    let result = match terminal {
        LinuxTerminal::GnomeTerminal => std::process::Command::new("gnome-terminal")
            .args(["--", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Konsole => std::process::Command::new("konsole")
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Xfce4Terminal => {
            // xfce4-terminal -e expects a single command string (shell-parsed)
            let wrapped = format!(
                "bash -lc {}",
                crate::dispatch_helpers::shell_escape(command)
            );
            std::process::Command::new("xfce4-terminal")
                .args(["-e", &wrapped])
                .stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn()
        }
        LinuxTerminal::Xterm => std::process::Command::new("xterm")
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
        LinuxTerminal::Custom(bin) => std::process::Command::new(bin)
            .args(["-e", "bash", "-lc", command])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn(),
    };
    match result {
        Ok(_) => Ok(()),
        Err(e) => Err(format!("failed to launch terminal: {}", e)),
    }
}

/// Shared VM/bastion fixtures for the bastion routing test modules below.
#[cfg(test)]
mod session_lookup_tests {
    use super::*;

    fn sessions_map(entries: &[(&str, &[&str])]) -> HashMap<String, Vec<String>> {
        entries
            .iter()
            .map(|(vm, sess)| (vm.to_string(), sess.iter().map(|s| s.to_string()).collect()))
            .collect()
    }

    #[test]
    fn test_match_session_found_on_single_vm() {
        let map = sessions_map(&[("vm-a", &["main:1", "scratch:0"]), ("vm-b", &["other:0"])]);
        let result = match_session_in_map(&map, "scratch");
        assert_eq!(
            result,
            SessionLookup::Found {
                vm_name: "vm-a".to_string()
            }
        );
    }

    #[test]
    fn test_match_session_not_found() {
        let map = sessions_map(&[("vm-a", &["main:1"])]);
        let result = match_session_in_map(&map, "nonexistent");
        assert_eq!(result, SessionLookup::NotFound);
    }

    #[test]
    fn test_match_session_ambiguous_across_vms() {
        let map = sessions_map(&[("vm-a", &["shared:0"]), ("vm-b", &["shared:1"])]);
        let result = match_session_in_map(&map, "shared");
        match result {
            SessionLookup::Ambiguous { vm_names } => {
                assert_eq!(vm_names, vec!["vm-a".to_string(), "vm-b".to_string()]);
            }
            other => panic!("expected Ambiguous, got {other:?}"),
        }
    }

    #[test]
    fn test_match_session_ignores_attached_suffix() {
        // Session name matching strips the ":attached" suffix via parse_session_name.
        let map = sessions_map(&[("vm-a", &["work:1"])]);
        let result = match_session_in_map(&map, "work");
        assert_eq!(
            result,
            SessionLookup::Found {
                vm_name: "vm-a".to_string()
            }
        );
    }
}

/// Shared VM/bastion fixtures for the bastion routing test modules below.
#[cfg(test)]
mod bastion_test_support {
    use super::*;
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};

    pub(super) fn vm(
        name: &str,
        location: &str,
        public_ip: Option<&str>,
        state: PowerState,
    ) -> VmInfo {
        VmInfo {
            name: name.to_string(),
            resource_group: "rg".to_string(),
            location: location.to_string(),
            vm_size: "Standard_D2s_v5".to_string(),
            power_state: state,
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: public_ip.map(|s| s.to_string()),
            private_ip: Some("10.0.0.4".to_string()),
            admin_username: Some("azureuser".to_string()),
            tags: HashMap::new(),
            created_time: None,
        }
    }

    /// Same as [`vm`] but with an explicit resource group, so tests can build
    /// two VMs that share a name across different resource groups.
    pub(super) fn vm_in_rg(name: &str, rg: &str, location: &str, state: PowerState) -> VmInfo {
        VmInfo {
            resource_group: rg.to_string(),
            ..vm(name, location, None, state)
        }
    }

    /// A bastion map keyed the way Azure actually scopes bastions:
    /// `(resource group, region) -> bastion name`.
    pub(super) fn bastion_map(entries: &[(&str, &str, &str)]) -> BastionMap {
        entries
            .iter()
            .map(|(rg, loc, name)| (bastion_key(rg, loc), name.to_string()))
            .collect()
    }
}

#[cfg(test)]
mod bastion_tunnel_plan_tests {
    use super::bastion_test_support::*;
    use super::*;
    use azlin_core::models::PowerState;

    /// The set of VM resource ids a plan list targets, order discarded.
    fn targeted_rids(plans: &[BastionTunnelPlan]) -> std::collections::BTreeSet<String> {
        plans.iter().map(|p| p.vm_resource_id.clone()).collect()
    }

    /// Regression: two bastion-only VMs behind the SAME bastion each need their
    /// own tunnel. Sharing one tunnel per bastion sent both probes to whichever
    /// VM was tunnelled first, so the other reported zero tmux sessions.
    #[test]
    fn plans_one_tunnel_per_vm_not_per_bastion() {
        let vms = [
            vm("dev", "centralus", None, PowerState::Running),
            vm("azt1", "centralus", None, PowerState::Running),
        ];
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        assert_eq!(planned.plans.len(), 2, "each VM needs its own tunnel");
        let names: Vec<&str> = planned.plans.iter().map(|p| p.vm_name.as_str()).collect();
        assert_eq!(names, vec!["dev", "azt1"]);
        assert_eq!(
            targeted_rids(&planned.plans).len(),
            2,
            "tunnels must target distinct VM resource ids"
        );
        assert!(planned.plans.iter().all(|p| p.bastion_name == "bst"));
        assert_eq!(planned.skipped, 0);
    }

    #[test]
    fn skips_vms_with_public_ips_and_non_running_vms() {
        let vms = [
            vm("public", "centralus", Some("4.4.4.4"), PowerState::Running),
            vm("stopped", "centralus", None, PowerState::Deallocated),
            vm("private", "centralus", None, PowerState::Running),
        ];
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        assert_eq!(planned.plans.len(), 1);
        assert_eq!(planned.plans[0].vm_name, "private");
        assert_eq!(
            planned.skipped, 0,
            "a VM that needs no tunnel is not a skipped VM"
        );
    }

    #[test]
    fn skips_regions_without_a_bastion() {
        let vms = [vm("orphan", "westus3", None, PowerState::Running)];
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        assert!(planned.plans.is_empty());
    }

    #[test]
    fn plans_distinct_bastions_for_distinct_regions() {
        let vms = [
            vm("a", "centralus", None, PowerState::Running),
            vm("b", "westus3", None, PowerState::Running),
        ];
        let planned = plan_bastion_tunnels(
            &vms,
            &bastion_map(&[
                ("rg", "centralus", "bst-cus"),
                ("rg", "westus3", "bst-wus3"),
            ]),
            "sub-1",
        );

        assert_eq!(planned.plans.len(), 2);
        assert_eq!(planned.plans[0].bastion_name, "bst-cus");
        assert_eq!(planned.plans[1].bastion_name, "bst-wus3");
    }

    /// A bastion is scoped to a resource group as well as a region. Keying the
    /// map by region alone lets a VM in `rg-b` be tunnelled through a bastion
    /// that only exists in `rg-a`.
    #[test]
    fn a_bastion_serves_only_its_own_resource_group() {
        let vms = [vm_in_rg("dev", "rg-b", "centralus", PowerState::Running)];
        let planned = plan_bastion_tunnels(
            &vms,
            &bastion_map(&[("rg-a", "centralus", "bst-a")]),
            "sub-1",
        );

        assert!(
            planned.plans.is_empty(),
            "a bastion in rg-a must not be used for a VM in rg-b"
        );
    }

    /// The invariant the pre-#1127 code provably violated: tunnel count is
    /// driven by the number of bastion-only VMs, never by the number of
    /// distinct bastions. Collapsing the map to one entry per bastion made
    /// these two numbers equal, which is exactly the bug.
    #[test]
    fn plan_count_tracks_vm_count_not_bastion_count() {
        let vms = [
            vm("dev", "centralus", None, PowerState::Running),
            vm("azt1", "centralus", None, PowerState::Running),
            vm("azt2", "centralus", None, PowerState::Running),
        ];
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        let distinct_bastions: std::collections::BTreeSet<&str> = planned
            .plans
            .iter()
            .map(|p| p.bastion_name.as_str())
            .collect();
        assert_eq!(distinct_bastions.len(), 1, "these VMs share one bastion");
        assert_eq!(
            planned.plans.len(),
            3,
            "one tunnel per bastion-only VM, not one per bastion"
        );
        assert_eq!(
            targeted_rids(&planned.plans).len(),
            3,
            "every tunnel must target a distinct VM resource id"
        );
    }

    /// The original symptom was order-dependent: whichever bastion-only VM was
    /// iterated first won the shared tunnel and the rest silently reported zero
    /// sessions. Planning must therefore be a pure function of the VM *set*.
    #[test]
    fn plans_are_order_independent() {
        let bstn = bastion_map(&[("rg", "centralus", "bst")]);
        let forward = [
            vm("dev", "centralus", None, PowerState::Running),
            vm("azt1", "centralus", None, PowerState::Running),
        ];
        let reversed = [
            vm("azt1", "centralus", None, PowerState::Running),
            vm("dev", "centralus", None, PowerState::Running),
        ];

        assert_eq!(
            targeted_rids(&plan_bastion_tunnels(&forward, &bstn, "sub-1").plans),
            targeted_rids(&plan_bastion_tunnels(&reversed, &bstn, "sub-1").plans),
            "the same VMs in a different order must yield the same tunnels"
        );
    }

    /// A VM is identified by its full resource id, not by its name: Azure
    /// permits the same VM name in two resource groups of one subscription,
    /// and a bastion tunnel is opened against a resource id. Deduplicating by
    /// name drops the second VM's tunnel, reproducing the #1127 symptom for a
    /// different reason.
    #[test]
    fn plans_a_tunnel_for_each_of_two_same_named_vms_in_different_resource_groups() {
        let vms = [
            vm_in_rg("dev", "rg-a", "centralus", PowerState::Running),
            vm_in_rg("dev", "rg-b", "centralus", PowerState::Running),
        ];
        let planned = plan_bastion_tunnels(
            &vms,
            &bastion_map(&[
                ("rg-a", "centralus", "bst-a"),
                ("rg-b", "centralus", "bst-b"),
            ]),
            "sub-1",
        );

        assert_eq!(
            planned.plans.len(),
            2,
            "same-named VMs in different resource groups are different VMs"
        );
        let rids = targeted_rids(&planned.plans);
        assert!(rids.iter().any(|r| r.contains("/resourceGroups/rg-a/")));
        assert!(rids.iter().any(|r| r.contains("/resourceGroups/rg-b/")));
        assert_eq!(
            planned
                .plans
                .iter()
                .map(|p| p.resource_group.as_str())
                .collect::<Vec<_>>(),
            vec!["rg-a", "rg-b"],
            "each tunnel is opened in its own VM's resource group"
        );
    }

    /// A genuinely duplicated VM entry must still collapse to one tunnel.
    #[test]
    fn deduplicates_a_repeated_vm_entry() {
        let vms = [
            vm("dev", "centralus", None, PowerState::Running),
            vm("dev", "centralus", None, PowerState::Running),
        ];
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        assert_eq!(
            planned.plans.len(),
            1,
            "the same VM must not get two tunnels"
        );
    }

    /// Tunnel creation is sequential and each one costs an Azure round trip, so
    /// a wide listing is bounded. What must never happen is silent truncation:
    /// the count of skipped VMs is carried out so the caller can report it.
    #[test]
    fn bounds_tunnel_fan_out_and_reports_how_many_it_skipped() {
        let over = MAX_BASTION_TUNNELS_PER_RUN + 3;
        let vms: Vec<_> = (0..over)
            .map(|i| {
                vm(
                    &format!("vm{:03}", i),
                    "centralus",
                    None,
                    PowerState::Running,
                )
            })
            .collect();
        let planned =
            plan_bastion_tunnels(&vms, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1");

        assert_eq!(planned.plans.len(), MAX_BASTION_TUNNELS_PER_RUN);
        assert_eq!(
            planned.skipped, 3,
            "VMs beyond the cap must be counted, not silently dropped"
        );
    }
}

#[cfg(test)]
mod bastion_discovery_tests {
    use super::bastion_test_support::*;
    use super::*;
    use azlin_core::models::PowerState;

    /// Discovery used to run against the resource group of whichever VM sorted
    /// first, so bastion-only VMs in every other resource group were skipped.
    /// It must run once per resource group that actually needs it.
    #[test]
    fn looks_up_every_resource_group_that_has_a_bastion_only_vm() {
        let vms = [
            vm_in_rg("a", "rg-a", "centralus", PowerState::Running),
            vm_in_rg("b", "rg-b", "centralus", PowerState::Running),
            vm_in_rg("c", "rg-a", "westus3", PowerState::Running),
        ];
        assert_eq!(
            resource_groups_needing_bastion_lookup(&vms),
            vec!["rg-a", "rg-b"],
            "one lookup per distinct resource group, deduplicated and ordered"
        );
    }

    /// A listing where everything is publicly reachable must not touch Azure.
    #[test]
    fn a_listing_with_no_private_vms_performs_no_lookup() {
        let vms = [
            vm("pub1", "centralus", Some("4.4.4.4"), PowerState::Running),
            vm("pub2", "westus3", Some("5.5.5.5"), PowerState::Running),
        ];
        assert!(resource_groups_needing_bastion_lookup(&vms).is_empty());
    }

    /// A stopped VM is never probed, so it must not trigger an `az` call.
    #[test]
    fn a_stopped_private_vm_does_not_trigger_a_lookup() {
        let vms = [vm_in_rg(
            "off",
            "rg-a",
            "centralus",
            PowerState::Deallocated,
        )];
        assert!(resource_groups_needing_bastion_lookup(&vms).is_empty());
    }

    /// The map is *inserted* with the bastion's location as `az network
    /// bastion list` reports it and *looked up* with the VM's location as the
    /// VM listing reports it. Those are two different `az` commands, and
    /// Azure is not consistent about casing. Comparing raw strings therefore
    /// made the bastion vanish on a casing difference alone, and a VM with no
    /// bastion in the map silently reports zero sessions.
    #[test]
    fn a_bastion_is_found_despite_azure_casing_differences() {
        // Both directions must survive: the map is built from one `az`
        // command's casing and probed with another's, and which of the two is
        // upper-cased is not ours to choose.
        let cases = [
            // (map rg, map location, vm rg, vm location)
            ("RG-Prod", "CentralUS", "rg-prod", "centralus"),
            ("rg-prod", "centralus", "RG-Prod", "CentralUS"),
            ("Rg-Prod", "centralUS", "rG-pROD", "CENTRALUS"),
        ];
        for (map_rg, map_loc, vm_rg, vm_loc) in cases {
            let map = bastion_map(&[(map_rg, map_loc, "bst-central")]);
            let mut vm = vm_in_rg("dev", vm_rg, vm_loc, PowerState::Running);
            vm.private_ip = None;
            match probe_route(&vm, &map, "sub-1") {
                ProbeRoute::Bastion { target, .. } => {
                    assert_eq!(target.bastion_name, "bst-central");
                }
                other => panic!(
                    "map({map_rg}/{map_loc}) vs vm({vm_rg}/{vm_loc}) dropped the bastion: {other:?}"
                ),
            }
        }
    }

    /// Normalization must not merge genuinely different coordinates.
    #[test]
    fn normalization_does_not_conflate_distinct_resource_groups_or_regions() {
        assert_eq!(
            bastion_key("RG", "CentralUS"),
            bastion_key("rg", "centralus")
        );
        assert_ne!(
            bastion_key("rg-a", "centralus"),
            bastion_key("rg-b", "centralus")
        );
        assert_ne!(bastion_key("rg", "centralus"), bastion_key("rg", "westus3"));
    }

    /// The displayed "Azure Bastion Hosts" table was built from the first
    /// VM's resource group, so a listing spanning resource groups showed one
    /// group's bastions and silently omitted the rest.
    #[test]
    fn the_bastion_table_covers_every_resource_group_in_the_listing() {
        let vms = [
            vm_in_rg("b", "rg-b", "centralus", PowerState::Running),
            vm_in_rg("a", "rg-a", "centralus", PowerState::Running),
            vm_in_rg("c", "rg-b", "westus3", PowerState::Running),
        ];
        assert_eq!(
            resource_groups_in_listing(&vms),
            vec!["rg-a", "rg-b"],
            "every distinct resource group, deduplicated, regardless of VM order"
        );
    }

    /// The table documents the bastions in the scope the user asked about, so
    /// unlike the routing lookup it must not disappear just because every VM
    /// happens to be stopped or publicly reachable right now.
    #[test]
    fn the_bastion_table_does_not_depend_on_power_state_or_public_ip() {
        let vms = [
            vm("pub", "centralus", Some("4.4.4.4"), PowerState::Running),
            vm_in_rg("off", "rg-z", "westus3", PowerState::Deallocated),
        ];
        assert!(
            resource_groups_needing_bastion_lookup(&vms).is_empty(),
            "nothing needs routing"
        );
        assert_eq!(
            resource_groups_in_listing(&vms),
            vec!["rg", "rg-z"],
            "but the table still covers both groups"
        );
    }

    /// An empty listing must not produce an `az` call against `""`.
    #[test]
    fn an_empty_listing_queries_nothing() {
        assert!(resource_groups_in_listing(&[]).is_empty());
    }

    /// Coordinates come back from `az` and go straight into an argument
    /// vector, so they are validated first. A name beginning with `-` would be
    /// parsed as a flag.
    #[test]
    fn rejects_bastion_coordinates_that_are_unsafe_or_incomplete() {
        assert!(valid_bastion_coordinates("bst-westus2", "westus2"));
        assert!(!valid_bastion_coordinates("", "westus2"), "empty name");
        assert!(!valid_bastion_coordinates("bst", ""), "empty location");
        assert!(
            !valid_bastion_coordinates("--query", "westus2"),
            "a name that would be read as a flag"
        );
        assert!(
            !valid_bastion_coordinates("-bst", "westus2"),
            "a name that would be read as a flag"
        );
    }

    /// Two virtual networks in one resource group means two bastions in one
    /// region. Whichever `az` happened to list last used to win the map slot,
    /// so the route a VM got depended on Azure's listing order — and a bastion
    /// that cannot see the VM produces the same empty row as having no bastion
    /// at all. First entry wins, deterministically.
    #[test]
    fn a_second_bastion_in_one_region_does_not_replace_the_first() {
        let mut map = BastionMap::new();
        let warnings = insert_bastions_for_group(
            &mut map,
            "rg-a",
            vec![
                ("bst-one".into(), "centralus".into(), "Standard".into()),
                ("bst-two".into(), "centralus".into(), "Standard".into()),
            ],
        );
        assert_eq!(
            map.get(&bastion_key("rg-a", "centralus")),
            Some(&"bst-one".to_string()),
            "the first bastion listed keeps the slot"
        );
        assert_eq!(warnings.len(), 1, "the bastion passed over must be named");
        assert!(
            warnings[0].contains("bst-two"),
            "the warning names the bastion that was ignored: {}",
            warnings[0]
        );
    }

    /// The same bastion arriving twice is not a conflict, and must not produce
    /// a warning an operator would have to investigate.
    #[test]
    fn the_same_bastion_listed_twice_is_not_a_conflict() {
        let mut map = BastionMap::new();
        let warnings = insert_bastions_for_group(
            &mut map,
            "rg-a",
            vec![
                ("bst-one".into(), "centralus".into(), "Standard".into()),
                ("bst-one".into(), "centralus".into(), "Standard".into()),
            ],
        );
        assert_eq!(map.len(), 1);
        assert!(warnings.is_empty(), "no conflict, so nothing to report");
    }

    /// Bastions in different regions of one resource group are independent
    /// slots, not a conflict: each serves the VMs that share its region.
    #[test]
    fn bastions_in_different_regions_each_keep_their_own_slot() {
        let mut map = BastionMap::new();
        let warnings = insert_bastions_for_group(
            &mut map,
            "rg-a",
            vec![
                ("bst-central".into(), "centralus".into(), "Standard".into()),
                ("bst-west".into(), "westus3".into(), "Standard".into()),
            ],
        );
        assert_eq!(
            map.get(&bastion_key("rg-a", "centralus")),
            Some(&"bst-central".to_string())
        );
        assert_eq!(
            map.get(&bastion_key("rg-a", "westus3")),
            Some(&"bst-west".to_string())
        );
        assert!(warnings.is_empty());
    }

    /// An unsafe name is dropped before it can take a slot, so a rejected
    /// entry must not shadow a valid bastion listed after it.
    #[test]
    fn a_rejected_bastion_does_not_take_the_slot() {
        let mut map = BastionMap::new();
        let warnings = insert_bastions_for_group(
            &mut map,
            "rg-a",
            vec![
                ("--query".into(), "centralus".into(), "Standard".into()),
                ("bst-real".into(), "centralus".into(), "Standard".into()),
            ],
        );
        assert_eq!(
            map.get(&bastion_key("rg-a", "centralus")),
            Some(&"bst-real".to_string()),
            "the valid bastion still gets the slot"
        );
        assert!(warnings.is_empty(), "a rejected entry is not a conflict");
    }
}

#[cfg(test)]
mod probe_route_tests {
    use super::bastion_test_support::*;
    use super::*;
    use azlin_core::models::{PowerState, VmInfo};

    /// Every ARM resource id in this module must be built one way, so the id a
    /// tunnel is opened against cannot drift from the id used to look its port
    /// back up, nor from the key the tunnel registry stores.
    #[test]
    fn build_vm_resource_id_uses_the_arm_path_format() {
        assert_eq!(
            build_vm_resource_id("sub-1", "rg-a", "dev"),
            "/subscriptions/sub-1/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/dev"
        );
    }

    /// Two VMs sharing a name in different resource groups have different ids,
    /// which is what makes the id — not the name — the safe map key.
    #[test]
    fn build_vm_resource_id_distinguishes_same_named_vms_across_resource_groups() {
        assert_ne!(
            build_vm_resource_id("sub-1", "rg-a", "dev"),
            build_vm_resource_id("sub-1", "rg-b", "dev")
        );
    }

    #[test]
    fn a_public_vm_is_probed_directly_even_when_its_region_has_a_bastion() {
        let route = probe_route(
            &vm("pub", "centralus", Some("4.4.4.4"), PowerState::Running),
            &bastion_map(&[("rg", "centralus", "bst")]),
            "sub-1",
        );
        assert_eq!(
            route,
            ProbeRoute::Direct {
                host: "4.4.4.4".to_string()
            },
            "a reachable public IP must not be routed through a bastion"
        );
    }

    /// The `collect_procs` defect: a bastion-only VM was probed at its own
    /// private IP, which is unroutable from the operator's machine, so the VM
    /// silently reported no processes. It must be routed through a tunnel
    /// opened against its own resource id — while keeping the private IP as a
    /// fallback for operators on a VPN or peered network.
    #[test]
    fn a_bastion_only_vm_is_routed_through_a_tunnel_to_its_own_resource_id() {
        let route = probe_route(
            &vm_in_rg("dev", "rg-a", "centralus", PowerState::Running),
            &bastion_map(&[("rg-a", "centralus", "bst")]),
            "sub-1",
        );
        match route {
            ProbeRoute::Bastion {
                target,
                fallback_host,
            } => {
                assert_eq!(target.bastion_name, "bst");
                assert_eq!(target.resource_group, "rg-a");
                assert_eq!(
                    target.vm_resource_id,
                    build_vm_resource_id("sub-1", "rg-a", "dev")
                );
                assert_eq!(fallback_host.as_deref(), Some("10.0.0.4"));
            }
            other => panic!("expected a bastion route, got {:?}", other),
        }
    }

    /// Pre-existing behaviour that must survive the fix: with no bastion for
    /// this VM the private IP may still be routable (VPN, peering), so keep
    /// trying it rather than declaring the VM unreachable.
    #[test]
    fn a_private_vm_with_no_bastion_still_tries_its_private_ip() {
        let route = probe_route(
            &vm("orphan", "westus3", None, PowerState::Running),
            &bastion_map(&[("rg", "centralus", "bst")]),
            "sub-1",
        );
        assert_eq!(
            route,
            ProbeRoute::Direct {
                host: "10.0.0.4".to_string()
            }
        );
    }

    /// `collect_health_data` used to skip any VM with no recorded IP, which
    /// dropped bastion-only VMs that were in fact reachable through a tunnel.
    #[test]
    fn a_vm_with_no_recorded_ip_is_still_reachable_through_its_bastion() {
        let vm = VmInfo {
            private_ip: None,
            ..vm_in_rg("dev", "rg-a", "centralus", PowerState::Running)
        };
        match probe_route(&vm, &bastion_map(&[("rg-a", "centralus", "bst")]), "sub-1") {
            ProbeRoute::Bastion { fallback_host, .. } => {
                assert_eq!(fallback_host, None, "there is no address to fall back to");
            }
            other => panic!("expected a bastion route, got {:?}", other),
        }
    }

    #[test]
    fn a_vm_with_no_address_and_no_bastion_is_unreachable() {
        let vm = VmInfo {
            private_ip: None,
            ..vm("ghost", "westus3", None, PowerState::Running)
        };
        assert_eq!(
            probe_route(&vm, &bastion_map(&[("rg", "centralus", "bst")]), "sub-1"),
            ProbeRoute::Unreachable
        );
    }

    /// Latency must never be measured through a tunnel: that times the tunnel,
    /// not the host, silently changing what the column means.
    #[test]
    fn latency_is_measured_only_on_a_directly_routable_address() {
        assert_eq!(
            latency_probe_host(&vm(
                "pub",
                "centralus",
                Some("4.4.4.4"),
                PowerState::Running
            )),
            Some("4.4.4.4".to_string())
        );
        assert_eq!(
            latency_probe_host(&vm_in_rg("dev", "rg-a", "centralus", PowerState::Running)),
            Some("10.0.0.4".to_string()),
            "a private IP may still be routable over VPN; the tunnel is never timed"
        );
    }

    /// A deallocated VM keeps its addresses in Azure metadata, and Azure hands
    /// released public IPs to other tenants. Timing one either stalls the
    /// listing for the full connect timeout or reports a latency measured
    /// against somebody else's host, attributed to a VM that is not running.
    #[test]
    fn latency_is_not_measured_for_a_stopped_vm() {
        assert_eq!(
            latency_probe_host(&vm(
                "stopped-pub",
                "centralus",
                Some("4.4.4.4"),
                PowerState::Stopped
            )),
            None,
            "a stopped VM's stale public IP must never be timed"
        );
        assert_eq!(
            latency_probe_host(&vm_in_rg(
                "stopped-priv",
                "rg-a",
                "centralus",
                PowerState::Stopped
            )),
            None,
            "a stopped VM's stale private IP must never be timed"
        );
    }
}

#[cfg(test)]
mod silent_degradation_tests {
    use super::bastion_test_support::*;
    use super::*;
    use azlin_core::models::PowerState;

    /// The bastion route carries a `fallback_host` precisely so a transport
    /// failure degrades instead of dropping the VM. If this ever returns
    /// `None` for a real address, `collect_procs` and `collect_tmux_sessions`
    /// go back to reporting a reachable VM as having nothing on it.
    #[test]
    fn a_real_private_ip_is_offered_as_a_fallback() {
        assert_eq!(direct_fallback_host(Some("10.0.0.4")), Some("10.0.0.4"));
        assert_eq!(direct_fallback_host(Some("fd00::4")), Some("fd00::4"));
    }

    /// `collect_health_data` flattens the address with `unwrap_or_default()`,
    /// so "this VM has no private IP" reaches the fallback as `""`. Treating
    /// that as an address builds `ssh user@`, which is not a probe: it fails
    /// slowly and for a reason that has nothing to do with the VM.
    #[test]
    fn an_absent_or_blank_address_is_not_a_fallback() {
        assert_eq!(direct_fallback_host(None), None);
        assert_eq!(direct_fallback_host(Some("")), None);
        assert_eq!(direct_fallback_host(Some("   ")), None);
        assert_eq!(direct_fallback_host(Some("\t")), None);
    }

    /// The two halves of the contract, stated together: `probe_route` supplies
    /// the private IP on the bastion route, and the fallback accepts it. This
    /// is what makes the bastion routing strictly more available than the
    /// direct-private-IP code it replaced, rather than a trade.
    #[test]
    fn bastion_routing_never_removes_the_direct_path_it_replaced() {
        let vm = vm_in_rg("azt1", "rg-a", "centralus", PowerState::Running);
        assert!(vm.public_ip.is_none(), "precondition: bastion-only");
        assert!(vm.private_ip.is_some(), "precondition: has a private IP");
        let route = probe_route(&vm, &bastion_map(&[("rg-a", "centralus", "bst")]), "sub-1");
        let ProbeRoute::Bastion { fallback_host, .. } = route else {
            panic!("a bastion-only VM must route through its bastion");
        };
        assert_eq!(
            direct_fallback_host(fallback_host.as_deref()),
            Some("10.0.0.4"),
            "the address the pre-routing code used must still be reachable"
        );
    }

    /// A tunnel that fails to open drops the VM from the results entirely. That
    /// is indistinguishable from "this VM has no sessions" unless we say so, on
    /// stderr, whether or not --verbose was passed.
    #[test]
    fn tunnel_failure_warning_names_the_vm_the_bastion_and_the_consequence() {
        let msg = tunnel_failure_warning("azt1", "bst", "bastion tunnel timed out");
        assert!(msg.contains("azt1"), "must name the VM: {}", msg);
        assert!(msg.contains("bst"), "must name the bastion: {}", msg);
        assert!(
            msg.contains("bastion tunnel timed out"),
            "must carry the underlying cause: {}",
            msg
        );
        assert!(
            msg.contains("will not be listed"),
            "must state that this VM's sessions are missing, not absent: {}",
            msg
        );
    }

    /// Only the first line of the error chain belongs on a warning line; the
    /// rest is for --verbose.
    #[test]
    fn tunnel_failure_warning_keeps_only_the_first_line_of_the_error() {
        let msg = tunnel_failure_warning(
            "azt1",
            "bst",
            "tunnel failed\ncaused by: RBAC denied\n  at frame 2",
        );
        assert!(msg.contains("tunnel failed"));
        assert!(
            !msg.contains("caused by"),
            "error chain must be trimmed: {}",
            msg
        );
        assert_eq!(msg.lines().count(), 1, "a warning is one line: {}", msg);
    }

    /// Tunnels are correctly separated by resource id, but the display maps are
    /// still keyed by VM name. Rendering one VM's sessions against another VM's
    /// row is worse than a blank cell, so colliding names are withheld.
    #[test]
    fn detects_vm_names_that_collide_across_resource_groups() {
        let vms = [
            vm_in_rg("build-agent", "dev-rg", "centralus", PowerState::Running),
            vm_in_rg("build-agent", "prod-rg", "centralus", PowerState::Running),
            vm_in_rg("unique", "dev-rg", "centralus", PowerState::Running),
        ];
        let colliding = colliding_vm_names(&vms);

        assert!(colliding.contains("build-agent"));
        assert!(
            !colliding.contains("unique"),
            "a unique name keeps its enrichment columns"
        );
        assert_eq!(colliding.len(), 1);
    }

    /// The ordinary single-resource-group listing must be unaffected.
    #[test]
    fn a_listing_with_unique_names_withholds_nothing() {
        let vms = [
            vm("a", "centralus", None, PowerState::Running),
            vm("b", "centralus", None, PowerState::Running),
        ];
        assert!(colliding_vm_names(&vms).is_empty());
    }

    /// Session and process names come from the listed hosts — the least
    /// observed machines in a fleet — and land in a terminal.
    #[test]
    fn remote_text_cannot_carry_escape_sequences_into_the_terminal() {
        let cleaned = sanitize_remote_text("main\x1b[2Jwiped\x07");
        assert!(
            !cleaned.contains('\x1b'),
            "ANSI escape survived: {:?}",
            cleaned
        );
        assert!(!cleaned.contains('\x07'), "BEL survived: {:?}", cleaned);
        assert!(
            cleaned.contains("main"),
            "legitimate text was lost: {:?}",
            cleaned
        );
    }

    #[test]
    fn remote_text_is_length_capped() {
        let cleaned = sanitize_remote_text(&"a".repeat(10_000));
        assert!(
            cleaned.len() <= MAX_REMOTE_TEXT_LEN,
            "unbounded remote text reached the renderer: {} chars",
            cleaned.len()
        );
    }

    #[test]
    fn ordinary_session_names_pass_through_unchanged() {
        assert_eq!(sanitize_remote_text("build-agent_1:2"), "build-agent_1:2");
    }

    /// Sanitized text is placed in a single table cell. A newline that survives
    /// sanitizing lets a listed host end the row and print arbitrary extra
    /// rows, so an operator reading `azlin vm list` cannot tell a real VM from
    /// one a compromised host invented.
    #[test]
    fn remote_text_cannot_forge_extra_table_rows() {
        let cleaned = sanitize_remote_text("bash\nazt-prod  Running  0 sessions");
        assert!(
            !cleaned.contains('\n'),
            "a newline survived into a table cell: {:?}",
            cleaned
        );
        assert!(
            cleaned.contains("bash"),
            "legitimate text was lost: {:?}",
            cleaned
        );
    }

    /// The line-break rule the module states must hold for every character a
    /// consumer breaks a line on, not just for `Cc`. `U+2028`/`U+2029` are
    /// `Zl`/`Zp`, so `char::is_control` lets them through and a name carrying
    /// one still ends the row.
    #[test]
    fn remote_text_strips_the_unicode_line_separators_too() {
        for sep in ['\u{2028}', '\u{2029}'] {
            let cleaned = sanitize_remote_text(&format!("bash{sep}azt-prod  Running"));
            assert!(
                !cleaned.contains(sep),
                "{:?} survived into a table cell: {:?}",
                sep,
                cleaned
            );
        }
    }

    /// The bidi/invisible filter has to cover the whole `Cf` block, not the
    /// handful of code points the "Trojan Source" write-ups name. A mark that
    /// occupies no column still reorders or hides the text beside it.
    #[test]
    fn remote_text_strips_the_rest_of_the_invisible_block() {
        for c in [
            '\u{061C}',  // arabic letter mark
            '\u{00AD}',  // soft hyphen
            '\u{2060}',  // word joiner
            '\u{206F}',  // nominal digit shapes
            '\u{E0041}', // tag latin capital A
        ] {
            let cleaned = sanitize_remote_text(&format!("azt{c}prod"));
            assert_eq!(
                cleaned, "aztprod",
                "U+{:04X} survived: {:?}",
                c as u32, cleaned
            );
        }
    }

    /// The C1 range is `Cc`, so `char::is_control` already covers the 8-bit
    /// CSI. Pinned so a future rewrite of the filter cannot quietly drop it.
    #[test]
    fn remote_text_strips_the_eight_bit_csi() {
        let cleaned = sanitize_remote_text("main\u{9B}2Jwiped");
        assert!(
            !cleaned.contains('\u{9B}'),
            "8-bit CSI survived: {:?}",
            cleaned
        );
    }

    /// Withholding the tmux/health/process columns is the right call for
    /// colliding names, but a blank column is exactly what the #1127 bug looked
    /// like. The warning is what separates "withheld on purpose" from
    /// "silently wrong".
    #[test]
    fn collision_warning_names_every_withheld_vm_and_says_why() {
        let colliding: std::collections::HashSet<String> =
            ["build-agent".to_string(), "runner".to_string()]
                .into_iter()
                .collect();
        let msg = collision_warning(&colliding);

        assert!(msg.contains("build-agent"), "must name each VM: {}", msg);
        assert!(msg.contains("runner"), "must name each VM: {}", msg);
        assert!(
            msg.contains("more than one resource group"),
            "must state the cause: {}",
            msg
        );
        assert!(
            msg.contains("withheld"),
            "must say the columns are withheld, not empty: {}",
            msg
        );
    }

    /// The warning is assembled from a HashSet, whose iteration order varies
    /// run to run; an operator diffing two listings must not see spurious churn.
    #[test]
    fn collision_warning_lists_names_in_a_stable_order() {
        let names: std::collections::HashSet<String> = ["zeta", "alpha", "mid"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let msg = collision_warning(&names);
        let alpha = msg.find("alpha").expect("alpha listed");
        let mid = msg.find("mid").expect("mid listed");
        let zeta = msg.find("zeta").expect("zeta listed");
        assert!(alpha < mid && mid < zeta, "names must be sorted: {}", msg);
    }
    /// `char::is_control` covers only `Cc`, so bidi overrides (`Cf`) survived
    /// it. `U+202E` reverses the rendering of the rest of the cell, which is
    /// enough to make one VM's row read as another's.
    #[test]
    fn remote_text_cannot_reorder_the_row_with_bidi_overrides() {
        assert!(
            !'\u{202E}'.is_control(),
            "precondition: the control filter alone does not catch this"
        );
        for hostile in [
            "ssh\u{202E}gpg",
            "ssh\u{202D}gpg",
            "ssh\u{200B}gpg",
            "ssh\u{2066}gpg",
            "ssh\u{FEFF}gpg",
        ] {
            let clean = sanitize_remote_text(hostile);
            assert_eq!(clean, "sshgpg", "not neutralized: {:?}", hostile);
        }
        // Ordinary non-ASCII text must survive untouched.
        assert_eq!(sanitize_remote_text("café-café"), "café-café");
    }

    /// The Latency column formatted its address as `"{ip}:22"` and parsed
    /// that. An IPv6 address needs brackets in that form, so it failed to
    /// parse; the old code then fell back to `0.0.0.0:22` and timed the
    /// operator's own machine, reporting the result as the VM's latency.
    /// Parsing the address itself is what makes IPv6 measurable at all.
    #[test]
    fn an_ipv6_address_is_a_valid_latency_target_and_is_never_loopback() {
        for raw in ["10.0.0.4", "2001:db8::1", "fe80::1"] {
            let parsed: std::net::IpAddr = raw.parse().expect("a real address parses");
            let addr = std::net::SocketAddr::new(parsed, 22);
            assert_eq!(addr.port(), 22);
            assert_eq!(addr.ip().to_string(), raw);
            assert!(
                !addr.ip().is_unspecified(),
                "{raw} must never degrade to 0.0.0.0, which times the local machine"
            );
        }
        // The bracket-less textual form is exactly what used to fail.
        assert!(
            "2001:db8::1:22".parse::<std::net::SocketAddr>().is_err(),
            "the old formatting really was broken for IPv6"
        );
    }

    /// A resource group whose bastion lookup fails must say so. Silently
    /// treating it as "no bastions here" routes every bastion-only VM in that
    /// group to an unroutable private IP and reports zero sessions — the exact
    /// symptom #1127 was filed for, reintroduced through the error path.
    #[test]
    fn bastion_lookup_failure_names_the_resource_group_and_the_consequence() {
        let msg = bastion_lookup_failure_warning("rg-prod", "AuthorizationFailed: denied");
        assert!(msg.contains("rg-prod"), "names the resource group: {msg}");
        assert!(
            msg.contains("AuthorizationFailed"),
            "carries the cause: {msg}"
        );
        assert!(
            msg.contains("no tmux") || msg.contains("bastion"),
            "states the consequence: {msg}"
        );
    }

    /// `az` errors are multi-line chains; only the first line belongs on a
    /// warning line, matching `tunnel_failure_warning`.
    #[test]
    fn bastion_lookup_failure_keeps_only_the_first_line_of_the_error() {
        let msg = bastion_lookup_failure_warning("rg", "boom\nstack frame\nmore detail");
        assert!(msg.contains("boom"));
        assert!(
            !msg.contains("stack frame"),
            "detail is --verbose-only: {msg}"
        );
    }
    /// Azure resource names and `az` error text are not authored by this
    /// machine, and a warning is not a safer place to print an escape sequence
    /// than a table cell is: a `\r` plus a cursor-movement sequence lets the
    /// named group overwrite the warning that names it.
    #[test]
    fn warnings_sanitize_every_string_this_machine_did_not_author() {
        let hostile = "rg\x1b[2K\rall clear";

        let lookup = bastion_lookup_failure_warning(hostile, hostile);
        let tunnel = tunnel_failure_warning(hostile, hostile, hostile);
        let collision = collision_warning(&std::collections::HashSet::from([hostile.to_string()]));

        for msg in [&lookup, &tunnel, &collision] {
            assert!(
                !msg.contains('\x1b') && !msg.contains('\r'),
                "control characters must not survive into a warning: {msg:?}"
            );
            assert_eq!(msg.lines().count(), 1, "a warning is one line: {msg:?}");
            // Stripping the ESC is what disarms the sequence; the printable
            // remainder stays visible rather than being silently swallowed,
            // so the operator can see what the group was really called.
            assert!(
                msg.contains("rg[2Kall clear"),
                "the text itself is kept, only the escape is stripped: {msg:?}"
            );
        }
    }

    /// A bidi override in a VM or bastion name reverses the rendering of
    /// everything after it, so one VM's warning can read as another's. Table
    /// cells already strip these; warnings must too.
    #[test]
    fn warnings_strip_bidi_overrides_not_just_control_characters() {
        let msg = tunnel_failure_warning("azt-prod\u{202E}", "bst", "denied");
        assert!(
            !msg.contains('\u{202E}'),
            "RIGHT-TO-LEFT OVERRIDE must not reach the terminal: {msg:?}"
        );
        assert!(msg.contains("azt-prod"), "the name is still named: {msg:?}");
    }

    /// The three probe call sites each spelled the identity fallback
    /// `to_str().unwrap_or("")`, which passes ssh `-i ""`. ssh then fails on a
    /// missing identity file and the probe reports the VM as unreachable —
    /// a key path that is not valid UTF-8 turns into a phantom dead VM.
    /// Omitting the flag is the same state as having no key at all.
    #[test]
    fn probe_ssh_opts_omits_the_identity_flag_rather_than_passing_an_empty_one() {
        let opts = probe_ssh_opts(7, None);
        assert!(
            !opts.iter().any(|o| o == "-i"),
            "no key means no -i at all: {opts:?}"
        );
        assert!(
            !opts.iter().any(|o| o.is_empty()),
            "an empty argument is never correct: {opts:?}"
        );
    }

    /// Every probe shares the connect timeout and batch mode; without
    /// `BatchMode=yes` a probe against a VM needing a passphrase blocks the
    /// whole listing on a prompt the operator cannot see behind the spinner.
    #[test]
    fn probe_ssh_opts_carries_the_timeout_and_batch_mode_and_the_key_when_there_is_one() {
        let key = std::path::PathBuf::from("/home/op/.ssh/id_ed25519");
        let opts = probe_ssh_opts(42, Some(&key));
        assert!(
            opts.windows(2)
                .any(|w| w[0] == "-o" && w[1] == "ConnectTimeout=42"),
            "the caller's timeout must be the one used: {opts:?}"
        );
        assert!(
            opts.windows(2)
                .any(|w| w[0] == "-o" && w[1] == "BatchMode=yes"),
            "a probe must never prompt: {opts:?}"
        );
        assert!(
            opts.windows(2)
                .any(|w| w[0] == "-i" && w[1] == "/home/op/.ssh/id_ed25519"),
            "the resolved key must be passed: {opts:?}"
        );
    }

    /// `discover_bastions` is a pure function of the VM list, which is what
    /// makes hoisting it out of the three collectors safe: the map a caller
    /// discovers once is the map each collector would have discovered for
    /// itself. If a VM list ever stops determining the set of groups looked
    /// up, the shared map becomes wrong for some collector and this fails.
    #[test]
    fn bastion_lookup_depends_only_on_the_vm_list() {
        let vms = vec![
            vm_in_rg("azt-a", "rg-a", "centralus", PowerState::Running),
            vm_in_rg("azt-b", "rg-b", "westus", PowerState::Running),
            // Public IP, so `rg-c` needs no bastion lookup at all.
            VmInfo {
                resource_group: "rg-c".to_string(),
                ..vm("azt-c", "centralus", Some("4.4.4.4"), PowerState::Running)
            },
        ];
        let groups = resource_groups_needing_bastion_lookup(&vms);
        assert_eq!(
            groups,
            vec!["rg-a".to_string(), "rg-b".to_string()],
            "only groups holding a bastion-only VM are looked up: {groups:?}"
        );

        // Calling it twice on the same slice would prove nothing about a pure
        // function. What the hoist actually depends on is that the answer is
        // fixed by the *contents* of the list and nothing else -- not the order
        // Azure returned the VMs in, and not which collector is asking.
        let reordered: Vec<VmInfo> = vms.iter().rev().cloned().collect();
        assert_eq!(
            resource_groups_needing_bastion_lookup(&reordered),
            groups,
            "lookup set depends on VM order, so the shared map is wrong for some collector"
        );
    }
}
