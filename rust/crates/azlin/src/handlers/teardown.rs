//! Session teardown — delete a VM together with every resource it owns.
//!
//! `az vm delete` removes only the VM. Disks and the NIC vanish because
//! `az vm create` sets their `deleteOption` to `Delete`, but Azure has no
//! equivalent for the Public IP or the NSG. Those were previously left behind
//! on every `destroy`/`delete`/`kill`, silently accruing charges (a Standard
//! static public IP bills even while unassociated).
//!
//! The selection and ordering rules live in [`azlin_azure::teardown`] as pure
//! functions; this module is the thin execution layer around them.

use anyhow::{Context, Result};
use azlin_azure::teardown::{
    format_teardown_plan, plan_recheck, plan_teardown, SkipReason, TeardownInputs, TeardownKind,
    TeardownPlan, TeardownResource, SESSION_TAG_KEY,
};
use azlin_azure::AzureOps;

/// Gather Azure state and compute the teardown plan for `vm_name`.
///
/// Performs only read operations, so it is safe to call from `--dry-run`.
pub fn build_teardown_plan(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
) -> Result<TeardownPlan> {
    // A missing VM is not an error: the caller may be cleaning up after a
    // partially-completed teardown, which is exactly the leak scenario.
    let vm = ops.get_vm(resource_group, vm_name).ok();
    let vm_exists = vm.is_some();
    let (session_tag, name_hints): (Option<String>, Vec<String>) = match vm.as_ref() {
        Some(vm) => (
            vm.tags
                .get(SESSION_TAG_KEY)
                .filter(|s| !s.is_empty())
                .cloned(),
            Vec::new(),
        ),
        // The VM is already gone, so its tag cannot be read — but its Public
        // IP and NSG may still be orphaned and billing. For a single VM
        // (not part of a pool), `azlin-session` is stamped with the VM's own
        // name, so guessing that as the tag is usually right. But pooled
        // sessions (`azlin new --name X --pool N`) stamp every member's tag
        // with the pool's base name `X`, not the member's own name (`X-1`,
        // `X-2`, ...; see `resolve_session_identity` in `create_helpers.rs`).
        // For those, this guess never matches the real tag, and tag-only
        // matching would silently leak the member's own Public IP/NSG
        // forever with no warning. `also_match_by_name` closes that gap: a
        // resource still needs *some* azlin-session tag, but no longer needs
        // it to equal this guess, as long as its own name is the
        // Azure-default name for exactly this VM.
        None => (
            Some(vm_name.to_string()),
            vec![format!("{vm_name}PublicIP"), format!("{vm_name}NSG")],
        ),
    };

    let disk_json = ops
        .list_disks_json(resource_group)
        .context("Failed to list disks for teardown")?;
    let nic_json = ops
        .list_nics_json(resource_group)
        .context("Failed to list NICs for teardown")?;
    let pip_json = ops
        .list_public_ips_json(resource_group)
        .context("Failed to list public IPs for teardown")?;
    let nsg_json = ops
        .list_nsgs_json(resource_group)
        .context("Failed to list NSGs for teardown")?;

    plan_teardown(&TeardownInputs {
        vm_name,
        resource_group,
        session_tag: session_tag.as_deref(),
        vm_exists,
        disk_json: &disk_json,
        nic_json: &nic_json,
        pip_json: &pip_json,
        nsg_json: &nsg_json,
        also_match_by_name: &name_hints,
    })
}

/// Render the `--dry-run` preview for a teardown.
///
/// Unlike the previous implementation, this validates against real Azure state:
/// it reports clearly when the VM does not exist, and still lists any leftover
/// tagged resources belonging to that session.
pub fn format_destroy_dry_run_live(
    ops: &dyn AzureOps,
    resource_group: &str,
    vm_name: &str,
) -> Result<String> {
    let plan = build_teardown_plan(ops, resource_group, vm_name)?;
    Ok(format_teardown_plan(&plan, vm_name, resource_group))
}

/// Delete every resource in the plan, in dependency order.
///
/// Individual failures are collected rather than aborting, so one stuck
/// resource cannot strand the rest and re-leak them. Deletes are 404-tolerant,
/// making the whole operation idempotent and safe to re-run.
pub fn execute_teardown(ops: &dyn AzureOps, resource_group: &str, vm_name: &str) -> Result<String> {
    let mut plan = build_teardown_plan(ops, resource_group, vm_name)?;

    if plan.resources.is_empty() {
        let mut msg = if plan.vm_exists {
            format!("Nothing to delete for '{vm_name}'")
        } else {
            format!("VM '{vm_name}' not found in '{resource_group}' — nothing to delete")
        };
        msg.push_str(&format_skipped_warning(&plan));
        return Ok(msg);
    }

    let mut deleted = 0usize;
    let mut failures: Vec<String> = Vec::new();

    for r in &plan.resources {
        let outcome = match r.kind {
            TeardownKind::Vm => ops.delete_vm(&r.resource_group, &r.name),
            TeardownKind::Disk => ops.delete_disk(&r.resource_group, &r.name),
            TeardownKind::Nic => ops.delete_nic(&r.resource_group, &r.name),
            TeardownKind::PublicIp => ops.delete_public_ip(&r.resource_group, &r.name),
            TeardownKind::Nsg => ops.delete_nsg(&r.resource_group, &r.name),
        };
        match outcome {
            Ok(()) => deleted += 1,
            Err(e) => failures.push(format!("{} '{}': {}", r.kind, r.name, e)),
        }
    }

    // Anything skipped as in-use was judged against a snapshot taken before a
    // single resource was deleted. Now that the NICs are gone, re-read Azure
    // and delete whatever is provably free — otherwise a Public IP or NSG that
    // was merely held by this session's own NIC leaks and bills forever.
    let recheck = recheck_freed_resources(ops, resource_group, &plan);
    for r in &recheck {
        let outcome = match r.kind {
            TeardownKind::PublicIp => ops.delete_public_ip(&r.resource_group, &r.name),
            TeardownKind::Nsg => ops.delete_nsg(&r.resource_group, &r.name),
            _ => continue,
        };
        match outcome {
            Ok(()) => deleted += 1,
            Err(e) => failures.push(format!("{} '{}': {}", r.kind, r.name, e)),
        }
    }
    plan.resources.extend(recheck.iter().cloned());
    plan.skipped
        .retain(|s| !recheck.iter().any(|r| r.name == s.name && r.kind == s.kind));

    if !failures.is_empty() {
        anyhow::bail!(
            "Deleted {deleted} of {} resource(s) for '{vm_name}'; \
             {} failed and may still be billing:\n  {}\n\
             Run 'azlin cleanup' to retry the remainder.",
            plan.resources.len(),
            failures.len(),
            failures.join("\n  ")
        );
    }

    // The VM itself is only ever in the plan when it still existed at
    // discovery time — e.g. re-running destroy to mop up a pool member's
    // leftover Public IP/NSG after its VM is already gone has no `Vm` entry
    // at all. Subtracting 1 unconditionally would then undercount every
    // associated resource actually deleted.
    let had_vm = plan.resources.iter().any(|r| r.kind == TeardownKind::Vm);
    let associated = if had_vm { deleted.saturating_sub(1) } else { deleted };
    let savings = plan.estimated_monthly_savings();
    let mut msg = if had_vm {
        format!("Deleted {vm_name} and {associated} associated resource(s)")
    } else {
        format!("VM '{vm_name}' was already gone; reclaimed {associated} orphaned resource(s)")
    };
    if savings > 0.0 {
        msg.push_str(&format!(" (~${savings:.2}/month reclaimed)"));
    }
    msg.push_str(&format_skipped_warning(&plan));
    Ok(msg)
}

/// Append a warning about resources deliberately left in place.
///
/// Untagged resources are never deleted automatically — ownership cannot be
/// proven, and guessing risks destroying a hand-made resource that merely
/// shares a resource group.
fn format_skipped_warning(plan: &TeardownPlan) -> String {
    if plan.skipped.is_empty() {
        return String::new();
    }
    let mut out = String::from("\n⚠️  Left in place (may keep billing):");
    for s in &plan.skipped {
        out.push_str(&format!("\n  {} {} — {}", s.kind, s.name, s.reason));
    }
    out.push_str("\n  Run 'azlin cleanup' to review and reclaim orphaned resources.");
    out
}

/// Re-read Azure after the NICs are gone and return the previously in-use
/// Public IPs and NSGs that are now provably free.
///
/// Best-effort by design: a failure here must never mask the teardown that
/// already succeeded, so read errors yield an empty list and the resources
/// stay reported as skipped.
fn recheck_freed_resources(
    ops: &dyn AzureOps,
    resource_group: &str,
    plan: &TeardownPlan,
) -> Vec<TeardownResource> {
    let needs_recheck = plan
        .skipped
        .iter()
        .any(|s| s.reason == SkipReason::InUse);
    if !needs_recheck {
        return Vec::new();
    }

    let (Ok(pip_json), Ok(nsg_json)) = (
        ops.list_public_ips_json(resource_group),
        ops.list_nsgs_json(resource_group),
    ) else {
        return Vec::new();
    };

    plan_recheck(
        &plan.skipped,
        plan.session_tag.as_deref(),
        resource_group,
        &pip_json,
        &nsg_json,
        &plan.also_match_by_name,
    )
    .unwrap_or_default()
}
