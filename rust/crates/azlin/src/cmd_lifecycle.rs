#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use console::Style;
use dialoguer::Confirm;
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
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = crate::handlers::handle_start(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::finished_ok(&msg));
        }
        azlin_cli::Commands::Stop {
            vm_name,
            resource_group,
            deallocate,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let (action, _done) = crate::stop_helpers::stop_action_labels(deallocate);
            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(action, &vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = crate::handlers::handle_stop(&vm_manager, &rg, &vm_name, deallocate)?;
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

            if !force {
                let confirmed = Confirm::new()
                    .with_prompt(crate::lifecycle_helpers::delete_confirm_prompt(&vm_name))
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Deleting", &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::finished_ok(&msg));
        }
        azlin_cli::Commands::Kill {
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
                "Killing", &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let _msg = crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::killed_message(&vm_name));
        }
        azlin_cli::Commands::Destroy {
            vm_name,
            resource_group,
            force,
            dry_run,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;

            if dry_run {
                println!("{}", crate::handlers::format_destroy_dry_run(&vm_name, &rg));
                return Ok(());
            }

            if !force {
                let confirmed = Confirm::new()
                    .with_prompt(crate::lifecycle_helpers::destroy_confirm_prompt(&vm_name))
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Destroying",
                &vm_name,
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            crate::handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(crate::lifecycle_helpers::destroyed_message(&vm_name));
        }
        azlin_cli::Commands::Killall {
            resource_group,
            force,
            prefix,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            if !force {
                let ok = Confirm::new()
                    .with_prompt(crate::lifecycle_helpers::killall_confirm_prompt(
                        &prefix, &rg,
                    ))
                    .default(false)
                    .interact()?;
                if !ok {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(crate::lifecycle_helpers::progress_message(
                "Deleting VMs with prefix",
                &format!("'{}'", prefix),
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let query = crate::lifecycle_helpers::killall_jmespath_query(&prefix);
            let args = crate::lifecycle_helpers::killall_list_args(&rg, &query);
            let output = std::process::Command::new("az").args(&args).output()?;

            if output.status.success() {
                let ids_raw = String::from_utf8_lossy(&output.stdout);
                let id_list = crate::lifecycle_helpers::parse_vm_ids(&ids_raw);
                if id_list.is_empty() {
                    pb.finish_and_clear();
                    println!(
                        "{}",
                        crate::lifecycle_helpers::killall_empty_message(&prefix)
                    );
                } else {
                    let del = std::process::Command::new("az")
                        .args(["vm", "delete", "--ids"])
                        .args(&id_list)
                        .args(["--yes"])
                        .output()?;
                    pb.finish_and_clear();
                    if del.status.success() {
                        println!(
                            "{}",
                            crate::lifecycle_helpers::killall_success_message(
                                id_list.len(),
                                &prefix
                            )
                        );
                    } else {
                        let stderr = String::from_utf8_lossy(&del.stderr);
                        anyhow::bail!(
                            "Failed to delete VMs: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
            } else {
                pb.finish_and_clear();
                anyhow::bail!("Failed to list VMs.");
            }
        }

        // -- Cleanup / Prune --
        azlin_cli::Commands::OsUpdate {
            vm_identifier,
            resource_group,
            timeout: _,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", vm_identifier));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            println!("Running OS updates on '{}'...", vm_identifier);
            let cmd = crate::update_helpers::build_os_update_cmd().to_string();
            let (code, stdout, stderr) = ssh_exec(&ip, &user, &cmd)?;
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
