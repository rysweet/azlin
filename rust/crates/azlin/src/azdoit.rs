use anyhow::Result;

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    eprintln!("azdoit (Rust) - NLP command interface not yet implemented.");
    eprintln!("Use the Python version: azdoit");
    std::process::exit(1);
}
