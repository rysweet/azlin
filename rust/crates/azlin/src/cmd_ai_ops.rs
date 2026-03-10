#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) async fn handle_ask(
    query: Option<String>,
    resource_group: Option<String>,
    dry_run: bool,
) -> Result<()> {
    let query_text = query.ok_or_else(|| anyhow::anyhow!("No query provided."))?;

    if dry_run {
        println!("Would query Claude API with: {}", query_text);
        return Ok(());
    }

    let client = azlin_ai::AnthropicClient::new()?;
    let rg = match resource_group {
        Some(rg) => rg,
        None => {
            let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
            config.default_resource_group.ok_or_else(|| {
                anyhow::anyhow!(
                    "No resource group specified. Use --resource-group or set in config."
                )
            })?
        }
    };

    let context = format!("Resource group: {}", rg);
    let pb = penguin_spinner("Querying Claude...");
    let answer = client.ask(&query_text, &context).await?;
    pb.finish_and_clear();
    println!("{}", answer);
    Ok(())
}

pub(crate) async fn handle_do(
    request: &str,
    dry_run: bool,
    yes: bool,
    verbose: bool,
) -> Result<()> {
    let client = azlin_ai::AnthropicClient::new()?;

    let pb = penguin_spinner("Generating commands...");
    let commands = client.execute(request).await?;
    pb.finish_and_clear();

    if commands.is_empty() {
        println!("No commands generated.");
        return Ok(());
    }

    println!("Generated commands:");
    for (i, cmd) in commands.iter().enumerate() {
        println!("  {}. {}", i + 1, cmd);
    }

    if dry_run {
        return Ok(());
    }

    if !safe_confirm("Execute these commands?", yes)? {
        println!("Cancelled.");
        return Ok(());
    }

    for cmd in &commands {
        let cmd_str = cmd.trim();
        if cmd_str.is_empty() {
            continue;
        }
        if !cmd_str.starts_with("az ") {
            eprintln!("Skipping non-Azure command: {}", cmd_str);
            continue;
        }
        let parts = match shlex::split(cmd_str) {
            Some(p) if !p.is_empty() => p,
            _ => {
                eprintln!("Failed to parse command: {}", cmd_str);
                continue;
            }
        };
        if verbose {
            eprintln!("[verbose] Executing: {}", cmd_str);
        }
        println!("$ {}", cmd_str);
        let output = std::process::Command::new(&parts[0])
            .args(&parts[1..])
            .output()?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        if !stdout.is_empty() {
            print!("{}", stdout);
        }
        if verbose && !stderr.is_empty() {
            eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
        }
        if !output.status.success() {
            eprintln!("Command failed with exit code: {:?}", output.status.code());
            if !verbose && !stderr.is_empty() {
                eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
            }
        }
    }
    Ok(())
}

pub(crate) async fn handle_doit_deploy(request: &str, dry_run: bool, yes: bool) -> Result<()> {
    let client = azlin_ai::AnthropicClient::new()?;

    let system_context = "You are azlin, an Azure VM fleet management tool. \
        Generate a list of azlin CLI commands to accomplish the user's request.\n\
        Format: one command per line, each an 'az' CLI command.\n\
        Available operations: az vm list, az vm start, az vm stop, az vm create, \
        az vm delete, az group create, az network nsg create, etc.";

    let pb = penguin_spinner("Generating deployment plan...");
    let commands = client.ask(request, system_context).await?;
    pb.finish_and_clear();

    println!("Plan:\n{}\n", commands);

    if dry_run {
        return Ok(());
    }

    if !safe_confirm("Execute this plan?", yes)? {
        println!("Cancelled.");
        return Ok(());
    }

    for line in commands.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || !trimmed.starts_with("az ") {
            continue;
        }
        let parts = match shlex::split(trimmed) {
            Some(p) if !p.is_empty() => p,
            _ => {
                eprintln!("Failed to parse command: {}", trimmed);
                continue;
            }
        };
        println!("-> {}", trimmed);
        let status = std::process::Command::new(&parts[0])
            .args(&parts[1..])
            .status()?;
        if !status.success() {
            eprintln!("Command failed with exit code: {:?}", status.code());
        }
    }
    Ok(())
}
