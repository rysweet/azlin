#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Keys { action } => match action {
            azlin_cli::KeysAction::List {
                resource_group,
                all_vms,
                vm_prefix,
            } => {
                // This listed the caller's `~/.ssh` directory and ignored all
                // three flags (#1089). `ls -l ~/.ssh` still does that; what it
                // could not do, and what the help has always promised, is say
                // which VMs carry which key.
                let rg = resolve_resource_group(resource_group)?;
                let prefix = crate::keys_list::prefix_filter(all_vms, &vm_prefix);

                let az = std::process::Command::new("az")
                    .args(crate::keys_list::build_vm_keys_args(&rg, prefix))
                    .output()
                    .context("Failed to run `az vm list`. Is the Azure CLI installed?")?;

                if !az.status.success() {
                    let stderr = String::from_utf8_lossy(&az.stderr);
                    anyhow::bail!(
                        "Failed to list VMs in '{}': {}",
                        rg,
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }

                let vms = crate::keys_list::parse_vm_keys(&az.stdout)?;
                if vms.is_empty() {
                    println!(
                        "{}",
                        crate::keys_list::empty_message(&rg, all_vms, &vm_prefix)
                    );
                    return Ok(());
                }

                azlin_cli::table::render_rows(
                    &["VM", "Type", "Fingerprint", "Comment"],
                    &crate::keys_list::build_rows(&vms),
                    output,
                );
            }
            azlin_cli::KeysAction::Rotate {
                resource_group,
                all_vms,
                no_backup,
                vm_prefix,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let ssh_dir = home_dir()?.join(".ssh");

                if !no_backup {
                    let backup_dir = ssh_dir.join(format!(
                        "backup_{}",
                        chrono::Utc::now().format("%Y%m%d_%H%M%S")
                    ));
                    std::fs::create_dir_all(&backup_dir)?;
                    for entry in std::fs::read_dir(&ssh_dir)? {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if crate::key_helpers::is_key_backup_candidate(&name) {
                            std::fs::copy(entry.path(), backup_dir.join(&name))?;
                        }
                    }
                    println!("Backed up existing keys to {}", backup_dir.display());
                }

                let new_key = ssh_dir.join("id_ed25519_azlin");
                if new_key.exists() {
                    std::fs::remove_file(&new_key)?;
                    let pub_key = ssh_dir.join("id_ed25519_azlin.pub");
                    if pub_key.exists() {
                        std::fs::remove_file(&pub_key)?;
                    }
                }

                let key_path_str = new_key.to_string_lossy();
                let keygen_args = crate::key_helpers::build_keygen_args(&key_path_str);
                let keygen = std::process::Command::new("ssh-keygen")
                    .args(&keygen_args)
                    .output()?;

                if !keygen.status.success() {
                    anyhow::bail!("Failed to generate new SSH key.");
                }
                println!("Generated new ed25519 key pair");

                let prefix_filter = if all_vms { "" } else { &vm_prefix };
                let query = crate::key_helpers::build_vm_prefix_query(prefix_filter);
                let mut az_args = vec!["vm", "list", "--resource-group", &rg, "--output", "json"];
                if let Some(ref q) = query {
                    az_args.extend(["--query", q.as_str()]);
                }

                let output = std::process::Command::new("az").args(&az_args).output()?;

                if output.status.success() {
                    let vms: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)
                        .context("Failed to parse VM list JSON")?;
                    let pub_key_content =
                        std::fs::read_to_string(ssh_dir.join("id_ed25519_azlin.pub"))?;
                    for vm_val in &vms {
                        let name = vm_val["name"].as_str().unwrap_or("");
                        let result = std::process::Command::new("az")
                            .args([
                                "vm",
                                "user",
                                "update",
                                "--resource-group",
                                &rg,
                                "--name",
                                name,
                                "--username",
                                DEFAULT_ADMIN_USERNAME,
                                "--ssh-key-value",
                                pub_key_content.trim(),
                            ])
                            .output();
                        match result {
                            Ok(o) if o.status.success() => {
                                println!("  Deployed key to VM '{}'", name);
                            }
                            Ok(o) => {
                                let stderr = String::from_utf8_lossy(&o.stderr);
                                eprintln!(
                                    "  Failed to deploy key to VM '{}': {}",
                                    name,
                                    stderr.trim()
                                );
                            }
                            Err(e) => {
                                eprintln!("  Failed to deploy key to VM '{}': {}", name, e);
                            }
                        }
                    }
                }

                println!("{}", crate::handlers::format_key_rotation_complete());
            }
            azlin_cli::KeysAction::Export { output } => {
                let ssh_dir = home_dir()?.join(".ssh");

                let pub_key = crate::key_helpers::find_preferred_pubkey(&ssh_dir);

                match pub_key {
                    Some(src) => {
                        std::fs::copy(&src, &output)?;
                        let fname = src
                            .file_name()
                            .map(|f| f.to_string_lossy().into_owned())
                            .unwrap_or_else(|| src.display().to_string());
                        println!(
                            "{}",
                            crate::handlers::format_key_exported(
                                &fname,
                                &output.display().to_string()
                            )
                        );
                    }
                    None => {
                        anyhow::bail!("No SSH public key found in {}", ssh_dir.display());
                    }
                }
            }
            azlin_cli::KeysAction::Backup { destination } => {
                let ssh_dir = home_dir()?.join(".ssh");

                let backup_dir = destination.unwrap_or_else(|| {
                    ssh_dir.join(format!(
                        "backup_{}",
                        chrono::Utc::now().format("%Y%m%d_%H%M%S")
                    ))
                });

                std::fs::create_dir_all(&backup_dir)?;
                let mut count = 0u32;
                for entry in std::fs::read_dir(&ssh_dir)? {
                    let entry = entry?;
                    let name = entry.file_name().to_string_lossy().to_string();
                    if crate::key_helpers::is_key_backup_candidate(&name) {
                        std::fs::copy(entry.path(), backup_dir.join(&name))?;
                        count += 1;
                    }
                }
                println!(
                    "{}",
                    crate::handlers::format_key_backup(count, &backup_dir.display().to_string())
                );
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
