#[allow(unused_imports)]
use super::*;
use anyhow::Result;

#[allow(clippy::too_many_arguments)]
pub(crate) async fn handle_vm_new(
    repo: Option<String>,
    size: Option<azlin_cli::VmSizeTier>,
    vm_size: Option<String>,
    region: Option<String>,
    resource_group: Option<String>,
    name: Option<String>,
    pool: Option<u32>,
    no_auto_connect: bool,
    config: Option<std::path::PathBuf>,
    template: Option<String>,
    nfs_storage: Option<String>,
    _no_nfs: bool,
    no_bastion: bool,
    _no_tmux: bool,
    _tmux_session: Option<String>,
    bastion_name: Option<String>,
    private: bool,
    yes: bool,
    _home_disk_size: Option<u32>,
    _no_home_disk: bool,
    _tmp_disk_size: Option<u32>,
    _os: Option<String>,
) -> Result<()> {
    // Validate flag combinations early, before creating any resources
    if private && no_bastion {
        anyhow::bail!(
            "--private and --no-bastion cannot be used together: \
             a private VM has no public IP and requires bastion for SSH access"
        );
    }

    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;

    // Resolve VM size: --vm-size overrides --size tier, which overrides config default
    let vm_count = pool.unwrap_or(1);
    let config_defaults = if let Some(ref config_path) = config {
        match azlin_core::AzlinConfig::load_from(config_path) {
            Ok(c) => c,
            Err(e) => {
                eprintln!(
                    "Warning: failed to load config from {}: {e}",
                    config_path.display()
                );
                azlin_core::AzlinConfig::default()
            }
        }
    } else {
        match azlin_core::AzlinConfig::load() {
            Ok(c) => c,
            Err(e) => {
                eprintln!("Warning: failed to load config, using defaults: {e}");
                azlin_core::AzlinConfig::default()
            }
        }
    };
    let user_specified_size = vm_size.is_some() || size.is_some();
    let user_specified_region = region.is_some();

    // --vm-size takes priority, then --size tier mapping, then config default
    let size = if let Some(explicit) = vm_size {
        explicit
    } else if let Some(tier) = size {
        match tier {
            azlin_cli::VmSizeTier::S => "Standard_D2s_v3".to_string(),
            azlin_cli::VmSizeTier::M => "Standard_D16s_v3".to_string(),
            azlin_cli::VmSizeTier::L => "Standard_D32s_v3".to_string(),
            azlin_cli::VmSizeTier::Xl => "Standard_D64s_v3".to_string(),
        }
    } else {
        config_defaults.default_vm_size.clone()
    };
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
    let created_private_key =
        crate::create_helpers::matching_private_key_for_public_key(&ssh_key_path);

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
            format!("azlin-vm-{}", chrono::Utc::now().format("%Y%m%d-%H%M%S%6f"))
        };

        azlin_core::models::validate_vm_name(&vm_name).map_err(|e| anyhow::anyhow!(e))?;

        let mut tags = std::collections::HashMap::new();
        tags.insert(
            "azlin-session".to_string(),
            crate::create_helpers::resolve_session_identity(
                name.as_deref(),
                &vm_name,
                vm_count as usize,
            ),
        );

        let params = azlin_core::models::CreateVmParams {
            name: vm_name.clone(),
            resource_group: rg.clone(),
            region: final_loc.clone(),
            vm_size: final_size.clone(),
            admin_username: admin_user.clone(),
            ssh_key_path: ssh_key_path.clone(),
            image: azlin_core::models::VmImage::default(),
            tags,
            public_ip_enabled: !private,
            disk_ids: vec![],
        };

        if let Err(e) = params.validate() {
            anyhow::bail!("Invalid VM parameters: {}", e);
        }

        let pb = penguin_spinner(&format!("Creating VM '{}'...", vm_name));
        let vm = vm_manager.create_vm(&params)?;
        pb.finish_and_clear();

        println!("VM '{}' created successfully!", vm.name);

        if let Some(ref nfs) = nfs_storage {
            eprintln!("Warning: --nfs-storage '{}' accepted but NFS mounting is not yet implemented in the Rust CLI.", nfs);
        }

        let mut table = crate::table_render::SimpleTable::new(&["Property", "Value"], &[14, 40]);
        table.add_row(vec!["Name".to_string(), vm.name.clone()]);
        table.add_row(vec!["Resource Group".to_string(), rg.clone()]);
        table.add_row(vec!["Size".to_string(), final_size.clone()]);
        table.add_row(vec!["Region".to_string(), final_loc.clone()]);
        table.add_row(vec!["State".to_string(), vm.power_state.to_string()]);
        if let Some(ref ip) = vm.public_ip {
            table.add_row(vec!["Public IP".to_string(), ip.clone()]);
        }
        if let Some(ref ip) = vm.private_ip {
            table.add_row(vec!["Private IP".to_string(), ip.clone()]);
        }
        println!("{table}");

        // Resolve SSH target with bastion support
        let target = if no_bastion {
            // --no-bastion: skip bastion auto-detection, use public IP only
            let vm_ip = vm
                .public_ip
                .as_deref()
                .filter(|ip| !ip.is_empty())
                .ok_or_else(|| {
                    anyhow::anyhow!(
                        "VM '{}' has no public IP and --no-bastion was specified; \
                     remove --no-bastion to allow bastion auto-detection",
                        vm_name
                    )
                })?
                .to_string();
            crate::VmSshTarget {
                vm_name: vm_name.clone(),
                ip: vm_ip,
                user: admin_user.clone(),
                bastion: None,
            }
        } else {
            resolve_vm_ssh_target(&vm.name, None, Some(rg.clone())).await?
        };

        // Set up bastion tunnel if needed (kept alive for auth + clone + connect)
        // --bastion-name overrides auto-detected bastion
        let _tunnel = if let Some(ref bastion) = target.bastion {
            let effective_bastion_name = bastion_name.as_deref().unwrap_or(&bastion.bastion_name);
            Some(crate::bastion_tunnel::ScopedBastionTunnel::new(
                effective_bastion_name,
                &bastion.resource_group,
                &bastion.vm_resource_id,
            )?)
        } else {
            None
        };
        let bastion_port = _tunnel.as_ref().map(|t| t.local_port);
        let effective_ip = if bastion_port.is_some() {
            "127.0.0.1"
        } else {
            &target.ip
        };

        // Forward auth credentials to the new VM (best-effort)
        if let Err(e) = crate::auth_forward::forward_auth_credentials(
            effective_ip,
            &admin_user,
            yes,
            bastion_port,
        ) {
            eprintln!("Warning: auth forwarding failed: {}", e);
        }

        if crate::create_helpers::should_seed_remote_home(name.as_deref(), vm_count) {
            let home_sync_dir = home_dir()?.join(".azlin").join("home");
            let ssh_transport = crate::dispatch_helpers::build_routed_ssh_transport(
                &target,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                created_private_key.as_deref(),
            );
            println!("Seeding remote home from {}...", home_sync_dir.display());
            let seeded = crate::create_helpers::seed_remote_home_with_runner(
                &home_sync_dir,
                &target.user,
                effective_ip,
                Some(ssh_transport.as_str()),
                |args| {
                    let status = std::process::Command::new("rsync").args(args).status()?;
                    Ok(status.code().unwrap_or(-1))
                },
            )?;
            if seeded {
                println!("Remote home seeded.");
            } else {
                println!(
                    "No seed files found in {}; skipping remote home seeding.",
                    home_sync_dir.display()
                );
            }
        }

        if let Some(ref repo_url) = repo {
            let clone_cmd = match crate::create_helpers::build_clone_cmd(repo_url) {
                Ok(cmd) => cmd,
                Err(e) => {
                    eprintln!("Invalid repository URL: {}", e);
                    return Ok(());
                }
            };
            println!("Cloning repository '{}'...", repo_url);
            let (exit_code, stdout, stderr) = target.exec(&clone_cmd)?;
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

        if !no_auto_connect && vm_count == 1 {
            println!("Connecting to '{}'...", vm_name);
            let identity_key = created_private_key.as_deref().or_else(|| {
                target
                    .bastion
                    .as_ref()
                    .and_then(|bastion| bastion.ssh_key_path.as_deref())
            });
            let ssh_args = crate::create_helpers::build_auto_connect_ssh_args(
                &target.user,
                effective_ip,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                identity_key,
            );
            let status = std::process::Command::new("ssh").args(&ssh_args).status()?;
            if !status.success() {
                eprintln!("SSH connection ended with exit code: {:?}", status.code());
            }
        }
    }
    Ok(())
}
