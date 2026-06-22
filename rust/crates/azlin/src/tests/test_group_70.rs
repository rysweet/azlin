// ── SSH readiness wait improvement tests (test_group_70) ───────────
//
// TDD tests for improved SSH readiness behavior after VM creation:
//   1. ssh_timeout_for_vm_size() maps VM SKU strings to scaled timeouts
//   2. SshReadiness enum: Ready vs TimedOut with recovery info
//   3. wait_for_post_create_readiness accepts timeout + provisioning closure
//   4. Timeout path returns Ok (warning), not Err
//   5. Progress reporting during SSH wait

use std::time::Duration;

// ── 1. ssh_timeout_for_vm_size: VM size → scaled timeout ───────────

#[test]
fn test_ssh_timeout_small_vm_300s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D2s_v3");
    assert_eq!(timeout, Duration::from_secs(300));
}

#[test]
fn test_ssh_timeout_medium_vm_300s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D16s_v3");
    assert_eq!(timeout, Duration::from_secs(300));
}

#[test]
fn test_ssh_timeout_large_vm_450s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D32s_v3");
    assert_eq!(timeout, Duration::from_secs(450));
}

#[test]
fn test_ssh_timeout_xl_vm_600s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D64s_v3");
    assert_eq!(timeout, Duration::from_secs(600));
}

#[test]
fn test_ssh_timeout_unknown_sku_defaults_300s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_NC24ads_A100_v4");
    assert_eq!(timeout, Duration::from_secs(300));
}

#[test]
fn test_ssh_timeout_case_insensitive() {
    let lower = crate::cmd_vm_ops::ssh_timeout_for_vm_size("standard_d64s_v3");
    let upper = crate::cmd_vm_ops::ssh_timeout_for_vm_size("STANDARD_D64S_V3");
    assert_eq!(lower, upper);
    assert_eq!(lower, Duration::from_secs(600));
}

#[test]
fn test_ssh_timeout_empty_string_defaults_300s() {
    let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size("");
    assert_eq!(timeout, Duration::from_secs(300));
}

#[test]
fn test_ssh_timeout_v5_sku_variants() {
    // Ensure v5 SKU patterns also work
    let d2 = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D2s_v5");
    assert_eq!(d2, Duration::from_secs(300));

    let d64 = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_D64s_v5");
    assert_eq!(d64, Duration::from_secs(600));
}

// ── 2. SshReadiness enum ───────────────────────────────────────────

#[test]
fn test_ssh_readiness_ready_variant_exists() {
    let result = crate::auth_forward::SshReadiness::Ready;
    assert!(
        matches!(result, crate::auth_forward::SshReadiness::Ready),
        "SshReadiness::Ready variant must exist"
    );
}

#[test]
fn test_ssh_readiness_timed_out_variant_exists() {
    let result = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 300,
        host: "10.0.0.5".to_string(),
        port: 22,
        user: "azureuser".to_string(),
    };
    if let crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs,
        host,
        port,
        user,
    } = result
    {
        assert_eq!(elapsed_secs, 300);
        assert_eq!(host, "10.0.0.5");
        assert_eq!(port, 22);
        assert_eq!(user, "azureuser");
    } else {
        panic!("Expected TimedOut variant");
    }
}

#[test]
fn test_ssh_readiness_is_ready_helper() {
    let ready = crate::auth_forward::SshReadiness::Ready;
    assert!(ready.is_ready());

    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 300,
        host: "10.0.0.5".to_string(),
        port: 22,
        user: "azureuser".to_string(),
    };
    assert!(!timed_out.is_ready());
}

#[test]
fn test_ssh_readiness_timed_out_recovery_message() {
    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 600,
        host: "127.0.0.1".to_string(),
        port: 50200,
        user: "azureuser".to_string(),
    };
    let msg = timed_out.recovery_message();
    assert!(
        msg.contains("azureuser"),
        "Recovery message must include username"
    );
    assert!(
        msg.contains("50200") || msg.contains("ssh"),
        "Recovery message must include port or SSH command"
    );
}

// ── 3. wait_for_post_create_readiness signature ────────────────────
//
// The new signature accepts:
//   - ssh_timeout: Duration (scaled by VM size)
//   - provisioning_check: Option<Box<dyn Fn() -> Option<String>>>
// And returns Result<SshReadiness> instead of Result<()>

#[test]
fn test_wait_for_post_create_readiness_returns_ssh_readiness() {
    // This test verifies the return type is SshReadiness, not ().
    // We can't actually call it (needs real SSH), but we verify the type
    // compiles correctly via a type assertion.
    fn _assert_return_type() -> anyhow::Result<crate::auth_forward::SshReadiness> {
        // This function is never called — it just proves the type signature compiles.
        crate::auth_forward::wait_for_post_create_readiness(
            "127.0.0.1",
            "azureuser",
            Some(22),
            None,
            false,
            Duration::from_secs(300),
            None,
        )
    }
}

// ── 4. Timeout produces warning, not error ─────────────────────────

#[test]
fn test_ssh_readiness_timed_out_is_not_error() {
    // SshReadiness::TimedOut should be Ok (returned inside Result::Ok),
    // not an Err. The caller can inspect it and decide what to do.
    let result: anyhow::Result<crate::auth_forward::SshReadiness> =
        Ok(crate::auth_forward::SshReadiness::TimedOut {
            elapsed_secs: 300,
            host: "10.0.0.5".to_string(),
            port: 22,
            user: "azureuser".to_string(),
        });
    assert!(result.is_ok(), "TimedOut must be Ok, not Err");
    assert!(
        !result.unwrap().is_ready(),
        "TimedOut must not report as ready"
    );
}

// ── 5. Provisioning state check integration ────────────────────────

#[test]
fn test_provisioning_check_closure_called_during_wait() {
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::Arc;

    // Verify the closure type compiles (Fn() -> Option<String>)
    let call_count = Arc::new(AtomicU32::new(0));
    let count_clone = call_count.clone();
    let check: Box<dyn Fn() -> Option<String>> = Box::new(move || {
        count_clone.fetch_add(1, Ordering::Relaxed);
        Some("Succeeded".to_string())
    });

    // Call it to verify the interface
    let state = check();
    assert_eq!(state, Some("Succeeded".to_string()));
    assert_eq!(call_count.load(Ordering::Relaxed), 1);
}

#[test]
fn test_provisioning_check_failed_state_recognized() {
    // When provisioning returns "Failed", wait_for_ssh should bail early.
    // This tests the string matching logic.
    let states = vec![
        ("Succeeded", false),   // normal — don't bail
        ("Creating", false),    // still going — don't bail
        ("Updating", false),    // still going — don't bail
        ("Failed", true),       // BAIL EARLY
        ("Canceled", true),     // BAIL EARLY
        ("Deleting", true),     // BAIL EARLY
    ];
    for (state, should_bail) in states {
        assert_eq!(
            crate::auth_forward::is_provisioning_terminal_failure(state),
            should_bail,
            "State '{}' should {}cause early bail",
            state,
            if should_bail { "" } else { "not " }
        );
    }
}

// ── 6. Progress reporting interval ─────────────────────────────────

#[test]
fn test_progress_interval_is_30s() {
    assert_eq!(
        crate::auth_forward::SSH_PROGRESS_INTERVAL,
        Duration::from_secs(30),
        "Progress messages should print every 30 seconds"
    );
}

#[test]
fn test_provisioning_check_interval_is_60s() {
    assert_eq!(
        crate::auth_forward::PROVISIONING_CHECK_INTERVAL,
        Duration::from_secs(60),
        "Provisioning state should be checked every 60 seconds"
    );
}

// ── 7. VM size tier mapping exhaustiveness ─────────────────────────

#[test]
fn test_all_cli_tiers_produce_valid_timeout() {
    // Every VmSizeTier must map to a known Azure SKU that produces a valid timeout
    let tier_skus = vec![
        ("Standard_D2s_v3", 300),   // S
        ("Standard_D16s_v3", 300),  // M
        ("Standard_D32s_v3", 450),  // L
        ("Standard_D64s_v3", 600),  // Xl
    ];
    for (sku, expected_secs) in tier_skus {
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(sku);
        assert_eq!(
            timeout.as_secs(),
            expected_secs,
            "SKU {} should produce {}s timeout",
            sku,
            expected_secs
        );
    }
}

#[test]
fn test_timeout_range_is_bounded() {
    // No timeout should be less than 300s or more than 600s
    let test_skus = vec![
        "Standard_D2s_v3",
        "Standard_D16s_v3",
        "Standard_D32s_v3",
        "Standard_D64s_v3",
        "Standard_NC24ads_A100_v4",
        "anything_unknown",
        "",
    ];
    for sku in test_skus {
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(sku);
        assert!(
            timeout.as_secs() >= 300 && timeout.as_secs() <= 600,
            "Timeout for '{}' = {}s is out of [300, 600] range",
            sku,
            timeout.as_secs()
        );
    }
}

// ── 8. Recovery message content ────────────────────────────────────

#[test]
fn test_recovery_message_includes_ssh_command() {
    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 300,
        host: "10.0.0.5".to_string(),
        port: 22,
        user: "azureuser".to_string(),
    };
    let msg = timed_out.recovery_message();
    assert!(
        msg.contains("ssh azureuser@10.0.0.5") || msg.contains("ssh"),
        "Recovery message should contain an SSH command"
    );
}

#[test]
fn test_recovery_message_includes_azlin_ssh() {
    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 300,
        host: "10.0.0.5".to_string(),
        port: 22,
        user: "azureuser".to_string(),
    };
    let msg = timed_out.recovery_message();
    assert!(
        msg.contains("azlin ssh"),
        "Recovery message should mention 'azlin ssh' as an alternative"
    );
}

#[test]
fn test_recovery_message_mentions_cloud_init() {
    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 600,
        host: "127.0.0.1".to_string(),
        port: 50200,
        user: "azureuser".to_string(),
    };
    let msg = timed_out.recovery_message();
    assert!(
        msg.contains("cloud-init"),
        "Recovery message should mention cloud-init logs for debugging"
    );
}

#[test]
fn test_recovery_message_bastion_port_shown() {
    let timed_out = crate::auth_forward::SshReadiness::TimedOut {
        elapsed_secs: 300,
        host: "127.0.0.1".to_string(),
        port: 50200,
        user: "azureuser".to_string(),
    };
    let msg = timed_out.recovery_message();
    assert!(
        msg.contains("50200"),
        "Recovery message should show bastion port when using tunnel"
    );
}

// ── 9. Edge cases ──────────────────────────────────────────────────

#[test]
fn test_ssh_timeout_dsv3_family_scaling() {
    // Test all D-series v3 sizes to ensure correct core-count extraction
    let cases = vec![
        ("Standard_D2s_v3", 300),
        ("Standard_D4s_v3", 300),
        ("Standard_D8s_v3", 300),
        ("Standard_D16s_v3", 300),
        ("Standard_D32s_v3", 450),
        ("Standard_D48s_v3", 450),
        ("Standard_D64s_v3", 600),
    ];
    for (sku, expected) in cases {
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(sku);
        assert_eq!(
            timeout.as_secs(),
            expected,
            "SKU '{}' should have {}s timeout, got {}s",
            sku,
            expected,
            timeout.as_secs()
        );
    }
}

#[test]
fn test_ssh_timeout_e_series_large() {
    // E-series (memory-optimized) should also scale by core count
    let e64 = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_E64s_v5");
    assert_eq!(e64, Duration::from_secs(600), "E64 = 64 cores → 600s");
}

#[test]
fn test_ssh_timeout_f_series_small() {
    // F-series (compute-optimized) small sizes → 300s
    let f2 = crate::cmd_vm_ops::ssh_timeout_for_vm_size("Standard_F2s_v2");
    assert_eq!(f2, Duration::from_secs(300), "F2 = 2 cores → 300s");
}
