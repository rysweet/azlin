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
        },

        _ => unreachable!(),
    }
    Ok(())
}
