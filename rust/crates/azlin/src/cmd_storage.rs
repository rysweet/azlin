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
        azlin_cli::Commands::Storage { action } => match action {
            azlin_cli::StorageAction::Create {
                name,
                size,
                tier,
                resource_group,
                region,
            } => {
                crate::cmd_storage_ops::handle_storage_create(
                    &name,
                    size,
                    &tier,
                    resource_group,
                    region,
                )
                .await?;
            }
            azlin_cli::StorageAction::List { resource_group } => {
                crate::cmd_storage_ops::handle_storage_list(resource_group)?;
            }
            azlin_cli::StorageAction::Status {
                name,
                resource_group,
            } => {
                crate::cmd_storage_ops::handle_storage_status(&name, resource_group)?;
            }
            azlin_cli::StorageAction::Mount {
                storage_name,
                vm,
                mount_point,
                resource_group,
            } => {
                crate::cmd_storage_ops::handle_storage_mount(
                    &storage_name,
                    &vm,
                    mount_point,
                    resource_group,
                )
                .await?;
            }
            azlin_cli::StorageAction::Unmount { vm, resource_group } => {
                crate::cmd_storage_ops::handle_storage_unmount(&vm, resource_group).await?;
            }
            azlin_cli::StorageAction::Delete {
                name,
                resource_group,
                force,
            } => {
                crate::cmd_storage_ops2::handle_storage_delete(&name, resource_group, force)?;
            }
            azlin_cli::StorageAction::MountFile {
                account,
                share,
                mount_point,
                resource_group,
            } => {
                crate::cmd_storage_ops2::handle_storage_mount_file(
                    &account,
                    &share,
                    mount_point,
                    resource_group,
                )?;
            }
            azlin_cli::StorageAction::UnmountFile { mount_point } => {
                crate::cmd_storage_ops2::handle_storage_unmount_file(mount_point)?;
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
