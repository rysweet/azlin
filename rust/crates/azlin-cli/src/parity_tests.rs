//! TDD tests for Python-to-Rust CLI parity.
//!
//! These tests define the contract: every missing flag, default value fix,
//! and new subcommand required for full Python CLI parity.
//!
//! Tests are grouped by gap category:
//!   1. Missing flags on existing commands
//!   2. Default value corrections
//!   3. Missing subcommands (doit destroy / doit delete)
//!
//! Each test will FAIL until the corresponding change is made in lib.rs.

#[cfg(test)]
mod parity_tests {
    use crate::*;
    use clap::CommandFactory;

    // =====================================================================
    // 1. CODE COMMAND — missing flags: --user, --key, --no-extensions, --workspace
    //    Also: vm_identifier must be required (String, not Option<String>)
    // =====================================================================

    #[test]
    fn test_code_has_user_flag_with_default() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { user, .. } = cli.command {
            assert_eq!(
                user, "azureuser",
                "code --user should default to 'azureuser'"
            );
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_user_flag_override() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm", "--user", "devuser"]);
        if let Commands::Code { user, .. } = cli.command {
            assert_eq!(user, "devuser", "code --user should accept custom value");
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_has_key_flag() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm", "--key", "/home/me/.ssh/id_rsa"]);
        if let Commands::Code { key, .. } = cli.command {
            assert_eq!(
                key,
                Some(std::path::PathBuf::from("/home/me/.ssh/id_rsa")),
                "code --key should accept SSH key path"
            );
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_key_defaults_to_none() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { key, .. } = cli.command {
            assert_eq!(key, None, "code --key should default to None");
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_has_no_extensions_flag() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm", "--no-extensions"]);
        if let Commands::Code { no_extensions, .. } = cli.command {
            assert!(no_extensions, "code --no-extensions should set flag to true");
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_no_extensions_defaults_false() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { no_extensions, .. } = cli.command {
            assert!(
                !no_extensions,
                "code --no-extensions should default to false"
            );
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_has_workspace_flag_with_default() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { workspace, .. } = cli.command {
            assert_eq!(
                workspace, "/home/user",
                "code --workspace should default to '/home/user'"
            );
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_workspace_flag_override() {
        let cli = Cli::parse_from(["azlin", "code", "my-vm", "--workspace", "/projects"]);
        if let Commands::Code { workspace, .. } = cli.command {
            assert_eq!(
                workspace, "/projects",
                "code --workspace should accept custom value"
            );
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_vm_identifier_is_required() {
        // vm_identifier must be a required positional arg (String, not Option<String>)
        let cli = Cli::parse_from(["azlin", "code", "my-vm"]);
        if let Commands::Code { vm_identifier, .. } = cli.command {
            // If vm_identifier is String, this compiles and the assertion works.
            // If it's still Option<String>, this test won't compile.
            let _: &str = &vm_identifier;
            assert_eq!(vm_identifier, "my-vm");
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_code_missing_vm_identifier_is_error() {
        // With vm_identifier required, parsing without it should fail
        let result = Cli::try_parse_from(["azlin", "code"]);
        assert!(
            result.is_err(),
            "code without vm_identifier should fail to parse"
        );
    }

    // =====================================================================
    // 2. LIST COMMAND — missing --verbose flag (long-only, no -v short)
    // =====================================================================

    #[test]
    fn test_list_has_verbose_flag() {
        let cli = Cli::parse_from(["azlin", "list", "--verbose"]);
        if let Commands::List { verbose, .. } = cli.command {
            assert!(verbose, "list --verbose should set flag to true");
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_verbose_defaults_false() {
        let cli = Cli::parse_from(["azlin", "list"]);
        if let Commands::List { verbose, .. } = cli.command {
            assert!(!verbose, "list verbose should default to false");
        } else {
            panic!("Expected List command");
        }
    }

    #[test]
    fn test_list_verbose_does_not_conflict_with_global_v() {
        // Global -v is for global verbose; list --verbose is command-specific
        let cli = Cli::parse_from(["azlin", "-v", "list", "--verbose"]);
        assert!(cli.verbose, "global -v should be true");
        if let Commands::List { verbose, .. } = cli.command {
            assert!(verbose, "list --verbose should also be true");
        } else {
            panic!("Expected List command");
        }
    }

    // =====================================================================
    // 3. BATCH STOP — missing --no-deallocate flag (default: deallocate=true)
    // =====================================================================

    #[test]
    fn test_batch_stop_has_no_deallocate_flag() {
        let cli = Cli::parse_from(["azlin", "batch", "stop", "--no-deallocate"]);
        if let Commands::Batch {
            action: BatchAction::Stop { no_deallocate, .. },
        } = cli.command
        {
            assert!(
                no_deallocate,
                "batch stop --no-deallocate should set flag to true"
            );
        } else {
            panic!("Expected Batch Stop command");
        }
    }

    #[test]
    fn test_batch_stop_deallocate_defaults_false() {
        // no_deallocate defaults to false (meaning deallocate=true by default, matching Python)
        let cli = Cli::parse_from(["azlin", "batch", "stop"]);
        if let Commands::Batch {
            action: BatchAction::Stop { no_deallocate, .. },
        } = cli.command
        {
            assert!(
                !no_deallocate,
                "batch stop --no-deallocate should default to false"
            );
        } else {
            panic!("Expected Batch Stop command");
        }
    }

    // =====================================================================
    // 4. DISK ADD — missing --mount flag (default: "/tmp")
    // =====================================================================

    #[test]
    fn test_disk_add_has_mount_flag_with_default() {
        let cli = Cli::parse_from(["azlin", "disk", "add", "my-vm", "--size", "128"]);
        if let Commands::Disk {
            action: DiskAction::Add { mount, .. },
        } = cli.command
        {
            assert_eq!(
                mount, "/tmp",
                "disk add --mount should default to '/tmp'"
            );
        } else {
            panic!("Expected Disk Add command");
        }
    }

    #[test]
    fn test_disk_add_mount_override() {
        let cli = Cli::parse_from([
            "azlin", "disk", "add", "my-vm", "--size", "128", "--mount", "/mnt/data",
        ]);
        if let Commands::Disk {
            action: DiskAction::Add { mount, .. },
        } = cli.command
        {
            assert_eq!(
                mount, "/mnt/data",
                "disk add --mount should accept custom value"
            );
        } else {
            panic!("Expected Disk Add command");
        }
    }

    // =====================================================================
    // 5. FLEET RUN — missing --if-mem-below flag (Option<f64>)
    // =====================================================================

    #[test]
    fn test_fleet_run_has_if_mem_below_flag() {
        let cli = Cli::parse_from([
            "azlin",
            "fleet",
            "run",
            "echo hello",
            "--if-mem-below",
            "75.5",
        ]);
        if let Commands::Fleet {
            action: FleetAction::Run { if_mem_below, .. },
        } = cli.command
        {
            assert_eq!(
                if_mem_below,
                Some(75.5),
                "fleet run --if-mem-below should accept float value"
            );
        } else {
            panic!("Expected Fleet Run command");
        }
    }

    #[test]
    fn test_fleet_run_if_mem_below_defaults_none() {
        let cli = Cli::parse_from(["azlin", "fleet", "run", "echo hello"]);
        if let Commands::Fleet {
            action: FleetAction::Run { if_mem_below, .. },
        } = cli.command
        {
            assert_eq!(
                if_mem_below, None,
                "fleet run --if-mem-below should default to None"
            );
        } else {
            panic!("Expected Fleet Run command");
        }
    }

    // =====================================================================
    // 6. RESTORE — missing --dry-run, --no-multi-tab, --verbose flags
    // =====================================================================

    #[test]
    fn test_restore_has_dry_run_flag() {
        let cli = Cli::parse_from(["azlin", "restore", "--dry-run"]);
        if let Commands::Restore { dry_run, .. } = cli.command {
            assert!(dry_run, "restore --dry-run should set flag to true");
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_restore_dry_run_defaults_false() {
        let cli = Cli::parse_from(["azlin", "restore"]);
        if let Commands::Restore { dry_run, .. } = cli.command {
            assert!(!dry_run, "restore --dry-run should default to false");
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_restore_has_no_multi_tab_flag() {
        let cli = Cli::parse_from(["azlin", "restore", "--no-multi-tab"]);
        if let Commands::Restore { no_multi_tab, .. } = cli.command {
            assert!(
                no_multi_tab,
                "restore --no-multi-tab should set flag to true"
            );
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_restore_no_multi_tab_defaults_false() {
        let cli = Cli::parse_from(["azlin", "restore"]);
        if let Commands::Restore { no_multi_tab, .. } = cli.command {
            assert!(
                !no_multi_tab,
                "restore --no-multi-tab should default to false"
            );
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_restore_has_verbose_flag() {
        let cli = Cli::parse_from(["azlin", "restore", "--verbose"]);
        if let Commands::Restore { verbose, .. } = cli.command {
            assert!(verbose, "restore --verbose should set flag to true");
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_restore_verbose_defaults_false() {
        let cli = Cli::parse_from(["azlin", "restore"]);
        if let Commands::Restore { verbose, .. } = cli.command {
            assert!(!verbose, "restore --verbose should default to false");
        } else {
            panic!("Expected Restore command");
        }
    }

    // =====================================================================
    // 7. DEFAULT VALUE FIXES
    // =====================================================================

    #[test]
    fn test_disk_add_sku_defaults_to_standard_lrs() {
        let cli = Cli::parse_from(["azlin", "disk", "add", "my-vm", "--size", "128"]);
        if let Commands::Disk {
            action: DiskAction::Add { sku, .. },
        } = cli.command
        {
            assert_eq!(
                sku, "Standard_LRS",
                "disk add --sku should default to 'Standard_LRS' (Python parity)"
            );
        } else {
            panic!("Expected Disk Add command");
        }
    }

    #[test]
    fn test_autopilot_enable_idle_threshold_defaults_120() {
        let cli = Cli::parse_from(["azlin", "autopilot", "enable"]);
        if let Commands::Autopilot {
            action: AutopilotAction::Enable { idle_threshold, .. },
        } = cli.command
        {
            assert_eq!(
                idle_threshold, 120,
                "autopilot enable --idle-threshold should default to 120 (Python parity)"
            );
        } else {
            panic!("Expected Autopilot Enable command");
        }
    }

    #[test]
    fn test_autopilot_enable_cpu_threshold_defaults_20() {
        let cli = Cli::parse_from(["azlin", "autopilot", "enable"]);
        if let Commands::Autopilot {
            action:
                AutopilotAction::Enable {
                    cpu_threshold, ..
                },
        } = cli.command
        {
            assert_eq!(
                cpu_threshold, 20,
                "autopilot enable --cpu-threshold should default to 20 (Python parity)"
            );
        } else {
            panic!("Expected Autopilot Enable command");
        }
    }

    // =====================================================================
    // 8. DOIT DESTROY & DOIT DELETE — new subcommands
    // =====================================================================

    #[test]
    fn test_doit_destroy_parses() {
        let cli = Cli::parse_from(["azlin", "doit", "destroy"]);
        if let Commands::Doit {
            action: DoitAction::Destroy { .. },
        } = cli.command
        {
            // Parses successfully — variant exists
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_destroy_has_force_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "destroy", "--force"]);
        if let Commands::Doit {
            action: DoitAction::Destroy { force, .. },
        } = cli.command
        {
            assert!(force, "doit destroy --force should set flag to true");
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_destroy_has_dry_run_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "destroy", "--dry-run"]);
        if let Commands::Doit {
            action: DoitAction::Destroy { dry_run, .. },
        } = cli.command
        {
            assert!(dry_run, "doit destroy --dry-run should set flag to true");
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_destroy_has_username_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "destroy", "--username", "testuser"]);
        if let Commands::Doit {
            action: DoitAction::Destroy { username, .. },
        } = cli.command
        {
            assert_eq!(
                username,
                Some("testuser".to_string()),
                "doit destroy --username should accept value"
            );
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_destroy_defaults() {
        let cli = Cli::parse_from(["azlin", "doit", "destroy"]);
        if let Commands::Doit {
            action:
                DoitAction::Destroy {
                    force,
                    dry_run,
                    username,
                },
        } = cli.command
        {
            assert!(!force, "doit destroy --force should default to false");
            assert!(!dry_run, "doit destroy --dry-run should default to false");
            assert_eq!(
                username, None,
                "doit destroy --username should default to None"
            );
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_delete_parses() {
        let cli = Cli::parse_from(["azlin", "doit", "delete"]);
        if let Commands::Doit {
            action: DoitAction::Delete { .. },
        } = cli.command
        {
            // Parses successfully — variant exists
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    #[test]
    fn test_doit_delete_has_force_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "delete", "--force"]);
        if let Commands::Doit {
            action: DoitAction::Delete { force, .. },
        } = cli.command
        {
            assert!(force, "doit delete --force should set flag to true");
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    #[test]
    fn test_doit_delete_has_dry_run_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "delete", "--dry-run"]);
        if let Commands::Doit {
            action: DoitAction::Delete { dry_run, .. },
        } = cli.command
        {
            assert!(dry_run, "doit delete --dry-run should set flag to true");
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    #[test]
    fn test_doit_delete_has_username_flag() {
        let cli = Cli::parse_from(["azlin", "doit", "delete", "--username", "testuser"]);
        if let Commands::Doit {
            action: DoitAction::Delete { username, .. },
        } = cli.command
        {
            assert_eq!(
                username,
                Some("testuser".to_string()),
                "doit delete --username should accept value"
            );
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    #[test]
    fn test_doit_delete_defaults() {
        let cli = Cli::parse_from(["azlin", "doit", "delete"]);
        if let Commands::Doit {
            action:
                DoitAction::Delete {
                    force,
                    dry_run,
                    username,
                },
        } = cli.command
        {
            assert!(!force, "doit delete --force should default to false");
            assert!(!dry_run, "doit delete --dry-run should default to false");
            assert_eq!(
                username, None,
                "doit delete --username should default to None"
            );
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    // =====================================================================
    // 9. EXISTING DOIT COMMANDS STILL WORK (regression guard)
    // =====================================================================

    #[test]
    fn test_doit_cleanup_still_works() {
        let cli = Cli::parse_from(["azlin", "doit", "cleanup", "--force", "--dry-run"]);
        if let Commands::Doit {
            action:
                DoitAction::Cleanup {
                    force, dry_run, ..
                },
        } = cli.command
        {
            assert!(force);
            assert!(dry_run);
        } else {
            panic!("Expected Doit Cleanup command");
        }
    }

    #[test]
    fn test_doit_deploy_still_works() {
        let cli = Cli::parse_from(["azlin", "doit", "deploy", "create a vm", "--dry-run"]);
        if let Commands::Doit {
            action:
                DoitAction::Deploy {
                    request, dry_run, ..
                },
        } = cli.command
        {
            assert_eq!(request, "create a vm");
            assert!(dry_run);
        } else {
            panic!("Expected Doit Deploy command");
        }
    }

    #[test]
    fn test_doit_examples_still_works() {
        let cli = Cli::parse_from(["azlin", "doit", "examples"]);
        assert!(matches!(
            cli.command,
            Commands::Doit {
                action: DoitAction::Examples
            }
        ));
    }

    // =====================================================================
    // 10. HELP TEXT VERIFICATION — flags should appear in --help output
    // =====================================================================

    #[test]
    fn test_code_help_shows_new_flags() {
        let mut cmd = Cli::command();
        let code_cmd = cmd
            .find_subcommand_mut("code")
            .expect("code subcommand should exist");
        let help = format!("{}", code_cmd.render_help());
        assert!(help.contains("--user"), "code --help should show --user");
        assert!(help.contains("--key"), "code --help should show --key");
        assert!(
            help.contains("--no-extensions"),
            "code --help should show --no-extensions"
        );
        assert!(
            help.contains("--workspace"),
            "code --help should show --workspace"
        );
    }

    #[test]
    fn test_list_help_shows_verbose() {
        let mut cmd = Cli::command();
        let list_cmd = cmd
            .find_subcommand_mut("list")
            .expect("list subcommand should exist");
        let help = format!("{}", list_cmd.render_help());
        assert!(
            help.contains("--verbose"),
            "list --help should show --verbose"
        );
    }

    #[test]
    fn test_batch_stop_help_shows_no_deallocate() {
        let mut cmd = Cli::command();
        let batch_cmd = cmd
            .find_subcommand_mut("batch")
            .expect("batch subcommand should exist");
        let stop_cmd = batch_cmd
            .find_subcommand_mut("stop")
            .expect("batch stop subcommand should exist");
        let help = format!("{}", stop_cmd.render_help());
        assert!(
            help.contains("--no-deallocate"),
            "batch stop --help should show --no-deallocate"
        );
    }

    #[test]
    fn test_disk_add_help_shows_mount() {
        let mut cmd = Cli::command();
        let disk_cmd = cmd
            .find_subcommand_mut("disk")
            .expect("disk subcommand should exist");
        let add_cmd = disk_cmd
            .find_subcommand_mut("add")
            .expect("disk add subcommand should exist");
        let help = format!("{}", add_cmd.render_help());
        assert!(
            help.contains("--mount"),
            "disk add --help should show --mount"
        );
    }

    #[test]
    fn test_fleet_run_help_shows_if_mem_below() {
        let mut cmd = Cli::command();
        let fleet_cmd = cmd
            .find_subcommand_mut("fleet")
            .expect("fleet subcommand should exist");
        let run_cmd = fleet_cmd
            .find_subcommand_mut("run")
            .expect("fleet run subcommand should exist");
        let help = format!("{}", run_cmd.render_help());
        assert!(
            help.contains("--if-mem-below"),
            "fleet run --help should show --if-mem-below"
        );
    }

    #[test]
    fn test_restore_help_shows_new_flags() {
        let mut cmd = Cli::command();
        let restore_cmd = cmd
            .find_subcommand_mut("restore")
            .expect("restore subcommand should exist");
        let help = format!("{}", restore_cmd.render_help());
        assert!(
            help.contains("--dry-run"),
            "restore --help should show --dry-run"
        );
        assert!(
            help.contains("--no-multi-tab"),
            "restore --help should show --no-multi-tab"
        );
        assert!(
            help.contains("--verbose"),
            "restore --help should show --verbose"
        );
    }

    #[test]
    fn test_doit_help_shows_destroy_and_delete() {
        let mut cmd = Cli::command();
        let doit_cmd = cmd
            .find_subcommand_mut("doit")
            .expect("doit subcommand should exist");
        let help = format!("{}", doit_cmd.render_help());
        assert!(
            help.contains("destroy"),
            "doit --help should show 'destroy' subcommand"
        );
        assert!(
            help.contains("delete"),
            "doit --help should show 'delete' subcommand"
        );
    }

    // =====================================================================
    // 11. EDGE CASES — combined flags, boundary values
    // =====================================================================

    #[test]
    fn test_code_all_new_flags_together() {
        let cli = Cli::parse_from([
            "azlin",
            "code",
            "my-vm",
            "--user",
            "devuser",
            "--key",
            "/tmp/key",
            "--no-extensions",
            "--workspace",
            "/projects",
        ]);
        if let Commands::Code {
            vm_identifier,
            user,
            key,
            no_extensions,
            workspace,
            ..
        } = cli.command
        {
            assert_eq!(vm_identifier, "my-vm");
            assert_eq!(user, "devuser");
            assert_eq!(key, Some(std::path::PathBuf::from("/tmp/key")));
            assert!(no_extensions);
            assert_eq!(workspace, "/projects");
        } else {
            panic!("Expected Code command");
        }
    }

    #[test]
    fn test_restore_all_new_flags_together() {
        let cli = Cli::parse_from([
            "azlin",
            "restore",
            "--dry-run",
            "--no-multi-tab",
            "--verbose",
        ]);
        if let Commands::Restore {
            dry_run,
            no_multi_tab,
            verbose,
            ..
        } = cli.command
        {
            assert!(dry_run);
            assert!(no_multi_tab);
            assert!(verbose);
        } else {
            panic!("Expected Restore command");
        }
    }

    #[test]
    fn test_autopilot_enable_custom_thresholds() {
        let cli = Cli::parse_from([
            "azlin",
            "autopilot",
            "enable",
            "--idle-threshold",
            "60",
            "--cpu-threshold",
            "50",
        ]);
        if let Commands::Autopilot {
            action:
                AutopilotAction::Enable {
                    idle_threshold,
                    cpu_threshold,
                    ..
                },
        } = cli.command
        {
            assert_eq!(idle_threshold, 60);
            assert_eq!(cpu_threshold, 50);
        } else {
            panic!("Expected Autopilot Enable command");
        }
    }

    #[test]
    fn test_disk_add_sku_override_still_works() {
        let cli = Cli::parse_from([
            "azlin",
            "disk",
            "add",
            "my-vm",
            "--size",
            "256",
            "--sku",
            "Premium_LRS",
        ]);
        if let Commands::Disk {
            action: DiskAction::Add { sku, .. },
        } = cli.command
        {
            assert_eq!(
                sku, "Premium_LRS",
                "explicit --sku Premium_LRS should override default"
            );
        } else {
            panic!("Expected Disk Add command");
        }
    }

    #[test]
    fn test_fleet_run_if_mem_below_zero() {
        let cli = Cli::parse_from([
            "azlin",
            "fleet",
            "run",
            "echo hello",
            "--if-mem-below",
            "0.0",
        ]);
        if let Commands::Fleet {
            action: FleetAction::Run { if_mem_below, .. },
        } = cli.command
        {
            assert_eq!(if_mem_below, Some(0.0));
        } else {
            panic!("Expected Fleet Run command");
        }
    }

    #[test]
    fn test_fleet_run_if_mem_below_100() {
        let cli = Cli::parse_from([
            "azlin",
            "fleet",
            "run",
            "echo hello",
            "--if-mem-below",
            "100.0",
        ]);
        if let Commands::Fleet {
            action: FleetAction::Run { if_mem_below, .. },
        } = cli.command
        {
            assert_eq!(if_mem_below, Some(100.0));
        } else {
            panic!("Expected Fleet Run command");
        }
    }

    #[test]
    fn test_doit_destroy_all_flags_together() {
        let cli = Cli::parse_from([
            "azlin",
            "doit",
            "destroy",
            "--force",
            "--dry-run",
            "--username",
            "admin",
        ]);
        if let Commands::Doit {
            action:
                DoitAction::Destroy {
                    force,
                    dry_run,
                    username,
                },
        } = cli.command
        {
            assert!(force);
            assert!(dry_run);
            assert_eq!(username, Some("admin".to_string()));
        } else {
            panic!("Expected Doit Destroy command");
        }
    }

    #[test]
    fn test_doit_delete_all_flags_together() {
        let cli = Cli::parse_from([
            "azlin",
            "doit",
            "delete",
            "--force",
            "--dry-run",
            "--username",
            "admin",
        ]);
        if let Commands::Doit {
            action:
                DoitAction::Delete {
                    force,
                    dry_run,
                    username,
                },
        } = cli.command
        {
            assert!(force);
            assert!(dry_run);
            assert_eq!(username, Some("admin".to_string()));
        } else {
            panic!("Expected Doit Delete command");
        }
    }

    // =====================================================================
    // 12. LOGS COMMAND — default value corrections + missing enum variants
    //
    //     Python CLI defaults: --lines 100, --type syslog
    //     Rust CLI (current):  --lines 50,  --type cloud-init
    //     Missing LogType variants: Azlin, All
    // =====================================================================

    #[test]
    fn test_logs_default_lines_is_100() {
        // Python CLI defaulted --lines to 100; Rust currently defaults to 50
        let cli = Cli::parse_from(["azlin", "logs", "my-vm"]);
        if let Commands::Logs { lines, .. } = cli.command {
            assert_eq!(lines, 100, "logs --lines should default to 100 (Python parity)");
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_default_type_is_syslog() {
        // Python CLI defaulted --type to syslog; Rust currently defaults to cloud-init
        let cli = Cli::parse_from(["azlin", "logs", "my-vm"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::Syslog),
                "logs --type should default to syslog (Python parity), got {:?}",
                log_type
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_type_azlin_variant_parses() {
        // LogType must include an Azlin variant for /var/log/azlin/azlin.log
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "--type", "azlin"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::Azlin),
                "logs --type azlin should parse to LogType::Azlin, got {:?}",
                log_type
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_type_all_variant_parses() {
        // LogType must include an All variant that shows all log sources
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "--type", "all"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::All),
                "logs --type all should parse to LogType::All, got {:?}",
                log_type
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_type_azlin_short_flag() {
        // -t azlin should also work (short form of --type)
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "-t", "azlin"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::Azlin),
                "-t azlin should parse to LogType::Azlin"
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_type_all_short_flag() {
        // -t all should also work (short form of --type)
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "-t", "all"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::All),
                "-t all should parse to LogType::All"
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_log_type_enum_has_five_variants() {
        // LogType should have exactly 5 variants: CloudInit, Syslog, Auth, Azlin, All
        // We verify by parsing all 5 possible values
        let variants = ["cloud-init", "syslog", "auth", "azlin", "all"];
        for v in &variants {
            let cli = Cli::parse_from(["azlin", "logs", "my-vm", "--type", v]);
            assert!(
                matches!(cli.command, Commands::Logs { .. }),
                "Failed to parse --type {} as valid LogType variant",
                v
            );
        }
    }

    #[test]
    fn test_logs_explicit_lines_override_still_works() {
        // Explicit -n value should override the new default
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "-n", "42"]);
        if let Commands::Logs { lines, .. } = cli.command {
            assert_eq!(lines, 42, "explicit -n 42 should override default");
        } else {
            panic!("Expected Logs command");
        }
    }

    #[test]
    fn test_logs_explicit_type_cloud_init_still_works() {
        // Even though default changed, explicit --type cloud-init must still work
        let cli = Cli::parse_from(["azlin", "logs", "my-vm", "--type", "cloud-init"]);
        if let Commands::Logs { log_type, .. } = cli.command {
            assert!(
                matches!(log_type, LogType::CloudInit),
                "explicit --type cloud-init should still parse correctly"
            );
        } else {
            panic!("Expected Logs command");
        }
    }

    // =====================================================================
    // 13. CLI STRUCTURE VALIDATION — clap debug_assert still passes
    // =====================================================================

    #[test]
    fn test_cli_structure_valid_after_parity_changes() {
        // clap's debug_assert validates there are no duplicate flags,
        // conflicting short options, or invalid argument configurations
        Cli::command().debug_assert();
    }
}
