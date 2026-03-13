use anyhow::{Context, Result};
use clap::CommandFactory;
use clap_complete::Shell;
use console::Style;
use std::io::Write;
use std::path::PathBuf;

/// Install shell completions for the detected or specified shell.
pub(crate) fn install_completions(shell: Shell) -> Result<()> {
    let bold = Style::new().bold();
    let cyan = Style::new().cyan();
    let green = Style::new().green();

    let (install_path, instructions) = completion_install_path(shell)?;

    println!(
        "Installing {} completions to {}",
        bold.apply_to(shell_name(shell)),
        cyan.apply_to(install_path.display())
    );

    // Generate completions to a buffer
    let mut buf = Vec::new();
    let mut cmd = azlin_cli::Cli::command();
    clap_complete::generate(shell, &mut cmd, "azlin", &mut buf);

    // Create parent directory if needed
    if let Some(parent) = install_path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create directory: {}", parent.display()))?;
    }

    // Write the completions file
    let mut file = std::fs::File::create(&install_path)
        .with_context(|| format!("Failed to create: {}", install_path.display()))?;
    file.write_all(&buf)?;

    println!("{} Completions installed.", green.apply_to("Done!"));

    if !instructions.is_empty() {
        println!();
        println!("  To activate, {}", instructions);
    }

    // Write a version marker so we can detect stale completions
    let marker_path = install_path.with_extension("version");
    let _ = std::fs::write(&marker_path, env!("CARGO_PKG_VERSION"));

    Ok(())
}

/// Detect the user's shell from $SHELL if no explicit shell was given.
pub(crate) fn detect_shell() -> Option<Shell> {
    let shell_var = std::env::var("SHELL").ok()?;
    if shell_var.contains("zsh") {
        Some(Shell::Zsh)
    } else if shell_var.contains("fish") {
        Some(Shell::Fish)
    } else if shell_var.contains("bash") {
        Some(Shell::Bash)
    } else {
        None
    }
}

/// Check if completions need updating (version mismatch or missing).
pub(crate) fn completions_need_update() -> bool {
    let shell = match detect_shell() {
        Some(s) => s,
        None => return false,
    };
    let (install_path, _) = match completion_install_path(shell) {
        Ok(p) => p,
        Err(_) => return false,
    };
    let marker_path = install_path.with_extension("version");
    match std::fs::read_to_string(&marker_path) {
        Ok(version) => version.trim() != env!("CARGO_PKG_VERSION"),
        Err(_) => !install_path.exists(),
    }
}

/// Returns (install_path, post_install_instructions) for the given shell.
fn completion_install_path(shell: Shell) -> Result<(PathBuf, String)> {
    let home = dirs::home_dir().context("Could not determine home directory")?;

    match shell {
        Shell::Bash => {
            // Try ~/.bash_completion.d/ first, fall back to ~/.local/share/bash-completion/completions/
            let bash_comp_d = home.join(".bash_completion.d");
            if bash_comp_d.exists() {
                Ok((
                    bash_comp_d.join("azlin"),
                    "restart your shell or run: source ~/.bash_completion.d/azlin".to_string(),
                ))
            } else {
                let xdg = home.join(".local/share/bash-completion/completions");
                Ok((
                    xdg.join("azlin"),
                    "restart your shell or run: source ~/.local/share/bash-completion/completions/azlin".to_string(),
                ))
            }
        }
        Shell::Zsh => {
            // Install to ~/.zfunc/ and add to fpath
            let zfunc = home.join(".zfunc");
            Ok((
                zfunc.join("_azlin"),
                "add 'fpath=(~/.zfunc $fpath); autoload -Uz compinit; compinit' to ~/.zshrc"
                    .to_string(),
            ))
        }
        Shell::Fish => {
            let fish_dir = home.join(".config/fish/completions");
            Ok((
                fish_dir.join("azlin.fish"),
                String::new(), // Fish auto-loads from this directory
            ))
        }
        _ => {
            // PowerShell, Elvish, etc. -- just print to stdout
            anyhow::bail!(
                "Auto-install not supported for {}. Use `azlin completions {}` to print completions.",
                shell_name(shell),
                shell_name(shell).to_lowercase()
            );
        }
    }
}

fn shell_name(shell: Shell) -> &'static str {
    match shell {
        Shell::Bash => "Bash",
        Shell::Zsh => "Zsh",
        Shell::Fish => "Fish",
        Shell::PowerShell => "PowerShell",
        Shell::Elvish => "Elvish",
        _ => "Unknown",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_completion_install_path_bash() {
        let (path, _instructions) = completion_install_path(Shell::Bash).unwrap();
        let name = path.file_name().unwrap().to_string_lossy();
        assert_eq!(name, "azlin");
    }

    #[test]
    fn test_completion_install_path_zsh() {
        let (path, instructions) = completion_install_path(Shell::Zsh).unwrap();
        let name = path.file_name().unwrap().to_string_lossy();
        assert_eq!(name, "_azlin");
        assert!(instructions.contains("fpath"));
    }

    #[test]
    fn test_completion_install_path_fish() {
        let (path, instructions) = completion_install_path(Shell::Fish).unwrap();
        assert!(path.to_string_lossy().contains("fish"));
        assert!(instructions.is_empty(), "fish auto-loads completions");
    }

    #[test]
    fn test_shell_name() {
        assert_eq!(shell_name(Shell::Bash), "Bash");
        assert_eq!(shell_name(Shell::Zsh), "Zsh");
        assert_eq!(shell_name(Shell::Fish), "Fish");
    }

    #[test]
    fn test_detect_shell_returns_option() {
        // Just verify no panic -- result depends on $SHELL
        let _result = detect_shell();
    }
}
