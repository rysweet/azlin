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
        azlin_cli::Commands::Sync {
            vm_name,
            dry_run,
            resource_group,
            ..
        } => {
            crate::cmd_sync_ops::handle_sync(vm_name, dry_run, resource_group)?;
        }

        azlin_cli::Commands::SyncKeys {
            vm_name,
            resource_group,
            ssh_user,
            ..
        } => {
            crate::cmd_sync_ops::handle_sync_keys(&vm_name, resource_group, &ssh_user)?;
        }

        azlin_cli::Commands::Cp {
            args,
            dry_run,
            resource_group,
            ..
        } => {
            crate::cmd_sync_ops::handle_cp(&args, dry_run, resource_group)?;
        }

        azlin_cli::Commands::Logs {
            vm_identifier,
            lines,
            follow,
            log_type,
            resource_group,
            ..
        } => {
            crate::cmd_sync_ops::handle_logs(
                &vm_identifier,
                lines,
                follow,
                log_type,
                resource_group,
            )
            .await?;
        }

        _ => unreachable!(),
    }
    Ok(())
}
