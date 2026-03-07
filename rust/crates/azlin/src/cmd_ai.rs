#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use dialoguer::Confirm;
use indicatif::{ProgressBar, ProgressStyle};

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Ask {
            query,
            resource_group,
            config: _,
            dry_run,
            auth_profile: _,
            ..
        } => {
            let query_text = query.ok_or_else(|| anyhow::anyhow!("No query provided."))?;

            if dry_run {
                println!("Would query Claude API with: {}", query_text);
                return Ok(());
            }

            let client = azlin_ai::AnthropicClient::new()?;
            let rg = match resource_group {
                Some(rg) => rg,
                None => {
                    let config =
                        azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
                    config.default_resource_group.ok_or_else(|| {
                        anyhow::anyhow!(
                            "No resource group specified. Use --resource-group or set in config."
                        )
                    })?
                }
            };

            let context = format!("Resource group: {}", rg);
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Querying Claude...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let answer = client.ask(&query_text, &context).await?;
            pb.finish_and_clear();
            println!("{}", answer);
        }
        azlin_cli::Commands::Do {
            request,
            dry_run,
            yes,
            verbose,
            ..
        } => {
            let client = azlin_ai::AnthropicClient::new()?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Generating commands...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let commands = client.execute(&request).await?;
            pb.finish_and_clear();

            if commands.is_empty() {
                println!("No commands generated.");
                return Ok(());
            }

            println!("Generated commands:");
            for (i, cmd) in commands.iter().enumerate() {
                println!("  {}. {}", i + 1, cmd);
            }

            if dry_run {
                return Ok(());
            }

            if !yes {
                let confirmed = Confirm::new()
                    .with_prompt("Execute these commands?")
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            for cmd in &commands {
                let cmd_str = cmd.trim();
                if cmd_str.is_empty() {
                    continue;
                }
                // Validate command starts with allowed prefix
                if !cmd_str.starts_with("az ") {
                    eprintln!("Skipping non-Azure command: {}", cmd_str);
                    continue;
                }
                // Use shlex for proper argument parsing
                let parts = match shlex::split(cmd_str) {
                    Some(p) if !p.is_empty() => p,
                    _ => {
                        eprintln!("Failed to parse command: {}", cmd_str);
                        continue;
                    }
                };
                if verbose {
                    eprintln!("[verbose] Executing: {}", cmd_str);
                }
                println!("$ {}", cmd_str);
                let output = std::process::Command::new(&parts[0])
                    .args(&parts[1..])
                    .output()?;
                let stdout = String::from_utf8_lossy(&output.stdout);
                let stderr = String::from_utf8_lossy(&output.stderr);
                if !stdout.is_empty() {
                    print!("{}", stdout);
                }
                if verbose && !stderr.is_empty() {
                    eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
                }
                if !output.status.success() {
                    eprintln!("Command failed with exit code: {:?}", output.status.code());
                    if !verbose && !stderr.is_empty() {
                        eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
                    }
                }
            }
        }
        azlin_cli::Commands::Doit { action } => {
            match action {
                azlin_cli::DoitAction::Deploy {
                    request, dry_run, ..
                } => {
                    let client = azlin_ai::AnthropicClient::new()?;

                    let system_context = "You are azlin, an Azure VM fleet management tool. \
                        Generate a list of azlin CLI commands to accomplish the user's request.\n\
                        Format: one command per line, each an 'az' CLI command.\n\
                        Available operations: az vm list, az vm start, az vm stop, az vm create, \
                        az vm delete, az group create, az network nsg create, etc.";

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Generating deployment plan...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let commands = client.ask(&request, system_context).await?;
                    pb.finish_and_clear();

                    println!("Plan:\n{}\n", commands);

                    if dry_run {
                        return Ok(());
                    }

                    let confirmed = Confirm::new()
                        .with_prompt("Execute this plan?")
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }

                    for line in commands.lines() {
                        let trimmed = line.trim();
                        if trimmed.is_empty() || !trimmed.starts_with("az ") {
                            continue;
                        }
                        let parts = match shlex::split(trimmed) {
                            Some(p) if !p.is_empty() => p,
                            _ => {
                                eprintln!("Failed to parse command: {}", trimmed);
                                continue;
                            }
                        };
                        println!("→ {}", trimmed);
                        let status = std::process::Command::new(&parts[0])
                            .args(&parts[1..])
                            .status()?;
                        if !status.success() {
                            eprintln!("Command failed with exit code: {:?}", status.code());
                        }
                    }
                }
                azlin_cli::DoitAction::Status { session } => {
                    // Check for doit-tagged VMs in the default RG to show deployment status
                    let rg = resolve_resource_group(None)?;
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vms = vm_manager.list_vms(&rg)?;
                    let doit_vms: Vec<_> = vms
                        .iter()
                        .filter(|vm| vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit"))
                        .collect();
                    if doit_vms.is_empty() {
                        let session_id = session.unwrap_or_else(|| "latest".to_string());
                        println!(
                            "No active doit deployments for session '{}' in '{}'.",
                            session_id, rg
                        );
                    } else {
                        println!("Doit deployments in '{}':", rg);
                        for vm in &doit_vms {
                            println!("  {} — {} — {}", vm.name, vm.power_state, vm.vm_size);
                        }
                    }
                }
                azlin_cli::DoitAction::List { username } => {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let rg = resolve_resource_group(None)?;
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Listing doit-created resources...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let vms = vm_manager.list_vms(&rg)?;
                    pb.finish_and_clear();
                    let filtered: Vec<_> = vms
                        .iter()
                        .filter(|vm| {
                            let has_tag =
                                vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
                            let user_match = username
                                .as_ref()
                                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
                            has_tag && user_match
                        })
                        .collect();
                    if filtered.is_empty() {
                        println!("No doit-created resources found.");
                    } else {
                        for vm in &filtered {
                            println!("  {} ({})", vm.name, vm.power_state);
                        }
                    }
                }
                azlin_cli::DoitAction::Show { resource_id } => {
                    let output = std::process::Command::new("az")
                        .args(["resource", "show", "--ids", &resource_id, "-o", "json"])
                        .output()?;
                    if output.status.success() {
                        print!("{}", String::from_utf8_lossy(&output.stdout));
                    } else {
                        eprintln!(
                            "Failed to show resource: {}",
                            azlin_core::sanitizer::sanitize(&String::from_utf8_lossy(
                                &output.stderr
                            ))
                        );
                    }
                }
                azlin_cli::DoitAction::Cleanup {
                    force,
                    dry_run,
                    username,
                } => {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let rg = resolve_resource_group(None)?;

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Finding doit-created resources...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let vms = vm_manager.list_vms(&rg)?;
                    pb.finish_and_clear();

                    let to_delete: Vec<_> = vms
                        .iter()
                        .filter(|vm| {
                            let has_tag =
                                vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
                            let user_match = username
                                .as_ref()
                                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
                            has_tag && user_match
                        })
                        .collect();

                    if to_delete.is_empty() {
                        println!("No doit-created resources to clean up.");
                        return Ok(());
                    }

                    println!("Resources to delete:");
                    for vm in &to_delete {
                        println!("  {} ({})", vm.name, vm.power_state);
                    }

                    if dry_run {
                        return Ok(());
                    }

                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt("Delete these resources?")
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    for vm in &to_delete {
                        println!("Deleting '{}'...", vm.name);
                        vm_manager.delete_vm(&rg, &vm.name)?;
                    }
                    println!("Cleanup complete.");
                }
                azlin_cli::DoitAction::Examples => {
                    println!("Example doit requests:");
                    println!("  azlin doit deploy \"Create a 2-VM cluster with Ubuntu 24.04\"");
                    println!("  azlin doit deploy \"Set up a dev VM with 4 cores and 16GB RAM\"");
                    println!("  azlin doit deploy \"Scale my fleet to 5 VMs in eastus2\"");
                    println!("  azlin doit deploy --dry-run \"Delete all stopped VMs\"");
                }
            }
        }

        // ── VM Lifecycle (New/Vm/Create aliases) ─────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
