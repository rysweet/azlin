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
        azlin_cli::Commands::Snapshot { action } => {
            let rg = match &action {
                azlin_cli::SnapshotAction::Create { resource_group, .. }
                | azlin_cli::SnapshotAction::List { resource_group, .. }
                | azlin_cli::SnapshotAction::Restore { resource_group, .. }
                | azlin_cli::SnapshotAction::Delete { resource_group, .. }
                | azlin_cli::SnapshotAction::Enable { resource_group, .. }
                | azlin_cli::SnapshotAction::Disable { resource_group, .. }
                | azlin_cli::SnapshotAction::Sync { resource_group, .. }
                | azlin_cli::SnapshotAction::Status { resource_group, .. } => {
                    resolve_resource_group(resource_group.clone())?
                }
            };

            match action {
                azlin_cli::SnapshotAction::Create { vm_name, .. } => {
                    crate::cmd_snapshot_ops::handle_snapshot_create(&vm_name, &rg).await?;
                }
                azlin_cli::SnapshotAction::List { vm_name, .. } => {
                    crate::cmd_snapshot_ops::handle_snapshot_list(&vm_name, &rg).await?;
                }
                azlin_cli::SnapshotAction::Restore {
                    vm_name,
                    snapshot_name,
                    force,
                    ..
                } => {
                    crate::cmd_snapshot_ops::handle_snapshot_restore(
                        &vm_name,
                        &snapshot_name,
                        force,
                        &rg,
                    )
                    .await?;
                }
                azlin_cli::SnapshotAction::Delete {
                    snapshot_name,
                    force,
                    ..
                } => {
                    crate::cmd_snapshot_ops2::handle_snapshot_delete(&snapshot_name, force, &rg)
                        .await?;
                }
                azlin_cli::SnapshotAction::Enable {
                    vm_name,
                    every,
                    keep,
                    ..
                } => {
                    crate::cmd_snapshot_ops2::handle_snapshot_enable(&vm_name, &rg, every, keep)?;
                }
                azlin_cli::SnapshotAction::Disable { vm_name, .. } => {
                    crate::cmd_snapshot_ops2::handle_snapshot_disable(&vm_name)?;
                }
                azlin_cli::SnapshotAction::Sync { vm, .. } => {
                    crate::cmd_snapshot_ops2::handle_snapshot_sync(vm.as_deref(), &rg).await?;
                }
                azlin_cli::SnapshotAction::Status { vm_name, .. } => {
                    crate::cmd_snapshot_ops2::handle_snapshot_status(&vm_name)?;
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
