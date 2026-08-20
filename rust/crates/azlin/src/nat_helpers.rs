//! NAT gateway provisioning for private (bastion-routed) VMs — see issue #1092.
//!
//! Azure Bastion is **inbound only**: it lets you reach a VM that has no public
//! IP. It provides no outbound internet. A private VM in a region without a NAT
//! gateway therefore has zero egress: it connects fine via `azlin connect`, but
//! every `apt`/`curl`/`wget` fails and the whole cloud-init toolchain install
//! collapses silently.
//!
//! This module mirrors [`crate::bastion_helpers`]: naming conventions, pure
//! `az` argv builders, and an idempotent orchestrator. The NAT gateway attaches
//! to the VM subnet (`default`) of the bastion VNet — **never** to
//! `AzureBastionSubnet`, which Azure rejects and which would be inbound-only
//! anyway.

use anyhow::Result;

/// The VM subnet inside the bastion VNet. Created by
/// [`crate::bastion_helpers::build_create_vnet_args`] as `--subnet-name default`.
const VM_SUBNET: &str = "default";

/// Verified-working idle timeout, in minutes, from the live subscription.
const IDLE_TIMEOUT_MINUTES: &str = "10";

// ── Naming conventions ───────────────────────────────────────────────

/// Return the canonical NAT gateway name for a given Azure region.
pub fn natgw_name_for_region(region: &str) -> String {
    format!("azlin-natgw-{}", region.to_lowercase())
}

/// Return the canonical NAT gateway SNAT public IP name for a given region.
///
/// The suffix is `-ip-tagged`, not the bastion's `-pip`: this matches the
/// resource already deployed and verified working, and keeps the two address
/// name spaces from colliding.
pub fn natgw_pip_name(region: &str) -> String {
    format!("azlin-natgw-{}-ip-tagged", region.to_lowercase())
}

// ── Input validation ─────────────────────────────────────────────────

/// Normalize and validate an Azure region name.
///
/// `region` reaches `az` as the value of `--location` and is interpolated into
/// resource names. It arrives unvalidated from `azlin new --region` and from
/// template files, so a leading `-` (which `az` would read as a flag) or a
/// shell metacharacter must be rejected here rather than trusted.
pub fn normalize_region(region: &str) -> Result<String> {
    let lowered = region.to_lowercase();
    if lowered.len() < 2 || lowered.len() > 32 {
        anyhow::bail!(
            "invalid Azure region '{region}': expected 2-32 characters \
             (e.g. 'southcentralus')"
        );
    }
    if !lowered.chars().all(|c| c.is_ascii_alphanumeric()) {
        anyhow::bail!(
            "invalid Azure region '{region}': expected letters and digits only \
             (e.g. 'southcentralus')"
        );
    }
    Ok(lowered)
}

/// Validate an Azure resource group name.
///
/// Azure permits alphanumerics, `_`, `-`, `.` and parentheses, up to 90
/// characters, and forbids a trailing period. The value is passed straight to
/// `--resource-group`, so a leading `-` is rejected as well.
pub fn validate_resource_group(rg: &str) -> Result<()> {
    if rg.is_empty() || rg.len() > 90 {
        anyhow::bail!("invalid resource group '{rg}': expected 1-90 characters");
    }
    if rg.starts_with('-') {
        anyhow::bail!("invalid resource group '{rg}': must not start with '-'");
    }
    if rg.ends_with('.') {
        anyhow::bail!("invalid resource group '{rg}': must not end with '.'");
    }
    if !rg
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-' | '.' | '(' | ')'))
    {
        anyhow::bail!(
            "invalid resource group '{rg}': only letters, digits, and \
             '_-.()' are allowed"
        );
    }
    Ok(())
}

/// Validate every value that reaches the `az` command line.
///
/// `ip_tags` is revalidated here even though the env path already checks it:
/// a hand-edited config file is deserialized with a bare `toml::from_str` and
/// bypasses that check entirely.
pub fn validate_nat_inputs(resource_group: &str, region: &str, ip_tags: &str) -> Result<()> {
    validate_resource_group(resource_group)?;
    normalize_region(region)?;
    azlin_core::AzlinConfig::validate_bastion_pip_ip_tags(ip_tags)
        .map_err(|e| anyhow::anyhow!("invalid ip tags for NAT gateway public IP: {e}"))?;
    Ok(())
}

// ── Az CLI command builders ──────────────────────────────────────────

/// Build `az network public-ip create` arguments for the NAT gateway's SNAT address.
///
/// Deliberately carries **no** `--tags`: an `azlin-session` tag would make
/// teardown classify this address as a session resource and delete it, taking
/// the whole region's egress with it.
pub fn build_create_natgw_pip_args(
    resource_group: &str,
    region: &str,
    ip_tags: &str,
) -> Vec<String> {
    let region = region.to_lowercase();
    vec![
        "network".into(),
        "public-ip".into(),
        "create".into(),
        "--resource-group".into(),
        resource_group.into(),
        "--name".into(),
        natgw_pip_name(&region),
        "--location".into(),
        region.clone(),
        "--sku".into(),
        "Standard".into(),
        "--allocation-method".into(),
        "Static".into(),
        // Four argv elements, not one space-joined string: `az` rejects "1 2 3".
        "--zone".into(),
        "1".into(),
        "2".into(),
        "3".into(),
        "--ip-tags".into(),
        ip_tags.into(),
        "--output".into(),
        "none".into(),
    ]
}

/// Build `az network nat gateway create` arguments.
///
/// The gateway is regional (no `--zone`) while its public IP is zonal. That
/// asymmetry is the shape verified working in the subscription; do not
/// "harmonise" it.
pub fn build_create_natgw_args(resource_group: &str, region: &str) -> Vec<String> {
    let region = region.to_lowercase();
    vec![
        "network".into(),
        "nat".into(),
        "gateway".into(),
        "create".into(),
        "--resource-group".into(),
        resource_group.into(),
        "--name".into(),
        natgw_name_for_region(&region),
        "--location".into(),
        region.clone(),
        "--sku".into(),
        "Standard".into(),
        "--idle-timeout".into(),
        IDLE_TIMEOUT_MINUTES.into(),
        "--public-ip-addresses".into(),
        natgw_pip_name(&region),
        "--output".into(),
        "none".into(),
    ]
}

/// Build `az network vnet subnet update` arguments attaching the NAT gateway
/// to the VM subnet.
pub fn build_attach_natgw_args(resource_group: &str, region: &str) -> Vec<String> {
    vec![
        "network".into(),
        "vnet".into(),
        "subnet".into(),
        "update".into(),
        "--resource-group".into(),
        resource_group.into(),
        "--vnet-name".into(),
        crate::bastion_helpers::bastion_vnet_name(region),
        "--name".into(),
        VM_SUBNET.into(),
        "--nat-gateway".into(),
        natgw_name_for_region(region),
        "--output".into(),
        "none".into(),
    ]
}

/// Build `az network vnet subnet show` arguments used to read the VM subnet's
/// current NAT gateway association.
pub fn build_check_subnet_args(resource_group: &str, region: &str) -> Vec<String> {
    vec![
        "network".into(),
        "vnet".into(),
        "subnet".into(),
        "show".into(),
        "--resource-group".into(),
        resource_group.into(),
        "--vnet-name".into(),
        crate::bastion_helpers::bastion_vnet_name(region),
        "--name".into(),
        VM_SUBNET.into(),
        "--output".into(),
        "json".into(),
    ]
}

// ── Subnet state ─────────────────────────────────────────────────────

/// Whether the VM subnet already has outbound internet via a NAT gateway.
///
/// There is deliberately no `Unknown` variant. `subnet update --nat-gateway`
/// *replaces* an existing association, so a failed read that degraded to
/// `Absent` would silently repoint a user's own gateway and start billing a
/// second one. Read failures surface as `Err` from [`detect_nat_status`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NatStatus {
    /// A NAT gateway is attached. `name` may be a gateway azlin did not create.
    Attached { name: String },
    /// No NAT gateway is attached — the subnet has no egress.
    Absent,
}

/// Read a subnet's NAT gateway association out of `az network vnet subnet show`
/// JSON.
///
/// Total by construction: every lookup is a `.get()` chain, so hostile or
/// unexpected shapes absorb to [`NatStatus::Absent`] rather than panicking.
pub fn parse_subnet_nat_status(subnet: &serde_json::Value) -> NatStatus {
    let name = subnet
        .get("natGateway")
        .and_then(|g| g.get("id"))
        .and_then(|id| id.as_str())
        .and_then(|id| id.rsplit('/').next())
        .filter(|name| !name.is_empty());

    match name {
        Some(name) => NatStatus::Attached {
            name: name.to_string(),
        },
        None => NatStatus::Absent,
    }
}

// ── Provisioning plan ────────────────────────────────────────────────

/// Return the ordered `az` invocations needed to give the VM subnet egress.
///
/// An already-attached gateway yields an empty plan — idempotency expressed as
/// a value, so the "never create a duplicate" requirement is testable without
/// touching Azure. Every name is deterministic and each `az ... create` is a
/// create-or-update, so re-running after an interrupted run converges.
pub fn plan_nat_provisioning(
    status: &NatStatus,
    resource_group: &str,
    region: &str,
    ip_tags: &str,
) -> Vec<Vec<String>> {
    match status {
        NatStatus::Attached { .. } => Vec::new(),
        NatStatus::Absent => vec![
            build_create_natgw_pip_args(resource_group, region, ip_tags),
            build_create_natgw_args(resource_group, region),
            build_attach_natgw_args(resource_group, region),
        ],
    }
}

// ── Orchestrator ─────────────────────────────────────────────────────

/// Azure error fragments that mean "you lack permission", not "it is absent".
const AUTHZ_MARKERS: [&str; 2] = ["AuthorizationFailed", "does not have authorization"];

/// Azure error fragments that mean "another write to this resource is in
/// flight" — a lost race, not a real failure.
const CONFLICT_MARKERS: [&str; 2] = ["AnotherOperationInProgress", "Conflict"];

/// Pause before re-reading the subnet. The failures this retry exists for —
/// ARM throttling (429) and transient 5xx — are time-based: an immediate
/// second call lands inside the same throttle window and fails identically.
/// Two seconds is long enough to clear a typical ARM retry-after and short
/// enough to be invisible next to `az vm create`.
const READ_RETRY_BACKOFF: std::time::Duration = std::time::Duration::from_secs(2);

/// Append the missing-role hint when an `az` failure was an authorization
/// denial. Provisioning egress needs write access to the VNet and to public
/// IPs; without naming the role the user cannot act on the error.
fn is_authz_failure(message: &str) -> bool {
    AUTHZ_MARKERS.iter().any(|m| message.contains(m))
}

fn annotate_authz(message: String) -> String {
    if is_authz_failure(&message) {
        format!(
            "{message}\n  This is a permissions failure, not a missing resource. \
             Provisioning egress requires the 'Network Contributor' role (or \
             equivalent write access to Microsoft.Network) on the resource group."
        )
    } else {
        message
    }
}

/// One attempt at reading the subnet. `Ok(None)` means the read itself failed.
fn try_detect_nat_status(resource_group: &str, region: &str) -> Result<NatStatus, String> {
    let args = build_check_subnet_args(resource_group, region);
    let output = crate::bastion_helpers::run_az(&args).map_err(|e| e.to_string())?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(azlin_core::sanitizer::sanitize(stderr.trim()).to_string());
    }
    let subnet: serde_json::Value =
        serde_json::from_slice(&output.stdout).map_err(|e| format!("output was not JSON: {e}"))?;
    Ok(parse_subnet_nat_status(&subnet))
}

/// Read the VM subnet's NAT gateway association from Azure.
///
/// Returns `Err` when the subnet cannot be read at all — including when the
/// bastion VNet does not exist yet. A read failure must never be downgraded to
/// "no gateway attached": the attach step *replaces* the subnet's association,
/// so proceeding blind could repoint someone else's gateway.
///
/// Because that makes a read failure fatal to `azlin new`, the read is retried
/// once after [`READ_RETRY_BACKOFF`]. ARM throttling and transient 5xx are
/// common enough that a single blip should not block VM creation.
///
/// An authorization denial is exempt: RBAC does not grant itself two seconds
/// later, so retrying one costs a measured ~4s of the ~6s failure path (a
/// failing ARM read is ~2.1s, plus the backoff) to reach an identical verdict.
/// Only authz is exempted. A *not-found* read is still retried, because
/// `ensure_bastion_infrastructure` may have created this very VNet moments
/// earlier and ARM read-after-write is not instantaneous.
pub fn detect_nat_status(resource_group: &str, region: &str) -> Result<NatStatus> {
    // This is the first `az` call on the private-VM path, and it runs *before*
    // `ensure_nat_gateway`'s validation — `cmd_vm_ops` calls it directly with a
    // resource group that came straight from the config file (deserialized with
    // a bare `toml::from_str`, so never field-validated). A value beginning with
    // `-` would be read by `az` as a flag, so guard at this boundary too rather
    // than relying on a caller that may not run first.
    validate_resource_group(resource_group)?;
    normalize_region(region)?;

    let first = match try_detect_nat_status(resource_group, region) {
        Ok(status) => return Ok(status),
        Err(e) => e,
    };
    if is_authz_failure(&first) {
        anyhow::bail!(
            "{}",
            annotate_authz(read_failure_message(region, &first, None))
        );
    }
    std::thread::sleep(READ_RETRY_BACKOFF);
    let second = match try_detect_nat_status(resource_group, region) {
        Ok(status) => return Ok(status),
        Err(e) => e,
    };
    anyhow::bail!(
        "{}",
        annotate_authz(read_failure_message(region, &first, Some(&second)))
    )
}

/// Render the failure text for an unreadable subnet.
///
/// `second` is `None` when the retry was skipped as pointless, so the message
/// never claims two attempts were made when only one was.
fn read_failure_message(region: &str, first: &str, second: Option<&str>) -> String {
    let vnet = crate::bastion_helpers::bastion_vnet_name(region);
    let region = region.to_lowercase();
    match second {
        Some(second) => format!(
            "`az network vnet subnet show` failed twice for subnet '{VM_SUBNET}' of \
             VNet '{vnet}' in {region}:\n  first attempt:  {first}\n  second attempt: {second}"
        ),
        None => format!(
            "`az network vnet subnet show` failed for subnet '{VM_SUBNET}' of \
             VNet '{vnet}' in {region}:\n  {first}"
        ),
    }
}

/// Pause before each post-conflict subnet re-check.
///
/// A 409 means a concurrent `azlin new` is *mid-write* on this subnet. Reading
/// it back immediately can land before that write commits, so azlin would
/// report a failure for work that succeeded a moment later (#1101). Three
/// seconds is longer than [`READ_RETRY_BACKOFF`] on purpose: that one waits
/// out an ARM throttle window, this one waits out somebody else's subnet PUT.
const CONFLICT_RECHECK_BACKOFF: std::time::Duration = std::time::Duration::from_secs(3);

/// How many times to re-check the subnet after a conflict.
///
/// One look is a coin flip on whether the other run has committed yet. Three,
/// spaced by [`CONFLICT_RECHECK_BACKOFF`], cover ~9s — invisible next to the
/// `az vm create` this is unblocking, and enough for a subnet association to
/// land in the common case.
const CONFLICT_RECHECK_ATTEMPTS: usize = 3;

/// Decide what a failed attach means and, if it was a lost race, wait for the
/// winner to finish.
///
/// Split out from [`ensure_nat_gateway`] with `sleep` and `recheck` injected
/// because that is the only way to test it: the behaviour that matters is
/// *ordering* — that the wait happens before the first re-read, not after it —
/// and neither a real sleep nor a real `az` call can be observed from a unit
/// test. The closures make both observable without a process mock, which is
/// why #1101 was deferred out of #1097 in the first place.
///
/// Returns the attached gateway's name when the race resolved in our favour.
fn resolve_attach_conflict<S, R>(
    attach_err: anyhow::Error,
    mut sleep: S,
    mut recheck: R,
) -> Result<String>
where
    S: FnMut(std::time::Duration),
    R: FnMut() -> Result<NatStatus>,
{
    if !CONFLICT_MARKERS
        .iter()
        .any(|m| attach_err.to_string().contains(m))
    {
        return Err(attach_err);
    }
    eprintln!("  Attach conflicted with a concurrent operation; re-checking subnet...");
    for _ in 0..CONFLICT_RECHECK_ATTEMPTS {
        // Wait first. The conflict is evidence that a write is in flight, so
        // the immediate read is the one guaranteed to be too early.
        sleep(CONFLICT_RECHECK_BACKOFF);
        match recheck() {
            Ok(NatStatus::Attached { name }) => return Ok(name),
            // The other run has not committed an association yet. It may still
            // be mid-write, so look again rather than calling the race lost.
            Ok(_) => continue,
            // The re-read itself failed. Reporting only the conflict would
            // send the user chasing a race that may not exist when the actual
            // problem is that the subnet is now unreadable — and if that was
            // an RBAC denial, `annotate_authz` is the one thing that tells
            // them which role they are missing. `detect_nat_status` already
            // retries a failing read internally, so there is nothing to gain
            // by looping on it here.
            Err(re_read) => {
                return Err(attach_err.context(conflict_recheck_failure_message(&re_read)))
            }
        }
    }
    // Every look came back with no association, so the original conflict is
    // still the real failure.
    Err(attach_err)
}

/// Render the context added when the post-conflict subnet re-read also failed.
///
/// Pure so the one branch that could lose an error is testable: the caller has
/// two errors in hand and must surface both.
///
/// Deliberately does NOT call [`annotate_authz`]. `detect_nat_status` already
/// annotates its own errors, so `re_read` arrives carrying the role hint when
/// it is a denial; re-annotating here would print that paragraph twice.
fn conflict_recheck_failure_message(re_read: &anyhow::Error) -> String {
    format!(
        "The attach conflicted with a concurrent operation, and the follow-up \
         subnet re-check also failed: {re_read}"
    )
}

/// Ensure the VM subnet in `region` has outbound internet via a NAT gateway.
///
/// Idempotent: an existing gateway — including one azlin did not create — is
/// reused and nothing is provisioned. A NAT gateway plus its Standard public
/// IP cost real money, so this must never create a second one.
///
/// `ip_tags` is the resolved Azure `--ip-tags` value; resolve it via
/// [`azlin_core::AzlinConfig::bastion_pip_ip_tags`], the same source the
/// bastion public IP uses.
pub fn ensure_nat_gateway(resource_group: &str, region: &str, ip_tags: &str) -> Result<()> {
    validate_nat_inputs(resource_group, region, ip_tags)?;
    let region = &normalize_region(region)?;

    let status = detect_nat_status(resource_group, region)?;
    if let NatStatus::Attached { name } = &status {
        eprintln!("  ✓ NAT gateway '{name}' already provides egress for {region}");
        return Ok(());
    }

    // Drive the same plan the tests assert against, rather than re-listing the
    // three commands here: a second hand-written sequence could drift from the
    // planner, and every drift creates a billable resource with the wrong shape.
    let plan = plan_nat_provisioning(&status, resource_group, region, ip_tags);
    let [create_pip, create_natgw, attach] = plan.as_slice() else {
        anyhow::bail!(
            "internal error: NAT provisioning plan had {} steps, expected 3",
            plan.len()
        );
    };

    let natgw = natgw_name_for_region(region);
    let pip = natgw_pip_name(region);

    eprintln!("Creating NAT gateway public IP '{pip}' (Standard, zones 1 2 3)...");
    run_nat_step(
        create_pip,
        &format!("Failed to create NAT gateway public IP '{pip}' in {region}"),
    )?;
    eprintln!("  ✓ Public IP '{pip}' ready");

    eprintln!("Creating NAT gateway '{natgw}' (Standard SKU, 10 min idle timeout)...");
    run_nat_step(
        create_natgw,
        &format!("Failed to create NAT gateway '{natgw}' in {region}"),
    )?;
    eprintln!("  ✓ NAT gateway '{natgw}' created");

    let vnet = crate::bastion_helpers::bastion_vnet_name(region);
    eprintln!("Attaching '{natgw}' to subnet '{VM_SUBNET}' of '{vnet}'...");
    if let Err(e) = run_nat_step(
        attach,
        &format!("Failed to attach NAT gateway '{natgw}' to subnet '{VM_SUBNET}' in {region}"),
    ) {
        // A concurrent `azlin new` in the same region writes the same subnet.
        // Azure serialises those with 409/AnotherOperationInProgress, so a
        // conflict here usually means the other run is doing the work. Wait,
        // then re-read before failing: the goal is egress on the subnet, not
        // winning the race.
        let name = resolve_attach_conflict(e, std::thread::sleep, || {
            detect_nat_status(resource_group, region)
        })?;
        eprintln!("  ✓ Subnet already attached to NAT gateway '{name}' by a concurrent run");
        return Ok(());
    }
    eprintln!("  ✓ Attached to subnet '{VM_SUBNET}' of '{vnet}'");
    eprintln!("  ✓ Outbound internet enabled for private VMs in {region}");

    Ok(())
}

/// Run one provisioning `az` command, annotating authorization failures with
/// the role the user is missing.
fn run_nat_step(args: &[String], context: &str) -> Result<()> {
    crate::bastion_helpers::run_az_or_bail(args, context)
        .map_err(|e| anyhow::anyhow!("{}", annotate_authz(e.to_string())))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Convenience: build the expected `Vec<String>` from string literals.
    fn sv(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    const RG: &str = "rysweet-linux-vm-pool";
    const REGION: &str = "southcentralus";
    const TAGS: &str = "FirstPartyUsage=/ATEVETNonProd";

    // ── Naming conventions ───────────────────────────────────────────
    //
    // A typo in either suffix silently double-bills a Standard public IP
    // (~$3.65/mo) and orphans the previous one, so both are asserted
    // verbatim rather than by `contains`.

    #[test]
    fn test_natgw_name_for_region() {
        assert_eq!(
            natgw_name_for_region("southcentralus"),
            "azlin-natgw-southcentralus"
        );
    }

    #[test]
    fn test_natgw_name_for_region_normalizes_case() {
        assert_eq!(
            natgw_name_for_region("SouthCentralUS"),
            "azlin-natgw-southcentralus"
        );
    }

    #[test]
    fn test_natgw_pip_name_uses_ip_tagged_suffix() {
        // The live, verified-working resource is `-ip-tagged`, NOT `-pip`.
        // `-pip` is the *bastion* convention; reusing it here would collide
        // in name space and mis-target the attach step.
        assert_eq!(
            natgw_pip_name("southcentralus"),
            "azlin-natgw-southcentralus-ip-tagged"
        );
    }

    #[test]
    fn test_natgw_pip_name_normalizes_case() {
        assert_eq!(natgw_pip_name("WestUS2"), "azlin-natgw-westus2-ip-tagged");
    }

    #[test]
    fn test_natgw_pip_name_is_not_the_bastion_pip_name() {
        assert_ne!(
            natgw_pip_name(REGION),
            crate::bastion_helpers::bastion_pip_name(REGION)
        );
    }

    // ── Argv builders: verbatim shapes ───────────────────────────────
    //
    // These vectors are load-bearing: they reproduce the configuration
    // verified working in the live subscription. Assert the whole vector,
    // not individual flags, so a reordering or dropped flag is caught.

    #[test]
    fn test_build_create_natgw_pip_args_verbatim() {
        assert_eq!(
            build_create_natgw_pip_args(RG, REGION, TAGS),
            sv(&[
                "network",
                "public-ip",
                "create",
                "--resource-group",
                RG,
                "--name",
                "azlin-natgw-southcentralus-ip-tagged",
                "--location",
                "southcentralus",
                "--sku",
                "Standard",
                "--allocation-method",
                "Static",
                "--zone",
                "1",
                "2",
                "3",
                "--ip-tags",
                TAGS,
                "--output",
                "none",
            ])
        );
    }

    #[test]
    fn test_build_create_natgw_pip_args_zone_is_four_argv_elements() {
        // `--zone 1 2 3` is a shell rendering of FOUR argv elements. Passing
        // "1 2 3" as one element makes az reject the value.
        let args = build_create_natgw_pip_args(RG, REGION, TAGS);
        let z = args.iter().position(|a| a == "--zone").unwrap();
        assert_eq!(&args[z..z + 4], &sv(&["--zone", "1", "2", "3"])[..]);
    }

    #[test]
    fn test_build_create_natgw_pip_args_emits_custom_ip_tags_verbatim() {
        let args = build_create_natgw_pip_args(RG, REGION, "FirstPartyUsage=/CustomTag");
        let i = args.iter().position(|a| a == "--ip-tags").unwrap();
        assert_eq!(args[i + 1], "FirstPartyUsage=/CustomTag");
    }

    #[test]
    fn test_build_create_natgw_pip_args_never_emits_session_tags() {
        // S1 corollary: an `azlin-session` tag flips teardown's classify()
        // from Skip(Untagged) to Candidate::Delete, so `azlin cleanup` would
        // destroy the region's egress. The SNAT address must stay untagged.
        let args = build_create_natgw_pip_args(RG, REGION, TAGS);
        assert!(
            !args.iter().any(|a| a == "--tags"),
            "NAT SNAT public IP must never carry --tags: it would make teardown delete it"
        );
    }

    #[test]
    fn test_build_create_natgw_args_verbatim() {
        assert_eq!(
            build_create_natgw_args(RG, REGION),
            sv(&[
                "network",
                "nat",
                "gateway",
                "create",
                "--resource-group",
                RG,
                "--name",
                "azlin-natgw-southcentralus",
                "--location",
                "southcentralus",
                "--sku",
                "Standard",
                "--idle-timeout",
                "10",
                "--public-ip-addresses",
                "azlin-natgw-southcentralus-ip-tagged",
                "--output",
                "none",
            ])
        );
    }

    #[test]
    fn test_build_create_natgw_args_is_regional_not_zonal() {
        // A zonal public IP paired with a REGIONAL NAT gateway is the shape
        // verified working in the subscription. It looks asymmetric and is
        // not a bug — do not "harmonise" by adding --zone here.
        let args = build_create_natgw_args(RG, REGION);
        assert!(
            !args.iter().any(|a| a == "--zone"),
            "NAT gateway must be regional (no --zone); only its public IP is zonal"
        );
    }

    #[test]
    fn test_build_create_natgw_args_idle_timeout_is_ten() {
        // 10 minutes is the verified value. Lowering it without measuring
        // trades SNAT-port pressure for connection churn.
        let args = build_create_natgw_args(RG, REGION);
        let i = args.iter().position(|a| a == "--idle-timeout").unwrap();
        assert_eq!(args[i + 1], "10");
    }

    #[test]
    fn test_build_attach_natgw_args_verbatim() {
        assert_eq!(
            build_attach_natgw_args(RG, REGION),
            sv(&[
                "network",
                "vnet",
                "subnet",
                "update",
                "--resource-group",
                RG,
                "--vnet-name",
                "azlin-bastion-southcentralus-vnet",
                "--name",
                "default",
                "--nat-gateway",
                "azlin-natgw-southcentralus",
                "--output",
                "none",
            ])
        );
    }

    #[test]
    fn test_build_check_subnet_args_verbatim() {
        assert_eq!(
            build_check_subnet_args(RG, REGION),
            sv(&[
                "network",
                "vnet",
                "subnet",
                "show",
                "--resource-group",
                RG,
                "--vnet-name",
                "azlin-bastion-southcentralus-vnet",
                "--name",
                "default",
                "--output",
                "json",
            ])
        );
    }

    #[test]
    fn test_no_builder_ever_touches_azure_bastion_subnet() {
        // Attaching a NAT gateway to AzureBastionSubnet is rejected by Azure,
        // and would give the bastion egress rather than the VMs. The target is
        // always the `default` VM subnet.
        let all = [
            build_create_natgw_pip_args(RG, REGION, TAGS),
            build_create_natgw_args(RG, REGION),
            build_attach_natgw_args(RG, REGION),
            build_check_subnet_args(RG, REGION),
        ];
        for args in &all {
            assert!(
                !args.iter().any(|a| a.contains("AzureBastionSubnet")),
                "no NAT command may reference AzureBastionSubnet: {args:?}"
            );
        }
    }

    #[test]
    fn test_builders_reuse_bastion_vnet_name() {
        // Re-deriving the VNet format string would silently drift from
        // bastion_helpers and break idempotency against deployed resources.
        let vnet = crate::bastion_helpers::bastion_vnet_name(REGION);
        assert!(build_attach_natgw_args(RG, REGION).contains(&vnet));
        assert!(build_check_subnet_args(RG, REGION).contains(&vnet));
    }

    #[test]
    fn test_builders_normalize_region_case() {
        let args = build_create_natgw_args(RG, "SouthCentralUS");
        assert!(args.contains(&"azlin-natgw-southcentralus".to_string()));
        assert!(args.contains(&"southcentralus".to_string()));
        assert!(!args.iter().any(|a| a.contains("SouthCentralUS")));
    }

    // ── Subnet JSON → NatStatus ──────────────────────────────────────
    //
    // Must be total: `.get()` chains only, never Value[] indexing, which
    // panics on some shapes. Malformed or hostile JSON absorbs to Absent.

    #[test]
    fn test_parse_subnet_nat_status_attached() {
        let v = serde_json::json!({
            "name": "default",
            "natGateway": {
                "id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rysweet-linux-vm-pool/providers/Microsoft.Network/natGateways/azlin-natgw-southcentralus",
                "resourceGroup": "rysweet-linux-vm-pool"
            }
        });
        assert_eq!(
            parse_subnet_nat_status(&v),
            NatStatus::Attached {
                name: "azlin-natgw-southcentralus".to_string()
            }
        );
    }

    #[test]
    fn test_parse_subnet_nat_status_attached_accepts_foreign_name() {
        // Idempotency is about egress *presence*, not name matching. A
        // hand-created gateway satisfies the requirement; creating ours
        // alongside it would double-bill and (worse) the attach step would
        // REPLACE theirs.
        let v = serde_json::json!({
            "natGateway": { "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/natGateways/corp-shared-egress" }
        });
        assert_eq!(
            parse_subnet_nat_status(&v),
            NatStatus::Attached {
                name: "corp-shared-egress".to_string()
            }
        );
    }

    #[test]
    fn test_parse_subnet_nat_status_null_is_absent() {
        let v = serde_json::json!({ "name": "default", "natGateway": null });
        assert_eq!(parse_subnet_nat_status(&v), NatStatus::Absent);
    }

    #[test]
    fn test_parse_subnet_nat_status_missing_key_is_absent() {
        // az omits the key entirely on a subnet that has never had one.
        let v = serde_json::json!({ "name": "default", "addressPrefix": "10.0.0.0/24" });
        assert_eq!(parse_subnet_nat_status(&v), NatStatus::Absent);
    }

    #[test]
    fn test_parse_subnet_nat_status_empty_object_is_absent() {
        assert_eq!(
            parse_subnet_nat_status(&serde_json::json!({})),
            NatStatus::Absent
        );
    }

    #[test]
    fn test_parse_subnet_nat_status_is_total_on_hostile_shapes() {
        // Must not panic on any of these.
        for v in [
            serde_json::json!([]),
            serde_json::json!("default"),
            serde_json::json!(42),
            serde_json::json!(null),
            serde_json::json!({ "natGateway": [] }),
            serde_json::json!({ "natGateway": "not-an-object" }),
            serde_json::json!({ "natGateway": { "id": null } }),
            serde_json::json!({ "natGateway": { "id": 7 } }),
            serde_json::json!({ "natGateway": {} }),
        ] {
            assert_eq!(parse_subnet_nat_status(&v), NatStatus::Absent, "input: {v}");
        }
    }

    // ── Provisioning plan ────────────────────────────────────────────

    #[test]
    fn test_plan_nat_provisioning_attached_is_empty() {
        // Idempotency, stated as a type-level guarantee: an attached gateway
        // yields ZERO commands, so no duplicate ~$32/mo gateway or $3.65/mo IP.
        let status = NatStatus::Attached {
            name: "azlin-natgw-southcentralus".to_string(),
        };
        assert_eq!(
            plan_nat_provisioning(&status, RG, REGION, TAGS),
            Vec::<Vec<String>>::new()
        );
    }

    #[test]
    fn test_plan_nat_provisioning_absent_emits_three_steps_in_order() {
        let plan = plan_nat_provisioning(&NatStatus::Absent, RG, REGION, TAGS);
        assert_eq!(plan.len(), 3, "expected pip → gateway → attach");
        assert_eq!(plan[0], build_create_natgw_pip_args(RG, REGION, TAGS));
        assert_eq!(plan[1], build_create_natgw_args(RG, REGION));
        assert_eq!(plan[2], build_attach_natgw_args(RG, REGION));
    }

    #[test]
    fn test_plan_nat_provisioning_threads_custom_ip_tags() {
        let plan = plan_nat_provisioning(&NatStatus::Absent, RG, REGION, "FirstPartyUsage=/Other");
        assert!(plan[0].contains(&"FirstPartyUsage=/Other".to_string()));
    }

    #[test]
    fn test_plan_nat_provisioning_is_rerunnable_after_partial_failure() {
        // Names are deterministic and `az ... create` is create-or-update, so
        // re-running after an interrupted run converges rather than duplicating.
        let a = plan_nat_provisioning(&NatStatus::Absent, RG, REGION, TAGS);
        let b = plan_nat_provisioning(&NatStatus::Absent, RG, REGION, TAGS);
        assert_eq!(a, b);
    }

    // ── Boundary validation (R-VAL-2 / R-VAL-3) ──────────────────────
    //
    // `region` is unvalidated on the `azlin new` path and also arrives from
    // template files; `resource_group` reaches `--resource-group` raw. A
    // leading '-' turns a value into an az flag.

    #[test]
    fn test_normalize_region_accepts_and_lowercases() {
        assert_eq!(
            normalize_region("SouthCentralUS").unwrap(),
            "southcentralus"
        );
        assert_eq!(normalize_region("westus2").unwrap(), "westus2");
    }

    #[test]
    fn test_normalize_region_rejects_injection_and_junk() {
        for bad in [
            "",
            "-g",
            "--output",
            "west us",
            "westus2;rm -rf /",
            "west/us",
            "west-us",
            "w",
            &"a".repeat(33),
        ] {
            assert!(
                normalize_region(bad).is_err(),
                "region {bad:?} must be rejected"
            );
        }
    }

    #[test]
    fn test_validate_resource_group_accepts_real_names() {
        for ok in ["rysweet-linux-vm-pool", "rg_1", "rg.name", "rg(paren)"] {
            assert!(
                validate_resource_group(ok).is_ok(),
                "rg {ok:?} must be accepted"
            );
        }
    }

    #[test]
    fn test_validate_resource_group_rejects_injection_and_junk() {
        for bad in [
            "",
            "-g",
            "--resource-group",
            "rg name",
            "rg/sub",
            "rg.",
            &"a".repeat(91),
        ] {
            assert!(
                validate_resource_group(bad).is_err(),
                "rg {bad:?} must be rejected"
            );
        }
    }

    #[test]
    fn test_validate_nat_inputs_rejects_bad_ip_tags() {
        // R-VAL-1: ip_tags is validated only on the env path; a hand-edited
        // config file bypasses it (load_from_path is a bare toml::from_str),
        // so revalidate at the point of use.
        assert!(validate_nat_inputs(RG, REGION, "no-equals-sign").is_err());
        assert!(validate_nat_inputs(RG, REGION, "").is_err());
        assert!(validate_nat_inputs(RG, REGION, "-Key=Value").is_err());
        assert!(validate_nat_inputs(RG, REGION, TAGS).is_ok());
    }

    #[test]
    fn test_validate_nat_inputs_rejects_bad_region_and_rg() {
        assert!(validate_nat_inputs(RG, "-g", TAGS).is_err());
        assert!(validate_nat_inputs("-g", REGION, TAGS).is_err());
    }

    #[test]
    fn test_detect_nat_status_validates_before_running_az() {
        // `detect_nat_status` is the FIRST az call on the private-VM path and
        // is invoked directly by `cmd_vm_ops`, ahead of `ensure_nat_gateway`'s
        // validation. A resource group beginning with `-` would reach the `az`
        // command line as a flag, so it must be rejected before the process
        // spawns rather than trusted to a caller that runs second.
        //
        // These cases fail during validation, so no `az` process is spawned
        // and the test stays offline.
        let err = detect_nat_status("-g", REGION).unwrap_err().to_string();
        assert!(
            err.contains("invalid resource group"),
            "must reject before spawning az: {err}"
        );
        let err = detect_nat_status(RG, "--debug").unwrap_err().to_string();
        assert!(
            err.contains("invalid Azure region"),
            "must reject before spawning az: {err}"
        );
    }

    // ── Error annotation ─────────────────────────────────────────────

    #[test]
    fn test_annotate_authz_adds_role_hint_for_denials() {
        let msg = annotate_authz(
            "Failed to create NAT gateway in westus2: AuthorizationFailed".to_string(),
        );
        assert!(
            msg.contains("Network Contributor"),
            "a permissions failure must name the role to request: {msg}"
        );
        assert!(
            msg.contains("AuthorizationFailed"),
            "the original az error must be preserved: {msg}"
        );
    }

    #[test]
    fn test_annotate_authz_matches_long_form_denial() {
        let msg = annotate_authz(
            "The client 'x' with object id 'y' does not have authorization to perform \
             action 'Microsoft.Network/natGateways/write'"
                .to_string(),
        );
        assert!(msg.contains("Network Contributor"));
    }

    #[test]
    fn test_annotate_authz_leaves_other_errors_untouched() {
        // Only a genuine denial gets the hint — otherwise the advice is noise
        // that sends users chasing the wrong problem.
        let original = "ResourceNotFound: the VNet does not exist".to_string();
        assert_eq!(annotate_authz(original.clone()), original);
    }

    #[test]
    fn test_conflict_markers_recognize_concurrent_writes() {
        // Two `azlin new` runs in one region serialise on the subnet write.
        for e in [
            "AnotherOperationInProgress: Another operation on this resource is in progress",
            "(Conflict) Cannot modify subnet while another operation is running",
        ] {
            assert!(
                CONFLICT_MARKERS.iter().any(|m| e.contains(m)),
                "must be treated as a lost race, not a failure: {e}"
            );
        }
    }

    #[test]
    fn test_authz_failures_are_not_retried() {
        // A failing ARM read measures ~2.1s, so retrying one costs ~4.2s
        // (two reads plus the backoff) on the critical path of `azlin new`.
        // That is worth paying for a throttle or a 5xx, which clear on their
        // own. It is pure waste for an RBAC denial, which does not.
        for e in [
            "AuthorizationFailed: the client does not have permission",
            "The client 'x' does not have authorization to perform action 'read'",
        ] {
            assert!(is_authz_failure(e), "must skip the pointless retry: {e}");
        }
    }

    #[test]
    fn test_not_found_is_still_retried() {
        // Deliberately NOT exempted. `ensure_bastion_infrastructure` creates
        // this VNet immediately before the NAT check runs, and ARM
        // read-after-write is not instantaneous, so a not-found here can be
        // eventual consistency that the retry genuinely resolves.
        for e in [
            "ResourceNotFound: the subnet could not be found",
            "ResourceGroupNotFound: Resource group 'rg' could not be found.",
            "(TooManyRequests) rate limit exceeded",
            "output was not JSON: EOF while parsing a value",
        ] {
            assert!(!is_authz_failure(e), "must keep its retry: {e}");
        }
    }

    #[test]
    fn test_read_failure_message_reports_only_the_attempts_made() {
        // The skipped-retry path must not claim two attempts happened.
        let one = read_failure_message("SouthCentralUS", "AuthorizationFailed", None);
        assert!(one.contains("failed for subnet"), "{one}");
        assert!(!one.contains("twice"), "must not overstate attempts: {one}");
        assert!(!one.contains("second attempt"), "{one}");

        let two = read_failure_message("SouthCentralUS", "429", Some("429 again"));
        assert!(two.contains("failed twice"), "{two}");
        assert!(two.contains("first attempt"), "{two}");
        assert!(two.contains("second attempt"), "{two}");

        // Both shapes keep the operator oriented: subnet, VNet, region.
        for m in [&one, &two] {
            assert!(m.contains("default"), "must name the subnet: {m}");
            assert!(
                m.contains("azlin-bastion-southcentralus-vnet"),
                "must name the VNet: {m}"
            );
            assert!(m.contains("southcentralus"), "must name the region: {m}");
        }
    }

    #[test]
    fn test_conflict_recheck_failure_message_keeps_the_re_read_error() {
        // The branch this covers used to be `_ => return Err(e)`, which threw
        // the re-read error away: the user learned there had been a conflict
        // but not that the subnet had since become unreadable.
        let msg = conflict_recheck_failure_message(&anyhow::anyhow!(
            "`az network vnet subnet show` failed for subnet 'default'"
        ));
        assert!(
            msg.contains("conflicted with a concurrent operation"),
            "must still report the original conflict: {msg}"
        );
        assert!(
            msg.contains("`az network vnet subnet show` failed"),
            "must not discard the re-read error: {msg}"
        );
    }

    #[test]
    fn test_conflict_recheck_failure_message_carries_the_role_hint_exactly_once() {
        // `detect_nat_status` annotates its own errors, so a denial arrives
        // already carrying the hint. Surfacing it is the fix; re-annotating it
        // here would print the same paragraph twice in one error.
        let already_annotated = anyhow::anyhow!(
            "{}",
            annotate_authz(read_failure_message(
                "centralus",
                "AuthorizationFailed: the client does not have authorization",
                None,
            ))
        );
        let msg = conflict_recheck_failure_message(&already_annotated);
        assert_eq!(
            msg.matches("Network Contributor").count(),
            1,
            "the role hint must survive, and must appear once: {msg}"
        );

        // And a non-authz failure must not be mislabeled as a permissions problem.
        let throttled = conflict_recheck_failure_message(&anyhow::anyhow!("429 TooManyRequests"));
        assert!(
            !throttled.contains("Network Contributor"),
            "throttling is not a permissions failure: {throttled}"
        );
    }

    // ── The post-conflict re-check (#1101) ───────────────────────────
    //
    // What matters here is *ordering*: the wait has to happen before the first
    // re-read, because the 409 is evidence that somebody else's write is in
    // flight and an immediate read is the one guaranteed to be too early. That
    // is unobservable through a real sleep and a real `az` call, which is why
    // the sleep and the re-read are injected.

    /// Record of what `resolve_attach_conflict` did, in order.
    ///
    /// The wait keeps its full `Duration`: recorded as whole seconds, a
    /// backoff of 500ms would log as `Slept(0)` and the ordering assertion
    /// below would compare `Slept(0)` against `Slept(0)` and pass.
    #[derive(Debug, PartialEq, Eq)]
    enum Step {
        Slept(std::time::Duration),
        Rechecked,
    }

    /// Drive `resolve_attach_conflict` with a scripted sequence of re-read
    /// results, returning its verdict alongside the calls it made.
    ///
    /// Running off the end of the script panics rather than inventing another
    /// result. A harness that pads a short script reports success for
    /// behaviour nobody wrote down — the same shape as the bugs it exists to
    /// catch.
    fn drive_conflict(
        attach_err: anyhow::Error,
        results: Vec<Result<NatStatus>>,
    ) -> (Result<String>, Vec<Step>) {
        let log = std::cell::RefCell::new(Vec::new());
        let scripted = results.len();
        let mut remaining = results.into_iter();
        let verdict = resolve_attach_conflict(
            attach_err,
            |d| log.borrow_mut().push(Step::Slept(d)),
            || {
                log.borrow_mut().push(Step::Rechecked);
                remaining.next().unwrap_or_else(|| {
                    panic!("re-checked more than the {scripted} scripted time(s)")
                })
            },
        );
        (verdict, log.into_inner())
    }

    #[test]
    fn conflict_waits_before_the_first_recheck() {
        let (verdict, steps) = drive_conflict(
            anyhow::anyhow!("AnotherOperationInProgress"),
            vec![Ok(NatStatus::Attached {
                name: "azlin-natgw-southcentralus".to_string(),
            })],
        );
        assert_eq!(verdict.unwrap(), "azlin-natgw-southcentralus");
        // The first thing that happens is the wait, not the read. Reading
        // first is the bug (#1101): it lands before the concurrent write
        // commits and reports a failure for work that succeeded.
        assert_eq!(
            steps,
            vec![Step::Slept(CONFLICT_RECHECK_BACKOFF), Step::Rechecked]
        );
    }

    #[test]
    fn a_non_conflict_failure_neither_waits_nor_rereads() {
        let (verdict, steps) = drive_conflict(
            anyhow::anyhow!("ResourceNotFound: no such subnet"),
            vec![Ok(NatStatus::Attached {
                name: "should-not-be-consulted".to_string(),
            })],
        );
        assert!(verdict.is_err());
        assert!(verdict
            .unwrap_err()
            .to_string()
            .contains("ResourceNotFound"));
        assert!(
            steps.is_empty(),
            "a real failure must not be delayed by a race that did not happen: {steps:?}"
        );
    }

    #[test]
    fn conflict_keeps_looking_while_the_other_run_finishes() {
        // The winner of the race has not committed its association yet on the
        // first two looks. Giving up there is what made this a coin flip.
        let (verdict, steps) = drive_conflict(
            anyhow::anyhow!("Conflict"),
            vec![
                Ok(NatStatus::Absent),
                Ok(NatStatus::Absent),
                Ok(NatStatus::Attached {
                    name: "azlin-natgw-westus2".to_string(),
                }),
            ],
        );
        assert_eq!(verdict.unwrap(), "azlin-natgw-westus2");
        assert_eq!(
            steps.iter().filter(|s| **s == Step::Rechecked).count(),
            3,
            "{steps:?}"
        );
        // Every re-read is preceded by its own wait.
        for pair in steps.chunks(2) {
            assert_eq!(
                pair,
                [Step::Slept(CONFLICT_RECHECK_BACKOFF), Step::Rechecked],
                "{steps:?}"
            );
        }
    }

    #[test]
    fn conflict_gives_up_after_the_bounded_number_of_looks() {
        let (verdict, steps) = drive_conflict(
            anyhow::anyhow!("AnotherOperationInProgress"),
            (0..CONFLICT_RECHECK_ATTEMPTS + 5)
                .map(|_| Ok(NatStatus::Absent))
                .collect(),
        );
        let err = verdict.unwrap_err().to_string();
        // The original conflict is still the real failure, and is what the
        // user sees — not a manufactured "gave up" message.
        assert!(err.contains("AnotherOperationInProgress"), "{err}");
        assert_eq!(
            steps.iter().filter(|s| **s == Step::Rechecked).count(),
            CONFLICT_RECHECK_ATTEMPTS,
            "the re-check must be bounded: {steps:?}"
        );
    }

    #[test]
    fn a_failing_recheck_surfaces_both_errors_and_stops() {
        let (verdict, steps) = drive_conflict(
            anyhow::anyhow!("AnotherOperationInProgress"),
            vec![Err(anyhow::anyhow!(
                "AuthorizationFailed on the subnet read"
            ))],
        );
        let err = format!("{:#}", verdict.unwrap_err());
        assert!(err.contains("AnotherOperationInProgress"), "{err}");
        assert!(err.contains("AuthorizationFailed"), "{err}");
        // `detect_nat_status` already retries a failing read internally;
        // looping on it here would only multiply the wait before the same
        // verdict.
        assert_eq!(
            steps.iter().filter(|s| **s == Step::Rechecked).count(),
            1,
            "{steps:?}"
        );
    }

    #[test]
    fn conflict_recheck_backoff_is_nonzero_and_bounded() {
        assert!(
            !CONFLICT_RECHECK_BACKOFF.is_zero(),
            "an immediate re-read is the bug this exists to fix (#1101)"
        );
        // Longer than the throttle backoff: this one waits out somebody
        // else's subnet PUT, not an ARM retry-after.
        assert!(CONFLICT_RECHECK_BACKOFF >= READ_RETRY_BACKOFF);
        let worst_case = CONFLICT_RECHECK_BACKOFF * CONFLICT_RECHECK_ATTEMPTS as u32;
        assert!(
            worst_case <= std::time::Duration::from_secs(30),
            "the whole re-check has to stay invisible next to `az vm create`"
        );
    }

    #[test]
    fn test_read_retry_backoff_is_nonzero_and_bounded() {
        // Zero would make the retry useless against ARM throttling; anything
        // long enough to notice would stall `azlin new` on every blip.
        assert!(
            !READ_RETRY_BACKOFF.is_zero(),
            "an immediate retry lands in the same throttle window"
        );
        assert!(
            READ_RETRY_BACKOFF <= std::time::Duration::from_secs(5),
            "backoff must stay invisible next to `az vm create`"
        );
    }

    #[test]
    fn test_conflict_markers_do_not_match_unrelated_failures() {
        for e in [
            "AuthorizationFailed",
            "ResourceNotFound",
            "SkuNotAvailable in this region",
        ] {
            assert!(
                !CONFLICT_MARKERS.iter().any(|m| e.contains(m)),
                "must NOT be swallowed as a race: {e}"
            );
        }
    }

    // ── NatStatus has no "unknown" variant ───────────────────────────

    #[test]
    fn test_nat_status_has_exactly_two_states() {
        // `subnet update --nat-gateway` REPLACES the existing association.
        // If a failed read degraded to Absent, we would silently repoint a
        // user-named gateway and start billing a second gateway + IP. So a
        // read failure must surface as Err from `detect_nat_status`, never as
        // a third NatStatus variant. This match is exhaustive by construction.
        let describe = |s: &NatStatus| match s {
            NatStatus::Attached { name } => format!("attached:{name}"),
            NatStatus::Absent => "absent".to_string(),
        };
        assert_eq!(describe(&NatStatus::Absent), "absent");
        assert_eq!(
            describe(&NatStatus::Attached { name: "x".into() }),
            "attached:x"
        );
    }
}
