//! azlin-cli: CLI command definitions and terminal UI rendering.

pub mod table;

use std::path::PathBuf;

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

    /// Service principal authentication profile to use
    #[arg(long, global = true)]
    pub auth_profile: Option<String>,
}

#[derive(Debug, Clone, clap::ValueEnum)]
pub enum OutputFormat {
    Table,
    Json,
    Csv,
}

// ---------------------------------------------------------------------------
// Log type enum for the logs command
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, clap::ValueEnum)]
pub enum LogType {
    CloudInit,
    Syslog,
    Auth,
}

// ---------------------------------------------------------------------------
// Top-level commands
// ---------------------------------------------------------------------------

#[derive(Subcommand, Debug)]
pub enum Commands {
    // ── NLP Commands ───────────────────────────────────────────────────
    /// Query VM fleet using natural language
    Ask {
        /// Natural language query
        query: Option<String>,

        /// Azure resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Show query plan without executing
        #[arg(long)]
        dry_run: bool,

        /// Command timeout in seconds
        #[arg(long, default_value = "30")]
        timeout: u32,

        /// Maximum results to display
        #[arg(long, default_value = "10")]
        max_results: u32,
    },

    /// Execute commands using natural language
    Do {
        /// Natural language request
        request: String,

        /// Show execution plan without running commands
        #[arg(long)]
        dry_run: bool,

        /// Skip confirmation prompts
        #[arg(short, long)]
        yes: bool,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Autonomous Azure infrastructure deployment (alias: do)
    #[command(name = "doit")]
    Doit {
        #[command(subcommand)]
        action: DoitAction,
    },

    /// Alias for doit
    #[command(name = "azdoit", hide = true)]
    AzDoit {
        #[command(subcommand)]
        action: DoitAction,
    },

    // ── VM Lifecycle ───────────────────────────────────────────────────
    /// Provision a new VM
    New {
        /// GitHub repository URL to clone
        #[arg(long)]
        repo: Option<String>,

        /// Azure VM size
        #[arg(long)]
        vm_size: Option<String>,

        /// Azure region
        #[arg(long)]
        region: Option<String>,

        /// Azure resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Custom VM name
        #[arg(long)]
        name: Option<String>,

        /// Number of VMs to create in parallel
        #[arg(long)]
        pool: Option<u32>,

        /// Do not auto-connect via SSH
        #[arg(long)]
        no_auto_connect: bool,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Template name to use for VM configuration
        #[arg(long)]
        template: Option<String>,

        /// NFS storage account name to mount as home directory
        #[arg(long)]
        nfs_storage: Option<String>,

        /// Disable tmux session management
        #[arg(long)]
        no_tmux: bool,

        /// Custom tmux session name
        #[arg(long)]
        tmux_session: Option<String>,

        /// Bastion host name to use for private VM
        #[arg(long)]
        bastion_name: Option<String>,

        /// Create VM without public IP (Bastion-only)
        #[arg(long)]
        private: bool,
    },

    /// Alias for new
    #[command(name = "vm", hide = true)]
    Vm {
        #[arg(long)]
        repo: Option<String>,
        #[arg(long)]
        vm_size: Option<String>,
        #[arg(long)]
        region: Option<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        pool: Option<u32>,
        #[arg(long)]
        no_auto_connect: bool,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        template: Option<String>,
        #[arg(long)]
        nfs_storage: Option<String>,
        #[arg(long)]
        bastion_name: Option<String>,
        #[arg(long)]
        private: bool,
    },

    /// Alias for new
    #[command(name = "create", hide = true)]
    Create {
        #[arg(long)]
        repo: Option<String>,
        #[arg(long)]
        vm_size: Option<String>,
        #[arg(long)]
        region: Option<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        pool: Option<u32>,
        #[arg(long)]
        no_auto_connect: bool,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long)]
        template: Option<String>,
        #[arg(long)]
        nfs_storage: Option<String>,
        #[arg(long)]
        bastion_name: Option<String>,
        #[arg(long)]
        private: bool,
    },

    /// Clone a VM with its home directory contents
    Clone {
        /// Source VM name
        source_vm: String,

        /// Number of clones to create
        #[arg(long, default_value = "1")]
        num_replicas: u32,

        /// Session name prefix for clones
        #[arg(long)]
        session_prefix: Option<String>,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// VM size for clones (default: same as source)
        #[arg(long)]
        vm_size: Option<String>,

        /// Azure region (default: same as source)
        #[arg(long)]
        region: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// List VMs in resource group
    List {
        /// Resource group name
        #[arg(short, long, alias = "rg")]
        resource_group: Option<String>,

        /// Show all VMs including stopped
        #[arg(long)]
        all: bool,

        /// Filter VMs by tag (format: key or key=value)
        #[arg(long)]
        tag: Option<String>,

        /// Show active tmux sessions (default: true, use --no-tmux to disable)
        #[arg(long, default_value = "true")]
        show_tmux: bool,

        /// Disable tmux session checking
        #[arg(long)]
        no_tmux: bool,

        /// Show SSH latency for each VM
        #[arg(long)]
        with_latency: bool,

        /// Show top processes on each VM
        #[arg(long)]
        show_procs: bool,

        /// Show VM health metrics (CPU, memory, disk)
        #[arg(long)]
        with_health: bool,

        /// Wide output (don't truncate VM names)
        #[arg(short, long)]
        wide: bool,

        /// Compact output
        #[arg(short, long)]
        compact: bool,

        /// Skip cache, fetch fresh data
        #[arg(long)]
        no_cache: bool,

        /// Show vCPU quota summary
        #[arg(short, long)]
        quota: bool,

        /// Scan all resource groups
        #[arg(short = 'a', long)]
        show_all_vms: bool,

        /// Filter VMs by name pattern (glob)
        #[arg(long)]
        vm_pattern: Option<String>,

        /// Include stopped/deallocated VMs (alias for --all)
        #[arg(long)]
        include_stopped: bool,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Set or view session name for a VM
    Session {
        /// VM name
        vm_name: String,

        /// Session name to set (omit to view current)
        session_name: Option<String>,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Clear session name
        #[arg(long)]
        clear: bool,
    },

    /// Show detailed status of VMs
    Status {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Show status for specific VM only
        #[arg(long)]
        vm: Option<String>,
    },

    /// Start a stopped VM
    Start {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Stop/deallocate a VM
    Stop {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Deallocate to save costs (default: yes)
        #[arg(long, default_value = "true")]
        deallocate: bool,
    },

    /// Connect to existing VM via SSH
    Connect {
        /// VM name, session name, or IP address
        vm_identifier: Option<String>,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Disable tmux session management
        #[arg(long)]
        no_tmux: bool,

        /// Custom tmux session name
        #[arg(long)]
        tmux_session: Option<String>,

        /// SSH username
        #[arg(long, default_value = "azureuser")]
        user: String,

        /// SSH private key path
        #[arg(long)]
        key: Option<PathBuf>,

        /// Disable auto-reconnect on SSH disconnect
        #[arg(long)]
        no_reconnect: bool,

        /// Maximum reconnection attempts
        #[arg(long, default_value = "3")]
        max_retries: u32,

        /// Skip prompts (auto-accept)
        #[arg(short, long)]
        yes: bool,
    },

    /// Update all development tools on a VM
    Update {
        /// VM name or session name
        vm_identifier: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Timeout per update in seconds
        #[arg(long, default_value = "300")]
        timeout: u32,
    },

    /// Manage VM tags
    Tag {
        #[command(subcommand)]
        action: TagAction,
    },

    // ── Environment Management ─────────────────────────────────────────
    /// Manage environment variables on VMs
    Env {
        #[command(subcommand)]
        action: EnvAction,
    },

    // ── Snapshot Commands ──────────────────────────────────────────────
    /// Manage VM snapshots and scheduled backups
    Snapshot {
        #[command(subcommand)]
        action: SnapshotAction,
    },

    // ── Storage Commands ──────────────────────────────────────────────
    /// Manage NFS storage for shared home directories
    Storage {
        #[command(subcommand)]
        action: StorageAction,
    },

    // ── Monitoring Commands ───────────────────────────────────────────
    /// VM health dashboard (Four Golden Signals)
    Health {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Check a single VM by name
        #[arg(long)]
        vm: Option<String>,

        /// Launch interactive TUI dashboard
        #[arg(long)]
        tui: bool,
    },

    /// Run 'w' command on all VMs (who's logged in)
    W {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Target a single VM by name
        #[arg(long)]
        vm: Option<String>,

        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },

    /// Run 'ps aux' on all VMs
    Ps {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Group output by VM instead of prefixing
        #[arg(long)]
        grouped: bool,

        /// Target a single VM by name
        #[arg(long)]
        vm: Option<String>,

        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },

    /// Show cost estimates for VMs
    Cost {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Show per-VM breakdown
        #[arg(long)]
        by_vm: bool,

        /// Start date (YYYY-MM-DD)
        #[arg(long)]
        from: Option<String>,

        /// End date (YYYY-MM-DD)
        #[arg(long)]
        to: Option<String>,

        /// Show monthly cost estimate
        #[arg(long)]
        estimate: bool,
    },

    /// Cost intelligence and optimization
    Costs {
        #[command(subcommand)]
        action: CostsAction,
    },

    /// View VM logs without SSH connection
    Logs {
        /// VM name, session name, or IP address
        vm_identifier: String,

        /// Number of log lines to show
        #[arg(short = 'n', long, default_value = "50")]
        lines: u32,

        /// Follow log output (like tail -f)
        #[arg(short, long)]
        follow: bool,

        /// Type of log to view
        #[arg(short = 't', long = "type", default_value = "cloud-init")]
        log_type: LogType,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Distributed real-time monitoring dashboard
    Top {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Refresh interval in seconds
        #[arg(short, long, default_value = "10")]
        interval: u32,

        /// SSH timeout per VM in seconds
        #[arg(short, long, default_value = "5")]
        timeout: u32,

        /// Target a single VM by name
        #[arg(long)]
        vm: Option<String>,

        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },

    // ── Deletion Commands ─────────────────────────────────────────────
    /// Delete a single VM
    Delete {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Skip confirmation prompt
        #[arg(short, long)]
        force: bool,
    },

    /// Delete a VM and all associated resources (force, no confirmation)
    Kill {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
    },

    /// Destroy a VM with dry-run and resource group deletion options
    Destroy {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,

        /// Show what would be deleted without actually deleting
        #[arg(long)]
        dry_run: bool,

        /// Delete the entire resource group
        #[arg(long)]
        delete_rg: bool,
    },

    /// Delete all VMs in resource group
    Killall {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,

        /// Only delete VMs with this prefix
        #[arg(long, default_value = "azlin")]
        prefix: String,
    },

    /// Find and remove orphaned resources (alias: prune)
    Cleanup {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Age threshold in days
        #[arg(long, default_value = "1")]
        age_days: u32,

        /// Idle threshold in days
        #[arg(long, default_value = "1")]
        idle_days: u32,

        /// Preview without deleting
        #[arg(long)]
        dry_run: bool,

        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,

        /// Include running VMs
        #[arg(long)]
        include_running: bool,

        /// Include named sessions
        #[arg(long)]
        include_named: bool,
    },

    /// Alias for cleanup
    #[command(hide = true)]
    Prune {
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long, default_value = "1")]
        age_days: u32,
        #[arg(long, default_value = "1")]
        idle_days: u32,
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        force: bool,
        #[arg(long)]
        include_running: bool,
        #[arg(long)]
        include_named: bool,
    },

    // ── SSH Key Management ────────────────────────────────────────────
    /// SSH key management and rotation
    Keys {
        #[command(subcommand)]
        action: KeysAction,
    },

    // ── Authentication ────────────────────────────────────────────────
    /// Manage service principal authentication profiles
    Auth {
        #[command(subcommand)]
        action: AuthAction,
    },

    // ── File Transfer ─────────────────────────────────────────────────
    /// Copy files between local machine and VMs
    Cp {
        /// Source and destination paths (last arg is destination)
        args: Vec<String>,

        /// Show what would be transferred
        #[arg(long)]
        dry_run: bool,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Sync ~/.azlin/home/ to VM home directory
    Sync {
        /// VM name to sync to
        #[arg(long)]
        vm_name: Option<String>,

        /// Show what would be synced
        #[arg(long)]
        dry_run: bool,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Manually sync SSH keys to VM authorized_keys
    #[command(name = "sync-keys")]
    SyncKeys {
        /// VM name
        vm_name: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// SSH username
        #[arg(long, default_value = "azureuser")]
        ssh_user: String,

        /// Timeout in seconds
        #[arg(long, default_value = "60")]
        timeout: u32,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    // ── Advanced Commands ─────────────────────────────────────────────
    /// Batch operations on multiple VMs
    Batch {
        #[command(subcommand)]
        action: BatchAction,
    },

    /// Fleet-wide command execution
    Fleet {
        #[command(subcommand)]
        action: FleetAction,
    },

    /// Multi-VM compose workflows
    Compose {
        #[command(subcommand)]
        action: ComposeAction,
    },

    /// GitHub Actions self-hosted runner fleet management
    #[command(name = "github-runner")]
    GithubRunner {
        #[command(subcommand)]
        action: GithubRunnerAction,
    },

    /// VM provisioning templates
    Template {
        #[command(subcommand)]
        action: TemplateAction,
    },

    /// Autonomous cost optimization
    Autopilot {
        #[command(subcommand)]
        action: AutopilotAction,
    },

    /// Open VS Code connected to VM
    Code {
        /// VM name or session name
        vm_identifier: Option<String>,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,
    },

    /// Manage multi-subscription contexts
    Context {
        #[command(subcommand)]
        action: ContextAction,
    },

    /// Manage VM data disks
    Disk {
        #[command(subcommand)]
        action: DiskAction,
    },

    /// IP diagnostics and connectivity checking
    Ip {
        #[command(subcommand)]
        action: IpAction,
    },

    /// Web dashboard for fleet management
    Web {
        #[command(subcommand)]
        action: WebAction,
    },

    /// Run OS updates on a VM
    #[command(name = "os-update")]
    OsUpdate {
        /// VM name or session name
        vm_identifier: String,

        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Timeout in seconds
        #[arg(long, default_value = "300")]
        timeout: u32,
    },

    /// Restore sessions across terminal tabs
    Restore {
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,

        /// Config file path
        #[arg(long)]
        config: Option<PathBuf>,

        /// Skip VM health checks
        #[arg(long)]
        skip_health_check: bool,

        /// Force restore even if VMs are stopped
        #[arg(long)]
        force: bool,

        /// Use specific terminal
        #[arg(long)]
        terminal: Option<String>,

        /// Exclude VMs by name pattern
        #[arg(long)]
        exclude: Option<String>,
    },

    /// Save/load/list session configurations
    Sessions {
        #[command(subcommand)]
        action: SessionsAction,
    },

    /// Show extended help for a command
    #[command(name = "azlin-help")]
    AzlinHelp {
        /// Command name to show help for
        command_name: Option<String>,
    },

    /// Manage configuration
    Config {
        #[command(subcommand)]
        action: ConfigAction,
    },

    /// Show detailed info about a specific VM
    Show {
        /// VM name
        name: String,
        /// Output format
        #[arg(short, long, default_value = "table")]
        output: OutputFormat,
    },

    /// Manage Azure Bastion hosts for secure VM connections
    Bastion {
        #[command(subcommand)]
        action: BastionAction,
    },

    /// Display version information
    Version,

    /// Generate shell completions
    Completions {
        /// Shell to generate completions for
        #[arg(value_enum)]
        shell: clap_complete::Shell,
    },
}

// ---------------------------------------------------------------------------
// Subcommand enums
// ---------------------------------------------------------------------------

#[derive(Subcommand, Debug)]
pub enum BastionAction {
    /// List Azure Bastion hosts
    List {
        /// Filter by resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Show status of a Bastion host
    Status {
        /// Bastion host name
        name: String,
        /// Resource group
        #[arg(long, alias = "rg")]
        resource_group: String,
    },
    /// Configure Bastion connection for a VM
    Configure {
        /// VM name to configure
        vm_name: String,
        /// Bastion host name
        #[arg(long)]
        bastion_name: String,
        /// VM resource group
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        /// Bastion resource group (defaults to VM resource group)
        #[arg(long, alias = "bastion-rg")]
        bastion_resource_group: Option<String>,
        /// Disable the mapping instead of enabling it
        #[arg(long)]
        disable: bool,
    },
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

// ── Env subcommands ───────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum EnvAction {
    /// Set environment variable on VM
    Set {
        /// VM name or IP
        vm_identifier: String,
        /// KEY=VALUE pair
        env_var: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Skip secret detection warnings
        #[arg(long)]
        force: bool,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
    /// List environment variables on VM
    List {
        /// VM name or IP
        vm_identifier: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Show full values (default: masked)
        #[arg(long)]
        show_values: bool,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
    /// Delete environment variable from VM
    Delete {
        /// VM name or IP
        vm_identifier: String,
        /// Variable key to delete
        key: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
    /// Export environment variables to .env file
    Export {
        /// VM name or IP
        vm_identifier: String,
        /// Output file path (stdout if omitted)
        output_file: Option<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
    /// Import environment variables from .env file
    Import {
        /// VM name or IP
        vm_identifier: String,
        /// Path to .env file
        env_file: PathBuf,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
    /// Clear all environment variables from VM
    Clear {
        /// VM name or IP
        vm_identifier: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
        /// Direct IP address (skip Azure lookup)
        #[arg(long)]
        ip: Option<String>,
    },
}

// ── Snapshot subcommands ──────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum SnapshotAction {
    /// Create a snapshot of a VM's OS disk
    Create {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// List all snapshots for a VM
    List {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Restore a VM from a snapshot
    Restore {
        /// VM name
        vm_name: String,
        /// Snapshot name
        snapshot_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
    },
    /// Delete a snapshot
    Delete {
        /// Snapshot name
        snapshot_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
    },
    /// Enable scheduled snapshots for a VM
    Enable {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Snapshot interval in hours
        #[arg(long)]
        every: u32,
        /// Number of snapshots to keep
        #[arg(long, default_value = "2")]
        keep: u32,
    },
    /// Disable scheduled snapshots for a VM
    Disable {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Sync snapshots for VMs with schedules
    Sync {
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Sync specific VM only
        #[arg(long)]
        vm: Option<String>,
    },
    /// Show snapshot schedule status for a VM
    Status {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
    },
}

// ── Storage subcommands ───────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum StorageAction {
    /// Create NFS storage for shared home directories
    Create {
        /// Storage account name
        name: String,
        /// Size in GB
        #[arg(long, default_value = "100")]
        size: u32,
        /// Storage tier
        #[arg(long, default_value = "Premium")]
        tier: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        region: Option<String>,
    },
    /// List NFS storage accounts
    List {
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Show storage usage and connected VMs
    Status {
        /// Storage account name
        name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Mount storage on VM
    Mount {
        /// Storage account name
        storage_name: String,
        /// VM name or identifier
        #[arg(long)]
        vm: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Unmount storage from VM
    Unmount {
        /// VM name or identifier
        #[arg(long)]
        vm: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Delete storage account
    Delete {
        /// Storage account name
        name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        /// Force delete even if VMs are connected
        #[arg(long)]
        force: bool,
    },
    /// Mount Azure Files share to local machine
    #[command(name = "mount-file")]
    MountFile {
        /// Storage account name
        #[arg(long)]
        account: String,
        /// File share name
        #[arg(long, default_value = "home")]
        share: String,
        /// Local mount point
        #[arg(long)]
        mount_point: Option<PathBuf>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Unmount Azure Files share from local machine
    #[command(name = "unmount-file")]
    UnmountFile {
        /// Local mount point to unmount
        #[arg(long)]
        mount_point: Option<PathBuf>,
    },
}

// ── Keys subcommands ──────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum KeysAction {
    /// Rotate SSH keys for all VMs in resource group
    Rotate {
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Rotate keys for all VMs (not just azlin prefix)
        #[arg(long)]
        all_vms: bool,
        /// Skip backup before rotation
        #[arg(long)]
        no_backup: bool,
        /// Only update VMs with this prefix
        #[arg(long, default_value = "azlin")]
        vm_prefix: String,
    },
    /// List VMs and their SSH public keys
    List {
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// List all VMs (not just azlin prefix)
        #[arg(long)]
        all_vms: bool,
        /// Only list VMs with this prefix
        #[arg(long, default_value = "azlin")]
        vm_prefix: String,
    },
    /// Export current SSH public key to file
    Export {
        /// Output file path
        #[arg(long)]
        output: PathBuf,
    },
    /// Backup current SSH keys
    Backup {
        /// Backup destination directory
        #[arg(long)]
        destination: Option<PathBuf>,
    },
}

// ── Auth subcommands ──────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum AuthAction {
    /// Set up service principal authentication profile
    Setup {
        /// Profile name
        #[arg(short, long, default_value = "default")]
        profile: String,
        /// Azure Tenant ID
        #[arg(long)]
        tenant_id: Option<String>,
        /// Azure Client ID / Application ID
        #[arg(long)]
        client_id: Option<String>,
        /// Azure Subscription ID
        #[arg(long)]
        subscription_id: Option<String>,
        /// Use certificate-based auth
        #[arg(long)]
        use_certificate: bool,
        /// Path to certificate file
        #[arg(long)]
        certificate_path: Option<PathBuf>,
    },
    /// Test authentication with a profile
    Test {
        /// Profile name
        #[arg(short, long, default_value = "default")]
        profile: String,
        /// Test specific subscription access
        #[arg(long)]
        subscription_id: Option<String>,
    },
    /// List available authentication profiles
    List,
    /// Show authentication profile details
    Show {
        /// Profile name
        profile: String,
    },
    /// Remove authentication profile
    Remove {
        /// Profile name
        profile: String,
        /// Skip confirmation
        #[arg(short, long)]
        yes: bool,
    },
}

// ── Tag subcommands ───────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum TagAction {
    /// Add tags to a VM
    Add {
        /// VM name
        vm_name: String,
        /// Tags in key=value format
        tags: Vec<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Remove tags from a VM
    Remove {
        /// VM name
        vm_name: String,
        /// Tag keys to remove
        tag_keys: Vec<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// List tags on a VM
    List {
        /// VM name
        vm_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
}

// ── Batch subcommands ─────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum BatchAction {
    /// Stop multiple VMs
    Stop {
        /// Filter VMs by tag (format: key=value)
        #[arg(long)]
        tag: Option<String>,
        /// Filter VMs by name pattern (glob)
        #[arg(long)]
        vm_pattern: Option<String>,
        /// Select all VMs in resource group
        #[arg(long)]
        all: bool,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Maximum parallel workers
        #[arg(long, default_value = "10")]
        max_workers: u32,
        /// Skip confirmation prompt
        #[arg(long)]
        confirm: bool,
    },
    /// Start multiple VMs
    Start {
        #[arg(long)]
        tag: Option<String>,
        #[arg(long)]
        vm_pattern: Option<String>,
        #[arg(long)]
        all: bool,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long, default_value = "10")]
        max_workers: u32,
        #[arg(long)]
        confirm: bool,
    },
    /// Execute command on multiple VMs
    Command {
        /// Command to run
        command: String,
        #[arg(long)]
        tag: Option<String>,
        #[arg(long)]
        vm_pattern: Option<String>,
        #[arg(long)]
        all: bool,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long, default_value = "10")]
        max_workers: u32,
        /// Command timeout in seconds
        #[arg(long, default_value = "300")]
        timeout: u32,
        /// Show command output from each VM
        #[arg(long)]
        show_output: bool,
    },
    /// Sync dotfiles to multiple VMs
    Sync {
        #[arg(long)]
        tag: Option<String>,
        #[arg(long)]
        vm_pattern: Option<String>,
        #[arg(long)]
        all: bool,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        #[arg(long, default_value = "10")]
        max_workers: u32,
        /// Show what would be synced without syncing
        #[arg(long)]
        dry_run: bool,
    },
}

// ── Fleet subcommands ─────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum FleetAction {
    /// Run a command across the fleet
    Run {
        /// Command to execute
        command: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        /// Filter VMs by tag (format: key=value)
        #[arg(long)]
        tag: Option<String>,
        /// Filter VMs by name pattern (glob)
        #[arg(long)]
        pattern: Option<String>,
        /// Run on all VMs
        #[arg(long)]
        all: bool,
        /// Max parallel workers
        #[arg(long, default_value = "10")]
        parallel: u32,
        /// Only run on idle VMs
        #[arg(long)]
        if_idle: bool,
        /// Only run if CPU below threshold
        #[arg(long)]
        if_cpu_below: Option<u32>,
        /// Route to least-loaded VMs first
        #[arg(long)]
        smart_route: bool,
        /// Limit execution to N VMs
        #[arg(long)]
        count: Option<u32>,
        /// Retry failed VMs once
        #[arg(long)]
        retry_failed: bool,
        /// Show diff of command outputs
        #[arg(long)]
        show_diff: bool,
        /// Command timeout in seconds
        #[arg(long, default_value = "300")]
        timeout: u32,
        /// Show what would be executed
        #[arg(long)]
        dry_run: bool,
    },
    /// Run a multi-step workflow across the fleet
    Workflow {
        /// Path to workflow YAML file
        workflow_file: PathBuf,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        tag: Option<String>,
        #[arg(long)]
        pattern: Option<String>,
        #[arg(long)]
        all: bool,
        #[arg(long, default_value = "10")]
        parallel: u32,
        #[arg(long)]
        show_diff: bool,
        #[arg(long)]
        dry_run: bool,
    },
}

// ── Compose subcommands ───────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum ComposeAction {
    /// Start services defined in compose file
    Up {
        /// Path to compose YAML file
        #[arg(short, long)]
        file: Option<PathBuf>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Stop services defined in compose file
    Down {
        #[arg(short, long)]
        file: Option<PathBuf>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
    /// Show status of composed services
    Ps {
        #[arg(short, long)]
        file: Option<PathBuf>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
    },
}

// ── GitHub Runner subcommands ─────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum GithubRunnerAction {
    /// Enable GitHub Actions runner fleet
    Enable {
        /// GitHub repository (owner/repo)
        #[arg(long)]
        repo: Option<String>,
        /// Runner pool name
        #[arg(long, default_value = "default")]
        pool: String,
        /// Number of runners
        #[arg(long, default_value = "2")]
        count: u32,
        /// VM size for runners
        #[arg(long)]
        vm_size: Option<String>,
        /// Runner labels (comma-separated)
        #[arg(long)]
        labels: Option<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Auto-scale based on queue depth
        #[arg(long)]
        auto_scale: bool,
    },
    /// Disable GitHub Actions runner fleet
    Disable {
        /// Runner pool name
        #[arg(long, default_value = "default")]
        pool: String,
        /// Keep VMs running (just unregister runners)
        #[arg(long)]
        keep_vms: bool,
    },
    /// Show runner fleet status
    Status {
        /// Runner pool name
        #[arg(long, default_value = "default")]
        pool: String,
    },
    /// Scale runner fleet
    Scale {
        /// Runner pool name
        #[arg(long, default_value = "default")]
        pool: String,
        /// Target number of runners
        #[arg(long)]
        count: u32,
    },
}

// ── Template subcommands ──────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum TemplateAction {
    /// Create a new VM template
    Create {
        /// Template name
        name: String,
        /// Template description
        #[arg(long)]
        description: Option<String>,
        /// Azure VM size
        #[arg(long)]
        vm_size: Option<String>,
        /// Azure region
        #[arg(long)]
        region: Option<String>,
        /// Path to cloud-init script file
        #[arg(long)]
        cloud_init: Option<PathBuf>,
    },
    /// List available templates
    List,
    /// Delete a template
    Delete {
        /// Template name
        name: String,
        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
    },
    /// Export a template to file
    Export {
        /// Template name
        name: String,
        /// Output file path
        output_file: PathBuf,
    },
    /// Import a template from file
    Import {
        /// Input file path
        input_file: PathBuf,
    },
    /// Save current VM config as a template (alias for create)
    Save {
        /// Template name
        name: String,
        /// Template description
        #[arg(long)]
        description: Option<String>,
        /// Azure VM size
        #[arg(long)]
        vm_size: Option<String>,
        /// Azure region
        #[arg(long)]
        region: Option<String>,
        /// Path to cloud-init script file
        #[arg(long)]
        cloud_init: Option<PathBuf>,
    },
    /// Show template details
    Show {
        /// Template name
        name: String,
    },
    /// Apply a template when creating a new VM
    Apply {
        /// Template name
        name: String,
    },
}

// ── Autopilot subcommands ─────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum AutopilotAction {
    /// Enable autonomous cost optimization
    Enable {
        /// Monthly budget in USD
        #[arg(long)]
        budget: Option<u32>,
        /// Optimization strategy
        #[arg(long, default_value = "balanced")]
        strategy: String,
        /// Idle threshold in minutes
        #[arg(long, default_value = "30")]
        idle_threshold: u32,
        /// CPU threshold percentage
        #[arg(long, default_value = "10")]
        cpu_threshold: u32,
    },
    /// Disable autopilot
    Disable {
        /// Keep configuration
        #[arg(long)]
        keep_config: bool,
    },
    /// Show autopilot status
    Status,
    /// Configure autopilot settings
    Config {
        /// Key=value pairs to set
        #[arg(long)]
        set: Vec<String>,
        /// Show current configuration
        #[arg(long)]
        show: bool,
    },
    /// Run autopilot check once
    Run {
        /// Show what would be done
        #[arg(long)]
        dry_run: bool,
    },
}

// ── Context subcommands ───────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum ContextAction {
    /// List all contexts
    List {
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Show current context
    Show {
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Switch to a context
    Use {
        /// Context name
        name: String,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Switch to a context (alias for use)
    Switch {
        /// Context name
        name: String,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Create a new context
    Create {
        /// Context name
        name: String,
        /// Subscription ID
        #[arg(long)]
        subscription_id: Option<String>,
        /// Tenant ID
        #[arg(long)]
        tenant_id: Option<String>,
        /// Resource group
        #[arg(long)]
        resource_group: Option<String>,
        /// Region
        #[arg(long)]
        region: Option<String>,
        /// Key Vault name
        #[arg(long)]
        key_vault_name: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Delete a context
    Delete {
        /// Context name
        name: String,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Skip confirmation prompt
        #[arg(short, long)]
        force: bool,
    },
    /// Rename a context
    Rename {
        /// Current name
        old_name: String,
        /// New name
        new_name: String,
        #[arg(long)]
        config: Option<PathBuf>,
    },
    /// Migrate legacy configuration
    Migrate {
        #[arg(long)]
        config: Option<PathBuf>,
        /// Force migration even if contexts exist
        #[arg(short, long)]
        force: bool,
    },
    /// Alias for show — display current active context
    #[command(hide = true)]
    Current {
        #[arg(long)]
        config: Option<PathBuf>,
    },
}

// ── Disk subcommands ──────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum DiskAction {
    /// Add a data disk to a VM
    Add {
        /// VM name
        vm_name: String,
        /// Disk size in GB
        #[arg(long)]
        size: u32,
        /// Disk SKU (Premium_LRS, Standard_LRS, etc.)
        #[arg(long, default_value = "Premium_LRS")]
        sku: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Logical Unit Number
        #[arg(long)]
        lun: Option<u32>,
    },
}

// ── IP subcommands ────────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum IpAction {
    /// Check IP connectivity
    Check {
        /// VM name, session name, or IP (check all if omitted)
        vm_identifier: Option<String>,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Check all VMs in resource group
        #[arg(long)]
        all: bool,
        /// Port to test connectivity
        #[arg(long, default_value = "22")]
        port: u32,
    },
}

// ── Web subcommands ───────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum WebAction {
    /// Start the web dashboard
    Start {
        /// Port to run the dev server on
        #[arg(long, default_value = "3000")]
        port: u32,
        /// Host to bind to
        #[arg(long, default_value = "localhost")]
        host: String,
    },
    /// Stop the web dashboard
    Stop,
}

// ── Costs subcommands ─────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum CostsAction {
    /// View current costs and spending dashboard
    Dashboard {
        #[arg(long, alias = "rg")]
        resource_group: String,
        /// Force refresh (ignore cache)
        #[arg(long)]
        refresh: bool,
    },
    /// Analyze historical cost data and trends
    History {
        #[arg(long, alias = "rg")]
        resource_group: String,
        /// Number of days to analyze
        #[arg(long, default_value = "30")]
        days: u32,
    },
    /// Manage budgets and alerts
    Budget {
        /// Action: set, show, or alerts
        action: String,
        #[arg(long, alias = "rg")]
        resource_group: String,
        /// Budget amount in USD
        #[arg(long)]
        amount: Option<f64>,
        /// Alert threshold percentage
        #[arg(long)]
        threshold: Option<u32>,
    },
    /// Get cost optimization recommendations
    Recommend {
        #[arg(long, alias = "rg")]
        resource_group: String,
        /// Filter by priority (low, medium, high)
        #[arg(long)]
        priority: Option<String>,
    },
    /// Execute cost-saving actions
    Actions {
        /// Action: list or execute
        action: String,
        #[arg(long, alias = "rg")]
        resource_group: String,
        /// Filter by priority
        #[arg(long)]
        priority: Option<String>,
        /// Show what would be done without executing
        #[arg(long)]
        dry_run: bool,
    },
}

// ── DoIt subcommands ──────────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum DoitAction {
    /// Deploy infrastructure from natural language request
    Deploy {
        /// Natural language request
        request: String,
        /// Output directory for generated artifacts
        #[arg(long)]
        output_dir: Option<PathBuf>,
        /// Maximum execution iterations
        #[arg(short, long, default_value = "50")]
        max_iterations: u32,
        /// Show what would be deployed without actually deploying
        #[arg(long)]
        dry_run: bool,
        /// Reduce output verbosity
        #[arg(short, long)]
        quiet: bool,
    },
    /// Check deployment status
    Status {
        /// Session ID to check
        #[arg(short, long)]
        session: Option<String>,
    },
    /// List all resources created by doit
    List {
        /// Azure username to filter by
        #[arg(short, long)]
        username: Option<String>,
    },
    /// Show detailed information about a resource
    Show {
        /// Full Azure resource ID
        resource_id: String,
    },
    /// Delete all doit-created resources
    Cleanup {
        /// Skip confirmation prompt
        #[arg(short, long)]
        force: bool,
        /// Show what would be deleted
        #[arg(long)]
        dry_run: bool,
        /// Azure username to filter by
        #[arg(short, long)]
        username: Option<String>,
    },
    /// Show example requests
    Examples,
}

// ── Sessions subcommands ──────────────────────────────────────────────────

#[derive(Subcommand, Debug)]
pub enum SessionsAction {
    /// Save current session state
    Save {
        /// Session name
        session_name: String,
        #[arg(long, alias = "rg")]
        resource_group: Option<String>,
        /// VM names to include in the session
        #[arg(long, num_args = 1..)]
        vms: Vec<String>,
        #[arg(long)]
        config: Option<PathBuf>,
        /// Session description
        #[arg(long)]
        description: Option<String>,
    },
    /// Load a saved session
    Load {
        /// Session name
        session_name: String,
    },
    /// Delete a saved session
    Delete {
        /// Session name
        session_name: String,
        /// Skip confirmation prompt
        #[arg(long, short)]
        force: bool,
    },
    /// List saved sessions
    List,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn test_cli_parses() {
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
    fn test_new_command() {
        let cli = Cli::parse_from([
            "azlin",
            "new",
            "--name",
            "my-vm",
            "--vm-size",
            "Standard_D2s_v3",
        ]);
        if let Commands::New { name, vm_size, .. } = cli.command {
            assert_eq!(name, Some("my-vm".to_string()));
            assert_eq!(vm_size, Some("Standard_D2s_v3".to_string()));
        } else {
            panic!("Expected New command");
        }
    }

    #[test]
    fn test_clone_command() {
        let cli = Cli::parse_from(["azlin", "clone", "source-vm", "--num-replicas", "3"]);
        if let Commands::Clone {
            source_vm,
            num_replicas,
            ..
        } = cli.command
        {
            assert_eq!(source_vm, "source-vm");
            assert_eq!(num_replicas, 3);
        } else {
            panic!("Expected Clone command");
        }
    }

    #[test]
    fn test_start_command() {
        let cli = Cli::parse_from(["azlin", "start", "my-vm"]);
        if let Commands::Start { vm_name, .. } = cli.command {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Start command");
        }
    }

    #[test]
    fn test_stop_command() {
        let cli = Cli::parse_from(["azlin", "stop", "my-vm"]);
        if let Commands::Stop {
            vm_name,
            deallocate,
            ..
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert!(deallocate);
        } else {
            panic!("Expected Stop command");
        }
    }

    #[test]
    fn test_connect_command() {
        let cli = Cli::parse_from(["azlin", "connect", "my-vm", "--no-tmux"]);
        if let Commands::Connect {
            vm_identifier,
            no_tmux,
            ..
        } = cli.command
        {
            assert_eq!(vm_identifier, Some("my-vm".to_string()));
            assert!(no_tmux);
        } else {
            panic!("Expected Connect command");
        }
    }

    #[test]
    fn test_kill_command() {
        let cli = Cli::parse_from(["azlin", "kill", "my-vm", "--force"]);
        if let Commands::Kill { vm_name, force, .. } = cli.command {
            assert_eq!(vm_name, "my-vm");
            assert!(force);
        } else {
            panic!("Expected Kill command");
        }
    }

    #[test]
    fn test_destroy_with_dry_run() {
        let cli = Cli::parse_from(["azlin", "destroy", "my-vm", "--dry-run"]);
        if let Commands::Destroy {
            vm_name, dry_run, ..
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert!(dry_run);
        } else {
            panic!("Expected Destroy command");
        }
    }

    #[test]
    fn test_killall_command() {
        let cli = Cli::parse_from(["azlin", "killall", "--prefix", "test-vm", "--force"]);
        if let Commands::Killall { prefix, force, .. } = cli.command {
            assert_eq!(prefix, "test-vm");
            assert!(force);
        } else {
            panic!("Expected Killall command");
        }
    }

    #[test]
    fn test_env_set() {
        let cli = Cli::parse_from(["azlin", "env", "set", "my-vm", "KEY=VALUE"]);
        if let Commands::Env {
            action:
                EnvAction::Set {
                    vm_identifier,
                    env_var,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(env_var, "KEY=VALUE");
        } else {
            panic!("Expected Env Set");
        }
    }

    #[test]
    fn test_env_list() {
        let cli = Cli::parse_from(["azlin", "env", "list", "my-vm", "--show-values"]);
        if let Commands::Env {
            action:
                EnvAction::List {
                    vm_identifier,
                    show_values,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert!(show_values);
        } else {
            panic!("Expected Env List");
        }
    }

    #[test]
    fn test_snapshot_create() {
        let cli = Cli::parse_from(["azlin", "snapshot", "create", "my-vm"]);
        if let Commands::Snapshot {
            action: SnapshotAction::Create { vm_name, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Snapshot Create");
        }
    }

    #[test]
    fn test_snapshot_restore() {
        let cli = Cli::parse_from([
            "azlin", "snapshot", "restore", "my-vm", "snap-001", "--force",
        ]);
        if let Commands::Snapshot {
            action:
                SnapshotAction::Restore {
                    vm_name,
                    snapshot_name,
                    force,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(snapshot_name, "snap-001");
            assert!(force);
        } else {
            panic!("Expected Snapshot Restore");
        }
    }

    #[test]
    fn test_storage_create() {
        let cli = Cli::parse_from(["azlin", "storage", "create", "team-shared", "--size", "200"]);
        if let Commands::Storage {
            action: StorageAction::Create { name, size, .. },
        } = cli.command
        {
            assert_eq!(name, "team-shared");
            assert_eq!(size, 200);
        } else {
            panic!("Expected Storage Create");
        }
    }

    #[test]
    fn test_keys_rotate() {
        let cli = Cli::parse_from(["azlin", "keys", "rotate", "--all-vms"]);
        if let Commands::Keys {
            action: KeysAction::Rotate { all_vms, .. },
        } = cli.command
        {
            assert!(all_vms);
        } else {
            panic!("Expected Keys Rotate");
        }
    }

    #[test]
    fn test_auth_setup() {
        let cli = Cli::parse_from(["azlin", "auth", "setup", "--profile", "prod"]);
        if let Commands::Auth {
            action: AuthAction::Setup { profile, .. },
        } = cli.command
        {
            assert_eq!(profile, "prod");
        } else {
            panic!("Expected Auth Setup");
        }
    }

    #[test]
    fn test_auth_remove() {
        let cli = Cli::parse_from(["azlin", "auth", "remove", "staging", "--yes"]);
        if let Commands::Auth {
            action: AuthAction::Remove { profile, yes },
        } = cli.command
        {
            assert_eq!(profile, "staging");
            assert!(yes);
        } else {
            panic!("Expected Auth Remove");
        }
    }

    #[test]
    fn test_cp_command() {
        let cli = Cli::parse_from(["azlin", "cp", "file.txt", "vm1:~/", "--dry-run"]);
        if let Commands::Cp { args, dry_run, .. } = cli.command {
            assert_eq!(args, vec!["file.txt", "vm1:~/"]);
            assert!(dry_run);
        } else {
            panic!("Expected Cp command");
        }
    }

    #[test]
    fn test_sync_command() {
        let cli = Cli::parse_from(["azlin", "sync", "--vm-name", "myvm", "--dry-run"]);
        if let Commands::Sync {
            vm_name, dry_run, ..
        } = cli.command
        {
            assert_eq!(vm_name, Some("myvm".to_string()));
            assert!(dry_run);
        } else {
            panic!("Expected Sync command");
        }
    }

    #[test]
    fn test_sync_keys_command() {
        let cli = Cli::parse_from(["azlin", "sync-keys", "myvm"]);
        if let Commands::SyncKeys { vm_name, .. } = cli.command {
            assert_eq!(vm_name, "myvm");
        } else {
            panic!("Expected SyncKeys command");
        }
    }

    #[test]
    fn test_health_command() {
        let cli = Cli::parse_from(["azlin", "health", "--vm", "my-vm"]);
        if let Commands::Health { vm, .. } = cli.command {
            assert_eq!(vm, Some("my-vm".to_string()));
        } else {
            panic!("Expected Health command");
        }
    }

    #[test]
    fn test_logs_command() {
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "-n", "100", "--follow"]);
        if let Commands::Logs {
            vm_identifier,
            lines,
            follow,
            ..
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(lines, 100);
            assert!(follow);
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_top_command() {
        let cli = Cli::parse_from(["azlin", "top", "-i", "5"]);
        if let Commands::Top { interval, .. } = cli.command {
            assert_eq!(interval, 5);
        } else {
            panic!("Expected Top command");
        }
    }

    #[test]
    fn test_cost_command() {
        let cli = Cli::parse_from(["azlin", "cost", "--by-vm", "--estimate"]);
        if let Commands::Cost {
            by_vm, estimate, ..
        } = cli.command
        {
            assert!(by_vm);
            assert!(estimate);
        } else {
            panic!("Expected Cost command");
        }
    }

    #[test]
    fn test_ask_command() {
        let cli = Cli::parse_from(["azlin", "ask", "which VMs cost the most?"]);
        if let Commands::Ask { query, .. } = cli.command {
            assert_eq!(query, Some("which VMs cost the most?".to_string()));
        } else {
            panic!("Expected Ask command");
        }
    }

    #[test]
    fn test_do_command() {
        let cli = Cli::parse_from(["azlin", "do", "create a new vm called Sam", "--dry-run"]);
        if let Commands::Do {
            request, dry_run, ..
        } = cli.command
        {
            assert_eq!(request, "create a new vm called Sam");
            assert!(dry_run);
        } else {
            panic!("Expected Do command");
        }
    }

    #[test]
    fn test_doit_deploy() {
        let cli = Cli::parse_from([
            "azlin",
            "doit",
            "deploy",
            "Give me App Service",
            "--dry-run",
        ]);
        if let Commands::Doit {
            action: DoitAction::Deploy {
                request, dry_run, ..
            },
        } = cli.command
        {
            assert_eq!(request, "Give me App Service");
            assert!(dry_run);
        } else {
            panic!("Expected Doit Deploy");
        }
    }

    #[test]
    fn test_batch_command() {
        let cli = Cli::parse_from([
            "azlin",
            "batch",
            "command",
            "uptime",
            "--all",
            "--show-output",
        ]);
        if let Commands::Batch {
            action:
                BatchAction::Command {
                    command,
                    all,
                    show_output,
                    ..
                },
        } = cli.command
        {
            assert_eq!(command, "uptime");
            assert!(all);
            assert!(show_output);
        } else {
            panic!("Expected Batch Command");
        }
    }

    #[test]
    fn test_fleet_run() {
        let cli = Cli::parse_from(["azlin", "fleet", "run", "apt update", "--all", "--dry-run"]);
        if let Commands::Fleet {
            action:
                FleetAction::Run {
                    command,
                    all,
                    dry_run,
                    ..
                },
        } = cli.command
        {
            assert_eq!(command, "apt update");
            assert!(all);
            assert!(dry_run);
        } else {
            panic!("Expected Fleet Run");
        }
    }

    #[test]
    fn test_compose_up() {
        let cli = Cli::parse_from(["azlin", "compose", "up"]);
        assert!(matches!(
            cli.command,
            Commands::Compose {
                action: ComposeAction::Up { .. }
            }
        ));
    }

    #[test]
    fn test_github_runner_enable() {
        let cli = Cli::parse_from([
            "azlin",
            "github-runner",
            "enable",
            "--repo",
            "owner/repo",
            "--count",
            "3",
        ]);
        if let Commands::GithubRunner {
            action: GithubRunnerAction::Enable { repo, count, .. },
        } = cli.command
        {
            assert_eq!(repo, Some("owner/repo".to_string()));
            assert_eq!(count, 3);
        } else {
            panic!("Expected GithubRunner Enable");
        }
    }

    #[test]
    fn test_template_create() {
        let cli = Cli::parse_from([
            "azlin",
            "template",
            "create",
            "dev-template",
            "--vm-size",
            "Standard_D4s_v3",
        ]);
        if let Commands::Template {
            action: TemplateAction::Create { name, vm_size, .. },
        } = cli.command
        {
            assert_eq!(name, "dev-template");
            assert_eq!(vm_size, Some("Standard_D4s_v3".to_string()));
        } else {
            panic!("Expected Template Create");
        }
    }

    #[test]
    fn test_autopilot_enable() {
        let cli = Cli::parse_from(["azlin", "autopilot", "enable", "--budget", "500"]);
        if let Commands::Autopilot {
            action: AutopilotAction::Enable { budget, .. },
        } = cli.command
        {
            assert_eq!(budget, Some(500));
        } else {
            panic!("Expected Autopilot Enable");
        }
    }

    #[test]
    fn test_context_create() {
        let cli = Cli::parse_from(["azlin", "context", "create", "prod", "--region", "eastus"]);
        if let Commands::Context {
            action: ContextAction::Create { name, region, .. },
        } = cli.command
        {
            assert_eq!(name, "prod");
            assert_eq!(region, Some("eastus".to_string()));
        } else {
            panic!("Expected Context Create");
        }
    }

    #[test]
    fn test_disk_add() {
        let cli = Cli::parse_from(["azlin", "disk", "add", "my-vm", "--size", "128"]);
        if let Commands::Disk {
            action: DiskAction::Add { vm_name, size, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(size, 128);
        } else {
            panic!("Expected Disk Add");
        }
    }

    #[test]
    fn test_web_start() {
        let cli = Cli::parse_from(["azlin", "web", "start", "--port", "8080"]);
        if let Commands::Web {
            action: WebAction::Start { port, .. },
        } = cli.command
        {
            assert_eq!(port, 8080);
        } else {
            panic!("Expected Web Start");
        }
    }

    #[test]
    fn test_os_update() {
        let cli = Cli::parse_from(["azlin", "os-update", "my-vm", "--timeout", "600"]);
        if let Commands::OsUpdate {
            vm_identifier,
            timeout,
            ..
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(timeout, 600);
        } else {
            panic!("Expected OsUpdate command");
        }
    }

    #[test]
    fn test_restore_command() {
        let cli = Cli::parse_from(["azlin", "restore", "--force"]);
        if let Commands::Restore { force, .. } = cli.command {
            assert!(force);
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_sessions_save() {
        let cli = Cli::parse_from(["azlin", "sessions", "save", "my-session"]);
        if let Commands::Sessions {
            action: SessionsAction::Save { session_name, .. },
        } = cli.command
        {
            assert_eq!(session_name, "my-session");
        } else {
            panic!("Expected Sessions Save");
        }
    }

    #[test]
    fn test_tag_add() {
        let cli = Cli::parse_from(["azlin", "tag", "add", "my-vm", "env=dev", "team=backend"]);
        if let Commands::Tag {
            action: TagAction::Add { vm_name, tags, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(tags, vec!["env=dev", "team=backend"]);
        } else {
            panic!("Expected Tag Add");
        }
    }

    #[test]
    fn test_costs_dashboard() {
        let cli = Cli::parse_from(["azlin", "costs", "dashboard", "--resource-group", "my-rg"]);
        if let Commands::Costs {
            action: CostsAction::Dashboard { resource_group, .. },
        } = cli.command
        {
            assert_eq!(resource_group, "my-rg");
        } else {
            panic!("Expected Costs Dashboard");
        }
    }

    #[test]
    fn test_ip_check() {
        let cli = Cli::parse_from(["azlin", "ip", "check", "--all", "--port", "443"]);
        if let Commands::Ip {
            action: IpAction::Check { all, port, .. },
        } = cli.command
        {
            assert!(all);
            assert_eq!(port, 443);
        } else {
            panic!("Expected Ip Check");
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

    #[test]
    fn test_cleanup_command() {
        let cli = Cli::parse_from(["azlin", "cleanup", "--dry-run", "--age-days", "7"]);
        if let Commands::Cleanup {
            dry_run, age_days, ..
        } = cli.command
        {
            assert!(dry_run);
            assert_eq!(age_days, 7);
        } else {
            panic!("Expected Cleanup command");
        }
    }

    #[test]
    fn test_update_command() {
        let cli = Cli::parse_from(["azlin", "update", "my-vm"]);
        if let Commands::Update { vm_identifier, .. } = cli.command {
            assert_eq!(vm_identifier, "my-vm");
        } else {
            panic!("Expected Update command");
        }
    }

    #[test]
    fn test_session_command() {
        let cli = Cli::parse_from(["azlin", "session", "vm-123", "my-project"]);
        if let Commands::Session {
            vm_name,
            session_name,
            ..
        } = cli.command
        {
            assert_eq!(vm_name, "vm-123");
            assert_eq!(session_name, Some("my-project".to_string()));
        } else {
            panic!("Expected Session command");
        }
    }

    #[test]
    fn test_status_command() {
        let cli = Cli::parse_from(["azlin", "status", "--vm", "my-vm"]);
        if let Commands::Status { vm, .. } = cli.command {
            assert_eq!(vm, Some("my-vm".to_string()));
        } else {
            panic!("Expected Status command");
        }
    }

    #[test]
    fn test_w_command() {
        let cli = Cli::parse_from(["azlin", "w"]);
        assert!(matches!(cli.command, Commands::W { .. }));
    }

    #[test]
    fn test_ps_command() {
        let cli = Cli::parse_from(["azlin", "ps", "--grouped"]);
        if let Commands::Ps { grouped, .. } = cli.command {
            assert!(grouped);
        } else {
            panic!("Expected Ps command");
        }
    }

    #[test]
    fn test_bastion_list() {
        let cli = Cli::parse_from(["azlin", "bastion", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Bastion {
                action: BastionAction::List { .. }
            }
        ));
    }

    #[test]
    fn test_bastion_list_with_rg() {
        let cli = Cli::parse_from(["azlin", "bastion", "list", "--resource-group", "my-rg"]);
        if let Commands::Bastion {
            action: BastionAction::List { resource_group },
        } = cli.command
        {
            assert_eq!(resource_group, Some("my-rg".to_string()));
        } else {
            panic!("Expected Bastion List command");
        }
    }

    #[test]
    fn test_bastion_status() {
        let cli = Cli::parse_from([
            "azlin",
            "bastion",
            "status",
            "my-bastion",
            "--resource-group",
            "my-rg",
        ]);
        if let Commands::Bastion {
            action:
                BastionAction::Status {
                    name,
                    resource_group,
                },
        } = cli.command
        {
            assert_eq!(name, "my-bastion");
            assert_eq!(resource_group, "my-rg");
        } else {
            panic!("Expected Bastion Status command");
        }
    }

    #[test]
    fn test_bastion_configure() {
        let cli = Cli::parse_from([
            "azlin",
            "bastion",
            "configure",
            "my-vm",
            "--bastion-name",
            "my-bastion",
            "--resource-group",
            "my-rg",
        ]);
        if let Commands::Bastion {
            action:
                BastionAction::Configure {
                    vm_name,
                    bastion_name,
                    resource_group,
                    disable,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(bastion_name, "my-bastion");
            assert_eq!(resource_group, Some("my-rg".to_string()));
            assert!(!disable);
        } else {
            panic!("Expected Bastion Configure command");
        }
    }

    #[test]
    fn test_bastion_configure_disable() {
        let cli = Cli::parse_from([
            "azlin",
            "bastion",
            "configure",
            "my-vm",
            "--bastion-name",
            "my-bastion",
            "--resource-group",
            "my-rg",
            "--disable",
        ]);
        if let Commands::Bastion {
            action: BastionAction::Configure { disable, .. },
        } = cli.command
        {
            assert!(disable);
        } else {
            panic!("Expected Bastion Configure command");
        }
    }

    // ── Additional CLI parser tests ─────────────────────────────────

    #[test]
    fn test_output_format_csv() {
        let cli = Cli::parse_from(["azlin", "-o", "csv", "list"]);
        assert!(matches!(cli.output, OutputFormat::Csv));
    }

    #[test]
    fn test_output_format_default_is_table() {
        let cli = Cli::parse_from(["azlin", "list"]);
        assert!(matches!(cli.output, OutputFormat::Table));
    }

    #[test]
    fn test_auth_profile_flag() {
        let cli = Cli::parse_from(["azlin", "--auth-profile", "prod", "list"]);
        assert_eq!(cli.auth_profile, Some("prod".to_string()));
    }

    #[test]
    fn test_delete_command() {
        let cli = Cli::parse_from(["azlin", "delete", "my-vm", "--force"]);
        if let Commands::Delete { vm_name, force, .. } = cli.command {
            assert_eq!(vm_name, "my-vm");
            assert!(force);
        } else {
            panic!("Expected Delete command");
        }
    }

    #[test]
    fn test_delete_command_without_force() {
        let cli = Cli::parse_from(["azlin", "delete", "my-vm"]);
        if let Commands::Delete { vm_name, force, .. } = cli.command {
            assert_eq!(vm_name, "my-vm");
            assert!(!force);
        } else {
            panic!("Expected Delete command");
        }
    }

    #[test]
    fn test_version_command() {
        let cli = Cli::parse_from(["azlin", "version"]);
        assert!(matches!(cli.command, Commands::Version));
    }

    #[test]
    fn test_show_command() {
        let cli = Cli::parse_from(["azlin", "show", "my-vm"]);
        if let Commands::Show { name, output } = cli.command {
            assert_eq!(name, "my-vm");
            assert!(matches!(output, OutputFormat::Table));
        } else {
            panic!("Expected Show command");
        }
    }

    #[test]
    fn test_code_command() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { vm_identifier, .. } = cli.command {
            assert_eq!(vm_identifier, Some("my-vm".to_string()));
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_command_no_vm() {
        let cli = Cli::parse_from(["azlin", "code"]);
        if let Commands::Code { vm_identifier, .. } = cli.command {
            assert!(vm_identifier.is_none());
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_compose_down() {
        let cli = Cli::parse_from(["azlin", "compose", "down"]);
        assert!(matches!(
            cli.command,
            Commands::Compose {
                action: ComposeAction::Down { .. }
            }
        ));
    }

    #[test]
    fn test_compose_ps() {
        let cli = Cli::parse_from(["azlin", "compose", "ps"]);
        assert!(matches!(
            cli.command,
            Commands::Compose {
                action: ComposeAction::Ps { .. }
            }
        ));
    }

    #[test]
    fn test_compose_up_with_file() {
        let cli = Cli::parse_from([
            "azlin",
            "compose",
            "up",
            "-f",
            "docker-compose.yml",
            "--resource-group",
            "rg1",
        ]);
        if let Commands::Compose {
            action:
                ComposeAction::Up {
                    file,
                    resource_group,
                },
        } = cli.command
        {
            assert_eq!(file, Some(PathBuf::from("docker-compose.yml")));
            assert_eq!(resource_group, Some("rg1".to_string()));
        } else {
            panic!("Expected Compose Up");
        }
    }

    #[test]
    fn test_fleet_run_with_all_options() {
        let cli = Cli::parse_from([
            "azlin",
            "fleet",
            "run",
            "uptime",
            "--resource-group",
            "rg1",
            "--tag",
            "env=dev",
            "--parallel",
            "5",
            "--smart-route",
            "--retry-failed",
            "--timeout",
            "60",
        ]);
        if let Commands::Fleet {
            action:
                FleetAction::Run {
                    command,
                    resource_group,
                    tag,
                    parallel,
                    smart_route,
                    retry_failed,
                    timeout,
                    ..
                },
        } = cli.command
        {
            assert_eq!(command, "uptime");
            assert_eq!(resource_group, Some("rg1".to_string()));
            assert_eq!(tag, Some("env=dev".to_string()));
            assert_eq!(parallel, 5);
            assert!(smart_route);
            assert!(retry_failed);
            assert_eq!(timeout, 60);
        } else {
            panic!("Expected Fleet Run");
        }
    }

    #[test]
    fn test_fleet_workflow() {
        let cli = Cli::parse_from(["azlin", "fleet", "workflow", "workflow.yml", "--all"]);
        if let Commands::Fleet {
            action: FleetAction::Workflow {
                workflow_file, all, ..
            },
        } = cli.command
        {
            assert_eq!(workflow_file, PathBuf::from("workflow.yml"));
            assert!(all);
        } else {
            panic!("Expected Fleet Workflow");
        }
    }

    #[test]
    fn test_disk_add_with_lun() {
        let cli = Cli::parse_from([
            "azlin", "disk", "add", "my-vm", "--size", "128", "--lun", "2",
        ]);
        if let Commands::Disk {
            action: DiskAction::Add { lun, sku, .. },
        } = cli.command
        {
            assert_eq!(lun, Some(2));
            assert_eq!(sku, "Premium_LRS");
        } else {
            panic!("Expected Disk Add");
        }
    }

    #[test]
    fn test_ip_check_single_vm() {
        let cli = Cli::parse_from(["azlin", "ip", "check", "my-vm"]);
        if let Commands::Ip {
            action:
                IpAction::Check {
                    vm_identifier,
                    all,
                    port,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, Some("my-vm".to_string()));
            assert!(!all);
            assert_eq!(port, 22);
        } else {
            panic!("Expected Ip Check");
        }
    }

    #[test]
    fn test_github_runner_disable() {
        let cli = Cli::parse_from(["azlin", "github-runner", "disable", "--keep-vms"]);
        if let Commands::GithubRunner {
            action: GithubRunnerAction::Disable { keep_vms, pool },
        } = cli.command
        {
            assert!(keep_vms);
            assert_eq!(pool, "default");
        } else {
            panic!("Expected GithubRunner Disable");
        }
    }

    #[test]
    fn test_github_runner_status() {
        let cli = Cli::parse_from(["azlin", "github-runner", "status"]);
        if let Commands::GithubRunner {
            action: GithubRunnerAction::Status { pool },
        } = cli.command
        {
            assert_eq!(pool, "default");
        } else {
            panic!("Expected GithubRunner Status");
        }
    }

    #[test]
    fn test_github_runner_scale() {
        let cli = Cli::parse_from([
            "azlin",
            "github-runner",
            "scale",
            "--pool",
            "ci",
            "--count",
            "5",
        ]);
        if let Commands::GithubRunner {
            action: GithubRunnerAction::Scale { pool, count },
        } = cli.command
        {
            assert_eq!(pool, "ci");
            assert_eq!(count, 5);
        } else {
            panic!("Expected GithubRunner Scale");
        }
    }

    #[test]
    fn test_autopilot_disable() {
        let cli = Cli::parse_from(["azlin", "autopilot", "disable", "--keep-config"]);
        if let Commands::Autopilot {
            action: AutopilotAction::Disable { keep_config },
        } = cli.command
        {
            assert!(keep_config);
        } else {
            panic!("Expected Autopilot Disable");
        }
    }

    #[test]
    fn test_autopilot_status() {
        let cli = Cli::parse_from(["azlin", "autopilot", "status"]);
        assert!(matches!(
            cli.command,
            Commands::Autopilot {
                action: AutopilotAction::Status
            }
        ));
    }

    #[test]
    fn test_autopilot_run() {
        let cli = Cli::parse_from(["azlin", "autopilot", "run", "--dry-run"]);
        if let Commands::Autopilot {
            action: AutopilotAction::Run { dry_run },
        } = cli.command
        {
            assert!(dry_run);
        } else {
            panic!("Expected Autopilot Run");
        }
    }

    #[test]
    fn test_context_list() {
        let cli = Cli::parse_from(["azlin", "context", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Context {
                action: ContextAction::List { .. }
            }
        ));
    }

    #[test]
    fn test_context_use() {
        let cli = Cli::parse_from(["azlin", "context", "use", "prod"]);
        if let Commands::Context {
            action: ContextAction::Use { name, .. },
        } = cli.command
        {
            assert_eq!(name, "prod");
        } else {
            panic!("Expected Context Use");
        }
    }

    #[test]
    fn test_context_delete() {
        let cli = Cli::parse_from(["azlin", "context", "delete", "old-ctx", "--force"]);
        if let Commands::Context {
            action: ContextAction::Delete { name, force, .. },
        } = cli.command
        {
            assert_eq!(name, "old-ctx");
            assert!(force);
        } else {
            panic!("Expected Context Delete");
        }
    }

    #[test]
    fn test_context_rename() {
        let cli = Cli::parse_from(["azlin", "context", "rename", "old", "new"]);
        if let Commands::Context {
            action: ContextAction::Rename {
                old_name, new_name, ..
            },
        } = cli.command
        {
            assert_eq!(old_name, "old");
            assert_eq!(new_name, "new");
        } else {
            panic!("Expected Context Rename");
        }
    }

    #[test]
    fn test_context_switch() {
        let cli = Cli::parse_from(["azlin", "context", "switch", "staging"]);
        if let Commands::Context {
            action: ContextAction::Switch { name, .. },
        } = cli.command
        {
            assert_eq!(name, "staging");
        } else {
            panic!("Expected Context Switch");
        }
    }

    #[test]
    fn test_context_current() {
        let cli = Cli::parse_from(["azlin", "context", "current"]);
        assert!(matches!(
            cli.command,
            Commands::Context {
                action: ContextAction::Current { .. }
            }
        ));
    }

    #[test]
    fn test_template_list() {
        let cli = Cli::parse_from(["azlin", "template", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Template {
                action: TemplateAction::List
            }
        ));
    }

    #[test]
    fn test_template_delete() {
        let cli = Cli::parse_from(["azlin", "template", "delete", "old-tpl", "--force"]);
        if let Commands::Template {
            action: TemplateAction::Delete { name, force },
        } = cli.command
        {
            assert_eq!(name, "old-tpl");
            assert!(force);
        } else {
            panic!("Expected Template Delete");
        }
    }

    #[test]
    fn test_template_export() {
        let cli = Cli::parse_from(["azlin", "template", "export", "tpl", "out.yaml"]);
        if let Commands::Template {
            action: TemplateAction::Export { name, output_file },
        } = cli.command
        {
            assert_eq!(name, "tpl");
            assert_eq!(output_file, PathBuf::from("out.yaml"));
        } else {
            panic!("Expected Template Export");
        }
    }

    #[test]
    fn test_template_import() {
        let cli = Cli::parse_from(["azlin", "template", "import", "in.yaml"]);
        if let Commands::Template {
            action: TemplateAction::Import { input_file },
        } = cli.command
        {
            assert_eq!(input_file, PathBuf::from("in.yaml"));
        } else {
            panic!("Expected Template Import");
        }
    }

    #[test]
    fn test_template_save() {
        let cli = Cli::parse_from([
            "azlin",
            "template",
            "save",
            "my-tpl",
            "--vm-size",
            "Standard_B2s",
            "--region",
            "eastus",
        ]);
        if let Commands::Template {
            action:
                TemplateAction::Save {
                    name,
                    vm_size,
                    region,
                    ..
                },
        } = cli.command
        {
            assert_eq!(name, "my-tpl");
            assert_eq!(vm_size, Some("Standard_B2s".to_string()));
            assert_eq!(region, Some("eastus".to_string()));
        } else {
            panic!("Expected Template Save");
        }
    }

    #[test]
    fn test_template_show() {
        let cli = Cli::parse_from(["azlin", "template", "show", "dev-tpl"]);
        if let Commands::Template {
            action: TemplateAction::Show { name },
        } = cli.command
        {
            assert_eq!(name, "dev-tpl");
        } else {
            panic!("Expected Template Show");
        }
    }

    #[test]
    fn test_template_apply() {
        let cli = Cli::parse_from(["azlin", "template", "apply", "gpu-box"]);
        if let Commands::Template {
            action: TemplateAction::Apply { name },
        } = cli.command
        {
            assert_eq!(name, "gpu-box");
        } else {
            panic!("Expected Template Apply");
        }
    }

    #[test]
    fn test_sessions_list() {
        let cli = Cli::parse_from(["azlin", "sessions", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Sessions {
                action: SessionsAction::List
            }
        ));
    }

    #[test]
    fn test_sessions_load() {
        let cli = Cli::parse_from(["azlin", "sessions", "load", "dev-session"]);
        if let Commands::Sessions {
            action: SessionsAction::Load { session_name },
        } = cli.command
        {
            assert_eq!(session_name, "dev-session");
        } else {
            panic!("Expected Sessions Load");
        }
    }

    #[test]
    fn test_sessions_delete() {
        let cli = Cli::parse_from(["azlin", "sessions", "delete", "old-session"]);
        if let Commands::Sessions {
            action: SessionsAction::Delete { session_name, force },
        } = cli.command
        {
            assert_eq!(session_name, "old-session");
            assert!(!force);
        } else {
            panic!("Expected Sessions Delete");
        }
    }

    #[test]
    fn test_sessions_save_with_vms() {
        let cli = Cli::parse_from([
            "azlin", "sessions", "save", "dev-team", "--vms", "vm-1", "vm-2", "vm-3",
        ]);
        if let Commands::Sessions {
            action: SessionsAction::Save {
                session_name, vms, ..
            },
        } = cli.command
        {
            assert_eq!(session_name, "dev-team");
            assert_eq!(vms, vec!["vm-1", "vm-2", "vm-3"]);
        } else {
            panic!("Expected Sessions Save with vms");
        }
    }

    #[test]
    fn test_costs_history() {
        let cli = Cli::parse_from([
            "azlin",
            "costs",
            "history",
            "--resource-group",
            "rg",
            "--days",
            "7",
        ]);
        if let Commands::Costs {
            action:
                CostsAction::History {
                    resource_group,
                    days,
                },
        } = cli.command
        {
            assert_eq!(resource_group, "rg");
            assert_eq!(days, 7);
        } else {
            panic!("Expected Costs History");
        }
    }

    #[test]
    fn test_costs_recommend() {
        let cli = Cli::parse_from([
            "azlin",
            "costs",
            "recommend",
            "--resource-group",
            "rg",
            "--priority",
            "high",
        ]);
        if let Commands::Costs {
            action:
                CostsAction::Recommend {
                    resource_group,
                    priority,
                },
        } = cli.command
        {
            assert_eq!(resource_group, "rg");
            assert_eq!(priority, Some("high".to_string()));
        } else {
            panic!("Expected Costs Recommend");
        }
    }

    #[test]
    fn test_config_show() {
        let cli = Cli::parse_from(["azlin", "config", "show"]);
        assert!(matches!(
            cli.command,
            Commands::Config {
                action: ConfigAction::Show
            }
        ));
    }

    #[test]
    fn test_config_get() {
        let cli = Cli::parse_from(["azlin", "config", "get", "default_region"]);
        if let Commands::Config {
            action: ConfigAction::Get { key },
        } = cli.command
        {
            assert_eq!(key, "default_region");
        } else {
            panic!("Expected Config Get");
        }
    }

    #[test]
    fn test_batch_stop() {
        let cli = Cli::parse_from(["azlin", "batch", "stop", "--all", "--confirm"]);
        if let Commands::Batch {
            action: BatchAction::Stop { all, confirm, .. },
        } = cli.command
        {
            assert!(all);
            assert!(confirm);
        } else {
            panic!("Expected Batch Stop");
        }
    }

    #[test]
    fn test_batch_start() {
        let cli = Cli::parse_from(["azlin", "batch", "start", "--tag", "env=dev"]);
        if let Commands::Batch {
            action: BatchAction::Start { tag, .. },
        } = cli.command
        {
            assert_eq!(tag, Some("env=dev".to_string()));
        } else {
            panic!("Expected Batch Start");
        }
    }

    #[test]
    fn test_batch_sync() {
        let cli = Cli::parse_from(["azlin", "batch", "sync", "--all", "--dry-run"]);
        if let Commands::Batch {
            action: BatchAction::Sync { all, dry_run, .. },
        } = cli.command
        {
            assert!(all);
            assert!(dry_run);
        } else {
            panic!("Expected Batch Sync");
        }
    }

    #[test]
    fn test_env_delete() {
        let cli = Cli::parse_from(["azlin", "env", "delete", "my-vm", "MY_KEY"]);
        if let Commands::Env {
            action: EnvAction::Delete {
                vm_identifier, key, ..
            },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(key, "MY_KEY");
        } else {
            panic!("Expected Env Delete");
        }
    }

    #[test]
    fn test_env_clear() {
        let cli = Cli::parse_from(["azlin", "env", "clear", "my-vm", "--force"]);
        if let Commands::Env {
            action:
                EnvAction::Clear {
                    vm_identifier,
                    force,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert!(force);
        } else {
            panic!("Expected Env Clear");
        }
    }

    #[test]
    fn test_env_export() {
        let cli = Cli::parse_from(["azlin", "env", "export", "my-vm", "env.out"]);
        if let Commands::Env {
            action:
                EnvAction::Export {
                    vm_identifier,
                    output_file,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(output_file, Some("env.out".to_string()));
        } else {
            panic!("Expected Env Export");
        }
    }

    #[test]
    fn test_env_import() {
        let cli = Cli::parse_from(["azlin", "env", "import", "my-vm", ".env"]);
        if let Commands::Env {
            action:
                EnvAction::Import {
                    vm_identifier,
                    env_file,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(env_file, PathBuf::from(".env"));
        } else {
            panic!("Expected Env Import");
        }
    }

    #[test]
    fn test_snapshot_list() {
        let cli = Cli::parse_from(["azlin", "snapshot", "list", "my-vm"]);
        if let Commands::Snapshot {
            action: SnapshotAction::List { vm_name, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Snapshot List");
        }
    }

    #[test]
    fn test_snapshot_delete() {
        let cli = Cli::parse_from(["azlin", "snapshot", "delete", "snap-001", "--force"]);
        if let Commands::Snapshot {
            action:
                SnapshotAction::Delete {
                    snapshot_name,
                    force,
                    ..
                },
        } = cli.command
        {
            assert_eq!(snapshot_name, "snap-001");
            assert!(force);
        } else {
            panic!("Expected Snapshot Delete");
        }
    }

    #[test]
    fn test_snapshot_enable() {
        let cli = Cli::parse_from([
            "azlin", "snapshot", "enable", "my-vm", "--every", "6", "--keep", "3",
        ]);
        if let Commands::Snapshot {
            action:
                SnapshotAction::Enable {
                    vm_name,
                    every,
                    keep,
                    ..
                },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(every, 6);
            assert_eq!(keep, 3);
        } else {
            panic!("Expected Snapshot Enable");
        }
    }

    #[test]
    fn test_snapshot_disable() {
        let cli = Cli::parse_from(["azlin", "snapshot", "disable", "my-vm"]);
        if let Commands::Snapshot {
            action: SnapshotAction::Disable { vm_name, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Snapshot Disable");
        }
    }

    #[test]
    fn test_storage_list() {
        let cli = Cli::parse_from(["azlin", "storage", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Storage {
                action: StorageAction::List { .. }
            }
        ));
    }

    #[test]
    fn test_storage_mount() {
        let cli = Cli::parse_from(["azlin", "storage", "mount", "mystorage", "--vm", "my-vm"]);
        if let Commands::Storage {
            action: StorageAction::Mount {
                storage_name, vm, ..
            },
        } = cli.command
        {
            assert_eq!(storage_name, "mystorage");
            assert_eq!(vm, "my-vm");
        } else {
            panic!("Expected Storage Mount");
        }
    }

    #[test]
    fn test_storage_delete() {
        let cli = Cli::parse_from(["azlin", "storage", "delete", "old-storage", "--force"]);
        if let Commands::Storage {
            action: StorageAction::Delete { name, force, .. },
        } = cli.command
        {
            assert_eq!(name, "old-storage");
            assert!(force);
        } else {
            panic!("Expected Storage Delete");
        }
    }

    #[test]
    fn test_keys_list() {
        let cli = Cli::parse_from(["azlin", "keys", "list", "--all-vms"]);
        if let Commands::Keys {
            action: KeysAction::List { all_vms, .. },
        } = cli.command
        {
            assert!(all_vms);
        } else {
            panic!("Expected Keys List");
        }
    }

    // Note: test_keys_export skipped due to global --output/-o flag shadowing the KeysAction::Export --output flag

    #[test]
    fn test_keys_backup() {
        let cli = Cli::parse_from(["azlin", "keys", "backup"]);
        if let Commands::Keys {
            action: KeysAction::Backup { destination },
        } = cli.command
        {
            assert!(destination.is_none());
        } else {
            panic!("Expected Keys Backup");
        }
    }

    #[test]
    fn test_auth_test() {
        let cli = Cli::parse_from(["azlin", "auth", "test"]);
        if let Commands::Auth {
            action: AuthAction::Test { profile, .. },
        } = cli.command
        {
            assert_eq!(profile, "default");
        } else {
            panic!("Expected Auth Test");
        }
    }

    #[test]
    fn test_auth_list() {
        let cli = Cli::parse_from(["azlin", "auth", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Auth {
                action: AuthAction::List
            }
        ));
    }

    #[test]
    fn test_auth_show() {
        let cli = Cli::parse_from(["azlin", "auth", "show", "prod"]);
        if let Commands::Auth {
            action: AuthAction::Show { profile },
        } = cli.command
        {
            assert_eq!(profile, "prod");
        } else {
            panic!("Expected Auth Show");
        }
    }

    #[test]
    fn test_tag_remove() {
        let cli = Cli::parse_from(["azlin", "tag", "remove", "my-vm", "env", "team"]);
        if let Commands::Tag {
            action: TagAction::Remove {
                vm_name, tag_keys, ..
            },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert_eq!(tag_keys, vec!["env", "team"]);
        } else {
            panic!("Expected Tag Remove");
        }
    }

    #[test]
    fn test_tag_list() {
        let cli = Cli::parse_from(["azlin", "tag", "list", "my-vm"]);
        if let Commands::Tag {
            action: TagAction::List { vm_name, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Tag List");
        }
    }

    #[test]
    fn test_web_stop() {
        let cli = Cli::parse_from(["azlin", "web", "stop"]);
        assert!(matches!(
            cli.command,
            Commands::Web {
                action: WebAction::Stop
            }
        ));
    }

    #[test]
    fn test_doit_status() {
        let cli = Cli::parse_from(["azlin", "doit", "status"]);
        assert!(matches!(
            cli.command,
            Commands::Doit {
                action: DoitAction::Status { .. }
            }
        ));
    }

    #[test]
    fn test_doit_list() {
        let cli = Cli::parse_from(["azlin", "doit", "list"]);
        assert!(matches!(
            cli.command,
            Commands::Doit {
                action: DoitAction::List { .. }
            }
        ));
    }

    #[test]
    fn test_doit_examples() {
        let cli = Cli::parse_from(["azlin", "doit", "examples"]);
        assert!(matches!(
            cli.command,
            Commands::Doit {
                action: DoitAction::Examples
            }
        ));
    }

    #[test]
    fn test_doit_cleanup() {
        let cli = Cli::parse_from(["azlin", "doit", "cleanup", "--force", "--dry-run"]);
        if let Commands::Doit {
            action: DoitAction::Cleanup { force, dry_run, .. },
        } = cli.command
        {
            assert!(force);
            assert!(dry_run);
        } else {
            panic!("Expected Doit Cleanup");
        }
    }

    #[test]
    fn test_connect_with_user_and_key() {
        let cli = Cli::parse_from([
            "azlin",
            "connect",
            "my-vm",
            "--user",
            "admin",
            "--key",
            "/path/to/key",
        ]);
        if let Commands::Connect {
            vm_identifier,
            user,
            key,
            ..
        } = cli.command
        {
            assert_eq!(vm_identifier, Some("my-vm".to_string()));
            assert_eq!(user, "admin");
            assert_eq!(key, Some(PathBuf::from("/path/to/key")));
        } else {
            panic!("Expected Connect command");
        }
    }

    #[test]
    fn test_connect_defaults() {
        let cli = Cli::parse_from(["azlin", "connect"]);
        if let Commands::Connect {
            vm_identifier,
            user,
            no_tmux,
            no_reconnect,
            max_retries,
            ..
        } = cli.command
        {
            assert!(vm_identifier.is_none());
            assert_eq!(user, "azureuser");
            assert!(!no_tmux);
            assert!(!no_reconnect);
            assert_eq!(max_retries, 3);
        } else {
            panic!("Expected Connect command");
        }
    }

    #[test]
    fn test_new_with_all_options() {
        let cli = Cli::parse_from([
            "azlin",
            "new",
            "--name",
            "test-vm",
            "--vm-size",
            "Standard_D4s_v3",
            "--region",
            "eastus",
            "--resource-group",
            "rg",
            "--repo",
            "https://github.com/user/repo",
            "--no-auto-connect",
            "--private",
            "--bastion-name",
            "mybastion",
        ]);
        if let Commands::New {
            name,
            vm_size,
            region,
            resource_group,
            repo,
            no_auto_connect,
            private,
            bastion_name,
            ..
        } = cli.command
        {
            assert_eq!(name, Some("test-vm".to_string()));
            assert_eq!(vm_size, Some("Standard_D4s_v3".to_string()));
            assert_eq!(region, Some("eastus".to_string()));
            assert_eq!(resource_group, Some("rg".to_string()));
            assert_eq!(repo, Some("https://github.com/user/repo".to_string()));
            assert!(no_auto_connect);
            assert!(private);
            assert_eq!(bastion_name, Some("mybastion".to_string()));
        } else {
            panic!("Expected New command");
        }
    }

    #[test]
    fn test_destroy_with_delete_rg() {
        let cli = Cli::parse_from(["azlin", "destroy", "my-vm", "--delete-rg", "--force"]);
        if let Commands::Destroy {
            vm_name,
            delete_rg,
            force,
            ..
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
            assert!(delete_rg);
            assert!(force);
        } else {
            panic!("Expected Destroy command");
        }
    }

    #[test]
    fn test_cleanup_with_all_flags() {
        let cli = Cli::parse_from([
            "azlin",
            "cleanup",
            "--age-days",
            "30",
            "--idle-days",
            "14",
            "--dry-run",
            "--force",
            "--include-running",
            "--include-named",
        ]);
        if let Commands::Cleanup {
            age_days,
            idle_days,
            dry_run,
            force,
            include_running,
            include_named,
            ..
        } = cli.command
        {
            assert_eq!(age_days, 30);
            assert_eq!(idle_days, 14);
            assert!(dry_run);
            assert!(force);
            assert!(include_running);
            assert!(include_named);
        } else {
            panic!("Expected Cleanup command");
        }
    }

    #[test]
    fn test_rg_alias_works() {
        let cli = Cli::parse_from(["azlin", "list", "--rg", "my-rg"]);
        if let Commands::List { resource_group, .. } = cli.command {
            assert_eq!(resource_group, Some("my-rg".to_string()));
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_tag_filter() {
        let cli = Cli::parse_from(["azlin", "list", "--tag", "env=dev"]);
        if let Commands::List { tag, .. } = cli.command {
            assert_eq!(tag, Some("env=dev".to_string()));
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_all_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--all"]);
        if let Commands::List { all, .. } = cli.command {
            assert!(all);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_wide_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--wide"]);
        if let Commands::List { wide, .. } = cli.command {
            assert!(wide);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_compact_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--compact"]);
        if let Commands::List { compact, .. } = cli.command {
            assert!(compact);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_latency_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--with-latency"]);
        if let Commands::List { with_latency, .. } = cli.command {
            assert!(with_latency);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_health_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--with-health"]);
        if let Commands::List { with_health, .. } = cli.command {
            assert!(with_health);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_no_tmux() {
        let cli = Cli::parse_from(["azlin", "list", "--no-tmux"]);
        if let Commands::List { no_tmux, .. } = cli.command {
            assert!(no_tmux);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_show_procs() {
        let cli = Cli::parse_from(["azlin", "list", "--show-procs"]);
        if let Commands::List { show_procs, .. } = cli.command {
            assert!(show_procs);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_quota() {
        let cli = Cli::parse_from(["azlin", "list", "--quota"]);
        if let Commands::List { quota, .. } = cli.command {
            assert!(quota);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_show_all_vms() {
        let cli = Cli::parse_from(["azlin", "list", "--show-all-vms"]);
        if let Commands::List { show_all_vms, .. } = cli.command {
            assert!(show_all_vms);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_vm_pattern() {
        let cli = Cli::parse_from(["azlin", "list", "--vm-pattern", "test-*"]);
        if let Commands::List { vm_pattern, .. } = cli.command {
            assert_eq!(vm_pattern.unwrap(), "test-*");
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_include_stopped() {
        let cli = Cli::parse_from(["azlin", "list", "--include-stopped"]);
        if let Commands::List { include_stopped, .. } = cli.command {
            assert!(include_stopped);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_with_no_cache() {
        let cli = Cli::parse_from(["azlin", "list", "--no-cache"]);
        if let Commands::List { no_cache, .. } = cli.command {
            assert!(no_cache);
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_azlin_help_command() {
        let cli = Cli::parse_from(["azlin", "azlin-help"]);
        if let Commands::AzlinHelp { command_name } = cli.command {
            assert!(command_name.is_none());
        } else {
            panic!("Expected AzlinHelp command");
        }
    }

    #[test]
    fn test_azlin_help_with_command() {
        let cli = Cli::parse_from(["azlin", "azlin-help", "connect"]);
        if let Commands::AzlinHelp { command_name } = cli.command {
            assert_eq!(command_name, Some("connect".to_string()));
        } else {
            panic!("Expected AzlinHelp command");
        }
    }

    #[test]
    fn test_context_show() {
        let cli = Cli::parse_from(["azlin", "context", "show"]);
        assert!(matches!(
            cli.command,
            Commands::Context {
                action: ContextAction::Show { .. }
            }
        ));
    }

    #[test]
    fn test_context_migrate() {
        let cli = Cli::parse_from(["azlin", "context", "migrate", "--force"]);
        if let Commands::Context {
            action: ContextAction::Migrate { force, .. },
        } = cli.command
        {
            assert!(force);
        } else {
            panic!("Expected Context Migrate");
        }
    }

    #[test]
    fn test_snapshot_status() {
        let cli = Cli::parse_from(["azlin", "snapshot", "status", "my-vm"]);
        if let Commands::Snapshot {
            action: SnapshotAction::Status { vm_name, .. },
        } = cli.command
        {
            assert_eq!(vm_name, "my-vm");
        } else {
            panic!("Expected Snapshot Status");
        }
    }

    #[test]
    fn test_snapshot_sync() {
        let cli = Cli::parse_from(["azlin", "snapshot", "sync", "--vm", "my-vm"]);
        if let Commands::Snapshot {
            action: SnapshotAction::Sync { vm, .. },
        } = cli.command
        {
            assert_eq!(vm, Some("my-vm".to_string()));
        } else {
            panic!("Expected Snapshot Sync");
        }
    }

    #[test]
    fn test_storage_status() {
        let cli = Cli::parse_from(["azlin", "storage", "status", "mystorage"]);
        if let Commands::Storage {
            action: StorageAction::Status { name, .. },
        } = cli.command
        {
            assert_eq!(name, "mystorage");
        } else {
            panic!("Expected Storage Status");
        }
    }

    #[test]
    fn test_storage_unmount() {
        let cli = Cli::parse_from(["azlin", "storage", "unmount", "--vm", "my-vm"]);
        if let Commands::Storage {
            action: StorageAction::Unmount { vm, .. },
        } = cli.command
        {
            assert_eq!(vm, "my-vm");
        } else {
            panic!("Expected Storage Unmount");
        }
    }

    #[test]
    fn test_costs_budget() {
        let cli = Cli::parse_from([
            "azlin",
            "costs",
            "budget",
            "set",
            "--resource-group",
            "rg",
            "--amount",
            "1000",
        ]);
        if let Commands::Costs {
            action:
                CostsAction::Budget {
                    action,
                    resource_group,
                    amount,
                    ..
                },
        } = cli.command
        {
            assert_eq!(action, "set");
            assert_eq!(resource_group, "rg");
            assert_eq!(amount, Some(1000.0));
        } else {
            panic!("Expected Costs Budget");
        }
    }

    #[test]
    fn test_costs_actions() {
        let cli = Cli::parse_from([
            "azlin",
            "costs",
            "actions",
            "list",
            "--resource-group",
            "rg",
            "--dry-run",
        ]);
        if let Commands::Costs {
            action:
                CostsAction::Actions {
                    action,
                    resource_group,
                    dry_run,
                    ..
                },
        } = cli.command
        {
            assert_eq!(action, "list");
            assert_eq!(resource_group, "rg");
            assert!(dry_run);
        } else {
            panic!("Expected Costs Actions");
        }
    }
}
