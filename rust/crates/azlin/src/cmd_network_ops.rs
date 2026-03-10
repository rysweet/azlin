#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) fn handle_disk_add(
    vm_name: &str,
    size: u32,
    sku: &str,
    resource_group: Option<String>,
    lun: Option<u32>,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    let disk_name = format!("{}_datadisk_{}", vm_name, lun.unwrap_or(0));

    let pb = penguin_spinner(&format!("Adding {} GB disk to {}...", size, vm_name));

    let output = std::process::Command::new("az")
        .args([
            "vm",
            "disk",
            "attach",
            "--resource-group",
            &rg,
            "--vm-name",
            vm_name,
            "--name",
            &disk_name,
            "--size-gb",
            &size.to_string(),
            "--sku",
            sku,
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
    Ok(())
}

pub(crate) fn handle_ip_check(
    vm_identifier: Option<String>,
    resource_group: Option<String>,
    port: u32,
) -> Result<()> {
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
    Ok(())
}

pub(crate) fn handle_web_start(port: u32, host: &str) -> Result<()> {
    let pwa_dir = std::env::current_dir()?.join("pwa");
    if !pwa_dir.exists() {
        anyhow::bail!(
            "PWA directory not found at {:?}. Make sure you're in the azlin project root.",
            pwa_dir
        );
    }

    let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
    let env_file = pwa_dir.join(".env.local");
    {
        let cfg = &config;
        let mut env_content = String::new();
        if let Some(ref rg) = cfg.default_resource_group {
            env_content.push_str(&format!("VITE_RESOURCE_GROUP={}\n", rg));
        }
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
    println!("Starting Azlin Mobile PWA on http://{}:{}", host, port);
    println!("Press Ctrl+C to stop the server");

    let pid_path = home_dir()?.join(".azlin").join("web.pid");
    if let Some(parent) = pid_path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let mut child = std::process::Command::new("npm")
        .args(["run", "dev", "--", "--port", &port_str, "--host", host])
        .current_dir(&pwa_dir)
        .spawn()?;

    std::fs::write(&pid_path, child.id().to_string())?;
    let status = child.wait()?;
    let _ = std::fs::remove_file(&pid_path);
    if !status.success() {
        std::process::exit(status.code().unwrap_or(1));
    }
    Ok(())
}

pub(crate) fn handle_web_stop() -> Result<()> {
    let pid_path = home_dir()?.join(".azlin").join("web.pid");
    if pid_path.exists() {
        let pid_str = std::fs::read_to_string(&pid_path)?;
        if let Ok(pid) = pid_str.trim().parse::<u32>() {
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
    Ok(())
}
