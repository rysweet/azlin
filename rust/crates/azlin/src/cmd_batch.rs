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
    let ids: Vec<String> = names.keys().cloned().collect();
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
                vm_pattern,
                all,
                yes,
                no_deallocate,
                ..
            } => {
                crate::batch_helpers::validate_selection(
                    all,
                    tag.as_deref(),
                    vm_pattern.as_deref(),
                )
                .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let selection =
                    crate::batch_helpers::describe_selection(tag.as_deref(), vm_pattern.as_deref());
                // --no-deallocate keeps the VMs allocated, mirroring `azlin stop`.
                let az_action = crate::batch_helpers::batch_stop_action(no_deallocate);
                let verb = if no_deallocate {
                    "Stop (keeping allocated)"
                } else {
                    "Stop and deallocate"
                };
                let prompt = crate::batch_helpers::build_confirmation_prompt(verb, &selection, &rg);
                if !safe_confirm(&prompt, yes)? {
                    println!("Cancelled.");
                    return Ok(());
                }
                let (ids, names) = list_vms_with_names(&rg, tag.as_deref())?;
                let ids = match vm_pattern.as_deref() {
                    Some(p) => crate::batch_helpers::filter_ids_by_pattern(&ids, &names, p),
                    None => ids,
                };
                if ids.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_match_message(
                            &rg,
                            tag.as_deref(),
                            vm_pattern.as_deref()
                        )
                    );
                } else {
                    let id_refs: Vec<&str> = ids.iter().map(|s| s.as_str()).collect();
                    let summary =
                        crate::batch_progress::run_batch_with_progress(az_action, &id_refs, &names);
                    println!("{}", summary.format_summary("stop"));
                }
            }
            azlin_cli::BatchAction::Start {
                resource_group,
                tag,
                vm_pattern,
                all,
                yes,
                ..
            } => {
                crate::batch_helpers::validate_selection(
                    all,
                    tag.as_deref(),
                    vm_pattern.as_deref(),
                )
                .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let selection =
                    crate::batch_helpers::describe_selection(tag.as_deref(), vm_pattern.as_deref());
                let prompt =
                    crate::batch_helpers::build_confirmation_prompt("Start", &selection, &rg);
                if !safe_confirm(&prompt, yes)? {
                    println!("Cancelled.");
                    return Ok(());
                }
                let (ids, names) = list_vms_with_names(&rg, tag.as_deref())?;
                let ids = match vm_pattern.as_deref() {
                    Some(p) => crate::batch_helpers::filter_ids_by_pattern(&ids, &names, p),
                    None => ids,
                };
                if ids.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_match_message(
                            &rg,
                            tag.as_deref(),
                            vm_pattern.as_deref()
                        )
                    );
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
                vm_pattern,
                all,
                show_output,
                ..
            } => {
                crate::batch_helpers::validate_selection(all, None, vm_pattern.as_deref())
                    .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let selection =
                    crate::batch_helpers::describe_selection(None, vm_pattern.as_deref());
                let pb = penguin_spinner(&format!(
                    "Running '{}' on {} in '{}'...",
                    command, selection, rg
                ));
                let mut vms = get_running_vm_targets(Some(rg.clone())).await?;
                if let Some(p) = vm_pattern.as_deref() {
                    vms.retain(|t| crate::batch_helpers::glob_match(p, &t.vm_name));
                }
                pb.finish_and_clear();
                if vms.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_running_match_message(
                            &rg,
                            vm_pattern.as_deref()
                        )
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
                vm_pattern,
                all,
                dry_run,
                ..
            } => {
                crate::batch_helpers::validate_selection(all, None, vm_pattern.as_deref())
                    .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let mut vms = get_running_vm_targets(Some(rg.clone())).await?;
                if let Some(p) = vm_pattern.as_deref() {
                    vms.retain(|t| crate::batch_helpers::glob_match(p, &t.vm_name));
                }
                if vms.is_empty() {
                    println!(
                        "{}",
                        crate::batch_helpers::format_no_running_match_message(
                            &rg,
                            vm_pattern.as_deref()
                        )
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
