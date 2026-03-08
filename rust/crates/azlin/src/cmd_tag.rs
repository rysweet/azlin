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
        azlin_cli::Commands::Tag { action } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            match action {
                azlin_cli::TagAction::Add {
                    vm_name,
                    tags,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let parsed: Vec<(String, String)> = tags
                        .iter()
                        .map(|tag| match crate::tag_helpers::parse_tag(tag) {
                            Some((k, v)) => Ok((k.to_string(), v.to_string())),
                            None => anyhow::bail!("Invalid tag format '{}'. Use key=value.", tag),
                        })
                        .collect::<Result<Vec<_>>>()?;
                    let msgs =
                        crate::handlers::handle_tag_add(&vm_manager, &rg, &vm_name, &parsed)?;
                    for msg in msgs {
                        println!("{}", msg);
                    }
                }
                azlin_cli::TagAction::Remove {
                    vm_name,
                    tag_keys,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let msgs =
                        crate::handlers::handle_tag_remove(&vm_manager, &rg, &vm_name, &tag_keys)?;
                    for msg in msgs {
                        println!("{}", msg);
                    }
                }
                azlin_cli::TagAction::List {
                    vm_name,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let tags = crate::handlers::handle_tag_list(&vm_manager, &rg, &vm_name)?;
                    azlin_cli::table::render_tags_table(&vm_name, &tags);
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
