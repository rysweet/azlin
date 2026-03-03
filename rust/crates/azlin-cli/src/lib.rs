//! azlin-cli: CLI command definitions and terminal UI rendering.

use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(
    name = "azlin",
    version,
    about = "Azure VM fleet management CLI",
    long_about = "Provision, manage, and monitor development VMs on Azure.\n\n\
                  Use 'azlin <command> --help' for more information about a command."
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,

    /// Enable verbose output
    #[arg(short, long, global = true)]
    pub verbose: bool,

    /// Output format
    #[arg(short, long, global = true, default_value = "table")]
    pub output: OutputFormat,
}

#[derive(Debug, Clone, clap::ValueEnum)]
pub enum OutputFormat {
    Table,
    Json,
    Csv,
}

#[derive(Subcommand, Debug)]
pub enum Commands {
    /// List all VMs in the resource group
    List {
        /// Resource group name (uses default if not specified)
        #[arg(short, long)]
        resource_group: Option<String>,

        /// Show all details
        #[arg(long)]
        detailed: bool,
    },

    /// Show detailed info about a specific VM
    Show {
        /// VM name
        name: String,
    },

    /// Start one or more VMs
    Start {
        /// VM names
        names: Vec<String>,
    },

    /// Stop one or more VMs
    Stop {
        /// VM names
        names: Vec<String>,

        /// Deallocate VMs (stop billing)
        #[arg(long)]
        deallocate: bool,
    },

    /// Provision a new VM
    Provision {
        /// VM name
        name: String,

        /// VM size
        #[arg(short = 's', long)]
        size: Option<String>,

        /// Azure region
        #[arg(short, long)]
        region: Option<String>,

        /// Resource group
        #[arg(short = 'g', long)]
        resource_group: Option<String>,
    },

    /// Delete a VM
    Delete {
        /// VM name
        name: String,

        /// Skip confirmation prompt
        #[arg(short, long)]
        force: bool,
    },

    /// Connect to a VM via SSH
    Connect {
        /// VM name
        name: String,
    },

    /// Manage configuration
    Config {
        #[command(subcommand)]
        action: ConfigAction,
    },

    /// Show costs and usage
    Costs {
        /// Resource group
        #[arg(short = 'g', long)]
        resource_group: Option<String>,
    },

    /// Display version information
    Version,
}

#[derive(Subcommand, Debug)]
pub enum ConfigAction {
    /// Show current configuration
    Show,
    /// Set a configuration value
    Set {
        /// Key to set
        key: String,
        /// Value to set
        value: String,
    },
    /// Get a configuration value
    Get {
        /// Key to get
        key: String,
    },
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn test_cli_parses() {
        // Verify CLI definition is valid
        Cli::command().debug_assert();
    }

    #[test]
    fn test_list_command() {
        let cli = Cli::parse_from(["azlin", "list"]);
        assert!(matches!(cli.command, Commands::List { .. }));
    }

    #[test]
    fn test_list_with_resource_group() {
        let cli = Cli::parse_from(["azlin", "list", "-r", "my-rg"]);
        if let Commands::List { resource_group, .. } = cli.command {
            assert_eq!(resource_group, Some("my-rg".to_string()));
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_provision_command() {
        let cli = Cli::parse_from(["azlin", "provision", "my-vm", "-s", "Standard_D2s_v3"]);
        if let Commands::Provision { name, size, .. } = cli.command {
            assert_eq!(name, "my-vm");
            assert_eq!(size, Some("Standard_D2s_v3".to_string()));
        } else {
            panic!("Expected Provision command");
        }
    }

    #[test]
    fn test_verbose_flag() {
        let cli = Cli::parse_from(["azlin", "-v", "list"]);
        assert!(cli.verbose);
    }

    #[test]
    fn test_output_format() {
        let cli = Cli::parse_from(["azlin", "-o", "json", "list"]);
        assert!(matches!(cli.output, OutputFormat::Json));
    }

    #[test]
    fn test_stop_with_deallocate() {
        let cli = Cli::parse_from(["azlin", "stop", "vm1", "vm2", "--deallocate"]);
        if let Commands::Stop { names, deallocate } = cli.command {
            assert_eq!(names, vec!["vm1", "vm2"]);
            assert!(deallocate);
        } else {
            panic!("Expected Stop command");
        }
    }

    #[test]
    fn test_config_set() {
        let cli = Cli::parse_from(["azlin", "config", "set", "default_region", "eastus"]);
        if let Commands::Config {
            action: ConfigAction::Set { key, value },
        } = cli.command
        {
            assert_eq!(key, "default_region");
            assert_eq!(value, "eastus");
        } else {
            panic!("Expected Config Set");
        }
    }
}
