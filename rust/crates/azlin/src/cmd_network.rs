#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

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
                let rg = resolve_resource_group(resource_group)?;
                let disk_name = format!("{}_datadisk_{}", vm_name, lun.unwrap_or(0));

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Adding {} GB disk to {}...", size, vm_name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let output = std::process::Command::new("az")
                    .args([
                        "vm",
                        "disk",
                        "attach",
                        "--resource-group",
                        &rg,
                        "--vm-name",
                        &vm_name,
                        "--name",
                        &disk_name,
                        "--size-gb",
                        &size.to_string(),
                        "--sku",
                        &sku,
                        "--new",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!(
                        "Attached {} GB disk '{}' to VM '{}'",
                        size, disk_name, vm_name
                    );
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to attach disk: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        },

        // ── IP ───────────────────────────────────────────────────────
        azlin_cli::Commands::Ip { action } => match action {
            azlin_cli::IpAction::Check {
                vm_identifier,
                resource_group,
                port,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if let Some(name) = vm_identifier {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, &name)?;

                    let ip = vm.public_ip.or(vm.private_ip);
                    match ip {
                        Some(addr) => {
                            println!("VM '{}': {}", name, addr);
                            let addr_port = format!("{}:{}", addr, port);
                            match addr_port.parse::<std::net::SocketAddr>() {
                                Ok(sock_addr) => {
                                    match std::net::TcpStream::connect_timeout(
                                        &sock_addr,
                                        std::time::Duration::from_secs(5),
                                    ) {
                                        Ok(_) => println!("  Port {} on {} is OPEN", port, addr),
                                        Err(_) => println!("  Port {} on {} is CLOSED", port, addr),
                                    }
                                }
                                Err(e) => eprintln!("  Invalid address '{}': {}", addr_port, e),
                            }
                        }
                        None => println!("VM '{}': no IP address found", name),
                    }
                } else {
                    println!(
                        "Specify a VM name or use --all to check all VMs in '{}'",
                        rg
                    );
                }
            }
        },

        // ── Web ──────────────────────────────────────────────────────
        azlin_cli::Commands::Web { action } => match action {
            azlin_cli::WebAction::Start { port, host } => {
                // Start the PWA dev server (same as Python: npm run dev in pwa/)
                let pwa_dir = std::env::current_dir()?.join("pwa");
                if !pwa_dir.exists() {
                    anyhow::bail!(
                        "PWA directory not found at {:?}. Make sure you're in the azlin project root.",
                        pwa_dir
                    );
                }

                // Generate env config from azlin context
                let config =
                    azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
                let env_file = pwa_dir.join(".env.local");
                {
                    let cfg = &config;
                    let mut env_content = String::new();
                    if let Some(ref rg) = cfg.default_resource_group {
                        env_content.push_str(&format!("VITE_RESOURCE_GROUP={}\n", rg));
                    }
                    // Get subscription from az CLI
                    let sub_output = std::process::Command::new("az")
                        .args(["account", "show", "--query", "id", "-o", "tsv"])
                        .output();
                    if let Ok(out) = sub_output {
                        let sub = String::from_utf8_lossy(&out.stdout).trim().to_string();
                        if !sub.is_empty() {
                            env_content.push_str(&format!("VITE_SUBSCRIPTION_ID={}\n", sub));
                        }
                    }
                    if !env_content.is_empty() {
                        std::fs::write(&env_file, &env_content)?;
                    }
                }

                let port_str = port.to_string();
                println!("🏴‍☠️ Starting Azlin Mobile PWA on http://{}:{}", host, port);
                println!("Press Ctrl+C to stop the server");

                // Write PID file for web stop
                let pid_path = home_dir()?.join(".azlin").join("web.pid");
                if let Some(parent) = pid_path.parent() {
                    std::fs::create_dir_all(parent)?;
                }

                let mut child = std::process::Command::new("npm")
                    .args(["run", "dev", "--", "--port", &port_str, "--host", &host])
                    .current_dir(&pwa_dir)
                    .spawn()?;

                std::fs::write(&pid_path, child.id().to_string())?;
                let status = child.wait()?;
                // Clean up PID file
                let _ = std::fs::remove_file(&pid_path);
                if !status.success() {
                    std::process::exit(status.code().unwrap_or(1));
                }
            }
            azlin_cli::WebAction::Stop => {
                // Check for a running web dashboard pid file
                let pid_path = home_dir()?.join(".azlin").join("web.pid");
                if pid_path.exists() {
                    let pid_str = std::fs::read_to_string(&pid_path)?;
                    if let Ok(pid) = pid_str.trim().parse::<u32>() {
                        // Check if process is running
                        let check = std::process::Command::new("kill")
                            .args(["-0", &pid.to_string()])
                            .output()?;
                        if check.status.success() {
                            let _ = std::process::Command::new("kill")
                                .arg(pid.to_string())
                                .output()?;
                            println!("Stopped web dashboard (PID {}).", pid);
                        } else {
                            println!("Web dashboard process {} not found.", pid);
                        }
                    }
                    let _ = std::fs::remove_file(&pid_path);
                } else {
                    println!("No web dashboard running. Start one with: azlin web start");
                }
            }
        },

        // ── Restore ──────────────────────────────────────────────────
        azlin_cli::Commands::Bastion { action } => match action {
            azlin_cli::BastionAction::List { resource_group } => {
                println!("Listing Bastion hosts...");
                let mut cmd = std::process::Command::new("az");
                cmd.args(["network", "bastion", "list", "-o", "json"]);
                if let Some(rg) = &resource_group {
                    cmd.args(["--resource-group", rg]);
                }
                let output = cmd.output()?;
                if !output.status.success() {
                    let err = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Error listing Bastion hosts: {}",
                        azlin_core::sanitizer::sanitize(&err)
                    );
                }
                let bastions: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)
                    .context("Failed to parse Bastion host list JSON")?;
                if bastions.is_empty() {
                    if let Some(rg) = &resource_group {
                        println!("No Bastion hosts found in resource group: {}", rg);
                    } else {
                        println!("No Bastion hosts found in subscription");
                    }
                } else {
                    println!("\nFound {} Bastion host(s):\n", bastions.len());
                    for b in &bastions {
                        let (name, rg, location, sku, state) =
                            crate::bastion_helpers::bastion_summary(b);
                        println!("  {}", name);
                        println!("    Resource Group: {}", rg);
                        println!("    Location: {}", location);
                        println!("    SKU: {}", sku);
                        println!("    State: {}", state);
                        println!();
                    }
                }
            }
            azlin_cli::BastionAction::Status {
                name,
                resource_group,
            } => {
                println!("Checking Bastion host: {}...", name);
                let output = std::process::Command::new("az")
                    .args([
                        "network",
                        "bastion",
                        "show",
                        "--name",
                        &name,
                        "--resource-group",
                        &resource_group,
                        "-o",
                        "json",
                    ])
                    .output()?;
                if !output.status.success() {
                    let err = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Bastion host not found: {} in {}: {}",
                        name,
                        resource_group,
                        azlin_core::sanitizer::sanitize(&err)
                    );
                }
                let b: serde_json::Value = serde_json::from_slice(&output.stdout)?;
                println!(
                    "\nBastion Host: {}",
                    b["name"].as_str().unwrap_or("unknown")
                );
                println!(
                    "Resource Group: {}",
                    b["resourceGroup"].as_str().unwrap_or("unknown")
                );
                println!("Location: {}", b["location"].as_str().unwrap_or("unknown"));
                println!("SKU: {}", b["sku"]["name"].as_str().unwrap_or("Standard"));
                println!(
                    "Provisioning State: {}",
                    b["provisioningState"].as_str().unwrap_or("Unknown")
                );
                println!("DNS Name: {}", b["dnsName"].as_str().unwrap_or("N/A"));
                let ip_config_list = crate::bastion_helpers::extract_ip_configs(&b);
                if !ip_config_list.is_empty() {
                    println!("\nIP Configurations: {}", ip_config_list.len());
                    for (idx, (subnet_short, pip_short)) in ip_config_list.iter().enumerate() {
                        println!("  [{}] Subnet: {}", idx + 1, subnet_short);
                        println!("      Public IP: {}", pip_short);
                    }
                }
            }
            azlin_cli::BastionAction::Configure {
                vm_name,
                bastion_name,
                resource_group,
                bastion_resource_group,
                disable,
            } => {
                let vm_rg = resolve_resource_group(resource_group)?;
                let bastion_rg = bastion_resource_group.unwrap_or_else(|| vm_rg.clone());

                let config_dir = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&config_dir)?;
                let config_path = config_dir.join("bastion_config.json");

                let mut config: serde_json::Value = if config_path.exists() {
                    let data = std::fs::read_to_string(&config_path)?;
                    serde_json::from_str(&data).unwrap_or(serde_json::json!({"mappings": {}}))
                } else {
                    serde_json::json!({"mappings": {}})
                };

                let mappings = config["mappings"]
                    .as_object_mut()
                    .ok_or_else(|| anyhow::anyhow!("Invalid bastion config format"))?;

                if disable {
                    mappings.remove(&vm_name);
                    std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
                    println!("✓ Disabled Bastion mapping for: {}", vm_name);
                } else {
                    mappings.insert(
                        vm_name.clone(),
                        serde_json::json!({
                            "bastion_name": bastion_name,
                            "vm_resource_group": vm_rg,
                            "bastion_resource_group": bastion_rg,
                        }),
                    );
                    std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
                    println!("✓ Configured {} to use Bastion: {}", vm_name, bastion_name);
                    println!("  VM RG: {}", vm_rg);
                    println!("  Bastion RG: {}", bastion_rg);
                    println!("\nConnection will now route through Bastion automatically.");
                }
            }
        },

        _ => unreachable!(),
    }
    Ok(())
}
