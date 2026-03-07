#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn handle_runner_enable(
    repo: Option<String>,
    pool: String,
    count: u32,
    labels: Option<String>,
    resource_group: Option<String>,
    vm_size: Option<String>,
    runner_dir: &std::path::Path,
) -> Result<()> {
    let rg = resolve_resource_group(resource_group)?;
    if let Err(e) = crate::name_validation::validate_name(&pool) {
        anyhow::bail!("Invalid pool name: {}", e);
    }
    let repo_name = repo.unwrap_or_else(|| "<not set>".to_string());
    let label_str = labels.unwrap_or_else(|| "self-hosted".to_string());
    let size = vm_size.unwrap_or_else(|| "Standard_B2s".to_string());

    let mut config = toml::map::Map::new();
    config.insert("pool".to_string(), toml::Value::String(pool.clone()));
    config.insert("repo".to_string(), toml::Value::String(repo_name.clone()));
    config.insert("count".to_string(), toml::Value::Integer(count as i64));
    config.insert("labels".to_string(), toml::Value::String(label_str.clone()));
    config.insert(
        "resource_group".to_string(),
        toml::Value::String(rg.clone()),
    );
    config.insert("vm_size".to_string(), toml::Value::String(size.clone()));
    config.insert("enabled".to_string(), toml::Value::Boolean(true));
    config.insert(
        "created".to_string(),
        toml::Value::String(chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()),
    );
    let val = toml::Value::Table(config);
    let pool_path = runner_dir.join(format!("{}.toml", pool));
    std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;

    println!("Enabling GitHub runner fleet:");
    println!("  Repository:     {}", repo_name);
    println!("  Pool:           {}", pool);
    println!("  Count:          {}", count);
    println!("  Labels:         {}", label_str);
    println!("  VM Size:        {}", size);
    println!("  Resource Group: {}", rg);

    for i in 0..count {
        let vm_name = format!("azlin-runner-{}-{}", pool, i + 1);
        let pb = indicatif::ProgressBar::new_spinner();
        pb.set_message(format!("Provisioning {}...", vm_name));
        pb.enable_steady_tick(std::time::Duration::from_millis(100));
        let out = std::process::Command::new("az")
            .args([
                "vm",
                "create",
                "--resource-group",
                &rg,
                "--name",
                &vm_name,
                "--image",
                "Ubuntu2204",
                "--size",
                &size,
                "--admin-username",
                DEFAULT_ADMIN_USERNAME,
                "--generate-ssh-keys",
                "--tags",
                &format!("azlin-runner=true pool={} repo={}", pool, repo_name),
                "--output",
                "json",
            ])
            .output()?;
        pb.finish_and_clear();
        if out.status.success() {
            println!("  Provisioned VM '{}'", vm_name);
        } else {
            let stderr = String::from_utf8_lossy(&out.stderr);
            eprintln!(
                "  Failed to provision '{}': {}",
                vm_name,
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
        }
    }
    println!(
        "Runner fleet configuration saved to {}",
        pool_path.display()
    );
    println!("Note: To complete setup, install the GitHub Actions runner on each VM.");
    Ok(())
}

pub(crate) fn handle_runner_disable(
    pool: &str,
    keep_vms: bool,
    runner_dir: &std::path::Path,
) -> Result<()> {
    let pool_path = runner_dir.join(format!("{}.toml", pool));
    if pool_path.exists() {
        if !keep_vms {
            let rg_output = std::process::Command::new("az")
                .args([
                    "vm",
                    "list",
                    "--query",
                    &format!("[?tags.pool=='{}'].id", pool),
                    "--output",
                    "tsv",
                ])
                .output()?;
            if rg_output.status.success() {
                let ids = String::from_utf8_lossy(&rg_output.stdout);
                let id_list: Vec<&str> = ids.lines().filter(|l| !l.is_empty()).collect();
                if !id_list.is_empty() {
                    println!("Deleting {} runner VM(s)...", id_list.len());
                    let mut args = vec!["vm", "delete", "--yes", "--ids"];
                    args.extend(id_list.iter().copied());
                    let del_output = std::process::Command::new("az").args(&args).output()?;
                    if !del_output.status.success() {
                        eprintln!(
                            "Warning: VM deletion may have failed (exit {})",
                            del_output.status.code().unwrap_or(-1)
                        );
                    }
                }
            }
        } else {
            println!("VMs will be kept running.");
        }
        std::fs::remove_file(&pool_path)?;
        println!("Runner pool '{}' disabled.", pool);
    } else {
        println!("Runner pool '{}' not found.", pool);
    }
    Ok(())
}

pub(crate) fn handle_runner_status(pool: &str, runner_dir: &std::path::Path) -> Result<()> {
    let pool_path = runner_dir.join(format!("{}.toml", pool));
    if pool_path.exists() {
        let content = std::fs::read_to_string(&pool_path)?;
        let val: toml::Value = toml::from_str(&content)?;
        println!("Runner pool '{}':", pool);
        if let Some(t) = val.as_table() {
            for (k, v) in t {
                println!("  {}: {}", k, v);
            }
        }
        let output = std::process::Command::new("az")
            .args([
                "vm",
                "list",
                "--query",
                &format!("[?tags.pool=='{}'].{{name:name, state:powerState}}", pool),
                "--output",
                "table",
            ])
            .output()?;
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            if !text.trim().is_empty() {
                println!("\nRunner VMs:");
                print!("{}", text);
            }
        }
    } else {
        println!("Runner pool '{}': not configured", pool);
        println!(
            "Enable with: azlin github-runner enable --repo <owner/repo> --pool {}",
            pool
        );
    }
    Ok(())
}

pub(crate) fn handle_runner_scale(
    pool: &str,
    count: u32,
    runner_dir: &std::path::Path,
) -> Result<()> {
    let pool_path = runner_dir.join(format!("{}.toml", pool));
    if pool_path.exists() {
        let content = std::fs::read_to_string(&pool_path)?;
        let mut val: toml::Value = toml::from_str(&content)?;
        let old_count = val
            .as_table()
            .and_then(|t| t.get("count"))
            .and_then(|v| v.as_integer())
            .unwrap_or(0) as u32;
        if let Some(t) = val.as_table_mut() {
            t.insert("count".to_string(), toml::Value::Integer(count as i64));
        }
        std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;
        println!(
            "Scaled runner pool '{}': {} -> {} runners",
            pool, old_count, count
        );
        if count > old_count {
            println!("Note: Provision additional VMs with 'azlin github-runner enable'");
        }
    } else {
        println!("Runner pool '{}' not configured.", pool);
    }
    Ok(())
}
