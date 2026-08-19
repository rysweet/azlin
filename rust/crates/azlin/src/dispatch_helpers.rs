use std::io::IsTerminal;

use anyhow::{Context, Result};

use super::*;

/// Prompt the user for confirmation, handling non-TTY stdin gracefully.
///
/// - If `force` is true, returns `Ok(true)` immediately (skip prompt).
/// - If stdin is a TTY, shows a dialoguer confirmation prompt.
/// - If stdin is NOT a TTY (piped, cron, CI), returns an error advising
///   the caller to use `--yes` or `--force`.
pub(crate) fn safe_confirm(prompt: &str, force: bool) -> Result<bool> {
    if force {
        return Ok(true);
    }
    if !std::io::stdin().is_terminal() {
        anyhow::bail!(
            "Confirmation required but stdin is not a terminal. \
             Use --yes or --force to skip."
        );
    }
    Ok(dialoguer::Confirm::new()
        .with_prompt(prompt)
        .default(false)
        .interact()?)
}

/// Build the Azure auth every command runs under, honouring the active context.
///
/// This is the single chokepoint (29 call sites) where an azlin context becomes
/// real. When a context is selected and pins a `subscription_id`, the Azure CLI
/// is switched to it and the switch is *verified* before anything else runs; see
/// [`azlin_azure::AzureAuth::for_subscription`]. Without this, `azlin context use
/// prod` was a no-op and `azlin destroy webdb --force` deleted `webdb` in the dev
/// subscription (#1090).
pub(crate) fn create_auth() -> Result<azlin_azure::AzureAuth> {
    let active = crate::active_context::load_active()?;
    match crate::active_context::target_subscription(active.as_ref()) {
        Some(subscription_id) => {
            let name = active.as_ref().map(|c| c.name.as_str()).unwrap_or("?");
            let auth = azlin_azure::AzureAuth::for_subscription(subscription_id).map_err(|e| {
                anyhow::anyhow!(
                    "Cannot run against the active context '{name}' \
                     (subscription {subscription_id}): {e}\n\
                     Run 'az login' to authenticate, 'azlin context show' to inspect the \
                     context, or 'azlin context use <other>' to select another."
                )
            })?;
            verify_tenant(&auth, active.as_ref())?;
            Ok(auth)
        }
        None => azlin_azure::AzureAuth::new().map_err(|e| {
            anyhow::anyhow!(
                "Azure authentication failed: {e}\n\
                 Run 'az login' to authenticate with Azure CLI."
            )
        }),
    }
}

/// Fail when the context pins a tenant the CLI is not signed in to.
///
/// A matching subscription id in a different tenant should be impossible, but
/// checking is one comparison and the failure mode it guards is destructive.
fn verify_tenant(
    auth: &azlin_azure::AzureAuth,
    active: Option<&crate::active_context::ActiveContext>,
) -> Result<()> {
    let (Some(want), Some(have)) = (
        active.and_then(|c| c.tenant_id.as_deref()),
        auth.tenant_id(),
    ) else {
        return Ok(());
    };
    if want != have {
        anyhow::bail!(
            "Active context pins tenant {want} but the Azure CLI is signed in to {have}.\n\
             Run 'az login --tenant {want}' before using this context."
        );
    }
    Ok(())
}

/// Resolve the resource group a command acts on.
///
/// Precedence is explicit flag > active context > global config default. The
/// active context sits above the config default so that `azlin context use prod`
/// actually moves commands into prod's resource group; before #1090 the context
/// value was written to disk and never read.
pub(crate) fn resolve_resource_group(explicit: Option<String>) -> Result<String> {
    if let Some(rg) = explicit {
        return Ok(rg);
    }
    let active = crate::active_context::load_active()?;
    let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
    crate::active_context::resolve_rg(None, active.as_ref(), config.default_resource_group)
        .ok_or_else(|| anyhow::anyhow!("{}", no_resource_group_help(active.as_ref())))
}

/// The message shown when no resource group can be resolved.
///
/// The old text opened with "azlin context create / azlin context use", neither
/// of which sets a resource group — only its step 3 did anything, so following
/// the instructions in order left the error in place. Each line here now names a
/// step that changes the outcome, ordered by the precedence actually applied.
pub(crate) fn no_resource_group_help(
    active: Option<&crate::active_context::ActiveContext>,
) -> String {
    let mut out = String::from("No resource group configured.\n\n");
    match active {
        Some(ctx) => out.push_str(&format!(
            "The active context '{}' does not set one.\n\n",
            ctx.name
        )),
        None => out.push_str("No context is selected.\n\n"),
    }
    out.push_str(
        "Set one of these — the first that applies wins:\n\
         \x20 1. pass --resource-group <rg> to this command\n\
         \x20 2. put it in a context and select that context:\n\
         \x20      azlin context create <name> --resource-group <rg> [--subscription-id <sub>]\n\
         \x20      azlin context use <name>\n\
         \x20 3. set the global default:\n\
         \x20      azlin config set default_resource_group <rg>\n\n\
         Run 'az group list --output table' to see the resource groups you have.",
    );
    out
}

/// Get the user's home directory, returning a clear error on failure.
/// Load the user's config, treating a malformed file as fatal.
///
/// `AzlinConfig::load()` already distinguishes the two cases correctly: a
/// *missing* file yields defaults (the legitimate first-run state), and only a
/// genuine read or parse failure returns `Err`. Call sites used to discard that
/// with `.unwrap_or_default()`, which collapses "you have no config" and "your
/// config is corrupt" into the same silent outcome.
///
/// That is not a neutral degradation. Falling back to defaults silently swaps
/// the user's region, VM size, image, timeouts, resource group and storage
/// mappings for built-in ones, so a command can run to completion against a
/// subscription or region the user never chose. It also produces misleading
/// diagnostics: a duplicate table on line 32 surfaced as "No resource group
/// specified. Use --resource-group or set in config." while the resource group
/// sat correctly in the file, making the advice impossible to act on (#1080).
///
/// So: defaults when there is no file, and a loud, actionable error naming the
/// file and the parser's line/column when there is one that cannot be read.
pub(crate) fn load_user_config() -> azlin_core::AzlinConfig {
    match azlin_core::AzlinConfig::load() {
        Ok(config) => config,
        Err(err) => {
            eprintln!("azlin-error: {err}");
            eprintln!();
            eprintln!(
                "azlin will not fall back to default settings for a config file it cannot read: \n\
                 doing so would silently run against a different region, resource group or VM \n\
                 size than the one you configured. Fix the file, or move it aside to start from \n\
                 defaults."
            );
            std::process::exit(2);
        }
    }
}

pub(crate) fn home_dir() -> Result<std::path::PathBuf> {
    dirs::home_dir().ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))
}

/// Escape a value for safe inclusion in a shell command.
pub(crate) fn shell_escape(s: &str) -> String {
    let mut escaped = String::with_capacity(s.len() + 2);
    escaped.push('\'');
    for c in s.chars() {
        if c == '\'' {
            escaped.push_str("'\\''");
        } else {
            escaped.push(c);
        }
    }
    escaped.push('\'');
    escaped
}

/// Look up a VM's OS disk resource ID and location via `az vm show`.
/// Returns `(disk_id, location)` for use in snapshot/clone operations.
pub(crate) fn lookup_vm_disk_info(rg: &str, vm_name: &str) -> Result<(String, String)> {
    let output = std::process::Command::new("az")
        .args([
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--query",
            "[storageProfile.osDisk.managedDisk.id, location]",
            "--output",
            "tsv",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to get OS disk for VM '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let raw = String::from_utf8_lossy(&output.stdout);
    let parts: Vec<&str> = raw.trim().lines().collect();
    if parts.len() < 2 || parts[0].is_empty() {
        anyhow::bail!("No OS disk found for VM '{}'", vm_name);
    }
    Ok((parts[0].to_string(), parts[1].to_string()))
}

/// Look up a VM's public IP address. Returns `Ok(None)` if the VM has no public IP
/// (bastion-only), `Ok(Some(ip))` if it has one.
pub(crate) fn lookup_vm_public_ip(rg: &str, vm_name: &str) -> Result<Option<String>> {
    let output = std::process::Command::new("az")
        .args([
            "vm",
            "list-ip-addresses",
            "--resource-group",
            rg,
            "--name",
            vm_name,
            "--query",
            "[0].virtualMachine.network.publicIpAddresses[0].ipAddress",
            "--output",
            "tsv",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to get public IP for VM '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let ip = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if ip.is_empty() || ip == "None" {
        Ok(None)
    } else {
        Ok(Some(ip))
    }
}

/// Resolve a single VM to a `VmSshTarget`, using --ip flag if provided.
/// Routes through bastion automatically for private-IP-only VMs.
pub(crate) async fn resolve_vm_ssh_target(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<VmSshTarget> {
    if let Some(ip) = ip_flag {
        return Ok(VmSshTarget {
            vm_name: vm_name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        });
    }
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let vm = vm_manager.get_vm(&rg, vm_name)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let ssh_key = resolve_ssh_key();
    let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
    if target.ip.is_empty() {
        anyhow::bail!("No IP address found for VM '{}'", vm_name);
    }
    Ok(target)
}

/// Resolve targets for W/Ps/Top: single VM (--vm/--ip) or all VMs via Azure.
/// Returns `Vec<VmSshTarget>` with bastion routing for private-IP-only VMs.
pub(crate) async fn resolve_vm_targets(
    vm_flag: Option<&str>,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<Vec<VmSshTarget>> {
    if let Some(ip) = ip_flag {
        let name = vm_flag.unwrap_or(ip);
        return Ok(vec![VmSshTarget {
            vm_name: name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        }]);
    }
    if let Some(vm_name) = vm_flag {
        let auth = create_auth()?;
        let vm_manager = azlin_azure::VmManager::new(&auth);
        let rg = resolve_resource_group(resource_group)?;
        let vm = vm_manager.get_vm(&rg, vm_name)?;
        let bastion_map: std::collections::HashMap<String, String> =
            list_helpers::detect_bastion_hosts(&rg)
                .unwrap_or_default()
                .into_iter()
                .map(|(name, location, _)| (location, name))
                .collect();
        let ssh_key = resolve_ssh_key();
        let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
        if target.ip.is_empty() {
            anyhow::bail!("No IP address found for VM '{}'", vm_name);
        }
        return Ok(vec![target]);
    }
    // List all running VMs
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let sub_id = vm_manager.subscription_id().to_string();
    let ssh_key = resolve_ssh_key();
    let vms = vm_manager.list_vms(&rg)?;
    let mut targets = Vec::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        if vm.public_ip.is_none() && vm.private_ip.is_none() {
            continue;
        }
        targets.push(build_ssh_target(&vm, &sub_id, &bastion_map, &ssh_key));
    }
    if targets.is_empty() {
        anyhow::bail!("No running VMs found. Use --vm or --ip to target a specific VM.");
    }
    Ok(targets)
}

/// Build a shared SSH prefix for a resolved VM target, opening a bastion tunnel
/// when required.
pub(crate) async fn build_routed_ssh_prefix(
    target: &VmSshTarget,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
) -> Result<(
    Vec<String>,
    Option<crate::bastion_tunnel::ScopedBastionTunnel>,
)> {
    build_routed_ssh_prefix_with_mode(target, connect_timeout, key_override, true).await
}

pub(crate) async fn build_routed_ssh_prefix_with_mode(
    target: &VmSshTarget,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
    batch_mode: bool,
) -> Result<(
    Vec<String>,
    Option<crate::bastion_tunnel::ScopedBastionTunnel>,
)> {
    if let Some(ref bastion) = target.bastion {
        let tunnel = crate::bastion_tunnel::ScopedBastionTunnel::new(
            &bastion.bastion_name,
            &bastion.resource_group,
            &bastion.vm_resource_id,
        )
        .await?;
        let mut prefix = crate::ssh_arg_helpers::build_tunneled_ssh_prefix_with_mode(
            &target.user,
            tunnel.local_port,
            connect_timeout,
            batch_mode,
        );
        if let Some(key_path) = key_override {
            crate::ssh_arg_helpers::inject_identity_key_before_destination(&mut prefix, key_path);
        } else if let Some(ref key_path) = bastion.ssh_key_path {
            crate::ssh_arg_helpers::inject_identity_key_before_destination(&mut prefix, key_path);
        }
        Ok((prefix, Some(tunnel)))
    } else {
        let mut prefix = crate::ssh_arg_helpers::build_ssh_prefix_with_mode(
            &target.ip,
            &target.user,
            connect_timeout,
            batch_mode,
        );
        if let Some(key_path) = crate::resolve_target_ssh_key_path(
            key_override,
            target.ssh_key_path.as_deref(),
            target.allow_preferred_key_fallback,
        ) {
            crate::ssh_arg_helpers::inject_identity_key_before_destination(&mut prefix, &key_path);
        }
        Ok((prefix, None))
    }
}

/// Build the `ssh ...` transport string used by rsync/scp-style commands for a
/// resolved target and optional already-open bastion tunnel port.
#[cfg(test)]
pub(crate) fn build_routed_ssh_transport(
    target: &VmSshTarget,
    bastion_port: Option<u16>,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
) -> String {
    build_routed_ssh_transport_with_mode(target, bastion_port, connect_timeout, key_override, true)
}

pub(crate) fn build_routed_ssh_transport_with_mode(
    target: &VmSshTarget,
    bastion_port: Option<u16>,
    connect_timeout: u64,
    key_override: Option<&std::path::Path>,
    batch_mode: bool,
) -> String {
    let mut parts = vec![
        "ssh".to_string(),
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
    ];
    if batch_mode {
        parts.push("-o".to_string());
        parts.push("BatchMode=yes".to_string());
    }

    if let Some(port) = bastion_port {
        parts.push("-p".to_string());
        parts.push(port.to_string());
        if let Some(key_path) = key_override {
            parts.push("-o".to_string());
            parts.push("IdentitiesOnly=yes".to_string());
            parts.push("-i".to_string());
            parts.push(key_path.display().to_string());
        } else if let Some(ref bastion) = target.bastion {
            if let Some(ref key_path) = bastion.ssh_key_path {
                parts.push("-o".to_string());
                parts.push("IdentitiesOnly=yes".to_string());
                parts.push("-i".to_string());
                parts.push(key_path.display().to_string());
            }
        }
    } else {
        if let Some(key_path) = crate::resolve_target_ssh_key_path(
            key_override,
            target.ssh_key_path.as_deref(),
            target.allow_preferred_key_fallback,
        ) {
            parts.push("-o".to_string());
            parts.push("IdentitiesOnly=yes".to_string());
            parts.push("-i".to_string());
            parts.push(key_path.display().to_string());
        }
    }

    parts.join(" ")
}

/// Run a remote command through the shared SSH routing path with a hard timeout.
pub(crate) async fn run_target_command_with_timeout(
    target: &VmSshTarget,
    remote_cmd: &str,
    timeout_secs: u64,
    key_override: Option<&std::path::Path>,
) -> Result<(i32, String, String)> {
    let config = load_user_config();
    let (mut prefix, _tunnel) =
        build_routed_ssh_prefix(target, config.ssh_connect_timeout, key_override).await?;
    prefix.push(remote_cmd.to_string());
    let arg_refs: Vec<&str> = prefix.iter().map(|arg| arg.as_str()).collect();
    azlin_azure::run_with_timeout("ssh", &arg_refs, timeout_secs)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_confirm_force_true_returns_ok_true() {
        // When force=true, should always return Ok(true) regardless of TTY state
        assert_eq!(safe_confirm("Delete everything?", true).unwrap(), true);
    }

    #[test]
    fn safe_confirm_force_true_ignores_prompt() {
        // Even with an empty prompt, force=true should succeed
        assert_eq!(safe_confirm("", true).unwrap(), true);
    }

    #[test]
    fn safe_confirm_non_tty_returns_error() {
        // In test environment, stdin is not a real TTY, so force=false should error.
        // Two possible error paths:
        //   1. is_terminal() == false → our bail with "stdin is not a terminal"
        //   2. is_terminal() == true (pseudo-TTY) → dialoguer IO error
        let result = safe_confirm("Proceed?", false);
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("not a terminal") || err_msg.contains("IO error"),
            "Expected terminal-related error, got: {}",
            err_msg
        );
    }

    #[test]
    fn safe_confirm_non_tty_error_suggests_flags() {
        let result = safe_confirm("Proceed?", false);
        let err_msg = result.unwrap_err().to_string();
        // When is_terminal() returns false we get our custom message with flag hints.
        // When is_terminal() returns true (pseudo-TTY) dialoguer fails with an IO
        // error — that's acceptable; the flag hints only appear in our own bail path.
        assert!(
            err_msg.contains("--yes")
                || err_msg.contains("--force")
                || err_msg.contains("not a terminal"),
            "Error should suggest --yes/--force or be a terminal error, got: {}",
            err_msg
        );
    }

    #[test]
    fn build_routed_ssh_transport_direct_uses_noninteractive_ssh() {
        let target = VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "1.2.3.4".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: None,
        };

        let transport = build_routed_ssh_transport(&target, None, 42, None);
        assert!(transport.contains("StrictHostKeyChecking=accept-new"));
        assert!(transport.contains("ConnectTimeout=42"));
        assert!(transport.contains("BatchMode=yes"));
        assert!(transport.contains("-i /tmp/key"));
        assert!(transport.contains("IdentitiesOnly=yes"));
    }

    #[test]
    fn build_routed_ssh_transport_bastion_includes_local_port() {
        let target = VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: Some(BastionRoute {
                bastion_name: "bastion".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard".to_string(),
                ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            }),
        };

        let transport = build_routed_ssh_transport(&target, Some(50210), 30, None);
        assert!(transport.contains("-p 50210"));
        assert!(transport.contains("-i /tmp/key"));
        assert!(transport.contains("BatchMode=yes"));
        assert!(transport.contains("IdentitiesOnly=yes"));
    }

    #[test]
    fn build_routed_ssh_transport_prefers_explicit_key_override() {
        let target = VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "1.2.3.4".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: true,
            bastion: None,
        };

        let override_key = std::path::Path::new("/tmp/created-key");
        let transport = build_routed_ssh_transport(&target, None, 30, Some(override_key));
        assert!(transport.contains("IdentitiesOnly=yes"));
        assert!(transport.contains("-i /tmp/created-key"));
    }

    #[test]
    fn build_routed_ssh_transport_direct_without_fallback_omits_identity_key() {
        let target = VmSshTarget {
            vm_name: "opaque-ip".to_string(),
            ip: "203.0.113.10".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        };

        let transport = build_routed_ssh_transport(&target, None, 30, None);
        assert!(!transport.contains("IdentitiesOnly=yes"));
        assert!(!transport.contains(" -i "));
    }

    #[tokio::test]
    async fn build_routed_ssh_prefix_direct_without_fallback_omits_identity_key() {
        let target = VmSshTarget {
            vm_name: "opaque-ip".to_string(),
            ip: "203.0.113.10".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: false,
            bastion: None,
        };

        let (prefix, tunnel) = build_routed_ssh_prefix(&target, 30, None).await.unwrap();
        assert!(tunnel.is_none());
        assert!(!prefix.iter().any(|arg| arg == "-i"));
        assert!(!prefix.iter().any(|arg| arg == "IdentitiesOnly=yes"));
    }
}
