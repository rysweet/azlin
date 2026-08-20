//! `azlin gui install` — install the containerised remote desktop on a VM.
//!
//! `azlin gui` installs a desktop with the VM's package manager, which only
//! works when the VM's repositories carry one. This command is the alternative:
//! the whole desktop stack runs as a pinned container on the VM's Docker.
//!
//! The install is **protocol-agnostic**: it provisions the desktop *and both*
//! protocol servers, because which one will be used is not known until the user
//! connects. The protocol is chosen at connect time with
//! `azlin gui <vm> --protocol vnc|rdp`.
//!
//! This module is deliberately thin. Every decision — which image, which port,
//! how the container is created, how failures are classified — lives in
//! [`azlin_core::gui_container`], which is pure and unit-tested without a VM.
//! Here we only resolve the VM, run the generated script over the existing SSH
//! or bastion route, and surface the result.
//!
//! # Security
//!
//! No Azure network security group rule is created, modified or read. The
//! desktop port is published on the VM's loopback interface only and is reached
//! exclusively through azlin's SSH tunnel.

#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use azlin_core::gui_container::{
    build_install_script, build_uninstall_script, describe_install_failure, DesktopGeometry,
    GuiInstallPlan, RDP_BRIDGE_PORT,
};

/// Hard timeout for the install phase. Pulling a desktop image is the slow part.
const GUI_INSTALL_TIMEOUT_SECS: u64 = 1_200;

/// Timeout for the (fast) uninstall phase.
const GUI_UNINSTALL_TIMEOUT_SECS: u64 = 120;

pub(crate) async fn dispatch(
    action: azlin_cli::GuiAction,
    _verbose: bool,
    _output: &azlin_cli::OutputFormat,
) -> Result<()> {
    let azlin_cli::GuiAction::Install {
        vm_identifier,
        uninstall,
        resource_group,
        user,
        key,
        resolution,
        depth,
        yes: _yes,
        protocol: deprecated_protocol,
    } = action;

    // `azlin gui install --protocol <x>` shipped in a release. It no longer
    // means anything — one install serves both protocols — but silently
    // breaking a flag that worked yesterday is worse than carrying a warning.
    if let Some(protocol) = deprecated_protocol {
        let name = match protocol {
            azlin_cli::GuiProtocolArg::Vnc => "vnc",
            azlin_cli::GuiProtocolArg::Rdp => "rdp",
        };
        eprintln!(
            "warning: `--protocol {name}` is deprecated on `gui install` and has no effect.\n\
             \x20        The install now provides both VNC and RDP; choose the protocol when you \
             connect:\n           azlin gui <vm> --protocol {name}"
        );
    }

    if !crate::cmd_gui::is_valid_resolution(&resolution) {
        anyhow::bail!(
            "Invalid resolution '{}'. Expected format: WIDTHxHEIGHT (e.g. 1920x1080)",
            resolution
        );
    }

    let Some(name) = vm_identifier else {
        anyhow::bail!("VM name is required. Usage: azlin gui install <vm-name>")
    };

    let rg = resolve_resource_group(resource_group)?;

    let pb = penguin_spinner(&format!("Looking up {}...", name));
    let mut target = resolve_vm_ssh_target(&name, None, Some(rg)).await?;
    target.user = crate::cmd_gui::resolve_gui_target_user(&user, &target.user);
    pb.finish_and_clear();

    let effective_key = key.or_else(resolve_ssh_key);

    if uninstall {
        return run_uninstall(&target, effective_key.as_deref()).await;
    }

    let plan = GuiInstallPlan::new(DesktopGeometry {
        resolution: resolution.clone(),
        depth,
    });

    println!(
        "Installing the desktop on {} using {}",
        name, plan.image.reference
    );
    println!(
        "  ports {} (VNC) and {} (RDP) are published on the VM's loopback interface only; \
         connect with `azlin gui {}`",
        plan.host_port, RDP_BRIDGE_PORT, name
    );

    let pb =
        penguin_spinner("Installing remote desktop container (this can take a few minutes)...");
    let result = crate::dispatch_helpers::run_target_command_with_timeout(
        &target,
        &wrap_for_shell(&build_install_script(&plan)),
        GUI_INSTALL_TIMEOUT_SECS,
        effective_key.as_deref(),
    )
    .await;
    pb.finish_and_clear();

    let outcome = classify_install_result(result, GUI_INSTALL_TIMEOUT_SECS)?;
    match outcome {
        InstallOutcome::AlreadyInstalled => {
            println!(
                "Remote desktop already installed ({}).",
                plan.image.reference
            )
        }
        InstallOutcome::Installed => {
            println!("Remote desktop installed ({}).", plan.image.reference)
        }
        InstallOutcome::InstalledVncOnly => {
            println!("Remote desktop installed ({}).", plan.image.reference);
            eprintln!(
                "warning: the RDP bridge could not be set up, so only VNC is available on this \
                 VM.\n         Re-run this command to retry it; `azlin gui {} --protocol vnc` \
                 works now.",
                name
            );
        }
    }
    // Only advertise the protocols that actually work. When the bridge failed,
    // printing the RDP connect line tells the user on stdout that a protocol is
    // available immediately after warning on stderr that it is not.
    let rdp_available = outcome != InstallOutcome::InstalledVncOnly;
    if rdp_available {
        println!("  clients: {}", plan.image.client_support);
    } else {
        println!("  clients: any standard VNC viewer");
    }
    // No padding before the annotation: `name` is variable-length, so the
    // spaces never aligned it with anything and the following line has none.
    println!("  connect: azlin gui {} (VNC, the default)", name);
    if rdp_available {
        println!("  connect: azlin gui {} --protocol rdp", name);
    }

    Ok(())
}

/// Result of a successful install run.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum InstallOutcome {
    /// A matching container was already present and was (re)started.
    AlreadyInstalled,
    /// The container was created.
    Installed,
    /// The desktop was created but the RDP bridge could not be built or
    /// started. VNC works; RDP does not. Degrading here rather than failing is
    /// deliberate — a desktop that serves one protocol beats no desktop.
    InstalledVncOnly,
}

/// Classify the outcome of running the install script on the VM.
///
/// A zero exit that does not carry the expected `azlin-result:` marker is
/// treated as a failure. Reporting success for a step that silently did nothing
/// is exactly the bug class this guards against.
pub(crate) fn classify_install_result(
    result: Result<(i32, String, String)>,
    timeout_secs: u64,
) -> Result<InstallOutcome> {
    match result {
        Ok((0, stdout, _)) => parse_install_success(&stdout),
        Ok((code, _, stderr)) => anyhow::bail!(
            "{}",
            describe_install_failure(code, &azlin_core::sanitizer::sanitize(&stderr))
        ),
        Err(err) => {
            let msg = err.to_string();
            if msg.contains("timed out") {
                anyhow::bail!(
                    "GUI install timed out after {} minutes. The image pull is usually the slow \
                     step; check the VM's outbound network access and retry.",
                    timeout_secs / 60
                );
            }
            anyhow::bail!(
                "GUI install failed: {}",
                azlin_core::sanitizer::sanitize(&msg)
            );
        }
    }
}

/// Interpret the install script's stdout marker.
pub(crate) fn parse_install_success(stdout: &str) -> Result<InstallOutcome> {
    for line in stdout.lines() {
        match line.trim() {
            "azlin-result: already-installed" => return Ok(InstallOutcome::AlreadyInstalled),
            "azlin-result: installed" => return Ok(InstallOutcome::Installed),
            "azlin-result: installed-vnc-only" => return Ok(InstallOutcome::InstalledVncOnly),
            _ => {}
        }
    }
    anyhow::bail!(
        "GUI install reported success but produced no completion marker, so the desktop may not \
         actually be installed. Re-run with --verbose, or check `docker ps -a` on the VM."
    )
}

async fn run_uninstall(target: &VmSshTarget, key_override: Option<&std::path::Path>) -> Result<()> {
    let script = wrap_for_shell(&build_uninstall_script());
    let pb = penguin_spinner("Removing remote desktop container...");
    let result = crate::dispatch_helpers::run_target_command_with_timeout(
        target,
        &script,
        GUI_UNINSTALL_TIMEOUT_SECS,
        key_override,
    )
    .await;
    pb.finish_and_clear();

    match result {
        Ok((0, _, _)) => {
            println!("Remote desktop removed.");
            Ok(())
        }
        Ok((code, _, stderr)) => anyhow::bail!(
            "Failed to remove the remote desktop (exit {}): {}",
            code,
            azlin_core::sanitizer::sanitize(stderr.trim())
        ),
        Err(err) => anyhow::bail!(
            "Failed to remove the remote desktop: {}",
            azlin_core::sanitizer::sanitize(&err.to_string())
        ),
    }
}

/// Wrap a generated script so it runs under a login shell on the VM.
pub(crate) fn wrap_for_shell(script: &str) -> String {
    format!("bash -lc {}", crate::dispatch_helpers::shell_escape(script))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn plan() -> GuiInstallPlan {
        GuiInstallPlan::new(DesktopGeometry::default())
    }

    fn ok(stdout: &str) -> Result<(i32, String, String)> {
        Ok((0, stdout.to_string(), String::new()))
    }

    fn failed(code: i32, stderr: &str) -> Result<(i32, String, String)> {
        Ok((code, String::new(), stderr.to_string()))
    }

    #[test]
    fn a_created_container_reports_installed() {
        let outcome = classify_install_result(ok("azlin-result: installed\n"), 60).unwrap();
        assert_eq!(outcome, InstallOutcome::Installed);
    }

    #[test]
    fn a_matching_container_reports_already_installed() {
        let outcome = classify_install_result(ok("azlin-result: already-installed\n"), 60).unwrap();
        assert_eq!(outcome, InstallOutcome::AlreadyInstalled);
    }

    /// A bridge failure must degrade, not fail: the user still has a desktop.
    #[test]
    fn a_failed_bridge_reports_a_vnc_only_install_rather_than_an_error() {
        let outcome =
            classify_install_result(ok("azlin-result: installed-vnc-only\n"), 60).unwrap();
        assert_eq!(outcome, InstallOutcome::InstalledVncOnly);
    }

    #[test]
    fn a_silent_success_is_treated_as_a_failure() {
        // A script that exits 0 without doing anything must not be reported as a
        // successful install.
        let err = classify_install_result(ok(""), 60).unwrap_err().to_string();
        assert!(err.contains("no completion marker"), "got: {err}");
    }

    #[test]
    fn docker_missing_produces_a_distro_neutral_remedy() {
        let err = classify_install_result(
            failed(2, "azlin-error: docker is not installed on this VM\n"),
            60,
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains("docker is not installed"));
        assert!(err.contains("docs.docker.com"));
        assert!(!err.contains("apt-get") && !err.contains("dnf"));
    }

    #[test]
    fn permission_failure_points_at_the_docker_group() {
        let err = classify_install_result(
            failed(
                3,
                "azlin-error: the docker daemon is not reachable as this user\n",
            ),
            60,
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains("usermod -aG docker"));
    }

    #[test]
    fn pull_failure_is_surfaced_not_swallowed() {
        let err = classify_install_result(
            failed(
                4,
                "azlin-error: failed to pull the desktop container image: no route to host\n",
            ),
            60,
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains("failed to pull"));
        assert!(err.contains("outbound network access"));
    }

    #[test]
    fn disk_exhaustion_is_reported_distinctly() {
        let err = classify_install_result(
            failed(
                7,
                "azlin-error: less than 4 GiB free for the container image\n",
            ),
            60,
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains("Free disk space"));
    }

    #[test]
    fn a_timeout_explains_the_likely_cause() {
        let err = classify_install_result(Err(anyhow::anyhow!("command timed out")), 1_200)
            .unwrap_err()
            .to_string();
        assert!(err.contains("timed out after 20 minutes"), "got: {err}");
    }

    #[test]
    fn a_transport_failure_is_reported_as_such() {
        let err = classify_install_result(Err(anyhow::anyhow!("ssh: connect refused")), 60)
            .unwrap_err()
            .to_string();
        assert!(err.contains("GUI install failed"));
        assert!(err.contains("connect refused"));
    }

    #[test]
    fn the_script_is_passed_through_a_login_shell() {
        let script = wrap_for_shell(&build_install_script(&plan()));
        assert!(script.starts_with("bash -lc "));
    }

    #[test]
    fn install_never_emits_an_azure_networking_command() {
        let script = wrap_for_shell(&build_install_script(&plan())).to_ascii_lowercase();
        for forbidden in ["nsg", "az network", "network-security"] {
            assert!(
                !script.contains(forbidden),
                "install must never touch Azure networking ({forbidden})"
            );
        }
    }

    #[test]
    fn uninstall_removes_the_container_and_its_state_without_touching_azure() {
        let script = wrap_for_shell(&build_uninstall_script());
        assert!(script.contains("docker rm -f"));
        assert!(script.contains(".azlin/gui"));
        assert!(!script.to_ascii_lowercase().contains("nsg"));
    }
}
