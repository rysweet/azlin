#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn handle_vm_new(
    repo: Option<String>,
    vm_size: Option<String>,
    region: Option<String>,
    resource_group: Option<String>,
    name: Option<String>,
    pool: Option<u32>,
    no_auto_connect: bool,
    template: Option<String>,
) -> Result<()> {
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;

    let vm_count = pool.unwrap_or(1);
    let config_defaults = azlin_core::AzlinConfig::load().unwrap_or_default();
    let user_specified_size = vm_size.is_some();
    let user_specified_region = region.is_some();
    let size = vm_size.unwrap_or_else(|| config_defaults.default_vm_size.clone());
    let loc = region.unwrap_or_else(|| config_defaults.default_region.clone());
    let admin_user = DEFAULT_ADMIN_USERNAME.to_string();
    let ssh_key_path = {
        let ssh_dir = dirs::home_dir().unwrap_or_default().join(".ssh");
        [
            "azlin_key.pub",
            "id_ed25519_azlin.pub",
            "id_ed25519.pub",
            "id_rsa.pub",
        ]
        .iter()
        .map(|f| ssh_dir.join(f))
        .find(|p| p.exists())
        .unwrap_or_else(|| ssh_dir.join("id_rsa.pub"))
    };

    let (tmpl_size, tmpl_region) = if let Some(ref tmpl_name) = template {
        if let Err(e) = crate::name_validation::validate_name(tmpl_name) {
            anyhow::bail!("Invalid template name: {}", e);
        }
        let templates_dir = dirs::home_dir()
            .unwrap_or_default()
            .join(".config")
            .join("azlin")
            .join("templates");
        let tmpl_path = templates_dir.join(format!("{}.toml", tmpl_name));
        if tmpl_path.exists() {
            let content = std::fs::read_to_string(&tmpl_path)?;
            let tmpl: toml::Value = content.parse()?;
            let ts = tmpl
                .get("vm_size")
                .and_then(|v| v.as_str())
                .map(String::from);
            let tr = tmpl
                .get("region")
                .and_then(|v| v.as_str())
                .map(String::from);
            (ts, tr)
        } else {
            eprintln!(
                "Template '{}' not found at {}",
                tmpl_name,
                tmpl_path.display()
            );
            (None, None)
        }
    } else {
        (None, None)
    };

    let final_size = if !user_specified_size {
        tmpl_size.unwrap_or(size)
    } else {
        size
    };
    let final_loc = if !user_specified_region {
        tmpl_region.unwrap_or(loc)
    } else {
        loc
    };

    for i in 0..vm_count {
        let vm_name = if let Some(ref n) = name {
            if vm_count > 1 {
                format!("{}-{}", n, i + 1)
            } else {
                n.clone()
            }
        } else {
            format!("azlin-vm-{}", chrono::Utc::now().format("%Y%m%d-%H%M%S"))
        };

        azlin_core::models::validate_vm_name(&vm_name).map_err(|e| anyhow::anyhow!(e))?;

        let params = azlin_core::models::CreateVmParams {
            name: vm_name.clone(),
            resource_group: rg.clone(),
            region: final_loc.clone(),
            vm_size: final_size.clone(),
            admin_username: admin_user.clone(),
            ssh_key_path: ssh_key_path.clone(),
            image: azlin_core::models::VmImage::default(),
            tags: std::collections::HashMap::new(),
        };

        if let Err(e) = params.validate() {
            anyhow::bail!("Invalid VM parameters: {}", e);
        }

        let pb = indicatif::ProgressBar::new_spinner();
        pb.set_message(format!("Creating VM '{}'...", vm_name));
        pb.enable_steady_tick(std::time::Duration::from_millis(100));
        let vm = vm_manager.create_vm(&params)?;
        pb.finish_and_clear();

        println!("VM '{}' created successfully!", vm.name);

        let mut table = Table::new();
        table
            .load_preset(UTF8_FULL)
            .apply_modifier(UTF8_ROUND_CORNERS);
        table.set_header(vec!["Property", "Value"]);
        table.add_row(vec!["Name", &vm.name]);
        table.add_row(vec!["Resource Group", &rg]);
        table.add_row(vec!["Size", &final_size]);
        table.add_row(vec!["Region", &final_loc]);
        table.add_row(vec!["State", &vm.power_state.to_string()]);
        if let Some(ref ip) = vm.public_ip {
            table.add_row(vec!["Public IP", ip]);
        }
        if let Some(ref ip) = vm.private_ip {
            table.add_row(vec!["Private IP", ip]);
        }
        println!("{table}");

        if let Some(ref repo_url) = repo {
            if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                let clone_cmd = match crate::create_helpers::build_clone_cmd(repo_url) {
                    Ok(cmd) => cmd,
                    Err(e) => {
                        eprintln!("Invalid repository URL: {}", e);
                        return Ok(());
                    }
                };
                println!("Cloning repository '{}'...", repo_url);
                let (exit_code, stdout, stderr) = ssh_exec(ip, &admin_user, &clone_cmd)?;
                if exit_code == 0 {
                    println!("Repository cloned successfully.");
                    if !stdout.is_empty() {
                        print!("{}", stdout);
                    }
                } else {
                    eprintln!(
                        "Failed to clone repository: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        }

        if !no_auto_connect && vm_count == 1 {
            if let Some(ref ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                println!("Connecting to '{}'...", vm_name);
                let status = std::process::Command::new("ssh")
                    .args([
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        &format!("{}@{}", admin_user, ip),
                    ])
                    .status()?;
                if !status.success() {
                    eprintln!("SSH connection ended with exit code: {:?}", status.code());
                }
            }
        }
    }
    Ok(())
}
