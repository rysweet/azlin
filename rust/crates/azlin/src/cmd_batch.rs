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
                max_workers,
                yes,
                no_deallocate,
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
                if !safe_confirm_with_flag(&prompt, yes, "--yes")? {
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
                    let summary = crate::batch_progress::run_batch_with_progress(
                        az_action,
                        &id_refs,
                        &names,
                        crate::fleet_select::worker_count(max_workers),
                    );
                    println!("{}", summary.format_summary("stop"));
                }
            }
            azlin_cli::BatchAction::Start {
                resource_group,
                tag,
                vm_pattern,
                all,
                max_workers,
                yes,
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
                if !safe_confirm_with_flag(&prompt, yes, "--yes")? {
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
                    let summary = crate::batch_progress::run_batch_with_progress(
                        "start",
                        &id_refs,
                        &names,
                        crate::fleet_select::worker_count(max_workers),
                    );
                    println!("{}", summary.format_summary("start"));
                }
            }
            azlin_cli::BatchAction::Command {
                command,
                resource_group,
                tag,
                vm_pattern,
                all,
                max_workers,
                timeout,
                show_output,
            } => {
                // `--tag` used to be dropped here — including from the
                // validation call, which was passed a literal `None`. So
                // `azlin batch command 'systemctl restart app' --tag env=dev`
                // ran on every running VM in the resource group and reported
                // success (#1089).
                crate::batch_helpers::validate_selection(
                    all,
                    tag.as_deref(),
                    vm_pattern.as_deref(),
                )
                .map_err(|e| anyhow::anyhow!(e))?;
                if let Some(t) = tag.as_deref() {
                    if crate::tag_helpers::parse_tag(t).is_none() {
                        anyhow::bail!("Invalid tag format '{}'. Use key=value.", t);
                    }
                }
                let rg = resolve_resource_group(resource_group)?;
                let workers = crate::fleet_select::worker_count(max_workers);
                let selection =
                    crate::batch_helpers::describe_selection(tag.as_deref(), vm_pattern.as_deref());
                let pb = penguin_spinner(&format!(
                    "Running '{}' on {} in '{}'...",
                    command, selection, rg
                ));
                // Filtering on `VmInfo` rather than on the built targets,
                // because a `VmSshTarget` carries no tags.
                let vms = resolve_fleet_targets(&rg, tag.as_deref(), vm_pattern.as_deref()).await?;
                pb.finish_and_clear();
                if vms.is_empty() {
                    // A selector that matches nothing is not a success: the
                    // pattern is wrong or the VMs are down, and a scripted
                    // run must not go green having touched no host.
                    anyhow::bail!(crate::fleet_select::format_no_match_message(
                        &rg,
                        tag.as_deref(),
                        vm_pattern.as_deref()
                    ));
                }
                println!(
                    "{}",
                    crate::batch_helpers::format_fleet_run_message(&command, vms.len())
                );
                let wrapped = crate::fleet_select::wrap_with_timeout(&command, timeout);
                let results = run_on_fleet_with_workers_and_timeout(
                    &vms,
                    &wrapped,
                    show_output,
                    workers,
                    crate::fleet_select::local_timeout_secs(timeout),
                    &command,
                );
                report_batch_timeouts(&vms, &results, timeout);
            }
            azlin_cli::BatchAction::Sync {
                resource_group,
                tag,
                vm_pattern,
                all,
                max_workers,
                dry_run,
            } => {
                // `--tag` was dropped here too, so a filtered sync pushed the
                // caller's dotfiles to every running VM (#1089).
                crate::batch_helpers::validate_selection(
                    all,
                    tag.as_deref(),
                    vm_pattern.as_deref(),
                )
                .map_err(|e| anyhow::anyhow!(e))?;
                if let Some(t) = tag.as_deref() {
                    if crate::tag_helpers::parse_tag(t).is_none() {
                        anyhow::bail!("Invalid tag format '{}'. Use key=value.", t);
                    }
                }
                let rg = resolve_resource_group(resource_group)?;
                let workers = crate::fleet_select::worker_count(max_workers);
                let vms = resolve_fleet_targets(&rg, tag.as_deref(), vm_pattern.as_deref()).await?;
                if vms.is_empty() {
                    anyhow::bail!(crate::fleet_select::format_no_match_message(
                        &rg,
                        tag.as_deref(),
                        vm_pattern.as_deref()
                    ));
                }
                let home = home_dir()?;
                let dotfiles = crate::sync_helpers::default_dotfiles();
                let failures = std::sync::atomic::AtomicUsize::new(0);
                crate::batch_progress::for_each_bounded(vms.len(), workers, |i| {
                    let target = &vms[i];
                    let (name, ip, user) = (&target.vm_name, &target.ip, &target.user);
                    for dotfile in &dotfiles {
                        let local = home.join(dotfile);
                        if !local.exists() {
                            continue;
                        }
                        if dry_run {
                            println!("[dry-run] Would sync {} to {}:{}", dotfile, name, dotfile);
                            continue;
                        }
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
                                failures.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                                let stderr = String::from_utf8_lossy(&o.stderr);
                                eprintln!(
                                    "Failed to sync {} to {}: {}",
                                    dotfile,
                                    name,
                                    azlin_core::sanitizer::sanitize(stderr.trim())
                                );
                            }
                            Err(e) => {
                                failures.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                                eprintln!("Failed to sync {} to {}: {}", dotfile, name, e)
                            }
                        }
                    }
                });
                let failed = failures.into_inner();
                if !dry_run {
                    // "Sync complete." after a wall of rsync errors was its
                    // own small silent success.
                    if failed > 0 {
                        anyhow::bail!(
                            "{} dotfile transfer(s) failed; see the errors above.",
                            failed
                        );
                    }
                    println!("Sync complete.");
                }
            }
        },
        azlin_cli::Commands::Fleet { action } => match action {
            azlin_cli::FleetAction::Run {
                command,
                resource_group,
                tag,
                pattern,
                all,
                parallel,
                if_idle,
                if_cpu_below,
                if_mem_below,
                smart_route,
                count,
                retry_failed,
                show_diff,
                timeout,
                dry_run,
            } => {
                use crate::fleet_select as fs;
                fs::validate_selection(all, tag.as_deref(), pattern.as_deref())
                    .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let workers = fs::worker_count(parallel);
                let selection = fs::describe_selection(tag.as_deref(), pattern.as_deref());
                if dry_run {
                    println!(
                        "Would run '{}' across fleet in '{}' on {} \
                         (timeout {}s, {} parallel worker(s))",
                        command, rg, selection, timeout, workers
                    );
                    return Ok(());
                }
                let pb = penguin_spinner(&format!("Gathering fleet VMs in '{}'...", rg));
                let mut vms =
                    resolve_fleet_targets(&rg, tag.as_deref(), pattern.as_deref()).await?;
                pb.finish_and_clear();
                if vms.is_empty() {
                    // Not a quiet success: a selector that matches nothing
                    // means the pattern is wrong or the VMs are down, and a
                    // CI job must not go green having run on no host at all.
                    anyhow::bail!(fs::format_no_match_message(
                        &rg,
                        tag.as_deref(),
                        pattern.as_deref()
                    ));
                }

                // --if-idle / --if-cpu-below / --if-mem-below / --smart-route
                // all need a load reading, so the probe is paid for once and
                // only when one of them was actually asked for.
                if fs::needs_load_probe(if_idle, if_cpu_below, if_mem_below, smart_route) {
                    let pb = penguin_spinner("Sampling fleet load...");
                    let loads = probe_fleet_load(&vms, workers);
                    pb.finish_and_clear();
                    let mut kept = Vec::new();
                    let mut kept_loads = Vec::new();
                    for (target, load) in vms.into_iter().zip(loads) {
                        match fs::load_gate(&load, if_idle, if_cpu_below, if_mem_below) {
                            Ok(()) => {
                                kept.push(target);
                                kept_loads.push(load);
                            }
                            Err(skipped) => {
                                println!("Skipping {}: {}", target.vm_name, skipped.reason());
                            }
                        }
                    }
                    if smart_route {
                        let order = fs::smart_route_order(&kept_loads);
                        let mut slots: Vec<Option<VmSshTarget>> =
                            kept.into_iter().map(Some).collect();
                        kept = order
                            .into_iter()
                            .map(|i| slots[i].take().expect("each index appears once"))
                            .collect();
                    }
                    vms = kept;
                    if vms.is_empty() {
                        println!("No VM passed the --if-* load gates; nothing to run.");
                        return Ok(());
                    }
                }

                vms = fs::apply_count(vms, count);
                if vms.is_empty() {
                    println!("--count 0 selected no VMs; nothing to run.");
                    return Ok(());
                }

                println!(
                    "{}",
                    crate::batch_helpers::format_fleet_across_message(&command, vms.len())
                );
                let wrapped = fs::wrap_with_timeout(&command, timeout);
                let local_timeout = fs::local_timeout_secs(timeout);
                let mut outputs =
                    collect_fleet_outputs(&vms, &wrapped, workers, local_timeout, &command);
                annotate_fleet_timeouts(&mut outputs, timeout);

                if retry_failed {
                    let failed: Vec<usize> = outputs
                        .iter()
                        .enumerate()
                        .filter(|(_, o)| !o.succeeded())
                        .map(|(i, _)| i)
                        .collect();
                    let mut recovered = 0;
                    if !failed.is_empty() {
                        println!(
                            "Retrying {} failed VM(s) once (--retry-failed)...",
                            failed.len()
                        );
                        let retry_targets: Vec<VmSshTarget> =
                            failed.iter().map(|i| vms[*i].clone()).collect();
                        let mut retried = collect_fleet_outputs(
                            &retry_targets,
                            &wrapped,
                            workers,
                            local_timeout,
                            &command,
                        );
                        annotate_fleet_timeouts(&mut retried, timeout);
                        for (slot, result) in failed.iter().zip(retried) {
                            if result.succeeded() {
                                recovered += 1;
                            }
                            outputs[*slot] = result;
                        }
                    }
                    println!("{}", fs::format_retry_summary(failed.len(), recovered));
                }

                if show_diff {
                    let entries: Vec<fs::DiffEntry> = outputs
                        .iter()
                        .map(|o| fs::DiffEntry {
                            vm_name: o.vm_name.clone(),
                            exit_code: o.exit_code,
                            output: o.combined_output(),
                        })
                        .collect();
                    println!("{}", fs::format_output_diff(&entries));
                } else {
                    crate::fleet_tabs::run_fleet_tabs(outputs, false)?;
                }
            }
            azlin_cli::FleetAction::Workflow {
                workflow_file,
                resource_group,
                tag,
                pattern,
                all,
                parallel,
                show_diff,
                dry_run,
            } => {
                use crate::fleet_select as fs;
                fs::validate_selection(all, tag.as_deref(), pattern.as_deref())
                    .map_err(|e| anyhow::anyhow!(e))?;
                let rg = resolve_resource_group(resource_group)?;
                let workers = fs::worker_count(parallel);
                let selection = fs::describe_selection(tag.as_deref(), pattern.as_deref());
                if dry_run {
                    println!(
                        "Would execute workflow '{}' on fleet in '{}' on {} \
                         ({} parallel worker(s))",
                        workflow_file.display(),
                        rg,
                        selection,
                        workers
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
                    let vms =
                        resolve_fleet_targets(&rg, tag.as_deref(), pattern.as_deref()).await?;
                    if vms.is_empty() {
                        anyhow::bail!(fs::format_no_match_message(
                            &rg,
                            tag.as_deref(),
                            pattern.as_deref()
                        ));
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
                            let results = run_on_fleet_with_workers(&vms, cmd, true, workers);
                            if show_diff {
                                let entries: Vec<fs::DiffEntry> = vms
                                    .iter()
                                    .zip(&results)
                                    .map(|(t, (code, stdout, stderr))| fs::DiffEntry {
                                        vm_name: t.vm_name.clone(),
                                        exit_code: *code,
                                        output: format!("{}{}", stdout, stderr),
                                    })
                                    .collect();
                                println!("{}", fs::format_output_diff(&entries));
                            }
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

/// Sample CPU and memory on every target so the `--if-*` gates and
/// `--smart-route` have a reading to work from.
///
/// A probe that fails yields an incomplete [`crate::fleet_select::VmLoad`]
/// rather than zeros, so an unreachable VM is reported as unmeasurable instead
/// of being silently ranked as the least-loaded host in the fleet.
fn probe_fleet_load(targets: &[VmSshTarget], workers: usize) -> Vec<crate::fleet_select::VmLoad> {
    let bars = crate::fleet_progress_bars(targets);
    crate::exec_fleet(
        targets,
        &crate::fleet_select::probe_command(),
        workers,
        &bars,
        crate::fleet_select::local_timeout_secs(crate::fleet_select::PROBE_TIMEOUT_SECS),
        "sampling load",
    )
    .into_iter()
    .map(|(code, stdout, _)| crate::fleet_select::parse_probe(code, &stdout))
    .collect()
}

/// Say so when `--timeout` is what killed a command.
///
/// Otherwise the user sees a bare `exit 124` with nothing tying it to the flag
/// they passed.
fn annotate_fleet_timeouts(outputs: &mut [crate::fleet_tabs::VmOutput], timeout: u32) {
    for out in outputs.iter_mut() {
        if let Some(note) = crate::fleet_select::timeout_note(out.exit_code, timeout) {
            if !out.stderr.is_empty() && !out.stderr.ends_with('\n') {
                out.stderr.push('\n');
            }
            out.stderr.push_str(&note);
            out.stderr.push('\n');
        }
    }
}

/// Run `command` across `targets` with at most `workers` concurrent SSH
/// sessions, returning one `VmOutput` per target in target order.
fn collect_fleet_outputs(
    targets: &[VmSshTarget],
    command: &str,
    workers: usize,
    local_timeout_secs: u64,
    display_command: &str,
) -> Vec<crate::fleet_tabs::VmOutput> {
    let bars = crate::fleet_progress_bars(targets);
    crate::exec_fleet(
        targets,
        command,
        workers,
        &bars,
        local_timeout_secs,
        display_command,
    )
    .into_iter()
    .zip(targets)
    .map(
        |((exit_code, stdout, stderr), target)| crate::fleet_tabs::VmOutput {
            vm_name: target.vm_name.clone(),
            exit_code,
            stdout,
            stderr,
        },
    )
    .collect()
}
