use anyhow::{Context, Result};
use clap::{CommandFactory, Parser};
use comfy_table::{
    modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Color, Table,
};
use console::Style;
use dialoguer::Confirm;
use indicatif::ProgressBar;

use super::*;

/// Dispatch a parsed CLI command. Separated from async_main for testability —
/// tests can construct a Cli struct and call this directly (in-process coverage).
#[cfg_attr(test, allow(dead_code))]
pub(crate) async fn dispatch_command(cli: azlin_cli::Cli) -> Result<()> {
    if cli.verbose {
        tracing::info!("Verbose mode enabled");
    }

    match cli.command {
        azlin_cli::Commands::Version => {
            println!("azlin {} (rust)", env!("CARGO_PKG_VERSION"));
        }
        azlin_cli::Commands::Config { action } => match action {
            azlin_cli::ConfigAction::Show => {
                let config = azlin_core::AzlinConfig::load()?;
                let json = serde_json::to_value(&config)?;
                let key_style = Style::new().cyan().bold();
                let val_style = Style::new().white();
                if let Some(obj) = json.as_object() {
                    for (k, v) in obj {
                        let display = match v {
                            serde_json::Value::String(s) => s.clone(),
                            serde_json::Value::Null => "null".to_string(),
                            other => other.to_string(),
                        };
                        println!(
                            "{}: {}",
                            key_style.apply_to(k),
                            val_style.apply_to(&display)
                        );
                    }
                }
            }
            azlin_cli::ConfigAction::Get { key } => {
                let config = azlin_core::AzlinConfig::load()?;
                let json = serde_json::to_value(&config)?;
                match json.get(&key) {
                    Some(serde_json::Value::String(s)) => println!("{s}"),
                    Some(val) => println!("{val}"),
                    None => eprintln!("Unknown config key: {key}"),
                }
            }
            azlin_cli::ConfigAction::Set { key, value } => {
                let mut config = azlin_core::AzlinConfig::load()?;
                let mut json = serde_json::to_value(&config)?;
                if let Some(obj) = json.as_object() {
                    if !obj.contains_key(&key) {
                        anyhow::bail!("Unknown config key: {key}");
                    }
                }
                let validated = azlin_core::AzlinConfig::validate_field(&key, &value)?;
                if let Some(obj) = json.as_object_mut() {
                    obj.insert(key.clone(), validated);
                    config = serde_json::from_value(json)?;
                    config.save()?;
                    println!("Set {key} = {value}");
                }
            }
        },
        cmd @ azlin_cli::Commands::List { .. } => {
            crate::cmd_list::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Start { .. }
        | cmd @ azlin_cli::Commands::Stop { .. }
        | cmd @ azlin_cli::Commands::Delete { .. }
        | cmd @ azlin_cli::Commands::Kill { .. }
        | cmd @ azlin_cli::Commands::Destroy { .. }
        | cmd @ azlin_cli::Commands::Killall { .. }
        | cmd @ azlin_cli::Commands::OsUpdate { .. } => {
            crate::cmd_lifecycle::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Connect { .. } | cmd @ azlin_cli::Commands::Show { .. } => {
            crate::cmd_connect::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Tag { .. } => {
            crate::cmd_tag::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::W { .. }
        | cmd @ azlin_cli::Commands::Ps { .. }
        | cmd @ azlin_cli::Commands::Top { .. }
        | cmd @ azlin_cli::Commands::Health { .. } => {
            crate::cmd_monitoring::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Env { .. } => {
            crate::cmd_env::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        azlin_cli::Commands::Cost {
            resource_group,
            by_vm,
            from,
            to,
            estimate,
            ..
        } => {
            let auth = create_auth()?;
            let rg = resolve_resource_group(resource_group)?;
            let cost_timeout = azlin_core::AzlinConfig::load()
                .map(|c| c.az_cli_timeout)
                .unwrap_or(120);

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Fetching cost data...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            match azlin_azure::get_cost_summary(&auth, &rg, cost_timeout) {
                Ok(summary) => {
                    pb.finish_and_clear();
                    let fmt_str = match &cli.output {
                        azlin_cli::OutputFormat::Json => "json",
                        azlin_cli::OutputFormat::Csv => "csv",
                        azlin_cli::OutputFormat::Table => "table",
                    };
                    println!(
                        "{}",
                        handlers::format_cost_summary(
                            &summary, fmt_str, &from, &to, estimate, by_vm
                        )
                    );
                }
                Err(e) => {
                    pb.finish_and_clear();
                    eprintln!("⚠ Cost data unavailable: {e}");
                    eprintln!("  Run 'az consumption usage list' for cost data via Azure CLI.");
                }
            }
        }
        cmd @ azlin_cli::Commands::Snapshot { .. } => {
            crate::cmd_snapshot::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Storage { .. } => {
            crate::cmd_storage::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Keys { .. } => {
            crate::cmd_keys::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Auth { .. } => {
            crate::cmd_auth::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Ask { .. }
        | cmd @ azlin_cli::Commands::Do { .. }
        | cmd @ azlin_cli::Commands::Doit { .. } => {
            crate::cmd_ai::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::New { .. }
        | cmd @ azlin_cli::Commands::Update { .. }
        | cmd @ azlin_cli::Commands::Clone { .. } => {
            crate::cmd_vm::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Session { .. }
        | cmd @ azlin_cli::Commands::Sessions { .. }
        | cmd @ azlin_cli::Commands::Status { .. }
        | cmd @ azlin_cli::Commands::Code { .. } => {
            crate::cmd_session::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Batch { .. } | cmd @ azlin_cli::Commands::Fleet { .. } => {
            crate::cmd_batch::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::GithubRunner { .. }
        | cmd @ azlin_cli::Commands::Compose { .. }
        | cmd @ azlin_cli::Commands::Template { .. } => {
            crate::cmd_infra::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Autopilot { .. } => {
            crate::cmd_autopilot::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Context { .. } => {
            crate::cmd_context::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Disk { .. }
        | cmd @ azlin_cli::Commands::Ip { .. }
        | cmd @ azlin_cli::Commands::Web { .. }
        | cmd @ azlin_cli::Commands::Bastion { .. } => {
            crate::cmd_network::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Cleanup { .. }
        | cmd @ azlin_cli::Commands::Costs { .. }
        | cmd @ azlin_cli::Commands::Restore { .. } => {
            crate::cmd_cleanup::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Sync { .. }
        | cmd @ azlin_cli::Commands::SyncKeys { .. }
        | cmd @ azlin_cli::Commands::Cp { .. }
        | cmd @ azlin_cli::Commands::Logs { .. } => {
            crate::cmd_sync::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        azlin_cli::Commands::Completions { shell } => {
            let mut cmd = azlin_cli::Cli::command();
            clap_complete::generate(shell, &mut cmd, "azlin", &mut std::io::stdout());
        }
        azlin_cli::Commands::AzlinHelp { command_name } => {
            println!("{}", handlers::build_extended_help(command_name.as_deref()));
        }
    }

    Ok(())
}

fn create_auth() -> Result<azlin_azure::AzureAuth> {
    azlin_azure::AzureAuth::new().map_err(|e| {
        anyhow::anyhow!(
            "Azure authentication failed: {e}\n\
             Run 'az login' to authenticate with Azure CLI."
        )
    })
}

fn resolve_resource_group(explicit: Option<String>) -> Result<String> {
    if let Some(rg) = explicit {
        return Ok(rg);
    }
    let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
    config.default_resource_group.ok_or_else(|| {
        anyhow::anyhow!(
            "No resource group configured.\n\n\
             Quick setup:\n\
             1. azlin context create <name> --subscription-id <sub> --tenant-id <tenant>\n\
             2. azlin context use <name>\n\
             3. azlin config set default_resource_group <rg-name>\n\n\
             Or pass --resource-group <name> to any command.\n\
             Run 'az account show' to find your subscription and tenant IDs."
        )
    })
}

/// Get the user's home directory, returning a clear error on failure.
fn home_dir() -> Result<std::path::PathBuf> {
    dirs::home_dir().ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))
}

/// Escape a value for safe inclusion in a shell command.
fn shell_escape(s: &str) -> String {
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

/// Resolve a single VM to a `VmSshTarget`, using --ip flag if provided.
/// Routes through bastion automatically for private-IP-only VMs.
async fn resolve_vm_ssh_target(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<VmSshTarget> {
    if let Some(ip) = ip_flag {
        return Ok(VmSshTarget {
            vm_name: vm_name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
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
async fn resolve_vm_targets(
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
