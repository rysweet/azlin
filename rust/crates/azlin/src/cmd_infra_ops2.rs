#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use dialoguer::Confirm;

pub(crate) async fn handle_compose_action(
    subcommand: &str,
    file: Option<&std::path::Path>,
    resource_group: Option<String>,
) -> Result<()> {
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let f = file
        .map(|p| p.display().to_string())
        .unwrap_or_else(|| "docker-compose.yml".to_string());

    let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
    if vms.is_empty() {
        println!("No running VMs found in resource group '{}'", rg);
        return Ok(());
    }

    let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
    let cmd = crate::compose_helpers::build_compose_cmd(subcommand, &escaped_f);
    let label = if subcommand == "ps" {
        format!("Docker compose status on {} VM(s):", vms.len())
    } else {
        format!(
            "Running 'docker compose {}' on {} VM(s)...",
            subcommand,
            vms.len()
        )
    };
    println!("{}", label);
    run_on_fleet(&vms, &cmd, true);
    Ok(())
}

pub(crate) fn handle_template_create(
    azlin_dir: &std::path::Path,
    name: &str,
    description: Option<&str>,
    vm_size: Option<&str>,
    region: Option<&str>,
    cloud_init: Option<&std::path::Path>,
) -> Result<()> {
    let tpl = crate::templates::build_template_toml(
        name,
        description,
        vm_size,
        region,
        cloud_init.map(|p| p.display().to_string()).as_deref(),
    );
    let path = crate::templates::save_template(azlin_dir, name, &tpl)?;
    println!("Saved template '{}' at {}", name, path.display());
    Ok(())
}

pub(crate) fn handle_template_list(
    azlin_dir: &std::path::Path,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    let rows = crate::templates::list_templates(azlin_dir)?;
    if rows.is_empty() {
        println!("No templates found.");
    } else {
        azlin_cli::table::render_rows(&["Name", "VM Size", "Region"], &rows, output);
    }
    Ok(())
}

pub(crate) fn handle_template_show(azlin_dir: &std::path::Path, name: &str) -> Result<()> {
    match crate::templates::load_template(azlin_dir, name) {
        Ok(tpl) => println!("{}", toml::to_string_pretty(&tpl).unwrap_or_default()),
        Err(_) => {
            anyhow::bail!("Template '{}' not found.", name);
        }
    }
    Ok(())
}

pub(crate) fn handle_template_apply(azlin_dir: &std::path::Path, name: &str) -> Result<()> {
    match crate::templates::load_template(azlin_dir, name) {
        Ok(tpl) => {
            let vm_size = tpl
                .get("vm_size")
                .and_then(|v| v.as_str())
                .unwrap_or("Standard_D4s_v3");
            let region = tpl
                .get("region")
                .and_then(|v| v.as_str())
                .unwrap_or("westus2");
            println!(
                "To create a VM with template '{}', run:\n  azlin new my-vm --size {} --region {}",
                name, vm_size, region
            );
        }
        Err(_) => {
            anyhow::bail!("Template '{}' not found.", name);
        }
    }
    Ok(())
}

pub(crate) fn handle_template_delete(
    azlin_dir: &std::path::Path,
    name: &str,
    force: bool,
) -> Result<()> {
    if crate::templates::load_template(azlin_dir, name).is_err() {
        anyhow::bail!("Template '{}' not found.", name);
    }
    if !force {
        let ok = Confirm::new()
            .with_prompt(format!("Delete template '{}'?", name))
            .default(false)
            .interact()?;
        if !ok {
            println!("Cancelled.");
            return Ok(());
        }
    }
    crate::templates::delete_template(azlin_dir, name)?;
    println!("Deleted template '{}'", name);
    Ok(())
}

pub(crate) fn handle_template_export(
    azlin_dir: &std::path::Path,
    name: &str,
    output_file: &std::path::Path,
) -> Result<()> {
    let path = azlin_dir.join(format!("{}.toml", name));
    if !path.exists() {
        anyhow::bail!("Template '{}' not found.", name);
    }
    std::fs::copy(&path, output_file)?;
    println!("Exported template '{}' to {}", name, output_file.display());
    Ok(())
}

pub(crate) fn handle_template_import(
    azlin_dir: &std::path::Path,
    input_file: &std::path::Path,
) -> Result<()> {
    let content = std::fs::read_to_string(input_file)?;
    let name = crate::templates::import_template(azlin_dir, &content)?;
    println!("Imported template '{}' from {}", name, input_file.display());
    Ok(())
}
