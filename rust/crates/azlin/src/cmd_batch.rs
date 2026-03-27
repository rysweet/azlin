#[allow(unused_imports)]
use super::*;
use anyhow::Result;

fn list_vms_with_names(
    rg: &str,
    tag: Option<&str>,
) -> Result<(Vec<String>, std::collections::HashMap<String, String>)> {
    let tag_filter = if let Some(t) = tag {
        let (key, value) = super::tag_helpers::parse_tag(t)
            .ok_or_else(|| anyhow::anyhow!("Invalid tag format '{}'. Use key=value.", t))?;
        format!("[?tags.{}=='{}'].{{id:id, name:name}}", key, value)
    } else {
        "[].{id:id, name:name}".to_string()
    };
    let list_output = std::process::Command::new("az")
        .args(["vm", "list", "-g", rg, "--query", &tag_filter, "-o", "tsv"])
        .output()?;
    let tsv = std::str::from_utf8(&list_output.stdout).unwrap_or("");
    let names = crate::batch_progress::parse_vm_id_name_pairs(tsv);
    let ids: Vec<String> = names.keys().map(String::clone).collect();
    Ok((ids, names))
}

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
                yes,
                no_deallocate: _no_deallocate,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = crate::batch_helpers::resolve_filter_display(tag.as_deref());
                let prompt =
                    crate::batch_helpers::build_confirmation_prompt("Stop", filter_msg, &rg);
                if !safe_confirm(&prompt, yes)? {
                    println!("Cancelled.");
                    return Ok(());
                }
                let (ids, names) = list_vms_with_names(&rg, tag.as_deref())?;
                if ids.is_empty() {
                    println!("{}", crate::batch_helpers::format_no_vms_message(&rg));
                } else {
                    let id_refs: Vec<&str> = ids.iter().map(|s| s.as_str()).collect();
                    let summary = crate::batch_progress::run_batch_with_progress(
                        "deallocate",
                        &id_refs,
                        &names,
                    );
                    println!("{}", summary.format_summary("stop"));
                }
            }
            azlin_cli::BatchAction::Start {
                resource_group,
                tag,
                yes,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = crate::batch_helpers::resolve_filter_display(tag.as_deref());
                let prompt =
                    crate::batch_helpers::build_confirmation_prompt("Start", filter_msg, &rg);
                if !safe_confirm(&prompt, yes)? {
                    println!("Cancelled.");
                    return Ok(());
                }
                let (ids, names) = list_vms_with_names(&rg, tag.as_deref())?;
                if ids.is_empty() {
                    println!("{}", crate::batch_helpers::format_no_vms_message(&rg));
                } else {
                    let id_refs: Vec<&str> = ids.iter().map(|s| s.as_str()).collect();
                    let summary =
                        crate::batch_progress::run_batch_with_progress("start", &id_refs, &names);
                    println!("{}", summary.format_summary("start"));
                }
            }
            azlin_cli::BatchAction::Command {
                command,
                resource_group,
                show_output,
                ..
            } => {
                let auth = create_auth()?;
                let _vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let pb =
                    penguin_spinner(&format!("Running '{}' on all VMs in '{}'...", command, rg));
                let vms = get_running_vm_targets(Some(rg.clone())).await?;
                pb.finish_and_clear();
                if vms.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_running_vms_message(&rg)
                    );
                } else {
                    println!(
                        "{}",
                        crate::batch_helpers::format_fleet_run_message(&command, vms.len())
                    );
                    run_on_fleet(&vms, &command, show_output);
                }
            }
            azlin_cli::BatchAction::Sync {
                resource_group,
                dry_run,
                ..
            } => {
                let auth = create_auth()?;
                let _vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let vms = get_running_vm_targets(Some(rg.clone())).await?;
                if vms.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_running_vms_message(&rg)
                    );
                    return Ok(());
                }
                let home = home_dir()?;
                let dotfiles = crate::sync_helpers::default_dotfiles();
                for target in &vms {
                    let (name, ip, user) = (&target.vm_name, &target.ip, &target.user);
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
                                    println!("Synced {} to {}", dotfile, name)
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
                                    eprintln!("Failed to sync {} to {}: {}", dotfile, name, e)
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
                    let _vm_manager = azlin_azure::VmManager::new(&auth);
                    let pb = penguin_spinner(&format!("Gathering fleet VMs in '{}'...", rg));
                    let vms = get_running_vm_targets(Some(rg.clone())).await?;
                    pb.finish_and_clear();
                    if vms.is_empty() {
                        println!(
                            "{}",
                            crate::batch_helpers::format_no_running_vms_message(&rg)
                        );
                    } else {
                        println!(
                            "{}",
                            crate::batch_helpers::format_fleet_across_message(&command, vms.len())
                        );
                        let outputs = collect_fleet_outputs(&vms, &command);
                        crate::fleet_tabs::run_fleet_tabs(outputs, false)?;
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
                    let _vm_manager = azlin_azure::VmManager::new(&auth);
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
                    let vms = get_running_vm_targets(Some(rg.clone())).await?;
                    if vms.is_empty() {
                        println!(
                            "{}",
                            crate::batch_helpers::format_no_running_vms_message(&rg)
                        );
                        return Ok(());
                    }
                    println!(
                        "Executing workflow '{}' on {} VM(s)...",
                        workflow_file.display(),
                        vms.len()
                    );
                    for (i, step_val) in steps.iter().enumerate() {
                        let step = crate::batch_helpers::extract_workflow_step(step_val, i);
                        if let Some(cmd) = &step.command {
                            println!(
                                "{}",
                                crate::batch_helpers::format_step_header(i + 1, &step.name)
                            );
                            run_on_fleet(&vms, cmd, true);
                        } else {
                            eprintln!(
                                "Step {} ('{}') has no 'command' or 'run' field, skipping",
                                i + 1,
                                step.name
                            );
                        }
                    }
                    println!("\nWorkflow execution complete.");
                }
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}

fn collect_fleet_outputs(
    targets: &[VmSshTarget],
    command: &str,
) -> Vec<crate::fleet_tabs::VmOutput> {
    let mp = indicatif::MultiProgress::new();
    let style = fleet_spinner_style();
    let bars: Vec<_> = targets
        .iter()
        .map(|t| {
            let pb = mp.add(indicatif::ProgressBar::new_spinner());
            pb.set_style(style.clone());
            pb.set_prefix(format!("{:>20}", t.vm_name));
            pb.set_message("connecting...");
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            pb
        })
        .collect();
    let mut outputs = Vec::with_capacity(targets.len());
    for (i, target) in targets.iter().enumerate() {
        bars[i].set_message(format!("running: {}", command));
        let (code, stdout, stderr) = match target.exec(command) {
            Ok(r) => r,
            Err(e) => (-1, String::new(), e.to_string()),
        };
        bars[i].finish_with_message(fleet_helpers::finish_message(code, &stdout, &stderr));
        outputs.push(crate::fleet_tabs::VmOutput {
            vm_name: target.vm_name.clone(),
            exit_code: code,
            stdout,
            stderr,
        });
    }
    outputs
}
