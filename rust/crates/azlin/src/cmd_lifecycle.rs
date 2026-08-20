#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use console::Style;
use indicatif::ProgressBar;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Start {
            vm_name,
            resource_group,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Starting", &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            let msg = crate::handlers::handle_start(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::finished_ok(&msg));
        }
        azlin_cli::Commands::Stop {
            vm_name,
            resource_group,
            deallocate,
            no_deallocate,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            // --no-deallocate overrides the default deallocate=true
            let effective_deallocate = deallocate && !no_deallocate;
            let (action, _done) = crate::stop_helpers::stop_action_labels(effective_deallocate);
            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(action, &vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            let msg =
                crate::handlers::handle_stop(&vm_manager, &rg, &vm_name, effective_deallocate)?;
            pb.finish_with_message(crate::lifecycle_helpers::finished_ok(&msg));
        }
        azlin_cli::Commands::Delete {
            vm_name,
            resource_group,
            force,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            if !safe_confirm(
                &crate::lifecycle_helpers::delete_confirm_prompt(&vm_name),
                force,
            )? {
                println!("Cancelled.");
                return Ok(());
            }

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Deleting", &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            let msg = crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::finished_ok(&msg));
        }
        azlin_cli::Commands::Kill {
            vm_name,
            resource_group,
            force,
        } => {
            // `--force` was declared and discarded, and `kill` prompted for
            // nothing — so the flag's existence told the user a prompt was
            // there to be skipped while the VM went away on the first Enter
            // (#1089). `kill` and `destroy` share `execute_teardown`; they now
            // share the confirmation too.
            //
            // Before authenticating, deliberately. The question is about
            // intent, not about Azure state, so a cancelled kill should cost
            // no API calls — and in a non-interactive context the user gets
            // "use --force" rather than an `az login` error that says nothing
            // about the real problem.
            if !safe_confirm(
                &crate::lifecycle_helpers::kill_confirm_prompt(&vm_name),
                force,
            )? {
                println!("Cancelled.");
                return Ok(());
            }

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Killing", &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            let _msg = crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::killed_message(&vm_name));
        }
        azlin_cli::Commands::Destroy {
            vm_name,
            resource_group,
            force,
            dry_run,
            delete_rg,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;

            // `--delete-rg` was previously accepted and silently ignored.
            // Honouring it is genuinely dangerous: resource groups routinely
            // hold hand-made VMs, VNets and IPs alongside azlin sessions, so
            // deleting the group would destroy unrelated user data. Reject it
            // explicitly and point at the targeted alternative.
            if delete_rg {
                anyhow::bail!(
                    "{}",
                    crate::lifecycle_helpers::delete_rg_rejected_message(&rg)
                );
            }

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            if dry_run {
                print!(
                    "{}",
                    crate::handlers::format_destroy_dry_run_live(&vm_manager, &rg, &vm_name)?
                );
                return Ok(());
            }

            if !safe_confirm(
                &crate::lifecycle_helpers::destroy_confirm_prompt(&vm_name),
                force,
            )? {
                println!("Cancelled.");
                return Ok(());
            }

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Destroying",
                &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            let msg = crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::destroyed_message(&vm_name));
            println!("{msg}");
        }
        azlin_cli::Commands::Killall {
            resource_group,
            force,
            prefix,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;

            // List every VM in the resource group first (read-only) so we can
            // tell "resource group is empty" apart from "prefix matched
            // nothing", and so the confirmation names the actual VMs.
            let all_query = crate::lifecycle_helpers::killall_all_names_query();
            let list_pb = penguin_spinner("Listing VMs...");
            let list_out = std::process::Command::new("az")
                .args(crate::lifecycle_helpers::killall_list_args(&rg, all_query))
                .output()?;
            list_pb.finish_and_clear();
            if !list_out.status.success() {
                anyhow::bail!("Failed to list VMs.");
            }
            let names_raw = String::from_utf8_lossy(&list_out.stdout);
            let all_names: Vec<String> = crate::lifecycle_helpers::parse_vm_ids(&names_raw)
                .into_iter()
                .map(str::to_string)
                .collect();
            let (matching, unmatched) =
                crate::lifecycle_helpers::partition_by_prefix(&all_names, &prefix);

            if matching.is_empty() {
                println!(
                    "{}",
                    crate::lifecycle_helpers::killall_no_match_message(&prefix, &rg, &unmatched)
                );
                return Ok(());
            }

            if !safe_confirm(
                &crate::lifecycle_helpers::killall_confirm_prompt(&prefix, &rg, &matching),
                force,
            )? {
                println!("Cancelled.");
                return Ok(());
            }

            let pb = penguin_spinner(&crate::lifecycle_helpers::progress_message(
                "Deleting VMs with prefix",
                &format!("'{}'", prefix),
            ));

            let query = crate::lifecycle_helpers::killall_jmespath_query(&prefix);
            let args = crate::lifecycle_helpers::killall_list_args(&rg, &query);
            let output = std::process::Command::new("az").args(&args).output()?;

            if !output.status.success() {
                pb.finish_and_clear();
                anyhow::bail!("Failed to list VMs.");
            }

            let names_raw = String::from_utf8_lossy(&output.stdout);
            // Re-listing picks up VMs deleted elsewhere since the enumeration,
            // but must never widen the set: the confirmation named specific
            // VMs, so anything not in that list is not ours to delete.
            let listed = crate::lifecycle_helpers::parse_vm_ids(&names_raw);
            let names = crate::lifecycle_helpers::narrow_to_confirmed(&listed, &matching);
            if names.is_empty() {
                // Only reachable if the matched VMs disappeared between the
                // enumeration above and this query; report it the same way.
                pb.finish_and_clear();
                println!(
                    "{}",
                    crate::lifecycle_helpers::killall_no_match_message(&prefix, &rg, &unmatched)
                );
            } else {
                // Tear each VM down individually rather than batching
                // `az vm delete --ids`. The batch form deletes only the VMs
                // and leaves every public IP and NSG behind — the same leak
                // this command previously shared with destroy/delete/kill.
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let mut messages = Vec::new();
                let mut failures = Vec::new();
                for name in &names {
                    match crate::handlers::handle_delete(&vm_manager, &rg, name) {
                        Ok(msg) => messages.push(msg),
                        Err(e) => failures.push(format!("{name}: {e}")),
                    }
                }
                pb.finish_and_clear();
                for msg in &messages {
                    println!("{msg}");
                }
                if !failures.is_empty() {
                    anyhow::bail!("Failed to delete VMs:\n  {}", failures.join("\n  "));
                }
                println!(
                    "{}",
                    crate::lifecycle_helpers::killall_success_message(messages.len(), &prefix)
                );
            }
        }

        // -- Cleanup / Prune --
        azlin_cli::Commands::OsUpdate {
            vm_identifier,
            resource_group,
            timeout,
        } => {
            let rg = resolve_resource_group(resource_group)?;

            let pb = penguin_spinner(&format!("Looking up {}...", vm_identifier));
            let target = resolve_vm_ssh_target(&vm_identifier, None, Some(rg.clone())).await?;
            pb.finish_and_clear();

            println!(
                "Running OS updates on '{}' (timeout {}s)...",
                vm_identifier, timeout
            );
            let cmd = crate::update_helpers::build_os_update_cmd().to_string();
            // An `apt` that never returns used to hold the command open
            // forever: `--timeout` was accepted and enforced nothing (#1089).
            let (code, stdout, stderr) = match crate::exec_under_timeout(&target, &cmd, timeout)? {
                crate::TimedExec::Finished {
                    code,
                    stdout,
                    stderr,
                } => (code, stdout, stderr),
                crate::TimedExec::TimedOut(note) => {
                    anyhow::bail!("OS update on '{}' {}", vm_identifier, note)
                }
            };
            if code == 0 {
                let green = Style::new().green();
                println!(
                    "{}",
                    green.apply_to(crate::lifecycle_helpers::os_update_success_message(
                        &vm_identifier
                    ))
                );
                if !stdout.trim().is_empty() {
                    println!("{}", stdout.trim());
                }
            } else {
                let red = Style::new().red();
                eprintln!(
                    "{}",
                    red.apply_to(format!("OS update failed on '{}'", vm_identifier))
                );
                anyhow::bail!(
                    "{}",
                    crate::lifecycle_helpers::os_update_failure_message(&vm_identifier, &stderr)
                );
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
