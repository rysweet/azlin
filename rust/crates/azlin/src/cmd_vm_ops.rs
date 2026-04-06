#[allow(unused_imports)]
use super::*;
use anyhow::Result;

fn requires_post_create_ssh(
    repo_requested: bool,
    has_home_seed_sources: bool,
    auto_connect_requested: bool,
) -> bool {
    repo_requested || has_home_seed_sources || auto_connect_requested
}

fn resource_group_from_arm_id(resource_id: &str) -> Option<&str> {
    resource_id
        .split("/resourceGroups/")
        .nth(1)?
        .split('/')
        .next()
}

fn select_bastion_resource_group(
    bastions: &[serde_json::Value],
    bastion_name: &str,
) -> Result<Option<String>> {
    let matches: Vec<String> = bastions
        .iter()
        .filter(|b| b["name"].as_str() == Some(bastion_name))
        .filter_map(|b| {
            b["resourceGroup"]
                .as_str()
                .map(str::to_owned)
                .or_else(|| b["id"].as_str().and_then(resource_group_from_arm_id).map(str::to_owned))
        })
        .collect();

    match matches.as_slice() {
        [] => Ok(None),
        [resource_group] => Ok(Some(resource_group.clone())),
        _ => anyhow::bail!(
            "Azure Bastion '{}' is ambiguous across resource groups: {}",
            bastion_name,
            matches.join(", ")
        ),
    }
}

fn resolve_bastion_resource_group_by_name(bastion_name: &str) -> Result<Option<String>> {
    let output = std::process::Command::new("az")
        .args(["network", "bastion", "list", "--output", "json"])
        .output()?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to query Azure Bastion hosts: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    let bastions: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)?;
    select_bastion_resource_group(&bastions, bastion_name)
}

fn apply_bastion_name_override(
    target: &mut crate::VmSshTarget,
    bastion_name: Option<&str>,
    bastion_resource_group: Option<&str>,
    resource_group: &str,
    subscription_id: &str,
    vm_name: &str,
    needs_bastion_route: bool,
) {
    let Some(override_name) = bastion_name else {
        return;
    };
    let override_resource_group = bastion_resource_group.unwrap_or(resource_group);

    if let Some(bastion) = &mut target.bastion {
        bastion.bastion_name = override_name.to_string();
        bastion.resource_group = override_resource_group.to_string();
        return;
    }

    if needs_bastion_route {
        target.bastion = Some(crate::BastionRoute {
            bastion_name: override_name.to_string(),
            resource_group: override_resource_group.to_string(),
            vm_resource_id: crate::ssh_arg_helpers::build_vm_resource_id(
                subscription_id,
                resource_group,
                vm_name,
            ),
            ssh_key_path: target.ssh_key_path.clone(),
        });
    }
}

fn apply_post_create_ssh_identity(
    target: &mut crate::VmSshTarget,
    created_private_key: Option<&std::path::Path>,
) {
    let Some(created_private_key) = created_private_key else {
        return;
    };
    let key_path = created_private_key.to_path_buf();
    target.ssh_key_path = Some(key_path.clone());
    if let Some(ref mut bastion) = target.bastion {
        bastion.ssh_key_path = Some(key_path);
    }
}

#[allow(clippy::too_many_arguments)]
fn prepare_post_create_target(
    target: &mut crate::VmSshTarget,
    created_private_key: Option<&std::path::Path>,
    bastion_name: Option<&str>,
    bastion_resource_group: Option<&str>,
    resource_group: &str,
    subscription_id: &str,
    vm_name: &str,
    needs_bastion_route: bool,
) {
    apply_post_create_ssh_identity(target, created_private_key);
    apply_bastion_name_override(
        target,
        bastion_name,
        bastion_resource_group,
        resource_group,
        subscription_id,
        vm_name,
        needs_bastion_route,
    );
}

fn post_create_bastion_route(target: &crate::VmSshTarget) -> Option<(&str, &str, &str)> {
    let bastion = target.bastion.as_ref()?;
    Some((
        bastion.bastion_name.as_str(),
        bastion.resource_group.as_str(),
        bastion.vm_resource_id.as_str(),
    ))
}

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
        crate::key_helpers::find_preferred_pubkey(&ssh_dir).ok_or_else(|| {
            anyhow::anyhow!(
                "No SSH public key found in ~/.ssh. Expected one of: {}",
                crate::key_helpers::preferred_pubkey_names().join(", ")
            )
        })?
    };
    let should_seed_home =
        crate::create_helpers::should_seed_remote_home(name.as_deref(), vm_count);
    let has_home_seed_sources = if should_seed_home {
        let home_sync_dir = home_dir()?.join(".azlin").join("home");
        crate::create_helpers::collect_home_seed_sources(&home_sync_dir)?.is_some()
    } else {
        false
    };
    let auto_connect_requested = !no_auto_connect && vm_count == 1;
    let interactive_post_create_ssh = std::io::stdin().is_terminal();
    let requires_created_private_key = requires_post_create_ssh(
        repo.is_some(),
        has_home_seed_sources,
        auto_connect_requested,
    );
    let created_private_key = if requires_created_private_key {
        Some(crate::create_helpers::require_matching_private_key_for_public_key(&ssh_key_path)?)
    } else {
        crate::create_helpers::matching_private_key_for_public_key(&ssh_key_path)
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
            eprintln!(
                "Warning: --nfs-storage '{}' accepted but NFS mounting is not yet implemented in the Rust CLI.",
                nfs
            );
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

        let created_private_key = match created_private_key.as_ref() {
            Some(key) => key,
            None => {
                println!(
                    "Provisioning used '{}' but matching private key '{}' is unavailable locally; skipping post-create SSH actions.",
                    ssh_key_path.display(),
                    ssh_key_path.with_extension("").display()
                );
                continue;
            }
        };

        // Resolve SSH target with bastion support
        let mut target = if no_bastion {
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
                ssh_key_path: Some(created_private_key.clone()),
                allow_preferred_key_fallback: true,
                bastion: None,
            }
        } else {
            resolve_vm_ssh_target(&vm.name, None, Some(rg.clone())).await?
        };
        let needs_bastion_route = crate::ssh_arg_helpers::needs_bastion(vm.public_ip.as_deref());
        let resolved_bastion_resource_group = if let Some(override_name) = bastion_name.as_deref() {
            if target.bastion.is_some() || needs_bastion_route {
                Some(
                    resolve_bastion_resource_group_by_name(override_name)?.ok_or_else(|| {
                        anyhow::anyhow!(
                            "Azure Bastion '{}' was not found in the current subscription",
                            override_name
                        )
                    })?,
                )
            } else {
                None
            }
        } else {
            None
        };
        prepare_post_create_target(
            &mut target,
            Some(created_private_key.as_path()),
            bastion_name.as_deref(),
            resolved_bastion_resource_group.as_deref(),
            &rg,
            vm_manager.subscription_id(),
            &vm.name,
            needs_bastion_route,
        );

        // Set up bastion tunnel if needed (kept alive for auth + clone + connect)
        // --bastion-name overrides auto-detected bastion
        let _tunnel = if let Some((bastion_name, resource_group, vm_resource_id)) =
            post_create_bastion_route(&target)
        {
            Some(crate::bastion_tunnel::ScopedBastionTunnel::new(
                bastion_name,
                resource_group,
                vm_resource_id,
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
            Some(created_private_key.as_path()),
            interactive_post_create_ssh,
        ) {
            eprintln!("Warning: auth forwarding failed: {}", e);
        }

        if should_seed_home {
            let home_sync_dir = home_dir()?.join(".azlin").join("home");
            let ssh_transport = crate::dispatch_helpers::build_routed_ssh_transport_with_mode(
                &target,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                Some(created_private_key.as_path()),
                !interactive_post_create_ssh,
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
            let mut ssh_args = crate::create_helpers::build_post_create_ssh_args(
                &target.user,
                effective_ip,
                bastion_port,
                config_defaults.ssh_connect_timeout,
                Some(created_private_key.as_path()),
                !interactive_post_create_ssh,
            );
            ssh_args.push(clone_cmd.clone());
            let (exit_code, stdout, stderr) = if interactive_post_create_ssh {
                let status = std::process::Command::new("ssh")
                    .args(&ssh_args)
                    .stdin(std::process::Stdio::inherit())
                    .stdout(std::process::Stdio::inherit())
                    .stderr(std::process::Stdio::inherit())
                    .status()?;
                (status.code().unwrap_or(-1), String::new(), String::new())
            } else {
                let output = std::process::Command::new("ssh").args(&ssh_args).output()?;
                (
                    output.status.code().unwrap_or(-1),
                    String::from_utf8_lossy(&output.stdout).to_string(),
                    String::from_utf8_lossy(&output.stderr).to_string(),
                )
            };
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
            let identity_key = target.ssh_key_path.as_deref().or_else(|| {
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

#[cfg(test)]
mod tests {
    #[test]
    fn test_apply_bastion_name_override_updates_target_route() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard".to_string(),
                ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            }),
        };

        super::apply_bastion_name_override(
            &mut target,
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        assert_eq!(
            target.bastion.as_ref().map(|b| b.bastion_name.as_str()),
            Some("override-bastion")
        );
        assert_eq!(
            target.bastion.as_ref().map(|b| b.resource_group.as_str()),
            Some("network-rg")
        );
    }

    #[test]
    fn test_apply_bastion_name_override_ignores_missing_override() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id: "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard".to_string(),
                ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            }),
        };

        super::apply_bastion_name_override(&mut target, None, None, "rg", "sub", "simard", true);

        assert_eq!(
            target.bastion.as_ref().map(|b| b.bastion_name.as_str()),
            Some("auto-detected")
        );
    }

    #[test]
    fn test_apply_bastion_name_override_creates_private_route_when_missing() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: Some(std::path::PathBuf::from("/tmp/key")),
            allow_preferred_key_fallback: true,
            bastion: None,
        };

        super::apply_bastion_name_override(
            &mut target,
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        let bastion = target.bastion.as_ref().unwrap();
        assert_eq!(bastion.bastion_name, "override-bastion");
        assert_eq!(bastion.resource_group, "network-rg");
        assert_eq!(
            bastion.ssh_key_path.as_deref(),
            Some(std::path::Path::new("/tmp/key"))
        );
        assert_eq!(
            bastion.vm_resource_id,
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard"
        );
    }

    #[test]
    fn test_prepare_post_create_target_reuses_key_and_override_for_bastion() {
        let mut target = crate::VmSshTarget {
            vm_name: "simard".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "azureuser".to_string(),
            ssh_key_path: None,
            allow_preferred_key_fallback: true,
            bastion: Some(crate::BastionRoute {
                bastion_name: "auto-detected".to_string(),
                resource_group: "rg".to_string(),
                vm_resource_id:
                    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard"
                        .to_string(),
                ssh_key_path: None,
            }),
        };

        let created_key = std::path::Path::new("/tmp/created-key");
        super::prepare_post_create_target(
            &mut target,
            Some(created_key),
            Some("override-bastion"),
            Some("network-rg"),
            "rg",
            "sub",
            "simard",
            true,
        );

        assert_eq!(target.ssh_key_path.as_deref(), Some(created_key));
        let bastion = target.bastion.as_ref().unwrap();
        assert_eq!(bastion.bastion_name, "override-bastion");
        assert_eq!(bastion.resource_group, "network-rg");
        assert_eq!(bastion.ssh_key_path.as_deref(), Some(created_key));
        assert_eq!(
            super::post_create_bastion_route(&target),
            Some((
                "override-bastion",
                "network-rg",
                "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/simard",
            ))
        );
    }

    #[test]
    fn test_select_bastion_resource_group_matches_by_name() {
        let bastions = vec![serde_json::json!({
            "name": "corp-bastion",
            "resourceGroup": "network-rg"
        })];
        assert_eq!(
            super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap(),
            Some("network-rg".to_string())
        );
    }

    #[test]
    fn test_select_bastion_resource_group_uses_arm_id_fallback() {
        let bastions = vec![serde_json::json!({
            "name": "corp-bastion",
            "id": "/subscriptions/sub/resourceGroups/network-rg/providers/Microsoft.Network/bastionHosts/corp-bastion"
        })];
        assert_eq!(
            super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap(),
            Some("network-rg".to_string())
        );
    }

    #[test]
    fn test_select_bastion_resource_group_rejects_ambiguous_matches() {
        let bastions = vec![
            serde_json::json!({"name": "corp-bastion", "resourceGroup": "network-rg-1"}),
            serde_json::json!({"name": "corp-bastion", "resourceGroup": "network-rg-2"}),
        ];
        let err = super::select_bastion_resource_group(&bastions, "corp-bastion").unwrap_err();
        assert!(err.to_string().contains("ambiguous"));
    }

    #[test]
    fn test_requires_post_create_ssh_is_false_for_create_only() {
        assert!(!super::requires_post_create_ssh(false, false, false));
    }

    #[test]
    fn test_requires_post_create_ssh_is_true_for_repo_seed_or_auto_connect() {
        assert!(super::requires_post_create_ssh(true, false, false));
        assert!(super::requires_post_create_ssh(false, true, false));
        assert!(super::requires_post_create_ssh(false, false, true));
    }
}
