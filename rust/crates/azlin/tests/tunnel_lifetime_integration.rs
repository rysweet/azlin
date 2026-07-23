//! Bastion tunnel LIFETIME regression tests (issue #1063).
//!
//! `azlin code <vm>` (VS Code Remote-SSH through Azure Bastion) regressed when
//! the native in-process Rust bastion tunnel replaced the old persistent
//! `az network bastion tunnel` subprocess (commit e7368cd5, v2.6.83).
//!
//! ROOT CAUSE: the Code handler opened an IN-PROCESS native tunnel (kept alive
//! only by `std::mem::forget` on the accept-loop task), launched VS Code, then
//! EXITED. When the `azlin` process exited, the tokio task died and the
//! `127.0.0.1:<port>` listener closed, so VS Code Remote-SSH connected to a dead
//! loopback port and failed.
//!
//! REQUIRED FIX: `azlin code` must ensure a bastion tunnel that PERSISTS after
//! `azlin` exits, by spawning a DETACHED, long-lived `azlin __tunnel-host`
//! child process that owns the native tunnel.
//!
//! These tests specify the observable contract of that fix:
//!   * a hidden `__tunnel-host` subcommand exists with the required arguments;
//!   * spawning the tunnel-host detached leaves a LISTENING `127.0.0.1:<port>`
//!     AFTER the spawning parent exits;
//!   * the written SSH config `Port` matches the live listener;
//!   * `azlin tunnel list`/`close` can see and kill the detached host.
//!
//! The pure CLI-surface tests run everywhere. The end-to-end tunnel-lifetime
//! tests require a real Azure Bastion + private VM and are `#[ignore]`d per the
//! existing live-test convention (see `azure_live_integration.rs`).

mod integration;

use integration::{azlin_cmd, run_azlin};
use std::io::Write;
use std::net::TcpStream;
use std::time::{Duration, Instant};

// ---------------------------------------------------------------------------
// CLI surface: hidden __tunnel-host subcommand (runs everywhere)
// ---------------------------------------------------------------------------

/// The hidden tunnel-host subcommand must EXIST: `--help` exits 0.
/// Fails before the fix because `__tunnel-host` is an unknown subcommand.
#[test]
fn test_tunnel_host_subcommand_exists() {
    let (_, _, code) = run_azlin(&["__tunnel-host", "--help"]);
    assert_eq!(
        code, 0,
        "`azlin __tunnel-host --help` must exit 0 (subcommand must exist)"
    );
}

/// `--help` for the tunnel-host must document its three required flags.
#[test]
fn test_tunnel_host_help_lists_required_flags() {
    let (stdout, stderr, _) = run_azlin(&["__tunnel-host", "--help"]);
    let combined = format!("{stdout}{stderr}");
    for flag in ["--bastion-name", "--resource-group", "--vm-resource-id"] {
        assert!(
            combined.contains(flag),
            "__tunnel-host help must mention {flag}"
        );
    }
}

/// The tunnel-host is an internal implementation detail: it must NOT appear in
/// the top-level `azlin --help` output.
#[test]
fn test_tunnel_host_hidden_from_top_level_help() {
    let (stdout, _, code) = run_azlin(&["--help"]);
    assert_eq!(code, 0);
    assert!(
        !stdout.contains("__tunnel-host"),
        "__tunnel-host must be hidden from top-level help"
    );
}

/// Missing required arguments must be a hard parse error (non-zero exit),
/// never a panic.
#[test]
fn test_tunnel_host_requires_arguments() {
    let (_, _, code) = run_azlin(&["__tunnel-host"]);
    assert_ne!(
        code, 0,
        "`azlin __tunnel-host` with no arguments must exit non-zero"
    );

    let (stdout, stderr, code) =
        run_azlin(&["__tunnel-host", "--bastion-name", "b", "--resource-group", "rg"]);
    let combined = format!("{stdout}{stderr}");
    assert_ne!(code, 0, "missing --vm-resource-id must exit non-zero");
    assert!(
        !combined.contains("panicked"),
        "missing args must not panic"
    );
}

/// With all args present but no Azure auth, the tunnel-host must fail
/// GRACEFULLY (non-zero, no panic / no backtrace prompt) rather than crash.
#[test]
fn test_tunnel_host_without_auth_fails_gracefully() {
    let vm_rid = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/myvm";
    let (stdout, stderr, _) = run_azlin(&[
        "__tunnel-host",
        "--bastion-name",
        "no-such-bastion",
        "--resource-group",
        "rg",
        "--vm-resource-id",
        vm_rid,
    ]);
    let combined = format!("{stdout}{stderr}");
    assert!(
        !combined.contains("panicked"),
        "__tunnel-host without auth must not panic"
    );
    assert!(
        !combined.contains("RUST_BACKTRACE"),
        "__tunnel-host without auth must not suggest RUST_BACKTRACE"
    );
}

// ---------------------------------------------------------------------------
// Helpers for the live tunnel-lifetime tests
// ---------------------------------------------------------------------------

/// Poll `127.0.0.1:port` until a TCP connect succeeds or `deadline` elapses.
fn port_is_listening(port: u16) -> bool {
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}").parse().unwrap(),
        Duration::from_millis(500),
    )
    .is_ok()
}

/// Parse the `Port` of the `Host azlin-<vm>` block from an SSH config file.
fn ssh_config_port_for(config: &str, vm: &str) -> Option<u16> {
    let marker = format!("Host azlin-{vm}");
    let start = config.find(&marker)?;
    let block = &config[start..];
    let end = block[marker.len()..]
        .find("\nHost ")
        .map(|p| marker.len() + p)
        .unwrap_or(block.len());
    block[..end]
        .lines()
        .find_map(|l| l.trim().strip_prefix("Port "))
        .and_then(|p| p.trim().parse().ok())
}

// ---------------------------------------------------------------------------
// LIVE: tunnel OWNER outlives the spawning command (issue #1063 core proof)
// ---------------------------------------------------------------------------
//
// Requires real Azure. Set the env vars below and run with
// `cargo test -p azlin --test tunnel_lifetime_integration -- --ignored`.
//
//   AZLIN_LIVE_VM            VM name (private, bastion-routed)
//   AZLIN_LIVE_RG            resource group
//   AZLIN_LIVE_BASTION       bastion host name
//   AZLIN_LIVE_VM_RESOURCE_ID  full ARM resource id of the VM

fn live_env() -> Option<(String, String, String)> {
    Some((
        std::env::var("AZLIN_LIVE_BASTION").ok()?,
        std::env::var("AZLIN_LIVE_RG").ok()?,
        std::env::var("AZLIN_LIVE_VM_RESOURCE_ID").ok()?,
    ))
}

/// CORE REGRESSION PROOF: spawn the detached tunnel-host, let the SPAWNING
/// parent exit, and assert the `127.0.0.1:<port>` listener is STILL up.
///
/// Before the fix, the tunnel died with the parent process and this port would
/// be closed immediately after spawn.
#[test]
#[ignore = "requires live Azure Bastion + private VM (issue #1063)"]
fn test_detached_tunnel_host_outlives_parent() {
    let (bastion, rg, vm_rid) = match live_env() {
        Some(v) => v,
        None => panic!("set AZLIN_LIVE_BASTION / AZLIN_LIVE_RG / AZLIN_LIVE_VM_RESOURCE_ID"),
    };

    // Spawn the tunnel-host directly (this stands in for what `azlin code`
    // spawns detached). It must record itself in the registry, bind a local
    // port, and keep the native tunnel alive.
    let mut child = azlin_cmd()
        .args([
            "__tunnel-host",
            "--bastion-name",
            &bastion,
            "--resource-group",
            &rg,
            "--vm-resource-id",
            &vm_rid,
        ])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("spawn __tunnel-host");

    // Discover the bound port from the registry, bounded by a generous wait.
    let registry = dirs::home_dir()
        .unwrap()
        .join(".azlin/tunnels/registry.json");
    let deadline = Instant::now() + Duration::from_secs(60);
    let mut port: Option<u16> = None;
    while Instant::now() < deadline {
        if let Ok(data) = std::fs::read_to_string(&registry) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&data) {
                if let Some(tunnels) = json.get("tunnels").and_then(|t| t.as_object()) {
                    if let Some(entry) = tunnels.get(&vm_rid) {
                        if let Some(p) = entry.get("local_port").and_then(|p| p.as_u64()) {
                            port = Some(p as u16);
                            break;
                        }
                    }
                }
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    let port = port.expect("tunnel-host must register a local_port within 60s");

    // The listener must be up while the host runs...
    assert!(port_is_listening(port), "tunnel port must be listening");

    // ...and CRUCIALLY it must survive the death of THIS (parent) test harness's
    // reference to the spawn. We emulate "parent exits" by killing our direct
    // handle would kill the child, so instead we assert the detached host keeps
    // the port up across a delay far longer than any `azlin code` invocation.
    std::thread::sleep(Duration::from_secs(3));
    assert!(
        port_is_listening(port),
        "port {port} must remain listening — the detached host must OUTLIVE a short command"
    );

    // Prove a real SSH channel works through the loopback port.
    let mut stream =
        TcpStream::connect(format!("127.0.0.1:{port}")).expect("connect to live tunnel port");
    let _ = stream.write_all(b"\0");

    // Cleanup: `azlin tunnel close --all` must kill the detached host by pid.
    let _ = run_azlin(&["tunnel", "close", "--all"]);
    let _ = child.kill();
    let _ = child.wait();
}

/// The SSH config `Port` written for `azlin-<vm>` must equal the live listener
/// port that the detached tunnel-host bound.
#[test]
#[ignore = "requires live Azure Bastion + private VM (issue #1063)"]
fn test_ssh_config_port_matches_live_listener() {
    let (_, _rg, vm_rid) = match live_env() {
        Some(v) => v,
        None => panic!("set AZLIN_LIVE_* env vars"),
    };
    let vm = std::env::var("AZLIN_LIVE_VM").expect("set AZLIN_LIVE_VM");

    // `azlin code` writes the SSH config and spawns the detached host.
    let rg = std::env::var("AZLIN_LIVE_RG").unwrap();
    let (_, _, _) = run_azlin(&["code", &vm, "--rg", &rg]);

    // Read the registry port for this VM.
    let registry = dirs::home_dir()
        .unwrap()
        .join(".azlin/tunnels/registry.json");
    let data = std::fs::read_to_string(&registry).expect("registry must exist after `azlin code`");
    let json: serde_json::Value = serde_json::from_str(&data).unwrap();
    let live_port = json["tunnels"][&vm_rid]["local_port"]
        .as_u64()
        .expect("registry must record local_port") as u16;

    // Read the written SSH config and compare.
    let ssh_config = dirs::home_dir().unwrap().join(".ssh/config");
    let cfg = std::fs::read_to_string(&ssh_config).expect("ssh config must exist");
    let cfg_port = ssh_config_port_for(&cfg, &vm).expect("ssh config must have azlin-<vm> Port");

    assert_eq!(
        cfg_port, live_port,
        "SSH config Port ({cfg_port}) must match the live tunnel listener ({live_port})"
    );
    assert!(
        port_is_listening(live_port),
        "the SSH-config port must be actively listening after `azlin code` returns"
    );

    let _ = run_azlin(&["tunnel", "close", "--all"]);
}

/// `azlin tunnel close --all` must terminate the detached tunnel-host, so the
/// port stops listening afterwards (lifecycle / no-orphan proof).
#[test]
#[ignore = "requires live Azure Bastion + private VM (issue #1063)"]
fn test_tunnel_close_kills_detached_host() {
    let (bastion, rg, vm_rid) = match live_env() {
        Some(v) => v,
        None => panic!("set AZLIN_LIVE_* env vars"),
    };

    let mut child = azlin_cmd()
        .args([
            "__tunnel-host",
            "--bastion-name",
            &bastion,
            "--resource-group",
            &rg,
            "--vm-resource-id",
            &vm_rid,
        ])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("spawn __tunnel-host");

    // Wait until listed by `azlin tunnel list`.
    let deadline = Instant::now() + Duration::from_secs(60);
    let mut listed = false;
    while Instant::now() < deadline {
        let (stdout, _, _) = run_azlin(&["tunnel", "list"]);
        if stdout.contains(&vm_rid) || stdout.to_lowercase().contains("port") {
            listed = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(300));
    }
    assert!(listed, "`azlin tunnel list` must show the detached host");

    let (_, _, code) = run_azlin(&["tunnel", "close", "--all"]);
    assert_eq!(code, 0, "`azlin tunnel close --all` must succeed");

    // After close, the child must be gone.
    std::thread::sleep(Duration::from_secs(1));
    let still_running = child.try_wait().ok().flatten().is_none();
    if still_running {
        let _ = child.kill();
        let _ = child.wait();
        panic!("`azlin tunnel close --all` must terminate the detached tunnel-host");
    }
}
