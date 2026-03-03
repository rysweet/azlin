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

    /// Enable verbose output
    #[arg(short, long)]
    verbose: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    if args.verbose {
        tracing_subscriber::fmt().with_env_filter("debug").init();
    }

    let request = args.request.join(" ");
    if request.is_empty() {
        eprintln!("Error: No request provided.");
        eprintln!("Usage: azdoit \"create a VM called dev-box\"");
        std::process::exit(1);
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

    println!("🤖 azdoit — Planning: {}", request);
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

    if !dialoguer::Confirm::new()
        .with_prompt(format!("Execute {} command(s)?", commands.len()))
        .default(false)
        .interact()?
    {
        println!("Cancelled.");
        return Ok(());
    }

    let allowed_prefixes = ["az ", "echo ", "azlin "];
    for (i, cmd) in commands.iter().enumerate() {
        let is_allowed = allowed_prefixes.iter().any(|p| cmd.starts_with(p));
        if !is_allowed {
            eprintln!("⚠ Skipping disallowed command: {}", cmd);
            continue;
        }
        println!("→ [{}/{}] {}", i + 1, commands.len(), cmd);
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
                "  ⚠ Command failed (exit {})",
                output.status.code().unwrap_or(-1)
            );
            if !output.stderr.is_empty() {
                eprintln!("{}", String::from_utf8_lossy(&output.stderr));
            }
        }
    }

    println!("\n✓ azdoit complete.");
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_azdoit_help() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .arg("--help")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("azdoit") || stdout.contains("natural language"));
    }

    #[test]
    fn test_azdoit_version() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .arg("--version")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("2.3.0"));
    }

    #[test]
    fn test_azdoit_no_args_fails() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .env_remove("ANTHROPIC_API_KEY")
            .output()
            .unwrap();
        // Should fail: no request and no API key
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_no_api_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["list", "my", "vms"])
            .env_remove("ANTHROPIC_API_KEY")
            .env_remove("AZURE_OPENAI_API_KEY")
            .output()
            .unwrap();
        // Should fail gracefully without API key
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(!output.status.success() || stderr.contains("API") || stderr.contains("error"));
    }

    #[test]
    fn test_command_allowlist() {
        let allowed_prefixes = ["az ", "echo ", "azlin "];
        // Allowed commands
        assert!(allowed_prefixes.iter().any(|p| "az vm list".starts_with(p)));
        assert!(allowed_prefixes.iter().any(|p| "echo hello".starts_with(p)));
        assert!(allowed_prefixes.iter().any(|p| "azlin list".starts_with(p)));
        // Disallowed commands
        assert!(!allowed_prefixes.iter().any(|p| "rm -rf /".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "curl evil.com".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "wget malware".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "sudo rm -rf".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "python -c 'hack'".starts_with(p)));
    }

    #[test]
    fn test_azdoit_dry_run_no_api_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--dry-run", "list", "vms"])
            .env_remove("ANTHROPIC_API_KEY")
            .env_remove("AZURE_OPENAI_API_KEY")
            .output()
            .unwrap();
        // Without an API key, even dry-run should fail at client creation
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_max_turns_flag() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--max-turns", "5", "--help"])
            .output()
            .unwrap();
        // --help should still work even with other flags
        assert!(output.status.success());
    }
}
