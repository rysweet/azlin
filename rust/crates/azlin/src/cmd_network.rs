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
        azlin_cli::Commands::Disk { action } => match action {
            azlin_cli::DiskAction::Add {
                vm_name,
                size,
                sku,
                resource_group,
                lun,
                mount: _mount,
                ..
            } => {
                crate::cmd_network_ops::handle_disk_add(&vm_name, size, &sku, resource_group, lun)?;
            }
        },

        azlin_cli::Commands::Ip { action } => match action {
            azlin_cli::IpAction::Check {
                vm_identifier,
                resource_group,
                port,
                ..
            } => {
                crate::cmd_network_ops::handle_ip_check(vm_identifier, resource_group, port)?;
            }
        },

        azlin_cli::Commands::Web { action } => match action {
            azlin_cli::WebAction::Start { port, host } => {
                crate::cmd_network_ops::handle_web_start(port, &host)?;
            }
            azlin_cli::WebAction::Stop => {
                crate::cmd_network_ops::handle_web_stop()?;
            }
        },

        azlin_cli::Commands::Bastion { action } => match action {
            azlin_cli::BastionAction::List { resource_group } => {
                crate::cmd_network_ops2::handle_bastion_list(resource_group)?;
            }
            azlin_cli::BastionAction::Status {
                name,
                resource_group,
            } => {
                crate::cmd_network_ops2::handle_bastion_status(&name, &resource_group)?;
            }
            azlin_cli::BastionAction::Configure {
                vm_name,
                bastion_name,
                resource_group,
                bastion_resource_group,
                disable,
            } => {
                crate::cmd_network_ops2::handle_bastion_configure(
                    &vm_name,
                    &bastion_name,
                    resource_group,
                    bastion_resource_group,
                    disable,
                )?;
            }
            azlin_cli::BastionAction::Sweep => {
                handle_bastion_sweep()?;
            }
        },

        _ => unreachable!(),
    }
    Ok(())
}

/// Kill orphaned `az network bastion tunnel` processes left over from before
/// the native tunnel migration. Only targets own-user processes (SEC-6).
fn handle_bastion_sweep() -> Result<()> {
    let output = std::process::Command::new("pgrep")
        .args(["-u", &whoami(), "-fa", "az network bastion tunnel"])
        .output();

    let output = match output {
        Ok(o) => o,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            println!("pgrep not found; cannot sweep orphaned az processes");
            return Ok(());
        }
        Err(e) => return Err(e.into()),
    };

    if !output.status.success() && output.status.code() == Some(1) {
        // pgrep exit code 1 = no matching processes
        println!("No orphaned az bastion tunnel processes found.");
        return Ok(());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let mut killed = 0u32;
    for line in stdout.lines() {
        let pid_str = line.split_whitespace().next().unwrap_or("");
        let Ok(pid) = pid_str.parse::<u32>() else {
            continue;
        };
        // Only kill processes whose cmdline matches exactly
        if !line.contains("az network bastion tunnel") {
            continue;
        }
        println!("Killing orphaned az bastion tunnel (PID {}): {}", pid, line.trim());
        let _ = std::process::Command::new("kill")
            .arg(pid.to_string())
            .status();
        killed += 1;
    }

    if killed == 0 {
        println!("No orphaned az bastion tunnel processes found.");
    } else {
        println!("Swept {} orphaned az bastion tunnel process(es).", killed);
    }
    Ok(())
}

fn whoami() -> String {
    std::env::var("USER")
        .or_else(|_| std::env::var("LOGNAME"))
        .unwrap_or_else(|_| {
            String::from_utf8_lossy(
                &std::process::Command::new("id")
                    .args(["-un"])
                    .output()
                    .map(|o| o.stdout)
                    .unwrap_or_default(),
            )
            .trim()
            .to_string()
        })
}
