#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Env { action } => match action {
            azlin_cli::EnvAction::Set {
                vm_identifier,
                env_var,
                resource_group,
                ip,
                ..
            } => {
                let (key, value) = match crate::env_helpers::split_env_var(&env_var) {
                    Some(kv) => kv,
                    None => {
                        anyhow::bail!("Invalid format. Use KEY=VALUE");
                    }
                };
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let escaped = shell_escape(value);
                let cmd = crate::env_helpers::build_env_set_cmd(key, &escaped);
                if cmd == "true" {
                    anyhow::bail!("Invalid environment variable key: {}", key);
                }
                target.exec_checked(&cmd)?;
                println!("Set {}={} on VM '{}'", key, value, vm_identifier);
            }
            azlin_cli::EnvAction::List {
                vm_identifier,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = target.exec_checked(crate::env_helpers::env_list_cmd())?;
                let mut table =
                    crate::table_render::SimpleTable::new(&["Variable", "Value"], &[30, 50]);
                for line in output.lines() {
                    if let Some((k, v)) = line.split_once('=') {
                        table.add_row(vec![k.to_string(), v.to_string()]);
                    }
                }
                println!("{table}");
            }
            azlin_cli::EnvAction::Delete {
                vm_identifier,
                key,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = crate::env_helpers::build_env_delete_cmd(&key);
                target.exec_checked(&cmd)?;
                println!("Deleted '{}' from VM '{}'", key, vm_identifier);
            }
            azlin_cli::EnvAction::Export {
                vm_identifier,
                output_file,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = target.exec_checked(crate::env_helpers::env_list_cmd())?;
                match output_file {
                    Some(path) => {
                        std::fs::write(&path, &output)?;
                        println!(
                            "Exported env vars from VM '{}' to '{}'",
                            vm_identifier, path
                        );
                    }
                    None => print!("{}", output),
                }
            }
            azlin_cli::EnvAction::Import {
                vm_identifier,
                env_file,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let content = std::fs::read_to_string(&env_file)?;
                for (key, value) in crate::env_helpers::parse_env_file(&content) {
                    let escaped = shell_escape(&value);
                    let cmd = crate::env_helpers::build_env_set_cmd(&key, &escaped);
                    if cmd == "true" {
                        eprintln!("Skipping invalid environment variable key: {}", key);
                        continue;
                    }
                    target.exec_checked(&cmd)?;
                }
                println!(
                    "Imported env vars from '{}' to VM '{}'",
                    env_file.display(),
                    vm_identifier
                );
            }
            azlin_cli::EnvAction::Clear {
                vm_identifier,
                force,
                resource_group,
                ip,
                ..
            } => {
                if !safe_confirm(
                    &format!(
                        "Clear all custom env vars on VM '{}'? This cannot be undone.",
                        vm_identifier
                    ),
                    force,
                )? {
                    println!("Cancelled.");
                    return Ok(());
                }
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = crate::env_helpers::env_clear_cmd();
                target.exec_checked(cmd)?;
                println!(
                    "Cleared all custom environment variables on VM '{}'",
                    vm_identifier
                );
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
