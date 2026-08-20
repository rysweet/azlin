#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use std::time::Duration;

// ── SSH timeout scaling by VM size ──────────────────────────────────

/// Returns a scaled SSH readiness timeout based on VM SKU core count.
/// Larger VMs may take longer to boot; smaller/unknown SKUs default to 300s.
pub(crate) fn ssh_timeout_for_vm_size(sku: &str) -> Duration {
    match extract_core_count(sku) {
        Some(n) if n > 48 => Duration::from_secs(600),
        Some(n) if n > 16 => Duration::from_secs(450),
        _ => Duration::from_secs(300),
    }
}

/// Extract core count from known Azure VM series (D, E, F).
pub(crate) fn extract_core_count(sku: &str) -> Option<u32> {
    for part in sku.split('_') {
        let bytes = part.as_bytes();
        if bytes.is_empty() {
            continue;
        }
        // Check if first char (case-insensitive) is d, e, or f
        let first = bytes[0] | 0x20; // ASCII lowercase
        if first == b'd' || first == b'e' || first == b'f' {
            let mut n: u32 = 0;
            for &b in &bytes[1..] {
                if b.is_ascii_digit() {
                    n = n.saturating_mul(10).saturating_add((b - b'0') as u32);
                } else {
                    break;
                }
            }
            if n > 0 && n <= 1024 {
                return Some(n);
            }
        }
    }
    None
}

/// Check a single region's quota and SKU availability via `az` CLI.
///
/// Uses `az_cli_with_timeout` for timeout protection, pipe-deadlock prevention,
/// and stderr sanitization. Parse failures are surfaced as errors (not silent
/// false-negatives) so broken CLI output doesn't masquerade as "region unavailable".
fn check_region_availability(
    region: &str,
    sku: &str,
    required_cores: u32,
) -> azlin_azure::region_fit::RegionCheckResult {
    let make_error = |msg: String| azlin_azure::region_fit::RegionCheckResult {
        region: region.to_string(),
        sku_available: false,
        quota_available: 0,
        quota_limit: 0,
        has_capacity: false,
        error: Some(msg),
    };

    // Check quota via `az vm list-usage` (timeout + sanitization via az_cli_with_timeout)
    let quota_json =
        match azlin_azure::az_cli_with_timeout(&["vm", "list-usage", "--location", region], 120) {
            Ok(json) => json,
            Err(e) => return make_error(format!("Failed to query quota: {e}")),
        };

    let (quota_available, quota_limit, has_capacity) =
        match azlin_azure::region_fit::parse_quota_json(&quota_json) {
            Ok(q) => {
                let avail = q.available_cores();
                let limit = q.total_regional_limit;
                let cap = q.has_capacity_for(required_cores);
                (avail, limit, cap)
            }
            Err(e) => return make_error(format!("Failed to parse quota response: {e}")),
        };

    // Check SKU availability via `az vm list-skus` (timeout + sanitization)
    let sku_available = match azlin_azure::az_cli_with_timeout(
        &["vm", "list-skus", "--location", region, "--size", sku],
        120,
    ) {
        Ok(json) => azlin_azure::region_fit::parse_sku_availability_json(&json, sku),
        Err(e) => return make_error(format!("Failed to query SKU availability: {e}")),
    };

    azlin_azure::region_fit::RegionCheckResult {
        region: region.to_string(),
        sku_available,
        quota_available,
        quota_limit,
        has_capacity,
        error: None,
    }
}

/// Create a managed disk via az CLI and return its resource ID.
///
/// `session_name` and `role` are used to tag the disk for orphan auditing.
/// `size_gb` must be between 16 and 4096 (Azure Premium SSD bounds).
fn create_managed_disk(
    name: &str,
    size_gb: u32,
    resource_group: &str,
    location: &str,
    session_name: &str,
    role: &str,
    timeout: u64,
) -> Result<String> {
    if !(16..=4096).contains(&size_gb) {
        anyhow::bail!(
            "Disk size must be between 16 and 4096 GB, got {} GB",
            size_gb
        );
    }

    let size_str = size_gb.to_string();
    let session_tag = format!("azlin-session={}", session_name);
    let role_tag = format!("azlin-role={}", role);
    let json = azlin_azure::vm::az_cli_with_timeout(
        &[
            "disk",
            "create",
            "--resource-group",
            resource_group,
            "--name",
            name,
            "--location",
            location,
            "--size-gb",
            &size_str,
            "--sku",
            "Premium_LRS",
            "--tags",
            &session_tag,
            &role_tag,
        ],
        timeout,
    )
    .context(format!("Failed to create managed disk '{}'", name))?;

    // Extract the disk resource ID from the JSON response
    let parsed: serde_json::Value =
        serde_json::from_str(&json).context("Failed to parse disk creation response")?;
    let disk_id = parsed["id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Disk creation response missing 'id' field"))?
        .to_string();

    Ok(disk_id)
}

/// Best-effort cleanup of orphaned managed disks (e.g., when VM creation fails).
fn cleanup_orphaned_disks(disk_ids: &[String], timeout: u64) {
    for disk_id in disk_ids {
        eprintln!("Cleaning up orphaned disk: {}", disk_id);
        if let Err(e) = azlin_azure::vm::az_cli_with_timeout(
            &["disk", "delete", "--ids", disk_id, "--yes", "--no-wait"],
            timeout,
        ) {
            eprintln!("WARNING: Failed to delete orphaned disk {}: {}", disk_id, e);
        }
    }
}

/// Map a VM size tier + family to an Azure SKU string.
pub(crate) fn tier_to_sku(tier: azlin_cli::VmSizeTier, family: azlin_cli::VmFamily) -> String {
    match (tier, family) {
        // D-series v5 (general purpose)
        (azlin_cli::VmSizeTier::Xs, azlin_cli::VmFamily::D) => "Standard_D2s_v5".to_string(),
        (azlin_cli::VmSizeTier::S, azlin_cli::VmFamily::D) => "Standard_D4s_v5".to_string(),
        (azlin_cli::VmSizeTier::M, azlin_cli::VmFamily::D) => "Standard_D8s_v5".to_string(),
        (azlin_cli::VmSizeTier::L, azlin_cli::VmFamily::D) => "Standard_D16s_v5".to_string(),
        (azlin_cli::VmSizeTier::Xl, azlin_cli::VmFamily::D) => "Standard_D32s_v5".to_string(),
        (azlin_cli::VmSizeTier::Xxl, azlin_cli::VmFamily::D) => "Standard_D64s_v5".to_string(),
        // E-series v5 (memory-optimized)
        (azlin_cli::VmSizeTier::Xs, azlin_cli::VmFamily::E) => "Standard_E2as_v5".to_string(),
        (azlin_cli::VmSizeTier::S, azlin_cli::VmFamily::E) => "Standard_E4as_v5".to_string(),
        (azlin_cli::VmSizeTier::M, azlin_cli::VmFamily::E) => "Standard_E8as_v5".to_string(),
        (azlin_cli::VmSizeTier::L, azlin_cli::VmFamily::E) => "Standard_E16as_v5".to_string(),
        (azlin_cli::VmSizeTier::Xl, azlin_cli::VmFamily::E) => "Standard_E32as_v5".to_string(),
        (azlin_cli::VmSizeTier::Xxl, azlin_cli::VmFamily::E) => "Standard_E64as_v5".to_string(),
    }
}

/// Action to take when no bastion host exists in the target region.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum BastionMissingAction {
    /// Create bastion infrastructure, then proceed with private VM.
    CreateBastion,
    /// Switch to public IP instead of bastion-routed.
    SwitchToPublicIp,
    /// Abort VM creation.
    Abort,
}

/// Decide what to do when bastion is missing in the target region.
///
/// - `yes` flag → auto-select CreateBastion
/// - non-TTY stdin → auto-select CreateBastion with warning
/// - TTY stdin → show interactive prompt with 3 options
pub(crate) fn prompt_bastion_action(region: &str, yes: bool) -> Result<BastionMissingAction> {
    use std::io::IsTerminal;

    eprintln!("No Azure Bastion found in {region}. A bastion is required to SSH into private VMs.");

    if yes {
        eprintln!("--yes flag set: auto-creating bastion infrastructure...");
        return Ok(BastionMissingAction::CreateBastion);
    }

    if !std::io::stdin().is_terminal() {
        eprintln!(
            "Warning: non-interactive session detected. Auto-creating bastion infrastructure \
             in {region}. Use --public or --no-bastion to skip bastion for CI pipelines."
        );
        return Ok(BastionMissingAction::CreateBastion);
    }

    let items = &[
        "Create bastion now (takes ~5-10 min)",
        "Switch to public IP instead",
        "Abort",
    ];
    let selection = dialoguer::Select::new()
        .with_prompt("How would you like to proceed?")
        .items(items)
        .default(0)
        .interact()?;

    Ok(match selection {
        0 => BastionMissingAction::CreateBastion,
        1 => BastionMissingAction::SwitchToPublicIp,
        _ => BastionMissingAction::Abort,
    })
}

/// Action to take when the VM subnet in the target region has no NAT gateway.
///
/// Mirrors [`BastionMissingAction`]. Azure Bastion is inbound-only, so a
/// private VM with a bastion but no NAT gateway is reachable yet has zero
/// outbound internet — see issue #1092.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum NatMissingAction {
    /// Create the NAT gateway, then proceed with the private VM.
    CreateNatGateway,
    /// Switch to a public IP instead — an instance IP provides its own egress.
    SwitchToPublicIp,
    /// Abort VM creation.
    Abort,
}

/// Decide what to do about a missing NAT gateway without touching the terminal.
///
/// Returns `None` when there is no automatic answer and the user must be
/// asked. Split out from [`prompt_nat_action`] so the policy is testable: the
/// bastion original reads ambient TTY state inline and cannot be tested at all.
pub(crate) fn decide_nat_action(yes: bool, stdin_is_tty: bool) -> Option<NatMissingAction> {
    if yes || !stdin_is_tty {
        return Some(NatMissingAction::CreateNatGateway);
    }
    None
}

/// Map a `dialoguer::Select` index onto an action.
///
/// Fails closed: any index the menu did not offer aborts rather than
/// proceeding without egress.
pub(crate) fn map_nat_selection(selection: usize) -> NatMissingAction {
    match selection {
        0 => NatMissingAction::CreateNatGateway,
        1 => NatMissingAction::SwitchToPublicIp,
        _ => NatMissingAction::Abort,
    }
}

/// The manual remediation steps, with no framing verdict of their own.
///
/// Shared by the two paths that reach it, which must NOT claim the same thing:
/// declining creates nothing, whereas a failure part-way through provisioning
/// may have already created the public IP and the gateway. So the verdict
/// belongs to the caller and only the steps are shared.
///
/// `resource_group` is interpolated rather than left as a `<rg>` placeholder:
/// a command the user has to hand-edit before running is not remediation.
fn nat_remediation_text(resource_group: &str, region: &str) -> String {
    let natgw = crate::nat_helpers::natgw_name_for_region(region);
    let pip = crate::nat_helpers::natgw_pip_name(region);
    format!(
        "Azure Bastion is inbound-only: it lets you reach the VM, but it does not \
         provide egress. Without a NAT gateway every apt/curl/wget on the VM fails \
         and the cloud-init toolchain install collapses.\n\n\
         To provision egress manually:\n  \
         az network public-ip create --resource-group {resource_group} --name {pip} \
         --location {region} --sku Standard --allocation-method Static --zone 1 2 3\n  \
         az network nat gateway create --resource-group {resource_group} --name {natgw} \
         --location {region} --sku Standard --idle-timeout 10 \
         --public-ip-addresses {pip}\n  \
         az network vnet subnet update --resource-group {resource_group} \
         --vnet-name {vnet} --name default --nat-gateway {natgw}\n\n\
         Or re-run with --public to give this VM its own public IP instead.",
        vnet = crate::bastion_helpers::bastion_vnet_name(region),
    )
}

/// The error text shown when the user declines NAT provisioning.
///
/// This issue is about silent degradation, so declining must fail loudly *and*
/// actionably: naming both resources and the exact `az` commands means a user
/// who says no can still fix it by hand.
pub(crate) fn nat_abort_message(resource_group: &str, region: &str) -> String {
    let region = region.to_lowercase();
    format!(
        "Aborted: the VM subnet in {region} has no NAT gateway, so a private VM \
         created there would have no outbound internet.\n{}",
        nat_remediation_text(resource_group, &region)
    )
}

/// The error text shown when NAT provisioning was attempted and failed.
///
/// Deliberately distinct from [`nat_abort_message`]. Provisioning creates the
/// public IP, then the gateway, then the subnet association, so a failure at
/// step two or three leaves real resources behind — a Standard public IP costs
/// money whether or not anything is attached to it. Calling that "Aborted"
/// tells the user nothing exists while two resources bill, which is the same
/// silent-degradation defect this issue exists to remove, one layer up.
pub(crate) fn nat_provisioning_failed_message(resource_group: &str, region: &str) -> String {
    let region = region.to_lowercase();
    let natgw = crate::nat_helpers::natgw_name_for_region(&region);
    let pip = crate::nat_helpers::natgw_pip_name(&region);
    format!(
        "NAT gateway provisioning FAILED for {region}, so no VM was created.\n\
         Provisioning runs in three steps, so partial resources may already exist \
         and may already be billing. Check resource group '{resource_group}' for \
         public IP '{pip}' and NAT gateway '{natgw}' before retrying:\n  \
         az network nat gateway list --resource-group {resource_group} -o table\n  \
         az network public-ip list --resource-group {resource_group} -o table\n\n\
         Re-running `azlin new` is safe: provisioning is idempotent and reuses \
         whatever already exists.\n\n{}",
        nat_remediation_text(resource_group, &region)
    )
}

/// Ask the user what to do about a missing NAT gateway.
///
/// - `--yes` or a non-TTY stdin → auto-create (never hang a script, never
///   silently ship a VM with no egress)
/// - interactive → three options mirroring the bastion prompt
pub(crate) fn prompt_nat_action(region: &str, yes: bool) -> Result<NatMissingAction> {
    use std::io::IsTerminal;

    eprintln!(
        "No NAT gateway found for the VM subnet in {region}. Private VMs there have \
         no outbound internet (Azure Bastion is inbound-only)."
    );

    if let Some(action) = decide_nat_action(yes, std::io::stdin().is_terminal()) {
        if yes {
            eprintln!("--yes flag set: auto-creating NAT gateway...");
        } else {
            eprintln!(
                "Warning: non-interactive session detected. Auto-creating a NAT gateway \
                 in {region} so the VM has outbound internet. Use --public to give the VM \
                 its own public IP instead."
            );
        }
        return Ok(action);
    }

    let items = &[
        "Create NAT gateway now (takes ~1-2 min, ~$36/mo per region)",
        "Switch to public IP instead",
        "Abort",
    ];
    let selection = dialoguer::Select::new()
        .with_prompt("How would you like to proceed?")
        .items(items)
        .default(0)
        .interact()?;

    Ok(map_nat_selection(selection))
}

fn requires_post_create_ssh(
    repo_requested: bool,
    has_home_seed_sources: bool,
    auto_connect_requested: bool,
) -> bool {
    repo_requested || has_home_seed_sources || auto_connect_requested
}

fn resource_group_from_arm_id(resource_id: &str) -> Option<&str> {
    resource_id
        .split("/resourceGroups/")
        .nth(1)?
        .split('/')
        .next()
}

fn select_bastion_resource_group(
    bastions: &[serde_json::Value],
    bastion_name: &str,
) -> Result<Option<String>> {
    let matches: Vec<String> = bastions
        .iter()
        .filter(|b| b["name"].as_str() == Some(bastion_name))
        .filter_map(|b| {
            b["resourceGroup"].as_str().map(str::to_owned).or_else(|| {
                b["id"]
                    .as_str()
                    .and_then(resource_group_from_arm_id)
                    .map(str::to_owned)
            })
        })
        .collect();

    match matches.as_slice() {
        [] => Ok(None),
        [resource_group] => Ok(Some(resource_group.clone())),
        _ => anyhow::bail!(
            "Azure Bastion '{}' is ambiguous across resource groups: {}",
            bastion_name,
            matches.join(", ")
        ),
    }
}

fn resolve_bastion_resource_group_by_name(bastion_name: &str) -> Result<Option<String>> {
    let output = std::process::Command::new("az")
        .args(["network", "bastion", "list", "--output", "json"])
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to query Azure Bastion hosts: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    let bastions: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)?;
    select_bastion_resource_group(&bastions, bastion_name)
}

fn apply_bastion_name_override(
    target: &mut crate::VmSshTarget,
    bastion_name: Option<&str>,
    bastion_resource_group: Option<&str>,
    resource_group: &str,
    subscription_id: &str,
    vm_name: &str,
    needs_bastion_route: bool,
) {
    let Some(override_name) = bastion_name else {
        return;
    };
    let override_resource_group = bastion_resource_group.unwrap_or(resource_group);

    if let Some(bastion) = &mut target.bastion {
        bastion.bastion_name = override_name.to_string();
        bastion.resource_group = override_resource_group.to_string();
        return;
    }

    if needs_bastion_route {
        target.bastion = Some(crate::BastionRoute {
            bastion_name: override_name.to_string(),
            resource_group: override_resource_group.to_string(),
            vm_resource_id: crate::ssh_arg_helpers::build_vm_resource_id(
                subscription_id,
                resource_group,
                vm_name,
            ),
            ssh_key_path: target.ssh_key_path.clone(),
        });
    }
}

fn apply_post_create_ssh_identity(
    target: &mut crate::VmSshTarget,
    created_private_key: Option<&std::path::Path>,
) {
    let Some(created_private_key) = created_private_key else {
        return;
    };
    let key_path = created_private_key.to_path_buf();
    target.ssh_key_path = Some(key_path.clone());
    if let Some(ref mut bastion) = target.bastion {
        bastion.ssh_key_path = Some(key_path);
    }
}

#[allow(clippy::too_many_arguments)]
fn prepare_post_create_target(
    target: &mut crate::VmSshTarget,
    created_private_key: Option<&std::path::Path>,
    bastion_name: Option<&str>,
    bastion_resource_group: Option<&str>,
    resource_group: &str,
    subscription_id: &str,
    vm_name: &str,
    needs_bastion_route: bool,
) {
    apply_post_create_ssh_identity(target, created_private_key);
    apply_bastion_name_override(
        target,
        bastion_name,
        bastion_resource_group,
        resource_group,
        subscription_id,
        vm_name,
        needs_bastion_route,
    );
}

fn post_create_bastion_route(target: &crate::VmSshTarget) -> Option<(&str, &str, &str)> {
    let bastion = target.bastion.as_ref()?;
    Some((
        bastion.bastion_name.as_str(),
        bastion.resource_group.as_str(),
        bastion.vm_resource_id.as_str(),
    ))
}

#[allow(clippy::too_many_arguments)]
pub(crate) async fn handle_vm_new(
    repo: Option<String>,
    size: Option<azlin_cli::VmSizeTier>,
    vm_size: Option<String>,
    vm_family: Option<azlin_cli::VmFamily>,
    region_fit: bool,
    region: Option<String>,
    resource_group: Option<String>,
    name: Option<String>,
    pool: Option<u32>,
    no_auto_connect: bool,
    template: Option<String>,
    nfs_storage: Option<String>,
    _no_nfs: bool,
    no_bastion: bool,
    _no_tmux: bool,
    _tmux_session: Option<String>,
    bastion_name: Option<String>,
    private: bool,
    public: bool,
    yes: bool,
    home_disk_size: Option<u32>,
    no_home_disk: bool,
    tmp_disk_size: Option<u32>,
    os_image: Option<String>,
) -> Result<()> {
    // Resolve public IP intent: default is private (bastion-routed).
    // --public or --no-bastion opts in to a public IP.
    // --private is now the default and kept for backward compat.
    let mut want_public_ip = public || no_bastion;

    if private && want_public_ip {
        anyhow::bail!(
            "--private and --public/--no-bastion cannot be used together: \
             a private VM has no public IP and requires bastion for SSH access"
        );
    }

    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;

    // Resolve VM size: --vm-size overrides --size tier, which overrides config default
    let vm_count = pool.unwrap_or(1);
    // `--config` is resolved once in main() and installed as the process
    // config path, so this is the same call every other command makes. The
    // previous code branched on a per-variant `config` field and, on either
    // branch, warned and continued with defaults — which meant a typo'd path
    // or a malformed file provisioned a VM of the default size in the default
    // region while printing "Warning:" above a wall of progress output.
    let config_defaults = crate::dispatch_helpers::load_user_config();
    let user_specified_size = vm_size.is_some() || size.is_some();
    let user_specified_region = region.is_some();

    // --vm-size takes priority, then --size tier mapping, then config default.
    // If --vm-family is set without --size, apply the family to the default tier (L).
    // For xl/2xl tiers, default to E-series (memory-optimized, better availability)
    // unless user explicitly requested D-series.
    let explicit_family = vm_family;
    let resolve_family = |tier: azlin_cli::VmSizeTier| -> azlin_cli::VmFamily {
        match explicit_family {
            Some(f) => f,
            None => match tier {
                azlin_cli::VmSizeTier::Xl | azlin_cli::VmSizeTier::Xxl => azlin_cli::VmFamily::E,
                _ => azlin_cli::VmFamily::D,
            },
        }
    };
    let size = if let Some(explicit) = vm_size {
        explicit
    } else if let Some(tier) = size {
        tier_to_sku(tier, resolve_family(tier))
    } else if let Some(family) = explicit_family {
        tier_to_sku(azlin_cli::VmSizeTier::L, family)
    } else {
        config_defaults.default_vm_size.clone()
    };
    // Region precedence matches the resource group's: --region, then the
    // active context, then the config default. Reading the config default
    // directly here meant a context's `region` was recorded and ignored
    // (#1090).
    let loc = crate::active_context::resolve_region(
        region,
        crate::active_context::load_active()?.as_ref(),
        config_defaults.default_region.clone(),
    );

    // ── Region-fit: auto-find a region with available quota + SKU ──────
    let loc = if region_fit {
        // Estimate cores from SKU name for capacity checking
        let estimated_cores = extract_core_count(&size).unwrap_or(8) * vm_count;
        let candidates = azlin_azure::region_fit::candidate_regions_with_preferred(&loc);
        let mut results = Vec::new();
        let mut found_region: Option<String> = None;

        eprintln!(
            "🔍 Scanning {} regions for available quota and SKU...",
            candidates.len()
        );

        for candidate in &candidates {
            let check = check_region_availability(candidate, &size, estimated_cores);
            let usable = check.is_usable();
            let avail = check.quota_available;
            results.push(check);
            if usable {
                found_region = Some(candidate.to_string());
                eprintln!(
                    "✓ Selected region: {} (SKU available, {} cores free)",
                    candidate, avail
                );
                break;
            }
        }

        if let Some(ref region) = found_region {
            region.clone()
        } else {
            eprintln!("✗ No region found with available quota and SKU.\n");
            eprintln!("{}", azlin_azure::region_fit::format_region_table(&results));
            anyhow::bail!(
                "No region found with available quota for {} (needs {} cores). \
                 Try a smaller VM size or request a quota increase.",
                size,
                estimated_cores,
            );
        }
    } else {
        loc
    };
    let admin_user = DEFAULT_ADMIN_USERNAME.to_string();
    let keypair = crate::key_helpers::ensure_ssh_keypair().map_err(|e| anyhow::anyhow!("{e}"))?;
    let ssh_key_path = keypair.public_key;
    let should_seed_home =
        crate::create_helpers::should_seed_remote_home(name.as_deref(), vm_count);
    let has_home_seed_sources = if should_seed_home {
        let home_sync_dir = home_dir()?.join(".azlin").join("home");
        crate::create_helpers::collect_home_seed_sources(&home_sync_dir)?.is_some()
    } else {
        false
    };
    let auto_connect_requested = !no_auto_connect && vm_count == 1;
    let interactive_post_create_ssh = std::io::stdin().is_terminal();
    let requires_created_private_key = requires_post_create_ssh(
        repo.is_some(),
        has_home_seed_sources,
        auto_connect_requested,
    );
    let created_private_key = if requires_created_private_key {
        Some(crate::create_helpers::require_matching_private_key_for_public_key(&ssh_key_path)?)
    } else {
        crate::create_helpers::matching_private_key_for_public_key(&ssh_key_path)
    };

    let (tmpl_size, tmpl_region) = if let Some(ref tmpl_name) = template {
        if let Err(e) = crate::name_validation::validate_name(tmpl_name) {
            anyhow::bail!("Invalid template name: {}", e);
        }
        let templates_dir = dirs::home_dir()
            .unwrap_or_default()
            .join(".config")
            .join("azlin")
            .join("templates");
        let tmpl_path = templates_dir.join(format!("{}.toml", tmpl_name));
        if tmpl_path.exists() {
            let content = std::fs::read_to_string(&tmpl_path)?;
            let tmpl: toml::Value = content.parse()?;
            let ts = tmpl
                .get("vm_size")
                .and_then(|v| v.as_str())
                .map(String::from);
            let tr = tmpl
                .get("region")
                .and_then(|v| v.as_str())
                .map(String::from);
            (ts, tr)
        } else {
            eprintln!(
                "Template '{}' not found at {}",
                tmpl_name,
                tmpl_path.display()
            );
            (None, None)
        }
    } else {
        (None, None)
    };

    let final_size = if !user_specified_size {
        tmpl_size.unwrap_or(size)
    } else {
        size
    };
    let final_loc = if !user_specified_region {
        tmpl_region.unwrap_or(loc)
    } else {
        loc
    };

    // ── Bastion pre-check: ensure bastion infrastructure exists before
    //    creating private VMs that depend on it for SSH access ──────────
    if !want_public_ip {
        let bastions = match crate::list_helpers::detect_bastion_hosts(&rg) {
            Ok(b) => b,
            Err(e) => {
                eprintln!(
                    "Warning: failed to detect bastion hosts ({}). \
                     Assuming none exist in {final_loc}.",
                    e
                );
                vec![]
            }
        };
        if !crate::bastion_helpers::bastion_exists_in_region(&bastions, &final_loc) {
            match prompt_bastion_action(&final_loc, yes)? {
                BastionMissingAction::CreateBastion => {
                    let pb = penguin_spinner(&format!(
                        "Provisioning bastion infrastructure in {}...",
                        final_loc
                    ));
                    let ip_tags = config_defaults.bastion_pip_ip_tags();
                    let result = crate::bastion_helpers::ensure_bastion_infrastructure(
                        &rg, &final_loc, &ip_tags,
                    );
                    pb.finish_and_clear();
                    result?;
                }
                BastionMissingAction::SwitchToPublicIp => {
                    eprintln!("Switching to public IP for this VM.");
                    want_public_ip = true;
                }
                BastionMissingAction::Abort => {
                    anyhow::bail!(
                        "Aborted: no bastion host in {final_loc} and user chose not to create one"
                    );
                }
            }
        }
    }

    // ── NAT gateway pre-check: a bastion is INBOUND only. Without a NAT
    //    gateway on the VM subnet a private VM has zero outbound internet:
    //    it connects fine, but apt/curl/wget all fail and the cloud-init
    //    toolchain install collapses silently (issue #1092).
    //
    //    `want_public_ip` is re-tested rather than nested in the block above
    //    because SwitchToPublicIp mutates it — a VM that just opted into a
    //    public IP has its own egress and needs no gateway. The check is
    //    outside the per-VM loop: a NAT gateway is regional and shared.
    if !want_public_ip {
        let ip_tags = config_defaults.bastion_pip_ip_tags();
        // The gate itself lives in `egress_gate` so every branch of it can be
        // driven from a unit test; the Azure read, the prompt and the
        // provisioning step are passed in from here (#1102). The property it
        // enforces — R4, never fall through to `az vm create` without egress —
        // is carried by `EgressDecision` having no "proceed anyway" variant.
        let decision = crate::egress_gate::resolve_private_vm_egress(
            &rg,
            &final_loc,
            || crate::nat_helpers::detect_nat_status(&rg, &final_loc),
            || prompt_nat_action(&final_loc, yes),
            || {
                let pb = penguin_spinner(&format!("Provisioning NAT gateway in {}...", final_loc));
                let result = crate::nat_helpers::ensure_nat_gateway(&rg, &final_loc, &ip_tags);
                pb.finish_and_clear();
                result
            },
        )?;
        match decision {
            crate::egress_gate::EgressDecision::NatGateway { name: Some(name) } => {
                eprintln!("  ✓ NAT gateway '{name}' provides egress for {final_loc}");
            }
            // Nothing to print: `None` means this run provisioned the
            // gateway, and `ensure_nat_gateway` has already reported each of
            // its three steps.
            crate::egress_gate::EgressDecision::NatGateway { name: None } => {}
            crate::egress_gate::EgressDecision::SwitchToPublicIp => {
                eprintln!(
                    "Switching to public IP for this VM \
                     (an instance IP provides its own egress)."
                );
                want_public_ip = true;
            }
        }
    }

    // R5. Collected across the loop so every VM's name and connection details
    // are printed before we exit non-zero — aborting mid-loop would strand a
    // billing VM the user cannot find.
    let mut degraded_vms = crate::egress_gate::DegradedVms::new();

    for i in 0..vm_count {
        let vm_name = if let Some(ref n) = name {
            if vm_count > 1 {
                format!("{}-{}", n, i + 1)
            } else {
                n.clone()
            }
        } else {
            format!("azlin-vm-{}", chrono::Utc::now().format("%Y%m%d-%H%M%S%6f"))
        };

        azlin_core::models::validate_vm_name(&vm_name).map_err(|e| anyhow::anyhow!(e))?;

        let mut tags = std::collections::HashMap::new();
        let session_tag = crate::create_helpers::resolve_session_identity(
            name.as_deref(),
            &vm_name,
            vm_count as usize,
        );
        tags.insert("azlin-session".to_string(), session_tag.clone());

        // Resolve OS image early (before creating billable resources like disks).
        // Priority: --os flag > config default_vm_image > VmImage::default()
        let image = if let Some(ref os_spec) = os_image {
            azlin_core::models::VmImage::from_image_spec(os_spec)
                .map_err(|e| anyhow::anyhow!("Invalid --os value: {}", e))?
        } else if let Some(ref config_image) = config_defaults.default_vm_image {
            azlin_core::models::VmImage::from_image_spec(config_image)
                .map_err(|e| anyhow::anyhow!("Invalid default_vm_image in config: {}", e))?
        } else {
            azlin_core::models::VmImage::default()
        };

        // Create managed data disks if requested (home disk at LUN 0, tmp disk at LUN 1)
        let default_home_size = 100;
        let want_home_disk = !no_home_disk;
        let home_size = home_disk_size.unwrap_or(default_home_size);
        let mut disk_ids = Vec::new();

        if want_home_disk {
            let disk_name = format!("{}_home", vm_name);
            println!("Creating home disk '{}' ({}GB)...", disk_name, home_size);
            match create_managed_disk(
                &disk_name,
                home_size,
                &rg,
                &final_loc,
                &session_tag,
                "home",
                vm_manager.az_cli_timeout(),
            ) {
                Ok(disk_id) => disk_ids.push(disk_id),
                Err(e) => {
                    // Clean up any partially created disks before propagating
                    cleanup_orphaned_disks(&disk_ids, vm_manager.az_cli_timeout());
                    return Err(e);
                }
            }
        }

        if let Some(tmp_size) = tmp_disk_size {
            let disk_name = format!("{}_tmp", vm_name);
            println!("Creating tmp disk '{}' ({}GB)...", disk_name, tmp_size);
            match create_managed_disk(
                &disk_name,
                tmp_size,
                &rg,
                &final_loc,
                &session_tag,
                "tmp",
                vm_manager.az_cli_timeout(),
            ) {
                Ok(disk_id) => disk_ids.push(disk_id),
                Err(e) => {
                    // Clean up any previously created disks before propagating
                    cleanup_orphaned_disks(&disk_ids, vm_manager.az_cli_timeout());
                    return Err(e);
                }
            }
        }

        let params = azlin_core::models::CreateVmParams {
            name: vm_name.clone(),
            resource_group: rg.clone(),
            region: final_loc.clone(),
            vm_size: final_size.clone(),
            admin_username: admin_user.clone(),
            ssh_key_path: ssh_key_path.clone(),
            image,
            tags,
            public_ip_enabled: want_public_ip,
            disk_ids: disk_ids.clone(),
            has_home_disk: want_home_disk,
            has_tmp_disk: tmp_disk_size.is_some(),
        };

        if let Err(e) = params.validate() {
            // Clean up orphaned disks before bailing
            cleanup_orphaned_disks(&disk_ids, vm_manager.az_cli_timeout());
            anyhow::bail!("Invalid VM parameters: {}", e);
        }

        let pb = penguin_spinner(&format!("Creating VM '{}'...", vm_name));
        let vm_result = vm_manager.create_vm(&params);
        pb.finish_and_clear();

        let vm = match vm_result {
            Ok(vm) => vm,
            Err(e) => {
                // Clean up orphaned disks on VM creation failure
                cleanup_orphaned_disks(&disk_ids, vm_manager.az_cli_timeout());
                return Err(e);
            }
        };

        if let Some(ref nfs) = nfs_storage {
            eprintln!(
                "Warning: --nfs-storage '{}' accepted but NFS mounting is not yet implemented in the Rust CLI.",
                nfs
            );
        }

        let mut table = crate::table_render::SimpleTable::new(&["Property", "Value"], &[14, 40]);
        table.add_row(vec!["Name".to_string(), vm.name.clone()]);
        table.add_row(vec!["Resource Group".to_string(), rg.clone()]);
        table.add_row(vec!["Size".to_string(), final_size.clone()]);
        table.add_row(vec!["Region".to_string(), final_loc.clone()]);
        table.add_row(vec!["State".to_string(), vm.power_state.to_string()]);
        if let Some(ref ip) = vm.public_ip {
            table.add_row(vec!["Public IP".to_string(), ip.clone()]);
        }
        if let Some(ref ip) = vm.private_ip {
            table.add_row(vec!["Private IP".to_string(), ip.clone()]);
        }
        println!("{table}");

        let created_private_key = match created_private_key.as_ref() {
            Some(key) => key,
            None => {
                println!("VM '{}' created successfully!", vm.name);
                println!(
                    "Provisioning used '{}' but matching private key '{}' is unavailable locally; skipping guest-readiness checks and post-create SSH actions.",
                    ssh_key_path.display(),
                    ssh_key_path.with_extension("").display()
                );
                continue;
            }
        };

        // Resolve SSH target with bastion support
        let mut target = if no_bastion {
            // --no-bastion: skip bastion auto-detection, use public IP only
            let vm_ip = vm
                .public_ip
                .as_deref()
                .filter(|ip| !ip.is_empty())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "VM '{}' has no public IP and --no-bastion was specified; \
                     remove --no-bastion to allow bastion auto-detection",
                        vm_name
                    )
                })?
                .to_string();
            crate::VmSshTarget {
                vm_name: vm_name.clone(),
                ip: vm_ip,
                user: admin_user.clone(),
                ssh_key_path: Some(created_private_key.clone()),
                allow_preferred_key_fallback: true,
                bastion: None,
            }
        } else {
            resolve_vm_ssh_target(&vm.name, None, Some(rg.clone())).await?
        };
        let needs_bastion_route = crate::ssh_arg_helpers::needs_bastion(vm.public_ip.as_deref());
        let resolved_bastion_resource_group = if let Some(override_name) = bastion_name.as_deref() {
            if target.bastion.is_some() || needs_bastion_route {
                Some(
                    resolve_bastion_resource_group_by_name(override_name)?.ok_or_else(|| {
                        anyhow::anyhow!(
                            "Azure Bastion '{}' was not found in the current subscription",
                            override_name
                        )
                    })?,
                )
            } else {
                None
            }
        } else {
            None
        };
        prepare_post_create_target(
            &mut target,
            Some(created_private_key.as_path()),
            bastion_name.as_deref(),
            resolved_bastion_resource_group.as_deref(),
            &rg,
            vm_manager.subscription_id(),
            &vm.name,
            needs_bastion_route,
        );

        // Set up bastion tunnel if needed (kept alive for auth + clone + connect)
        // --bastion-name overrides auto-detected bastion
        let _tunnel = if let Some((bastion_name, resource_group, vm_resource_id)) =
            post_create_bastion_route(&target)
        {
            Some(
                crate::bastion_tunnel::ScopedBastionTunnel::new(
                    bastion_name,
                    resource_group,
                    vm_resource_id,
                )
                .await?,
            )
        } else {
            None
        };
        let bastion_port = _tunnel.as_ref().map(|t| t.local_port);
        let effective_ip = if bastion_port.is_some() {
            "127.0.0.1"
        } else {
            &target.ip
        };

        let ssh_timeout = ssh_timeout_for_vm_size(&final_size);
        let readiness = crate::auth_forward::wait_for_post_create_readiness(
            effective_ip,
            &admin_user,
            bastion_port,
            Some(created_private_key.as_path()),
            interactive_post_create_ssh,
            ssh_timeout,
            None,
        )
        .with_context(|| format!("VM '{}' was created but is not yet guest-ready", vm.name))?;

        if !readiness.is_ready() {
            eprintln!("⚠ {}", readiness.recovery_message());
        }

        // Cheap outbound-internet probe. A private VM with no NAT gateway is
        // reachable and reports Running, so without this check a silently
        // broken VM is announced as "created successfully" (issue #1092).
        // `egress_probe_shortcut` skips the round-trip in the two cases where
        // it cannot change the verdict -- a public-IP VM, and a VM whose SSH
        // readiness timed out.
        let egress = match crate::auth_forward::egress_probe_shortcut(
            want_public_ip,
            readiness.is_ready(),
        ) {
            Some(status) => status,
            None => crate::auth_forward::verify_egress(
                effective_ip,
                &admin_user,
                bastion_port,
                Some(created_private_key.as_path()),
                interactive_post_create_ssh,
            ),
        };
        match egress {
            crate::auth_forward::EgressStatus::Failed => {
                eprintln!(
                    "⚠ {}",
                    crate::auth_forward::egress_failure_message(&vm.name, &rg, &final_loc)
                );
                degraded_vms.record(&vm.name);
                // Deliberately not an early return: the VM exists and is
                // billing, so its name and connection details must still be
                // printed. The non-zero exit is raised after the loop.
                println!(
                    "VM '{}' created — DEGRADED: no outbound internet access.",
                    vm.name
                );
            }
            crate::auth_forward::EgressStatus::Unknown => {
                eprintln!(
                    "Warning: could not verify outbound internet on '{}'. If package \
                     installs fail, check for a NAT gateway in {final_loc}.",
                    vm.name
                );
                println!("VM '{}' created successfully!", vm.name);
            }
            crate::auth_forward::EgressStatus::Ok => {
                println!("VM '{}' created successfully!", vm.name);
            }
        }

        // Forward auth credentials to the new VM (best-effort)
        if let Err(e) = crate::auth_forward::forward_auth_credentials(
            effective_ip,
            &admin_user,
            yes,
            bastion_port,
            Some(created_private_key.as_path()),
            interactive_post_create_ssh,
        ) {
            eprintln!("Warning: auth forwarding failed: {}", e);
        }

        if should_seed_home {
            let home_sync_dir = home_dir()?.join(".azlin").join("home");
            let ssh_transport = crate::dispatch_helpers::build_routed_ssh_transport_with_mode(
                &target,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                Some(created_private_key.as_path()),
                !interactive_post_create_ssh,
            );
            println!("Seeding remote home from {}...", home_sync_dir.display());
            let seeded = crate::create_helpers::seed_remote_home_with_runner(
                &home_sync_dir,
                &target.user,
                effective_ip,
                Some(ssh_transport.as_str()),
                |args| {
                    let status = std::process::Command::new("rsync").args(args).status()?;
                    Ok(status.code().unwrap_or(-1))
                },
            )?;
            if seeded {
                println!("Remote home seeded.");
            } else {
                println!(
                    "No seed files found in {}; skipping remote home seeding.",
                    home_sync_dir.display()
                );
            }
        }

        if let Some(ref repo_url) = repo {
            let clone_cmd = match crate::create_helpers::build_clone_cmd(repo_url) {
                Ok(cmd) => cmd,
                Err(e) => {
                    eprintln!("Invalid repository URL: {}", e);
                    return Ok(());
                }
            };
            println!("Cloning repository '{}'...", repo_url);
            let mut ssh_args = crate::create_helpers::build_post_create_ssh_args(
                &target.user,
                effective_ip,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                Some(created_private_key.as_path()),
                !interactive_post_create_ssh,
            );
            ssh_args.push(clone_cmd.clone());
            let (exit_code, stdout, stderr) = if interactive_post_create_ssh {
                let status = std::process::Command::new("ssh")
                    .args(&ssh_args)
                    .stdin(std::process::Stdio::inherit())
                    .stdout(std::process::Stdio::inherit())
                    .stderr(std::process::Stdio::inherit())
                    .status()?;
                (status.code().unwrap_or(-1), String::new(), String::new())
            } else {
                let output = std::process::Command::new("ssh").args(&ssh_args).output()?;
                (
                    output.status.code().unwrap_or(-1),
                    String::from_utf8_lossy(&output.stdout).to_string(),
                    String::from_utf8_lossy(&output.stderr).to_string(),
                )
            };
            if exit_code == 0 {
                println!("Repository cloned successfully.");
                if !stdout.is_empty() {
                    print!("{}", stdout);
                }
            } else {
                eprintln!(
                    "Failed to clone repository: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
        }

        if !no_auto_connect && vm_count == 1 {
            println!("Connecting to '{}'...", vm_name);
            let identity_key = target.ssh_key_path.as_deref().or_else(|| {
                target
                    .bastion
                    .as_ref()
                    .and_then(|bastion| bastion.ssh_key_path.as_deref())
            });
            let ssh_args = crate::create_helpers::build_auto_connect_ssh_args(
                &target.user,
                effective_ip,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                identity_key,
            );
            let status = std::process::Command::new("ssh").args(&ssh_args).status()?;
            if !status.success() {
                eprintln!("SSH connection ended with exit code: {:?}", status.code());
            }
        }
    }

    // Every VM's name and connection details have now been printed, so it is
    // safe to exit non-zero. Reporting a VM with no egress as a success is the
    // silent degradation this whole change exists to remove.
    if let Some(failure) = degraded_vms.into_failure(&final_loc) {
        return Err(failure);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_apply_bastion_name_override_updates_target_route() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard".to_string(),
                ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            }),
        };

        super::apply_bastion_name_override(
            &mut target,
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        assert_eq!(
            target.bastion.as_ref().map(|b| b.bastion_name.as_str()),
            Some("override-bastion")
        );
        assert_eq!(
            target.bastion.as_ref().map(|b| b.resource_group.as_str()),
            Some("network-rg")
        );
    }

    #[test]
    fn test_apply_bastion_name_override_ignores_missing_override() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard".to_string(),
                ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            }),
        };

        super::apply_bastion_name_override(&mut target, None, None, "rg", "sub", "simard", true);

        assert_eq!(
            target.bastion.as_ref().map(|b| b.bastion_name.as_str()),
            Some("auto-detected")
        );
    }

    #[test]
    fn test_apply_bastion_name_override_creates_private_route_when_missing() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: None,
        };

        super::apply_bastion_name_override(
            &mut target,
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        let bastion = target.bastion.as_ref().unwrap();
        assert_eq!(bastion.bastion_name, "override-bastion");
        assert_eq!(bastion.resource_group, "network-rg");
        assert_eq!(
            bastion.ssh_key_path.as_deref(),
            Some(std::path::Path::new("/tmp/key"))
        );
        assert_eq!(
            bastion.vm_resource_id,
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard"
        );
    }

    #[test]
    fn test_prepare_post_create_target_reuses_key_and_override_for_bastion() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id:
                    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard"
                        .to_string(),
                ssh_key_path: None,
            }),
        };

        let created_key = std::path::Path::new("/tmp/created-key");
        super::prepare_post_create_target(
            &mut target,
            Some(created_key),
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        assert_eq!(target.ssh_key_path.as_deref(), Some(created_key));
        let bastion = target.bastion.as_ref().unwrap();
        assert_eq!(bastion.bastion_name, "override-bastion");
        assert_eq!(bastion.resource_group, "network-rg");
        assert_eq!(bastion.ssh_key_path.as_deref(), Some(created_key));
        assert_eq!(
            super::post_create_bastion_route(&target),
            Some((
                "override-bastion",
                "network-rg",
                "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard",
            ))
        );
    }

    #[test]
    fn test_select_bastion_resource_group_matches_by_name() {
        let bastions = vec![serde_json::json!({
            "name": "corp-bastion",
            "resourceGroup": "network-rg"
        })];
        assert_eq!(
            super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap(),
            Some("network-rg".to_string())
        );
    }

    #[test]
    fn test_select_bastion_resource_group_uses_arm_id_fallback() {
        let bastions = vec![serde_json::json!({
            "name": "corp-bastion",
            "id": "/subscriptions/sub/resourceGroups/network-rg/providers/Microsoft.Network/bastionHosts/corp-bastion"
        })];
        assert_eq!(
            super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap(),
            Some("network-rg".to_string())
        );
    }

    #[test]
    fn test_select_bastion_resource_group_rejects_ambiguous_matches() {
        let bastions = vec![
            serde_json::json!({"name": "corp-bastion", "resourceGroup": "network-rg-1"}),
            serde_json::json!({"name": "corp-bastion", "resourceGroup": "network-rg-2"}),
        ];
        let err = super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap_err();
        assert!(err.to_string().contains("ambiguous"));
    }

    #[test]
    fn test_requires_post_create_ssh_is_false_for_create_only() {
        assert!(!super::requires_post_create_ssh(false, false, false));
    }

    #[test]
    fn test_requires_post_create_ssh_is_true_for_repo_seed_or_auto_connect() {
        assert!(super::requires_post_create_ssh(true, false, false));
        assert!(super::requires_post_create_ssh(false, true, false));
        assert!(super::requires_post_create_ssh(false, false, true));
    }

    // ── BastionMissingAction enum tests ──────────────────────────────

    #[test]
    fn test_bastion_missing_action_enum_variants() {
        // Verify all three variants exist and are distinguishable
        let create = super::BastionMissingAction::CreateBastion;
        let switch = super::BastionMissingAction::SwitchToPublicIp;
        let abort = super::BastionMissingAction::Abort;
        assert_ne!(create, switch);
        assert_ne!(create, abort);
        assert_ne!(switch, abort);
    }

    #[test]
    fn test_bastion_missing_action_is_copy() {
        let action = super::BastionMissingAction::CreateBastion;
        let copy = action; // Copy
        assert_eq!(action, copy);
    }

    // ── prompt_bastion_action tests ──────────────────────────────────

    #[test]
    fn test_prompt_bastion_action_yes_flag_returns_create_bastion() {
        // When --yes is set, should always auto-create without prompting
        let result = super::prompt_bastion_action("eastus2", true).unwrap();
        assert_eq!(result, super::BastionMissingAction::CreateBastion);
    }

    #[test]
    #[ignore = "requires non-TTY stdin; hangs in interactive terminals because dialoguer blocks"]
    fn test_prompt_bastion_action_non_tty_returns_create_bastion() {
        // In CI/non-interactive mode (piped stdin), should auto-create.
        // This test only works when stdin is NOT a terminal (e.g. CI piped
        // stdin). In an interactive TTY session, dialoguer::Select blocks
        // forever waiting for user input, so we #[ignore] by default and
        // run explicitly in CI with: cargo test -- --ignored
        let result = super::prompt_bastion_action("westus", false);
        match result {
            Ok(action) => assert_eq!(action, super::BastionMissingAction::CreateBastion),
            Err(e) => {
                assert!(
                    e.to_string().contains("io error") || e.to_string().contains("not a terminal"),
                    "Unexpected error: {e}"
                );
            }
        }
    }

    // ── tier_to_sku tests ────────────────────────────────────────────

    #[test]
    fn test_tier_to_sku_d_series_all_tiers() {
        use azlin_cli::{VmFamily, VmSizeTier};
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xs, VmFamily::D),
            "Standard_D2s_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::S, VmFamily::D),
            "Standard_D4s_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::M, VmFamily::D),
            "Standard_D8s_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::L, VmFamily::D),
            "Standard_D16s_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xl, VmFamily::D),
            "Standard_D32s_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xxl, VmFamily::D),
            "Standard_D64s_v5"
        );
    }

    #[test]
    fn test_tier_to_sku_e_series_all_tiers() {
        use azlin_cli::{VmFamily, VmSizeTier};
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xs, VmFamily::E),
            "Standard_E2as_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::S, VmFamily::E),
            "Standard_E4as_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::M, VmFamily::E),
            "Standard_E8as_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::L, VmFamily::E),
            "Standard_E16as_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xl, VmFamily::E),
            "Standard_E32as_v5"
        );
        assert_eq!(
            super::tier_to_sku(VmSizeTier::Xxl, VmFamily::E),
            "Standard_E64as_v5"
        );
    }

    #[test]
    fn test_tier_to_sku_e_series_xl_is_memory_optimized() {
        use azlin_cli::{VmFamily, VmSizeTier};
        let sku = super::tier_to_sku(VmSizeTier::Xl, VmFamily::E);
        // E-series SKUs should contain "E" and "as" (AMD memory-optimized)
        assert!(sku.contains("_E"), "E-series SKU must contain _E prefix");
        assert!(
            sku.contains("as_v5"),
            "E-series SKU must be AMD-based (as_v5)"
        );
    }

    #[test]
    fn test_tier_to_sku_d_series_uses_ds_v5() {
        use azlin_cli::{VmFamily, VmSizeTier};
        let sku = super::tier_to_sku(VmSizeTier::M, VmFamily::D);
        assert!(sku.contains("_D"), "D-series SKU must contain _D prefix");
        assert!(
            sku.contains("s_v5"),
            "D-series SKU must be v5 with premium storage (s_v5)"
        );
    }

    // ── NAT gateway policy (issue #1092) ─────────────────────────────
    //
    // Mirrors the bastion prompt, with one deliberate improvement: the
    // bastion original is untestable because it reads ambient TTY state
    // inline. Here the decision is a pure function of (yes, stdin_is_tty)
    // and `prompt_nat_action` is a thin dialoguer shell over it.

    use super::{
        decide_nat_action, map_nat_selection, nat_abort_message, nat_provisioning_failed_message,
        NatMissingAction,
    };

    #[test]
    fn test_decide_nat_action_yes_flag_auto_creates() {
        assert_eq!(
            decide_nat_action(true, true),
            Some(NatMissingAction::CreateNatGateway)
        );
        assert_eq!(
            decide_nat_action(true, false),
            Some(NatMissingAction::CreateNatGateway)
        );
    }

    #[test]
    fn test_decide_nat_action_non_tty_auto_creates() {
        // CI and `azlin new` from a script must not hang on a prompt, and
        // must not silently produce a VM with no egress.
        assert_eq!(
            decide_nat_action(false, false),
            Some(NatMissingAction::CreateNatGateway)
        );
    }

    #[test]
    fn test_decide_nat_action_interactive_defers_to_prompt() {
        // None means "no automatic answer — ask the user".
        assert_eq!(decide_nat_action(false, true), None);
    }

    #[test]
    fn test_map_nat_selection_mirrors_bastion_option_order() {
        assert_eq!(map_nat_selection(0), NatMissingAction::CreateNatGateway);
        assert_eq!(map_nat_selection(1), NatMissingAction::SwitchToPublicIp);
        assert_eq!(map_nat_selection(2), NatMissingAction::Abort);
    }

    #[test]
    fn test_map_nat_selection_unknown_index_aborts() {
        // Fail closed: an unexpected index must never mean "create" or
        // "proceed anyway".
        assert_eq!(map_nat_selection(99), NatMissingAction::Abort);
    }

    #[test]
    fn test_nat_abort_message_is_actionable() {
        // R4: declining must fail LOUDLY. The message has to be enough to
        // fix the problem by hand — this whole issue is about silent
        // degradation, so an unactionable error would just move the failure.
        let msg = nat_abort_message("my-rg", "centralus");
        assert!(msg.contains("centralus"), "must name the region: {msg}");
        assert!(
            msg.contains("azlin-natgw-centralus"),
            "must name the gateway: {msg}"
        );
        assert!(
            msg.contains("azlin-natgw-centralus-ip-tagged"),
            "must name the public IP: {msg}"
        );
        assert!(
            msg.contains("az network nat gateway create"),
            "must give the manual remediation: {msg}"
        );
        assert!(
            msg.to_lowercase().contains("inbound"),
            "must state that Bastion is inbound-only, or users will assume \
             the bastion already gives them egress: {msg}"
        );
        assert!(
            msg.to_lowercase().contains("outbound") || msg.to_lowercase().contains("egress"),
            "must name the missing capability: {msg}"
        );
    }

    #[test]
    fn test_nat_abort_message_normalizes_region_case() {
        let msg = nat_abort_message("my-rg", "CentralUS");
        assert!(msg.contains("azlin-natgw-centralus"));
        assert!(!msg.contains("azlin-natgw-CentralUS"));
    }

    #[test]
    fn test_nat_messages_interpolate_the_resource_group() {
        // AC7 asks for actionable remediation. A command carrying a literal
        // `<rg>` placeholder is not actionable: the user must hand-edit it
        // before it runs, and the resource group is in scope at both call
        // sites, so leaving it unbound was pure loss.
        for msg in [
            nat_abort_message("prod-rg", "centralus"),
            nat_provisioning_failed_message("prod-rg", "centralus"),
        ] {
            assert!(
                !msg.contains("<rg>"),
                "must not print a placeholder resource group: {msg}"
            );
            assert!(
                msg.contains("--resource-group prod-rg"),
                "must name the real resource group: {msg}"
            );
        }
    }

    #[test]
    fn test_provisioning_failure_is_not_reported_as_an_abort() {
        // The distinction is the point: declining creates nothing, whereas a
        // failure mid-sequence can leave a Standard public IP and a gateway
        // behind, both billing. Saying "Aborted" there would repeat the exact
        // silent-degradation defect this issue exists to remove.
        let msg = nat_provisioning_failed_message("prod-rg", "centralus");
        assert!(
            !msg.starts_with("Aborted"),
            "a failed attempt is not an abort: {msg}"
        );
        assert!(
            msg.to_lowercase().contains("failed"),
            "must say provisioning failed: {msg}"
        );
        assert!(
            msg.contains("azlin-natgw-centralus-ip-tagged")
                && msg.contains("azlin-natgw-centralus"),
            "must name both resources that may already be billing: {msg}"
        );
        assert!(
            msg.to_lowercase().contains("billing") || msg.to_lowercase().contains("bill"),
            "must warn that partial resources may cost money: {msg}"
        );
        assert!(
            msg.contains("az network nat gateway list"),
            "must give the user a way to check what exists: {msg}"
        );
    }

    #[test]
    fn test_both_nat_messages_share_the_remediation_steps() {
        // The framing differs; the fix does not. If these ever diverge, one
        // of the two paths is teaching the user a stale command.
        let abort = nat_abort_message("prod-rg", "centralus");
        let failed = nat_provisioning_failed_message("prod-rg", "centralus");
        let steps = super::nat_remediation_text("prod-rg", "centralus");
        assert!(abort.contains(&steps));
        assert!(failed.contains(&steps));
    }
}
