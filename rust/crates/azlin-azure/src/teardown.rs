//! Teardown planner — decides which Azure resources belong to a session and
//! in what order they must be deleted.
//!
//! `az vm delete` removes only the VM. Disks and the NIC disappear because
//! `az vm create` defaults their `deleteOption` to `Delete`, but Azure has no
//! equivalent implicit delete for the Public IP or the Network Security Group.
//! Those resources are left behind and keep billing. This module enumerates
//! them so the deletion commands can reclaim them.
//!
//! Every function here is pure and operates on `az ... list -o json` output,
//! mirroring [`crate::orphan_detector`], so the selection and ordering rules
//! are fully unit-testable without touching Azure.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

/// Tag key that identifies the azlin session a resource belongs to.
pub const SESSION_TAG_KEY: &str = "azlin-session";

/// Estimated monthly cost of an idle Standard static public IP, in USD.
///
/// Standard SKU public IPs bill even while unassociated, which is what makes
/// leaking them expensive.
pub const ORPHANED_PUBLIC_IP_MONTHLY_COST: f64 = 3.65;

/// A category of Azure resource that participates in session teardown.
///
/// The ordinal ordering of these variants is the dependency order in which the
/// resources must be deleted; see [`TeardownKind::deletion_order`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum TeardownKind {
    Vm,
    Disk,
    Nic,
    PublicIp,
    Nsg,
}

impl TeardownKind {
    /// Position of this resource kind in the deletion sequence.
    ///
    /// Azure refuses to delete a Public IP or an NSG while a NIC still
    /// references it, so the NIC must be deleted (and awaited) first.
    pub fn deletion_order(self) -> u8 {
        match self {
            Self::Vm => 0,
            Self::Disk => 1,
            Self::Nic => 2,
            Self::PublicIp => 3,
            Self::Nsg => 4,
        }
    }
}

impl std::fmt::Display for TeardownKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Vm => write!(f, "VM"),
            Self::Disk => write!(f, "Disk"),
            Self::Nic => write!(f, "NIC"),
            Self::PublicIp => write!(f, "Public IP"),
            Self::Nsg => write!(f, "NSG"),
        }
    }
}

/// A resource selected for deletion.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TeardownResource {
    pub name: String,
    pub kind: TeardownKind,
    pub resource_group: String,
    /// Estimated monthly cost reclaimed by deleting this resource, in USD.
    pub estimated_monthly_cost: f64,
}

/// Why a candidate resource was excluded from the teardown plan.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkipReason {
    /// The resource carries no `azlin-session` tag, so ownership cannot be
    /// proven. Deleting it would risk destroying someone else's resource.
    Untagged,
    /// The resource is still associated with something outside this teardown.
    InUse,
}

impl std::fmt::Display for SkipReason {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Untagged => write!(f, "no {SESSION_TAG_KEY} tag — ownership unproven"),
            Self::InUse => write!(f, "still associated with another resource"),
        }
    }
}

/// A candidate that looked session-related but was deliberately not deleted.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SkippedResource {
    pub name: String,
    pub kind: TeardownKind,
    pub reason: SkipReason,
}

/// The ordered set of resources to delete, plus anything deliberately skipped.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TeardownPlan {
    /// Resources to delete, already sorted into dependency order.
    pub resources: Vec<TeardownResource>,
    /// Candidates excluded from deletion, retained so the user can be warned.
    pub skipped: Vec<SkippedResource>,
    /// Whether the target VM was found in Azure.
    pub vm_exists: bool,
    /// The `azlin-session` tag this plan matched on, retained so a follow-up
    /// re-check can apply the identical ownership rule.
    pub session_tag: Option<String>,
    /// Exact resource names that prove ownership independently of the tag
    /// value, retained so a follow-up re-check can apply the identical rule.
    /// See [`TeardownInputs::also_match_by_name`].
    pub also_match_by_name: Vec<String>,
}

impl TeardownPlan {
    /// Total estimated monthly saving from executing this plan, in USD.
    pub fn estimated_monthly_savings(&self) -> f64 {
        self.resources
            .iter()
            .map(|r| r.estimated_monthly_cost)
            .sum()
    }

    /// Resources of a given kind, preserving plan order.
    pub fn of_kind(&self, kind: TeardownKind) -> Vec<&TeardownResource> {
        self.resources.iter().filter(|r| r.kind == kind).collect()
    }
}

/// Inputs to [`plan_teardown`], all raw `az ... list -o json` output.
pub struct TeardownInputs<'a> {
    /// Name of the VM being torn down.
    pub vm_name: &'a str,
    /// Resource group being operated on.
    pub resource_group: &'a str,
    /// Value of the VM's `azlin-session` tag, if the VM exists and is tagged.
    ///
    /// `None` means resources cannot be proven to belong to this session, so
    /// nothing beyond the VM's own disks and NIC will be deleted.
    pub session_tag: Option<&'a str>,
    /// Whether the VM currently exists in Azure.
    pub vm_exists: bool,
    pub disk_json: &'a str,
    pub nic_json: &'a str,
    pub pip_json: &'a str,
    pub nsg_json: &'a str,
    /// Exact resource names known to belong to this VM by Azure's own default
    /// per-VM naming convention (`<vm>PublicIP`, `<vm>NSG`), used as a
    /// fallback ownership signal that does not depend on `session_tag`
    /// matching exactly.
    ///
    /// Needed because pooled sessions (`azlin new --name X --pool N`) stamp
    /// *every* pool member's `azlin-session` tag with the pool's base name
    /// `X`, not the member's own VM name (`X-1`, `X-2`, …; see
    /// `resolve_session_identity`). When VM `X-1` no longer exists, its tag
    /// cannot be read live, so `session_tag` can only be guessed — and
    /// guessing `X-1` never equals the real tag `X`. Without this escape
    /// hatch that guess-mismatch makes `classify` silently `Ignore` the
    /// member's own orphaned Public IP/NSG (not even a warning), leaking it
    /// forever. A resource is only ever matched this way if it also carries
    /// *some* non-empty `azlin-session` tag — an untagged resource with a
    /// coincidentally matching name is still never touched.
    ///
    /// Empty when the VM exists and its tag was read live: exact tag
    /// equality is authoritative in that case and needs no name fallback.
    pub also_match_by_name: &'a [String],
}

/// Extract the final segment of an Azure resource ID.
///
/// Used for exact-match ownership checks. Deliberately exact: prefix matching
/// on names is unsafe because sessions can be prefix-adjacent siblings (e.g.
/// `copilot-test-1783435804` vs `copilot-test2-1784625385`).
fn resource_name_from_id(id: &str) -> Option<&str> {
    id.rsplit('/').find(|s| !s.is_empty())
}

/// Whether an Azure resource ID refers to a resource with exactly this name.
fn id_refers_to(id: &str, name: &str) -> bool {
    resource_name_from_id(id) == Some(name)
}

/// Read the `azlin-session` tag from a resource JSON object.
fn session_tag_of(resource: &serde_json::Value) -> Option<&str> {
    resource
        .get("tags")?
        .get(SESSION_TAG_KEY)?
        .as_str()
        .filter(|s| !s.is_empty())
}

/// Read a resource's `name` and `resourceGroup`, falling back to `default_rg`.
fn name_and_group<'a>(
    resource: &'a serde_json::Value,
    default_rg: &'a str,
) -> Option<(&'a str, &'a str)> {
    let name = resource.get("name")?.as_str()?;
    let rg = resource
        .get("resourceGroup")
        .and_then(|r| r.as_str())
        .unwrap_or(default_rg);
    Some((name, rg))
}

/// Whether a Public IP is free of any association.
///
/// Shared with orphan detection in `cleanup` so the two paths cannot drift.
pub fn public_ip_is_unassociated(ip: &serde_json::Value) -> bool {
    ip.get("ipConfiguration")
        .map(|v| v.is_null())
        .unwrap_or(true)
}

/// Whether an NSG is free of any association.
///
/// An NSG is only unassociated when it is referenced by neither a NIC nor a
/// subnet. Shared with orphan detection in `cleanup`.
pub fn nsg_is_unassociated(nsg: &serde_json::Value) -> bool {
    let non_empty_array = |key: &str| {
        nsg.get(key)
            .and_then(|v| v.as_array())
            .map(|a| !a.is_empty())
            .unwrap_or(false)
    };
    !non_empty_array("networkInterfaces") && !non_empty_array("subnets")
}

/// Parse an `az ... list -o json` array, tolerating an empty body.
fn parse_list(json: &str, what: &str) -> Result<Vec<serde_json::Value>> {
    let trimmed = json.trim();
    if trimmed.is_empty() {
        return Ok(Vec::new());
    }
    serde_json::from_str(trimmed).with_context(|| format!("Failed to parse {what} list JSON"))
}

/// Build the ordered teardown plan for a session.
///
/// Selection rules, in the order they are applied:
///
/// * **Disks and NICs** are selected by exact association with the target VM
///   (`managedBy` / `virtualMachine.id`), which is authoritative and needs no
///   tag.
/// * **Public IPs and NSGs** are selected only when their `azlin-session` tag
///   exactly equals the VM's, or — see `TeardownInputs::also_match_by_name`
///   — when they are tagged for *some* azlin session and their own name is
///   the Azure-default name for this exact VM. Untagged candidates are
///   skipped and reported — ownership cannot be proven, and deleting them
///   could destroy another session's resources.
/// * A Public IP or NSG still bound to something *outside* this teardown is
///   skipped as in-use. Being bound to this VM's own NIC does not disqualify
///   it, since that NIC is deleted first.
/// * VNets, subnets, and SSH public keys are never enumerated: shared
///   infrastructure is out of scope by construction.
pub fn plan_teardown(inputs: &TeardownInputs) -> Result<TeardownPlan> {
    let rg = inputs.resource_group;
    let mut plan = TeardownPlan {
        vm_exists: inputs.vm_exists,
        session_tag: inputs.session_tag.map(str::to_string),
        also_match_by_name: inputs.also_match_by_name.to_vec(),
        ..Default::default()
    };

    if inputs.vm_exists {
        plan.resources.push(TeardownResource {
            name: inputs.vm_name.to_string(),
            kind: TeardownKind::Vm,
            resource_group: rg.to_string(),
            estimated_monthly_cost: 0.0,
        });
    }

    // Disks owned by the target VM. `managedBy` is the authoritative owner
    // reference, so no tag is required.
    for disk in parse_list(inputs.disk_json, "disk")? {
        let owned = disk
            .get("managedBy")
            .and_then(|m| m.as_str())
            .map(|id| id_refers_to(id, inputs.vm_name))
            .unwrap_or(false);
        if !owned {
            continue;
        }
        if let Some((name, disk_rg)) = name_and_group(&disk, rg) {
            let size_gb = disk
                .get("diskSizeGb")
                .and_then(|s| s.as_f64())
                .unwrap_or(0.0);
            plan.resources.push(TeardownResource {
                name: name.to_string(),
                kind: TeardownKind::Disk,
                resource_group: disk_rg.to_string(),
                estimated_monthly_cost: size_gb * 0.04,
            });
        }
    }

    // NICs attached to the target VM. Collected separately as well, because a
    // Public IP or NSG bound only to one of these is safe to delete once the
    // NIC is gone.
    let mut target_nic_names: Vec<String> = Vec::new();
    for nic in parse_list(inputs.nic_json, "NIC")? {
        let attached = nic
            .get("virtualMachine")
            .and_then(|v| v.get("id"))
            .and_then(|id| id.as_str())
            .map(|id| id_refers_to(id, inputs.vm_name))
            .unwrap_or(false);
        if !attached {
            continue;
        }
        let Some((name, nic_rg)) = name_and_group(&nic, rg) else {
            continue;
        };
        target_nic_names.push(name.to_string());
        plan.resources.push(TeardownResource {
            name: name.to_string(),
            kind: TeardownKind::Nic,
            resource_group: nic_rg.to_string(),
            estimated_monthly_cost: 0.0,
        });
    }

    // True when every association points at a NIC this teardown already
    // removes, so the resource will be free by the time we reach it.
    let bound_only_to_target_nics = |ids: &[&str]| -> bool {
        ids.iter().all(|id| {
            resource_name_from_id(id)
                .map(|n| target_nic_names.iter().any(|t| t == n))
                .unwrap_or(false)
        })
    };

    for ip in parse_list(inputs.pip_json, "public IP")? {
        let Some((name, ip_rg)) = name_and_group(&ip, rg) else {
            continue;
        };
        // The NIC's ipConfiguration ID embeds the NIC name, e.g.
        // `.../networkInterfaces/<nic>/ipConfigurations/ipconfig1`, so strip
        // the trailing segment before comparing.
        let free = public_ip_is_unassociated(&ip)
            || ip
                .get("ipConfiguration")
                .and_then(|c| c.get("id"))
                .and_then(|id| id.as_str())
                .and_then(|id| id.rsplit_once("/ipConfigurations/").map(|(nic, _)| nic))
                .map(|nic_id| bound_only_to_target_nics(&[nic_id]))
                .unwrap_or(false);
        let name_hint = inputs.also_match_by_name.iter().any(|n| n == name);

        match classify(session_tag_of(&ip), inputs.session_tag, free, name_hint) {
            Candidate::Delete => plan.resources.push(TeardownResource {
                name: name.to_string(),
                kind: TeardownKind::PublicIp,
                resource_group: ip_rg.to_string(),
                estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
            }),
            Candidate::Skip(reason) => plan.skipped.push(SkippedResource {
                name: name.to_string(),
                kind: TeardownKind::PublicIp,
                reason,
            }),
            Candidate::Ignore => {}
        }
    }

    for nsg in parse_list(inputs.nsg_json, "NSG")? {
        let Some((name, nsg_rg)) = name_and_group(&nsg, rg) else {
            continue;
        };
        // A subnet association always disqualifies an NSG: subnets are shared
        // infrastructure that outlives any single session.
        let subnet_bound = nsg
            .get("subnets")
            .and_then(|v| v.as_array())
            .map(|a| !a.is_empty())
            .unwrap_or(false);
        let nic_ids: Vec<&str> = nsg
            .get("networkInterfaces")
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|n| n.get("id").and_then(|i| i.as_str()))
                    .collect()
            })
            .unwrap_or_default();
        let free =
            !subnet_bound && (nsg_is_unassociated(&nsg) || bound_only_to_target_nics(&nic_ids));
        let name_hint = inputs.also_match_by_name.iter().any(|n| n == name);

        match classify(session_tag_of(&nsg), inputs.session_tag, free, name_hint) {
            Candidate::Delete => plan.resources.push(TeardownResource {
                name: name.to_string(),
                kind: TeardownKind::Nsg,
                resource_group: nsg_rg.to_string(),
                estimated_monthly_cost: 0.0,
            }),
            Candidate::Skip(reason) => plan.skipped.push(SkippedResource {
                name: name.to_string(),
                kind: TeardownKind::Nsg,
                reason,
            }),
            Candidate::Ignore => {}
        }
    }

    plan.resources
        .sort_by_key(|r| (r.kind.deletion_order(), r.name.clone()));
    Ok(plan)
}

/// Outcome of evaluating one tag-matched candidate resource.
enum Candidate {
    Delete,
    Skip(SkipReason),
    /// Belongs to a different session, or to no azlin session at all — not our
    /// business and not worth reporting.
    Ignore,
}

/// Re-evaluate resources that the plan skipped as [`SkipReason::InUse`].
///
/// The teardown plan is computed once, before anything is deleted, from a
/// single snapshot of Azure state. A Public IP or NSG that is still bound to
/// the session's NIC at that moment is correctly identified as in-use, but the
/// first-pass escape hatch (`bound only to a NIC we are about to delete`) is
/// only as good as the association data Azure returns at snapshot time. If it
/// misreports — a lagging back-reference, an association recorded against a
/// resource the snapshot did not include — the resource is skipped permanently
/// and leaks, billing indefinitely.
///
/// This second pass closes that hole: after the NICs are gone, re-read the
/// Public IPs and NSGs and delete the ones that are *now* provably free. The
/// safety rules are unchanged and strictly narrower than the first pass — the
/// resource must still carry an exactly-matching `azlin-session` tag, must
/// have been part of the plan, and must have no association whatsoever.
pub fn plan_recheck(
    skipped: &[SkippedResource],
    session_tag: Option<&str>,
    resource_group: &str,
    pip_json: &str,
    nsg_json: &str,
    also_match_by_name: &[String],
) -> Result<Vec<TeardownResource>> {
    let was_skipped_in_use = |name: &str, kind: TeardownKind| {
        skipped
            .iter()
            .any(|s| s.name == name && s.kind == kind && s.reason == SkipReason::InUse)
    };
    // Same ownership rule as the first pass: an exact tag match, or a
    // resource that is tagged for *some* azlin session and whose own name
    // proves it belongs to this VM (see `TeardownInputs::also_match_by_name`).
    let is_owned = |resource_tag: Option<&str>, name: &str| {
        resource_tag == session_tag
            || (resource_tag.is_some() && also_match_by_name.iter().any(|n| n == name))
    };

    let mut freed = Vec::new();

    for ip in parse_list(pip_json, "public IP")? {
        let Some((name, ip_rg)) = name_and_group(&ip, resource_group) else {
            continue;
        };
        if !was_skipped_in_use(name, TeardownKind::PublicIp) {
            continue;
        }
        if !is_owned(session_tag_of(&ip), name) || !public_ip_is_unassociated(&ip) {
            continue;
        }
        freed.push(TeardownResource {
            name: name.to_string(),
            kind: TeardownKind::PublicIp,
            resource_group: ip_rg.to_string(),
            estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
        });
    }

    for nsg in parse_list(nsg_json, "NSG")? {
        let Some((name, nsg_rg)) = name_and_group(&nsg, resource_group) else {
            continue;
        };
        if !was_skipped_in_use(name, TeardownKind::Nsg) {
            continue;
        }
        if !is_owned(session_tag_of(&nsg), name) || !nsg_is_unassociated(&nsg) {
            continue;
        }
        freed.push(TeardownResource {
            name: name.to_string(),
            kind: TeardownKind::Nsg,
            resource_group: nsg_rg.to_string(),
            estimated_monthly_cost: 0.0,
        });
    }

    freed.sort_by_key(|r| (r.kind.deletion_order(), r.name.clone()));
    Ok(freed)
}

/// Decide the fate of a Public IP or NSG.
///
/// Tag-only matching: a resource is deletable only when its `azlin-session`
/// tag exactly equals the target session's. Exact equality means a
/// prefix-adjacent sibling session (`copilot-test-…` vs `copilot-test2-…`)
/// can never be matched by accident.
///
/// `name_hint` is a narrow escape hatch for `also_match_by_name`: when true,
/// the resource's own name has already been proven (by the caller) to be the
/// Azure-default name for *this exact* VM, so a mismatched tag value no
/// longer disqualifies it — only used for the pooled-session case where the
/// real tag can differ from any single member's VM name. A resource still
/// needs *some* `azlin-session` tag to be eligible; `name_hint` never
/// overrides the untagged case.
fn classify(
    resource_tag: Option<&str>,
    target_session: Option<&str>,
    is_free: bool,
    name_hint: bool,
) -> Candidate {
    match (resource_tag, target_session) {
        (Some(tag), Some(target)) if tag == target => {
            if is_free {
                Candidate::Delete
            } else {
                Candidate::Skip(SkipReason::InUse)
            }
        }
        // Tag didn't match exactly, but the resource's own name proves it
        // belongs to this VM (e.g. a pool member whose `azlin-session` tag is
        // the pool's base name, not its own VM name).
        (Some(_), _) if name_hint => {
            if is_free {
                Candidate::Delete
            } else {
                Candidate::Skip(SkipReason::InUse)
            }
        }
        // Tagged for a different session — leave it alone entirely.
        (Some(_), _) => Candidate::Ignore,
        // Untagged resources are never deleted. Report them only when they are
        // otherwise free, so the user learns about a potential leak without
        // being warned about healthy in-use infrastructure.
        (None, _) if is_free => Candidate::Skip(SkipReason::Untagged),
        (None, _) => Candidate::Ignore,
    }
}

/// Render a teardown plan for `--dry-run`.
pub fn format_teardown_plan(plan: &TeardownPlan, vm_name: &str, resource_group: &str) -> String {
    let mut out = String::new();

    if !plan.vm_exists {
        out.push_str(&format!(
            "VM '{vm_name}' was not found in resource group '{resource_group}'.\n"
        ));
    }

    if plan.resources.is_empty() {
        out.push_str("Dry run -- nothing to delete.\n");
    } else {
        out.push_str("Dry run -- would delete:\n");
        for r in &plan.resources {
            out.push_str(&format!("  {:<10} {}\n", format!("{}:", r.kind), r.name));
        }
        out.push_str(&format!("  Resource group: {resource_group}\n"));
        let savings = plan.estimated_monthly_savings();
        if savings > 0.0 {
            out.push_str(&format!("\n💰 Estimated savings: ${savings:.2}/month\n"));
        }
    }

    if !plan.skipped.is_empty() {
        out.push_str("\n⚠️  Not deleted (may remain and keep billing):\n");
        for s in &plan.skipped {
            out.push_str(&format!(
                "  {:<10} {} — {}\n",
                format!("{}:", s.kind),
                s.name,
                s.reason
            ));
        }
        out.push_str("  Run 'azlin cleanup' to review and reclaim orphaned resources.\n");
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const VM: &str = "copilot-test2-1784625385";
    const SESSION: &str = "copilot-test2";
    const RG: &str = "myvm_group";

    fn vm_id(name: &str) -> String {
        format!("/subscriptions/sub/resourceGroups/{RG}/providers/Microsoft.Compute/virtualMachines/{name}")
    }

    fn nic_id(name: &str) -> String {
        format!("/subscriptions/sub/resourceGroups/{RG}/providers/Microsoft.Network/networkInterfaces/{name}")
    }

    /// Public IP, NIC, disk and NSG for `VM`, all tagged for `SESSION`.
    fn full_inputs() -> (String, String, String, String) {
        let disks = format!(
            r#"[{{"name":"{VM}_OsDisk_1_abc","managedBy":"{}","resourceGroup":"{RG}","diskSizeGb":5,
                  "tags":{{"azlin-session":"{SESSION}"}}}},
                {{"name":"{VM}_home","managedBy":"{}","resourceGroup":"{RG}","diskSizeGb":100,
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            vm_id(VM),
            vm_id(VM)
        );
        let nics = format!(
            r#"[{{"name":"{VM}VMNic","resourceGroup":"{RG}","virtualMachine":{{"id":"{}"}},
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            vm_id(VM)
        );
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}",
                  "ipConfiguration":{{"id":"{}/ipConfigurations/ipconfig1"}},
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id(&format!("{VM}VMNic"))
        );
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":[],
                  "networkInterfaces":[{{"id":"{}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id(&format!("{VM}VMNic"))
        );
        (disks, nics, pips, nsgs)
    }

    fn plan_with(disks: &str, nics: &str, pips: &str, nsgs: &str) -> TeardownPlan {
        plan_teardown(&TeardownInputs {
            vm_name: VM,
            resource_group: RG,
            session_tag: Some(SESSION),
            vm_exists: true,
            disk_json: disks,
            nic_json: nics,
            pip_json: pips,
            nsg_json: nsgs,
            also_match_by_name: &[],
        })
        .unwrap()
    }

    fn default_plan() -> TeardownPlan {
        let (d, n, p, g) = full_inputs();
        plan_with(&d, &n, &p, &g)
    }

    // ── The core bug: IP and NSG must be in the teardown set ─────────────

    #[test]
    fn public_ip_is_included_in_teardown() {
        let plan = default_plan();
        let ips = plan.of_kind(TeardownKind::PublicIp);
        assert_eq!(ips.len(), 1, "public IP must be scheduled for deletion");
        assert_eq!(ips[0].name, format!("{VM}PublicIP"));
    }

    #[test]
    fn nsg_is_included_in_teardown() {
        let plan = default_plan();
        let nsgs = plan.of_kind(TeardownKind::Nsg);
        assert_eq!(nsgs.len(), 1, "NSG must be scheduled for deletion");
        assert_eq!(nsgs[0].name, format!("{VM}NSG"));
    }

    #[test]
    fn teardown_includes_vm_disks_nic_ip_and_nsg() {
        let plan = default_plan();
        assert_eq!(plan.of_kind(TeardownKind::Vm).len(), 1);
        assert_eq!(plan.of_kind(TeardownKind::Disk).len(), 2);
        assert_eq!(plan.of_kind(TeardownKind::Nic).len(), 1);
        assert_eq!(plan.of_kind(TeardownKind::PublicIp).len(), 1);
        assert_eq!(plan.of_kind(TeardownKind::Nsg).len(), 1);
    }

    #[test]
    fn leaked_public_ip_cost_is_reported() {
        let plan = default_plan();
        let ip = plan.of_kind(TeardownKind::PublicIp)[0];
        assert!((ip.estimated_monthly_cost - ORPHANED_PUBLIC_IP_MONTHLY_COST).abs() < 0.01);
    }

    // ── Ordering ────────────────────────────────────────────────────────

    #[test]
    fn nic_is_deleted_before_public_ip_and_nsg() {
        let plan = default_plan();
        let pos = |kind: TeardownKind| {
            plan.resources
                .iter()
                .position(|r| r.kind == kind)
                .unwrap_or_else(|| panic!("{kind} missing from plan"))
        };
        let nic = pos(TeardownKind::Nic);
        assert!(
            nic < pos(TeardownKind::PublicIp),
            "NIC must precede public IP or Azure rejects the delete as in-use"
        );
        assert!(
            nic < pos(TeardownKind::Nsg),
            "NIC must precede NSG or Azure rejects the delete as in-use"
        );
    }

    #[test]
    fn vm_is_deleted_first() {
        let plan = default_plan();
        assert_eq!(plan.resources[0].kind, TeardownKind::Vm);
    }

    #[test]
    fn deletion_order_is_strictly_increasing() {
        let plan = default_plan();
        let orders: Vec<u8> = plan
            .resources
            .iter()
            .map(|r| r.kind.deletion_order())
            .collect();
        let mut sorted = orders.clone();
        sorted.sort_unstable();
        assert_eq!(orders, sorted);
    }

    // ── The sibling-session hazard ──────────────────────────────────────

    #[test]
    fn prefix_adjacent_sibling_session_is_not_matched() {
        // `copilot-test-1783435804` is a prefix-adjacent sibling of
        // `copilot-test2-1784625385`. Naive prefix matching would delete the
        // wrong session's resources.
        let sibling_pips = r#"[
            {"name":"copilot-test-1783435804PublicIP","resourceGroup":"myvm_group",
             "ipConfiguration":null,"tags":{"azlin-session":"copilot-test"}}
        ]"#;
        let sibling_nsgs = r#"[
            {"name":"copilot-test-1783435804NSG","resourceGroup":"myvm_group",
             "subnets":[],"networkInterfaces":[],"tags":{"azlin-session":"copilot-test"}}
        ]"#;
        let plan = plan_with("[]", "[]", sibling_pips, sibling_nsgs);
        assert!(
            plan.of_kind(TeardownKind::PublicIp).is_empty(),
            "sibling session's public IP must never be deleted"
        );
        assert!(
            plan.of_kind(TeardownKind::Nsg).is_empty(),
            "sibling session's NSG must never be deleted"
        );
        assert!(
            plan.skipped.is_empty(),
            "another session's resources are not our business to warn about"
        );
    }

    #[test]
    fn sibling_disk_with_prefix_adjacent_name_is_not_matched() {
        let disks = format!(
            r#"[{{"name":"copilot-test-1783435804_home","managedBy":"{}",
                  "resourceGroup":"{RG}","diskSizeGb":100}}]"#,
            vm_id("copilot-test-1783435804")
        );
        let plan = plan_with(&disks, "[]", "[]", "[]");
        assert!(plan.of_kind(TeardownKind::Disk).is_empty());
    }

    #[test]
    fn sibling_nic_is_not_matched() {
        let nics = format!(
            r#"[{{"name":"copilot-test-1783435804VMNic","resourceGroup":"{RG}",
                  "virtualMachine":{{"id":"{}"}}}}]"#,
            vm_id("copilot-test-1783435804")
        );
        let plan = plan_with("[]", &nics, "[]", "[]");
        assert!(plan.of_kind(TeardownKind::Nic).is_empty());
    }

    // ── In-use resources are never deleted ──────────────────────────────

    #[test]
    fn public_ip_associated_with_foreign_nic_is_skipped() {
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}",
                  "ipConfiguration":{{"id":"{}/ipConfigurations/ipconfig1"}},
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id("someone-elses-nic")
        );
        let plan = plan_with("[]", "[]", &pips, "[]");
        assert!(
            plan.of_kind(TeardownKind::PublicIp).is_empty(),
            "an in-use public IP must not be deleted"
        );
        assert_eq!(plan.skipped.len(), 1);
        assert_eq!(plan.skipped[0].reason, SkipReason::InUse);
    }

    #[test]
    fn nsg_attached_to_subnet_is_skipped_as_shared_infrastructure() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}",
                  "subnets":[{{"id":"/subscriptions/sub/.../subnets/default"}}],
                  "networkInterfaces":[],"tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let plan = plan_with("[]", "[]", "[]", &nsgs);
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        assert_eq!(plan.skipped[0].reason, SkipReason::InUse);
    }

    #[test]
    fn nsg_attached_to_foreign_nic_is_skipped() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":[],
                  "networkInterfaces":[{{"id":"{}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id("someone-elses-nic")
        );
        let plan = plan_with("[]", "[]", "[]", &nsgs);
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        assert_eq!(plan.skipped[0].reason, SkipReason::InUse);
    }

    #[test]
    fn public_ip_bound_to_our_own_nic_is_still_deleted() {
        // Association with the NIC we are about to delete must not disqualify
        // the IP — otherwise teardown would never reclaim anything.
        let plan = default_plan();
        assert_eq!(plan.of_kind(TeardownKind::PublicIp).len(), 1);
    }

    // ── Tag-only matching ───────────────────────────────────────────────

    #[test]
    fn untagged_public_ip_is_skipped_not_deleted() {
        let pips =
            format!(r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null}}]"#);
        let plan = plan_with("[]", "[]", &pips, "[]");
        assert!(
            plan.of_kind(TeardownKind::PublicIp).is_empty(),
            "ownership is unproven without a tag — must not delete"
        );
        assert_eq!(plan.skipped.len(), 1);
        assert_eq!(plan.skipped[0].reason, SkipReason::Untagged);
    }

    #[test]
    fn untagged_nsg_is_skipped_not_deleted() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":[],"networkInterfaces":[]}}]"#
        );
        let plan = plan_with("[]", "[]", "[]", &nsgs);
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        assert_eq!(plan.skipped[0].reason, SkipReason::Untagged);
    }

    #[test]
    fn untagged_but_in_use_resource_is_not_warned_about() {
        // `myvm-ip` in the real subscription: untagged and healthily attached
        // to an unrelated VM. Warning about it would be noise.
        let pips = r#"[{"name":"myvm-ip","resourceGroup":"myvm_group",
                        "ipConfiguration":{"id":"/subscriptions/s/resourceGroups/myvm_group/providers/Microsoft.Network/networkInterfaces/myvm693_z1/ipConfigurations/ipconfig1"}}]"#;
        let plan = plan_with("[]", "[]", pips, "[]");
        assert!(plan
            .resources
            .iter()
            .all(|r| r.kind != TeardownKind::PublicIp));
        assert!(plan.skipped.is_empty());
    }

    #[test]
    fn no_session_tag_on_vm_means_no_ip_or_nsg_deleted() {
        let (d, n, p, g) = full_inputs();
        let plan = plan_teardown(&TeardownInputs {
            vm_name: VM,
            resource_group: RG,
            session_tag: None,
            vm_exists: true,
            disk_json: &d,
            nic_json: &n,
            pip_json: &p,
            nsg_json: &g,
            also_match_by_name: &[],
        })
        .unwrap();
        assert!(plan.of_kind(TeardownKind::PublicIp).is_empty());
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        // Disks and NIC are still safe: association is authoritative.
        assert_eq!(plan.of_kind(TeardownKind::Disk).len(), 2);
        assert_eq!(plan.of_kind(TeardownKind::Nic).len(), 1);
    }

    // ── Shared infrastructure is never enumerated ───────────────────────

    #[test]
    fn vnets_and_ssh_keys_are_never_in_the_plan() {
        let plan = default_plan();
        assert!(plan
            .resources
            .iter()
            .all(|r| !r.name.to_lowercase().contains("vnet")));
        assert!(plan.resources.iter().all(|r| matches!(
            r.kind,
            TeardownKind::Vm
                | TeardownKind::Disk
                | TeardownKind::Nic
                | TeardownKind::PublicIp
                | TeardownKind::Nsg
        )));
    }

    // ── Missing VM ──────────────────────────────────────────────────────

    #[test]
    fn absent_vm_still_reports_leftover_tagged_resources() {
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let plan = plan_teardown(&TeardownInputs {
            vm_name: VM,
            resource_group: RG,
            session_tag: Some(SESSION),
            vm_exists: false,
            disk_json: "[]",
            nic_json: "[]",
            pip_json: &pips,
            nsg_json: "[]",
            also_match_by_name: &[],
        })
        .unwrap();
        assert!(!plan.vm_exists);
        assert!(plan.of_kind(TeardownKind::Vm).is_empty());
        assert_eq!(plan.of_kind(TeardownKind::PublicIp).len(), 1);
    }

    // ── Robustness ──────────────────────────────────────────────────────

    #[test]
    fn empty_and_blank_json_are_tolerated() {
        for body in ["[]", "", "   "] {
            let plan = plan_with(body, body, body, body);
            assert_eq!(plan.resources.len(), 1, "only the VM itself");
        }
    }

    #[test]
    fn malformed_json_is_an_error() {
        assert!(plan_teardown(&TeardownInputs {
            vm_name: VM,
            resource_group: RG,
            session_tag: Some(SESSION),
            vm_exists: true,
            disk_json: "not json",
            nic_json: "[]",
            pip_json: "[]",
            nsg_json: "[]",
            also_match_by_name: &[],
        })
        .is_err());
    }

    #[test]
    fn empty_session_tag_is_treated_as_untagged() {
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
                  "tags":{{"azlin-session":""}}}}]"#
        );
        let plan = plan_with("[]", "[]", &pips, "[]");
        assert!(plan.of_kind(TeardownKind::PublicIp).is_empty());
        assert_eq!(plan.skipped[0].reason, SkipReason::Untagged);
    }

    #[test]
    fn resource_group_falls_back_to_target_when_absent() {
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","ipConfiguration":null,
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let plan = plan_with("[]", "[]", &pips, "[]");
        assert_eq!(plan.of_kind(TeardownKind::PublicIp)[0].resource_group, RG);
    }

    // ── Association predicates (shared with cleanup) ────────────────────

    #[test]
    fn public_ip_association_predicate() {
        let free: serde_json::Value = serde_json::json!({"ipConfiguration": null});
        let bound: serde_json::Value = serde_json::json!({"ipConfiguration": {"id": "x"}});
        assert!(public_ip_is_unassociated(&free));
        assert!(!public_ip_is_unassociated(&bound));
        assert!(public_ip_is_unassociated(&serde_json::json!({})));
    }

    #[test]
    fn nsg_association_predicate() {
        assert!(nsg_is_unassociated(&serde_json::json!({
            "networkInterfaces": [], "subnets": []
        })));
        assert!(!nsg_is_unassociated(&serde_json::json!({
            "networkInterfaces": [{"id": "n"}], "subnets": []
        })));
        assert!(!nsg_is_unassociated(&serde_json::json!({
            "networkInterfaces": [], "subnets": [{"id": "s"}]
        })));
        assert!(nsg_is_unassociated(&serde_json::json!({})));
    }

    // ── Dry-run rendering ───────────────────────────────────────────────

    #[test]
    fn dry_run_enumerates_every_resource() {
        let out = format_teardown_plan(&default_plan(), VM, RG);
        assert!(out.contains(VM));
        assert!(out.contains(&format!("{VM}VMNic")));
        assert!(out.contains(&format!("{VM}PublicIP")));
        assert!(out.contains(&format!("{VM}NSG")));
        assert!(out.contains(&format!("{VM}_home")));
        assert!(out.contains("Resource group: myvm_group"));
    }

    #[test]
    fn dry_run_reports_estimated_savings() {
        let out = format_teardown_plan(&default_plan(), VM, RG);
        assert!(out.contains("Estimated savings"));
        assert!(out.contains("$3.65") || out.contains("/month"));
    }

    #[test]
    fn dry_run_states_clearly_when_vm_is_absent() {
        let plan = TeardownPlan {
            vm_exists: false,
            ..Default::default()
        };
        let out = format_teardown_plan(&plan, VM, RG);
        assert!(out.contains("not found"));
        assert!(out.contains("nothing to delete"));
    }

    #[test]
    fn dry_run_warns_about_skipped_resources() {
        let plan = TeardownPlan {
            resources: vec![],
            skipped: vec![SkippedResource {
                name: format!("{VM}PublicIP"),
                kind: TeardownKind::PublicIp,
                reason: SkipReason::Untagged,
            }],
            vm_exists: true,
            session_tag: Some(SESSION.to_string()),
            also_match_by_name: Vec::new(),
        };
        let out = format_teardown_plan(&plan, VM, RG);
        assert!(out.contains("Not deleted"));
        assert!(out.contains(&format!("{VM}PublicIP")));
        assert!(out.contains("azlin cleanup"));
    }

    #[test]
    fn kind_display_strings() {
        assert_eq!(TeardownKind::Vm.to_string(), "VM");
        assert_eq!(TeardownKind::Disk.to_string(), "Disk");
        assert_eq!(TeardownKind::Nic.to_string(), "NIC");
        assert_eq!(TeardownKind::PublicIp.to_string(), "Public IP");
        assert_eq!(TeardownKind::Nsg.to_string(), "NSG");
    }

    #[test]
    fn resource_name_extraction_ignores_trailing_slash() {
        assert_eq!(resource_name_from_id("/a/b/c"), Some("c"));
        assert_eq!(resource_name_from_id("/a/b/c/"), Some("c"));
        assert_eq!(resource_name_from_id(""), None);
    }

    // ── The NSG leak: association must be re-evaluated after NIC deletion ─

    /// The exact shape observed in the live provision test: an NSG whose only
    /// association is the NIC being torn down must be planned for deletion.
    #[test]
    fn nsg_bound_only_to_target_nic_is_deleted() {
        let plan = default_plan();
        assert_eq!(plan.of_kind(TeardownKind::Nsg).len(), 1);
        assert!(plan.skipped.is_empty());
    }

    /// `subnets: null` is what Azure actually returns for an unassociated
    /// subnet list, not `[]`. It must not be read as an association.
    #[test]
    fn nsg_with_null_subnets_and_target_nic_is_deleted() {
        let (d, n, p, _) = full_inputs();
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":[{{"id":"{}","resourceGroup":"{RG}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id(&format!("{VM}VMNic"))
        );
        let plan = plan_with(&d, &n, &p, &nsgs);
        assert_eq!(plan.of_kind(TeardownKind::Nsg).len(), 1);
    }

    /// An NSG shared with a live NIC outside this session must survive.
    #[test]
    fn nsg_bound_to_unrelated_live_nic_is_skipped() {
        let (d, n, p, _) = full_inputs();
        let nics = format!(
            r#"[{{"name":"{VM}VMNic","resourceGroup":"{RG}","virtualMachine":{{"id":"{}"}}}},
                 {{"name":"someone-elses-nic","resourceGroup":"{RG}",
                   "virtualMachine":{{"id":"{}"}}}}]"#,
            vm_id(VM),
            vm_id("someone-elses-vm")
        );
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":[{{"id":"{}"}},{{"id":"{}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id(&format!("{VM}VMNic")),
            nic_id("someone-elses-nic")
        );
        let plan = plan_with(&d, &nics, &p, &nsgs);
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        assert!(plan
            .skipped
            .iter()
            .any(|s| s.kind == TeardownKind::Nsg && s.reason == SkipReason::InUse));
    }

    /// A subnet association is shared infrastructure and always disqualifying,
    /// even when the NIC side is entirely ours.
    #[test]
    fn nsg_bound_to_subnet_is_skipped() {
        let (d, n, p, _) = full_inputs();
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}",
                  "subnets":[{{"id":"/subscriptions/s/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworks/v/subnets/default"}}],
                  "networkInterfaces":[{{"id":"{}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id(&format!("{VM}VMNic"))
        );
        let plan = plan_with(&d, &n, &p, &nsgs);
        assert!(plan.of_kind(TeardownKind::Nsg).is_empty());
        assert!(plan
            .skipped
            .iter()
            .any(|s| s.kind == TeardownKind::Nsg && s.reason == SkipReason::InUse));
    }

    // ── plan_recheck: the second pass that closes the leak ───────────────

    fn skipped_nsg() -> Vec<SkippedResource> {
        vec![SkippedResource {
            name: format!("{VM}NSG"),
            kind: TeardownKind::Nsg,
            reason: SkipReason::InUse,
        }]
    }

    /// The live failure, end to end: an NSG skipped as in-use, which the NIC
    /// deletion then frees, must be picked up and deleted by the re-check.
    #[test]
    fn recheck_deletes_nsg_freed_by_nic_deletion() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":null,"tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let freed = plan_recheck(&skipped_nsg(), Some(SESSION), RG, "[]", &nsgs, &[]).unwrap();
        assert_eq!(freed.len(), 1);
        assert_eq!(freed[0].kind, TeardownKind::Nsg);
        assert_eq!(freed[0].name, format!("{VM}NSG"));
    }

    /// The re-check must never widen ownership: an NSG that is now free but
    /// belongs to another session stays untouched.
    #[test]
    fn recheck_ignores_other_sessions_nsg() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":null,"tags":{{"azlin-session":"someone-else"}}}}]"#
        );
        let freed = plan_recheck(&skipped_nsg(), Some(SESSION), RG, "[]", &nsgs, &[]).unwrap();
        assert!(freed.is_empty());
    }

    /// Still genuinely associated after the NICs are gone — leave it alone.
    #[test]
    fn recheck_leaves_still_associated_nsg() {
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":[{{"id":"{}"}}],
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#,
            nic_id("someone-elses-nic")
        );
        let freed = plan_recheck(&skipped_nsg(), Some(SESSION), RG, "[]", &nsgs, &[]).unwrap();
        assert!(freed.is_empty());
    }

    /// The re-check only ever revisits what the plan itself skipped as in-use;
    /// an unrelated free NSG in the same group is not swept up.
    #[test]
    fn recheck_ignores_resources_not_in_the_plan() {
        let nsgs = format!(
            r#"[{{"name":"unrelated-nsg","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":null,"tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let freed = plan_recheck(&skipped_nsg(), Some(SESSION), RG, "[]", &nsgs, &[]).unwrap();
        assert!(freed.is_empty());
    }

    /// Untagged skips are a different failure mode and must not be revisited.
    #[test]
    fn recheck_ignores_untagged_skips() {
        let skipped = vec![SkippedResource {
            name: format!("{VM}NSG"),
            kind: TeardownKind::Nsg,
            reason: SkipReason::Untagged,
        }];
        let nsgs = format!(
            r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":null,"tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let freed = plan_recheck(&skipped, Some(SESSION), RG, "[]", &nsgs, &[]).unwrap();
        assert!(freed.is_empty());
    }

    /// The same second-pass guarantee applies to a Public IP.
    #[test]
    fn recheck_deletes_public_ip_freed_by_nic_deletion() {
        let skipped = vec![SkippedResource {
            name: format!("{VM}PublicIP"),
            kind: TeardownKind::PublicIp,
            reason: SkipReason::InUse,
        }];
        let pips = format!(
            r#"[{{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
                  "tags":{{"azlin-session":"{SESSION}"}}}}]"#
        );
        let freed = plan_recheck(&skipped, Some(SESSION), RG, &pips, "[]", &[]).unwrap();
        assert_eq!(freed.len(), 1);
        assert_eq!(freed[0].kind, TeardownKind::PublicIp);
    }

    /// The plan carries the tag it matched on, so the re-check can apply the
    /// identical ownership rule without re-deriving it.
    #[test]
    fn plan_retains_session_tag_for_recheck() {
        assert_eq!(default_plan().session_tag.as_deref(), Some(SESSION));
    }

    // ── Pooled sessions: name-hint fallback when the VM is already gone ──
    //
    // `azlin new --name my-dev-pool --pool 3` tags every member's Public IP
    // and NSG with `azlin-session=my-dev-pool` — the pool's base name, not
    // the member's own VM name (`my-dev-pool-1`, `my-dev-pool-2`, ...). See
    // `resolve_session_identity` in `azlin/src/create_helpers.rs`. When a
    // pool member's VM has already been deleted, its true tag cannot be read
    // live, so the caller can only *guess* `session_tag = vm_name` — which
    // never equals the real pool tag. `also_match_by_name` is the escape
    // hatch that recovers ownership from the resource's own Azure-default
    // name instead.

    const POOL_VM: &str = "my-dev-pool-1";
    const POOL_TAG: &str = "my-dev-pool";

    #[test]
    fn pool_member_orphan_is_recovered_by_name_hint_when_vm_absent_and_tag_mismatches() {
        let pips = format!(
            r#"[{{"name":"{POOL_VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
                  "tags":{{"azlin-session":"{POOL_TAG}"}}}}]"#
        );
        let nsgs = format!(
            r#"[{{"name":"{POOL_VM}NSG","resourceGroup":"{RG}","subnets":[],
                  "networkInterfaces":[],"tags":{{"azlin-session":"{POOL_TAG}"}}}}]"#
        );
        let hints = vec![format!("{POOL_VM}PublicIP"), format!("{POOL_VM}NSG")];
        let plan = plan_teardown(&TeardownInputs {
            vm_name: POOL_VM,
            resource_group: RG,
            // The caller's best guess once the VM is gone: never equal to the
            // real pool tag `POOL_TAG`.
            session_tag: Some(POOL_VM),
            vm_exists: false,
            disk_json: "[]",
            nic_json: "[]",
            pip_json: &pips,
            nsg_json: &nsgs,
            also_match_by_name: &hints,
        })
        .unwrap();
        assert_eq!(
            plan.of_kind(TeardownKind::PublicIp).len(),
            1,
            "the pool member's own public IP must be recovered despite the tag mismatch"
        );
        assert_eq!(
            plan.of_kind(TeardownKind::Nsg).len(),
            1,
            "the pool member's own NSG must be recovered despite the tag mismatch"
        );
        assert!(
            plan.skipped.is_empty(),
            "a correctly name-matched, free resource is deleted outright, not warned about"
        );
    }

    #[test]
    fn pool_sibling_is_not_matched_by_another_members_name_hint() {
        // `my-dev-pool-2` shares the same `azlin-session` tag as `my-dev-pool-1`
        // (both are members of the same pool), but its resources are outside
        // this teardown's `also_match_by_name` hints, which only ever name
        // `my-dev-pool-1`'s own resources.
        let pips = format!(
            r#"[{{"name":"my-dev-pool-2PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
                  "tags":{{"azlin-session":"{POOL_TAG}"}}}}]"#
        );
        let hints = vec![format!("{POOL_VM}PublicIP"), format!("{POOL_VM}NSG")];
        let plan = plan_teardown(&TeardownInputs {
            vm_name: POOL_VM,
            resource_group: RG,
            session_tag: Some(POOL_VM),
            vm_exists: false,
            disk_json: "[]",
            nic_json: "[]",
            pip_json: &pips,
            nsg_json: "[]",
            also_match_by_name: &hints,
        })
        .unwrap();
        assert!(
            plan.of_kind(TeardownKind::PublicIp).is_empty(),
            "a sibling pool member's public IP must never be swept up"
        );
        assert!(plan.skipped.is_empty());
    }

    #[test]
    fn name_hint_does_not_rescue_a_genuinely_untagged_resource() {
        // A coincidentally-named, hand-made resource with no azlin tag at
        // all must stay conservative: reported, never deleted.
        let pips = format!(
            r#"[{{"name":"{POOL_VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null}}]"#
        );
        let hints = vec![format!("{POOL_VM}PublicIP")];
        let plan = plan_teardown(&TeardownInputs {
            vm_name: POOL_VM,
            resource_group: RG,
            session_tag: Some(POOL_VM),
            vm_exists: false,
            disk_json: "[]",
            nic_json: "[]",
            pip_json: &pips,
            nsg_json: "[]",
            also_match_by_name: &hints,
        })
        .unwrap();
        assert!(
            plan.of_kind(TeardownKind::PublicIp).is_empty(),
            "name alone is not proof of azlin ownership"
        );
        assert_eq!(plan.skipped[0].reason, SkipReason::Untagged);
    }

    #[test]
    fn recheck_deletes_pool_member_nsg_via_name_hint_despite_tag_mismatch() {
        let skipped = vec![SkippedResource {
            name: format!("{POOL_VM}NSG"),
            kind: TeardownKind::Nsg,
            reason: SkipReason::InUse,
        }];
        let nsgs = format!(
            r#"[{{"name":"{POOL_VM}NSG","resourceGroup":"{RG}","subnets":null,
                  "networkInterfaces":null,"tags":{{"azlin-session":"{POOL_TAG}"}}}}]"#
        );
        let hints = vec![format!("{POOL_VM}NSG")];
        let freed = plan_recheck(&skipped, Some(POOL_VM), RG, "[]", &nsgs, &hints).unwrap();
        assert_eq!(freed.len(), 1);
        assert_eq!(freed[0].name, format!("{POOL_VM}NSG"));
    }
}
