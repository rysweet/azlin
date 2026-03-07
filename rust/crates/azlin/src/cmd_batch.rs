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
        azlin_cli::Commands::Batch { action } => match action {
            azlin_cli::BatchAction::Stop {
                resource_group,
                tag,
                confirm,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = tag.as_deref().unwrap_or("all");
                if !confirm {
                    let ok = Confirm::new()
                        .with_prompt(format!("Stop VMs matching '{}' in {}?", filter_msg, rg))
                        .default(false)
                        .interact()?;
                    if !ok {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                let query = crate::batch_helpers::build_vm_list_query(tag.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", &query, "-o", "tsv"])
                    .output()?;
                let tsv = std::str::from_utf8(&list_output.stdout).unwrap_or("");
                let ids = crate::batch_helpers::parse_vm_ids(tsv);
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let args = crate::batch_helpers::build_batch_args("deallocate", &ids);
                    let output = std::process::Command::new("az").args(&args).output()?;
                    let msg =
                        crate::batch_helpers::summarise_batch("stop", &rg, output.status.success());
                    if output.status.success() {
                        println!("{}", msg);
                    } else {
                        eprintln!("{}", msg);
                    }
                }
            }
            azlin_cli::BatchAction::Start {
                resource_group,
                tag,
                confirm,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = tag.as_deref().unwrap_or("all");
                if !confirm {
                    let ok = Confirm::new()
                        .with_prompt(format!("Start VMs matching '{}' in {}?", filter_msg, rg))
                        .default(false)
                        .interact()?;
                    if !ok {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                let query = crate::batch_helpers::build_vm_list_query(tag.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", &query, "-o", "tsv"])
                    .output()?;
                let tsv = std::str::from_utf8(&list_output.stdout).unwrap_or("");
                let ids = crate::batch_helpers::parse_vm_ids(tsv);
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let args = crate::batch_helpers::build_batch_args("start", &ids);
                    let output = std::process::Command::new("az").args(&args).output()?;
                    let msg = crate::batch_helpers::summarise_batch(
                        "start",
                        &rg,
                        output.status.success(),
                    );
                    if output.status.success() {
                        println!("{}", msg);
                    } else {
                        eprintln!("{}", msg);
                    }
                }
            }
            azlin_cli::BatchAction::Command {
                command,
                resource_group,
                show_output,
                ..
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Running '{}' on all VMs in '{}'...", command, rg));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                pb.finish_and_clear();

                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                } else {
                    println!("Running '{}' on {} VM(s)...", command, vms.len());
                    run_on_fleet(&vms, &command, show_output);
                }
            }
            azlin_cli::BatchAction::Sync {
                resource_group,
                dry_run,
                ..
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let home = home_dir()?;
                let dotfiles = crate::sync_helpers::default_dotfiles();

                for (name, ip, user) in &vms {
                    for dotfile in &dotfiles {
                        let local = home.join(dotfile);
                        if !local.exists() {
                            continue;
                        }
                        if dry_run {
                            println!("[dry-run] Would sync {} to {}:{}", dotfile, name, dotfile);
                        } else {
                            let output = std::process::Command::new("rsync")
                                .args(["-az", "-e", "ssh -o StrictHostKeyChecking=accept-new"])
                                .arg(local.as_os_str())
                                .arg(format!("{}@{}:~/{}", user, ip, dotfile))
                                .output();
                            match output {
                                Ok(o) if o.status.success() => {
                                    println!("Synced {} to {}", dotfile, name);
                                }
                                Ok(o) => {
                                    let stderr = String::from_utf8_lossy(&o.stderr);
                                    eprintln!(
                                        "Failed to sync {} to {}: {}",
                                        dotfile,
                                        name,
                                        azlin_core::sanitizer::sanitize(stderr.trim())
                                    );
                                }
                                Err(e) => {
                                    eprintln!("Failed to sync {} to {}: {}", dotfile, name, e);
                                }
                            }
                        }
                    }
                }
                if !dry_run {
                    println!("Sync complete.");
                }
            }
        },

        // ── Fleet ────────────────────────────────────────────────────
        azlin_cli::Commands::Fleet { action } => match action {
            azlin_cli::FleetAction::Run {
                command,
                resource_group,
                dry_run,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if dry_run {
                    println!("Would run '{}' across fleet in '{}'", command, rg);
                } else {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Gathering fleet VMs in '{}'...", rg));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                    pb.finish_and_clear();

                    if vms.is_empty() {
                        println!("No running VMs found in resource group '{}'", rg);
                    } else {
                        println!("Running '{}' across {} VM(s)...", command, vms.len());
                        run_on_fleet(&vms, &command, true);
                        println!("Fleet execution complete.");
                    }
                }
            }
            azlin_cli::FleetAction::Workflow {
                workflow_file,
                resource_group,
                dry_run,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if dry_run {
                    println!(
                        "Would execute workflow '{}' on fleet in '{}'",
                        workflow_file.display(),
                        rg
                    );
                } else {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);

                    let content = std::fs::read_to_string(&workflow_file).map_err(|e| {
                        anyhow::anyhow!(
                            "Failed to read workflow file '{}': {}",
                            workflow_file.display(),
                            e
                        )
                    })?;
                    let workflow: serde_yaml::Value = serde_yaml::from_str(&content)
                        .map_err(|e| anyhow::anyhow!("Failed to parse workflow YAML: {}", e))?;

                    let steps = workflow
                        .get("steps")
                        .and_then(|s| s.as_sequence())
                        .ok_or_else(|| {
                            anyhow::anyhow!("Workflow YAML must contain a 'steps' array")
                        })?;

                    let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                    if vms.is_empty() {
                        println!("No running VMs found in resource group '{}'", rg);
                        return Ok(());
                    }

                    println!(
                        "Executing workflow '{}' on {} VM(s)...",
                        workflow_file.display(),
                        vms.len()
                    );
                    for (i, step) in steps.iter().enumerate() {
                        let default_name = format!("step-{}", i + 1);
                        let step_name = step
                            .get("name")
                            .and_then(|n| n.as_str())
                            .unwrap_or(&default_name);
                        let cmd = step
                            .get("command")
                            .or_else(|| step.get("run"))
                            .and_then(|c| c.as_str());

                        if let Some(cmd) = cmd {
                            println!("\n── Step {}: {} ──", i + 1, step_name);
                            run_on_fleet(&vms, cmd, true);
                        } else {
                            eprintln!(
                                "Step {} ('{}') has no 'command' or 'run' field, skipping",
                                i + 1,
                                step_name
                            );
                        }
                    }
                    println!("\nWorkflow execution complete.");
                }
            }
        },

        // ── Compose ──────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
