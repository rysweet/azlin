use std::io::IsTerminal;

use anyhow::Result;
use clap::Parser;

/// Execute natural language Azure commands using AI (standalone CLI).
///
/// azdoit uses AI to iteratively pursue Azure infrastructure objectives.
///
/// Quick Start:
///   1. Set API key: export ANTHROPIC_API_KEY=your-key-here
///   2. Try: azdoit "create a VM called dev-box"
#[derive(Parser)]
#[command(name = "azdoit", version = "2.3.0")]
struct Args {
    /// Natural language request describing what to do
    request: Vec<String>,

    /// Maximum number of AI turns
    #[arg(long, default_value = "10")]
    max_turns: u32,

    /// Show plan without executing
    #[arg(long)]
    dry_run: bool,

    /// Skip confirmation prompts
    #[arg(short, long)]
    yes: bool,

    /// Enable verbose output
    #[arg(short, long)]
    verbose: bool,
}

/// Command safety classification result.
#[derive(Debug, PartialEq)]
enum CommandSafety {
    /// Command passes allowlist and is not dangerous.
    Allowed,
    /// Command does not match any allowed prefix.
    Disallowed,
    /// Command matches allowlist but contains a dangerous pattern.
    Dangerous,
}

/// Allowed command prefixes.
const ALLOWED_PREFIXES: &[&str] = &["az ", "echo ", "azlin "];

/// Patterns in `az` commands that are blocked for safety.
const DANGEROUS_PATTERNS: &[&str] = &[
    "run-command",
    "extension set",
    "extension delete",
    "vm user",
    "vm secret",
    "az rest",
    "deployment create",
    "deployment group create",
    "resource create",
    "role assignment create",
    "ad app",
    "ad sp",
    "keyvault secret set",
    "storage account keys",
];

/// Classify a command string for safety.
fn classify_command(cmd: &str) -> CommandSafety {
    let trimmed = cmd.trim();
    let is_allowed = ALLOWED_PREFIXES.iter().any(|p| trimmed.starts_with(p));
    if !is_allowed {
        return CommandSafety::Disallowed;
    }
    if trimmed.starts_with("az ") && DANGEROUS_PATTERNS.iter().any(|d| trimmed.contains(d)) {
        return CommandSafety::Dangerous;
    }
    CommandSafety::Allowed
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    if args.verbose {
        tracing_subscriber::fmt().with_env_filter("debug").init();
    }

    let request = args.request.join(" ");
    if request.is_empty() {
        anyhow::bail!("No request provided. Usage: azdoit \"create a VM called dev-box\"");
    }

    let client = azlin_ai::AnthropicClient::new()
        .map_err(|e| anyhow::anyhow!("AI client error: {}. Set ANTHROPIC_API_KEY.", e))?;

    let system_prompt = format!(
        "You are azdoit, an Azure infrastructure automation tool. \
        The user wants to: {}\n\
        Generate a sequence of Azure CLI (az) commands to accomplish this.\n\
        Format each command on its own line, prefixed with '$ '.\n\
        Include brief explanations before each command.\n\
        Maximum {} steps.",
        request, args.max_turns
    );

    println!("azdoit -- Planning: {}", request);
    println!();

    let response = client.ask(&system_prompt, &request).await?;

    if args.dry_run {
        println!("Plan (dry-run, not executing):\n");
        println!("{}", response);
        return Ok(());
    }

    println!("{}\n", response);

    let commands: Vec<&str> = response
        .lines()
        .filter(|l| l.trim().starts_with("$ "))
        .map(|l| l.trim().strip_prefix("$ ").unwrap_or(l.trim()))
        .collect();

    if commands.is_empty() {
        println!("No executable commands found in the plan.");
        return Ok(());
    }

    if !args.yes {
        if !std::io::stdin().is_terminal() {
            anyhow::bail!(
                "Confirmation required but stdin is not a terminal. \
                 Use --yes to skip."
            );
        }
        if !dialoguer::Confirm::new()
            .with_prompt(format!("Execute {} command(s)?", commands.len()))
            .default(false)
            .interact()?
        {
            println!("Cancelled.");
            return Ok(());
        }
    }

    for (i, cmd) in commands.iter().enumerate() {
        let trimmed = cmd.trim();
        match classify_command(trimmed) {
            CommandSafety::Allowed => {}
            CommandSafety::Disallowed => {
                eprintln!("Skipping disallowed command: {}", trimmed);
                continue;
            }
            CommandSafety::Dangerous => {
                eprintln!("Blocked potentially dangerous command: {}", trimmed);
                continue;
            }
        }
        println!("-> [{}/{}] {}", i + 1, commands.len(), cmd);
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        if parts.is_empty() {
            continue;
        }
        let output = std::process::Command::new(parts[0])
            .args(&parts[1..])
            .output()?;
        if !output.stdout.is_empty() {
            print!("{}", String::from_utf8_lossy(&output.stdout));
        }
        if !output.status.success() {
            eprintln!(
                "  Command failed (exit {})",
                output.status.code().unwrap_or(-1)
            );
            if !output.stderr.is_empty() {
                eprintln!(
                    "{}",
                    azlin_core::sanitizer::sanitize(&String::from_utf8_lossy(&output.stderr))
                );
            }
        }
    }

    println!("\nazdoit complete.");
    Ok(())
}

#[cfg(test)]
#[allow(deprecated)]
#[path = "azdoit_tests.rs"]
mod tests;

#[cfg(test)]
#[allow(deprecated)]
#[path = "azdoit_tests2.rs"]
mod tests2;
