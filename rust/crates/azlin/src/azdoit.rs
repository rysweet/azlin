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

    for (i, cmd) in commands.iter().enumerate() {
        println!("→ [{}/{}] {}", i + 1, commands.len(), cmd);
        let output = std::process::Command::new("sh")
            .args(["-c", cmd])
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
