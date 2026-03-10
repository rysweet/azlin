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
        azlin_cli::Commands::New {
            repo,
            vm_size,
            region,
            resource_group,
            name,
            pool,
            no_auto_connect,
            template,
            yes,
            ..
        } => {
            crate::cmd_vm_ops::handle_vm_new(
                repo,
                vm_size,
                region,
                resource_group,
                name,
                pool,
                no_auto_connect,
                template,
                yes,
            )
            .await?;
        }
        azlin_cli::Commands::Vm { action } => match action {
            azlin_cli::VmAction::UpdateTools {
                vm_identifier,
                resource_group,
                timeout: _,
                ..
            } => {
                crate::cmd_vm_ops2::handle_vm_update(&vm_identifier, resource_group).await?;
            }
        },
        azlin_cli::Commands::Clone {
            source_vm,
            num_replicas,
            resource_group,
            ..
        } => {
            crate::cmd_vm_ops2::handle_vm_clone(&source_vm, num_replicas, resource_group)?;
        }
        _ => unreachable!(),
    }
    Ok(())
}
