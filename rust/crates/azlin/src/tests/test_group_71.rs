// ── VM size tier revamp + region-fit + vm-family tests (test_group_71) ──
//
// TDD tests for:
//   1. New VmSizeTier enum (Xs, S, M, L, Xl, Xxl)
//   2. VmFamily enum (D, E)
//   3. tier_to_sku() mapping function
//   4. region_fit module: parse_quota_json, parse_sku_availability_json,
//      check_region_quota, find_available_region
//   5. Error handler --region-fit suggestion
//   6. CLI flag parsing for --region-fit and --vm-family

// ═══════════════════════════════════════════════════════════════════════
// 1. VmSizeTier enum — new tiers Xs and Xxl exist
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_vm_size_tier_xs_variant_exists() {
    let tier = azlin_cli::VmSizeTier::Xs;
    assert!(matches!(tier, azlin_cli::VmSizeTier::Xs));
}

#[test]
fn test_vm_size_tier_xxl_variant_exists() {
    let tier = azlin_cli::VmSizeTier::Xxl;
    assert!(matches!(tier, azlin_cli::VmSizeTier::Xxl));
}

#[test]
fn test_vm_size_tier_all_six_variants() {
    // All six tiers must exist and be distinct
    let tiers = vec![
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmSizeTier::Xxl,
    ];
    assert_eq!(tiers.len(), 6, "Must have exactly 6 VM size tiers");
}

// ═══════════════════════════════════════════════════════════════════════
// 2. VmFamily enum — D-series and E-series
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_vm_family_d_variant_exists() {
    let family = azlin_cli::VmFamily::D;
    assert!(matches!(family, azlin_cli::VmFamily::D));
}

#[test]
fn test_vm_family_e_variant_exists() {
    let family = azlin_cli::VmFamily::E;
    assert!(matches!(family, azlin_cli::VmFamily::E));
}

// ═══════════════════════════════════════════════════════════════════════
// 3. tier_to_sku() — D-family (default) tier mapping to v5 SKUs
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_tier_to_sku_d_xs() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D2s_v5");
}

#[test]
fn test_tier_to_sku_d_s() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D4s_v5");
}

#[test]
fn test_tier_to_sku_d_m() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D8s_v5");
}

#[test]
fn test_tier_to_sku_d_l() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D16s_v5");
}

#[test]
fn test_tier_to_sku_d_xl() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D32s_v5");
}

#[test]
fn test_tier_to_sku_d_xxl() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xxl,
        azlin_cli::VmFamily::D,
    );
    assert_eq!(sku, "Standard_D64s_v5");
}

// ═══════════════════════════════════════════════════════════════════════
// 4. tier_to_sku() — E-family (memory-optimized) mapping
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_tier_to_sku_e_xs() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E2as_v5");
}

#[test]
fn test_tier_to_sku_e_s() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E4as_v5");
}

#[test]
fn test_tier_to_sku_e_m() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E8as_v5");
}

#[test]
fn test_tier_to_sku_e_l() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E16as_v5");
}

#[test]
fn test_tier_to_sku_e_xl() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E32as_v5");
}

#[test]
fn test_tier_to_sku_e_xxl() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::Xxl,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E64as_v5");
}

// ═══════════════════════════════════════════════════════════════════════
// 5. tier_to_sku() — all D-family SKUs use v5 (not v3)
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_all_d_family_skus_are_v5() {
    let tiers = vec![
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmSizeTier::Xxl,
    ];
    for tier in tiers {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::D);
        assert!(
            sku.ends_with("_v5"),
            "D-family tier {:?} produced SKU '{}' which is not v5",
            tier,
            sku
        );
    }
}

#[test]
fn test_all_e_family_skus_are_v5() {
    let tiers = vec![
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmSizeTier::Xxl,
    ];
    for tier in tiers {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::E);
        assert!(
            sku.ends_with("_v5"),
            "E-family tier {:?} produced SKU '{}' which is not v5",
            tier,
            sku
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 6. tier_to_sku() — core count consistency
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_tier_core_counts_d_family() {
    // Each tier should map to the expected core count
    let expected = vec![
        (azlin_cli::VmSizeTier::Xs, 2),
        (azlin_cli::VmSizeTier::S, 4),
        (azlin_cli::VmSizeTier::M, 8),
        (azlin_cli::VmSizeTier::L, 16),
        (azlin_cli::VmSizeTier::Xl, 32),
        (azlin_cli::VmSizeTier::Xxl, 64),
    ];
    for (tier, cores) in expected {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::D);
        // SKU format: Standard_D{cores}s_v5
        assert!(
            sku.contains(&format!("D{}s", cores)),
            "Tier {:?} should have {} cores but SKU is '{}'",
            tier,
            cores,
            sku,
        );
    }
}

#[test]
fn test_tier_core_counts_e_family() {
    let expected = vec![
        (azlin_cli::VmSizeTier::Xs, 2),
        (azlin_cli::VmSizeTier::S, 4),
        (azlin_cli::VmSizeTier::M, 8),
        (azlin_cli::VmSizeTier::L, 16),
        (azlin_cli::VmSizeTier::Xl, 32),
        (azlin_cli::VmSizeTier::Xxl, 64),
    ];
    for (tier, cores) in expected {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::E);
        assert!(
            sku.contains(&format!("E{}as", cores)),
            "Tier {:?} should have {} cores but SKU is '{}'",
            tier,
            cores,
            sku,
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 7. SSH timeout still works with new v5 SKUs from tier mappings
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_ssh_timeout_for_new_tier_skus_v5() {
    let tier_expected: Vec<(azlin_cli::VmSizeTier, u64)> = vec![
        (azlin_cli::VmSizeTier::Xs, 300),  // 2 cores → 300s
        (azlin_cli::VmSizeTier::S, 300),   // 4 cores → 300s
        (azlin_cli::VmSizeTier::M, 300),   // 8 cores → 300s
        (azlin_cli::VmSizeTier::L, 300),   // 16 cores → 300s
        (azlin_cli::VmSizeTier::Xl, 450),  // 32 cores → 450s (>16)
        (azlin_cli::VmSizeTier::Xxl, 600), // 64 cores → 600s (>48)
    ];
    for (tier, expected_secs) in tier_expected {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::D);
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(&sku);
        assert_eq!(
            timeout.as_secs(),
            expected_secs,
            "Tier {:?} (SKU {}) should have {}s timeout",
            tier,
            sku,
            expected_secs,
        );
    }
}

#[test]
fn test_ssh_timeout_for_e_family_skus() {
    // E-series SKUs should also produce correct timeouts via extract_core_count
    let e_skus = vec![
        ("Standard_E2as_v5", 300),   // 2 cores
        ("Standard_E8as_v5", 300),   // 8 cores
        ("Standard_E32as_v5", 450),  // 32 cores
        ("Standard_E64as_v5", 600),  // 64 cores
    ];
    for (sku, expected_secs) in e_skus {
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(sku);
        assert_eq!(
            timeout.as_secs(),
            expected_secs,
            "E-family SKU {} should have {}s timeout",
            sku,
            expected_secs,
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 8. region_fit module — parse_quota_json
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_parse_quota_json_extracts_vcpu_usage() {
    let json = r#"[
        {
            "currentValue": 24,
            "limit": 100,
            "localName": "Total Regional vCPUs",
            "name": { "localizedValue": "Total Regional vCPUs", "value": "cores" }
        },
        {
            "currentValue": 8,
            "limit": 50,
            "localName": "Standard Dv5 Family vCPUs",
            "name": { "localizedValue": "Standard Dv5 Family vCPUs", "value": "standardDv5Family" }
        }
    ]"#;
    let quota = azlin_azure::region_fit::parse_quota_json(json).unwrap();
    assert_eq!(quota.total_regional_used, 24);
    assert_eq!(quota.total_regional_limit, 100);
    assert_eq!(quota.available_cores(), 76);
}

#[test]
fn test_parse_quota_json_family_specific() {
    let json = r#"[
        {
            "currentValue": 10,
            "limit": 100,
            "localName": "Total Regional vCPUs",
            "name": { "localizedValue": "Total Regional vCPUs", "value": "cores" }
        },
        {
            "currentValue": 4,
            "limit": 20,
            "localName": "Standard Dv5 Family vCPUs",
            "name": { "localizedValue": "Standard Dv5 Family vCPUs", "value": "standardDv5Family" }
        }
    ]"#;
    let quota = azlin_azure::region_fit::parse_quota_json(json).unwrap();
    // Family-specific quota should also be tracked
    let dv5 = quota.family_quota("standardDv5Family");
    assert!(dv5.is_some(), "Should find Dv5 family quota entry");
    let dv5 = dv5.unwrap();
    assert_eq!(dv5.used, 4);
    assert_eq!(dv5.limit, 20);
}

#[test]
fn test_parse_quota_json_empty_array() {
    let json = "[]";
    let result = azlin_azure::region_fit::parse_quota_json(json);
    assert!(result.is_err(), "Empty quota list should return error");
}

#[test]
fn test_parse_quota_json_invalid_json() {
    let result = azlin_azure::region_fit::parse_quota_json("not json");
    assert!(result.is_err());
}

// ═══════════════════════════════════════════════════════════════════════
// 9. region_fit module — parse_sku_availability_json
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_parse_sku_available() {
    let json = r#"[
        {
            "name": "Standard_D8s_v5",
            "restrictions": []
        }
    ]"#;
    let available =
        azlin_azure::region_fit::parse_sku_availability_json(json, "Standard_D8s_v5");
    assert!(available, "SKU with no restrictions should be available");
}

#[test]
fn test_parse_sku_restricted_zone() {
    let json = r#"[
        {
            "name": "Standard_D8s_v5",
            "restrictions": [
                {
                    "reasonCode": "NotAvailableForSubscription",
                    "type": "Zone"
                }
            ]
        }
    ]"#;
    let available =
        azlin_azure::region_fit::parse_sku_availability_json(json, "Standard_D8s_v5");
    assert!(
        !available,
        "SKU with NotAvailableForSubscription restriction should be unavailable"
    );
}

#[test]
fn test_parse_sku_not_in_list() {
    let json = r#"[
        {
            "name": "Standard_D4s_v5",
            "restrictions": []
        }
    ]"#;
    let available =
        azlin_azure::region_fit::parse_sku_availability_json(json, "Standard_D8s_v5");
    assert!(!available, "SKU not in the list should be unavailable");
}

#[test]
fn test_parse_sku_empty_list() {
    let json = "[]";
    let available =
        azlin_azure::region_fit::parse_sku_availability_json(json, "Standard_D8s_v5");
    assert!(!available, "Empty SKU list should mean unavailable");
}

// ═══════════════════════════════════════════════════════════════════════
// 10. region_fit module — RegionQuota arithmetic
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_region_quota_available_cores() {
    let quota = azlin_azure::region_fit::RegionQuota {
        region: "westus2".to_string(),
        total_regional_used: 40,
        total_regional_limit: 100,
        family_quotas: vec![],
    };
    assert_eq!(quota.available_cores(), 60);
}

#[test]
fn test_region_quota_available_cores_at_limit() {
    let quota = azlin_azure::region_fit::RegionQuota {
        region: "westus2".to_string(),
        total_regional_used: 100,
        total_regional_limit: 100,
        family_quotas: vec![],
    };
    assert_eq!(quota.available_cores(), 0);
}

#[test]
fn test_region_quota_has_capacity_for() {
    let quota = azlin_azure::region_fit::RegionQuota {
        region: "westus2".to_string(),
        total_regional_used: 40,
        total_regional_limit: 100,
        family_quotas: vec![],
    };
    assert!(quota.has_capacity_for(60));
    assert!(quota.has_capacity_for(1));
    assert!(!quota.has_capacity_for(61));
}

// ═══════════════════════════════════════════════════════════════════════
// 11. region_fit module — candidate region list
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_default_candidate_regions_is_nonempty() {
    let regions = azlin_azure::region_fit::default_candidate_regions();
    assert!(!regions.is_empty(), "Must have at least one candidate region");
}

#[test]
fn test_default_candidate_regions_contains_common_regions() {
    let regions = azlin_azure::region_fit::default_candidate_regions();
    assert!(regions.contains(&"westus2"), "Should contain westus2");
    assert!(regions.contains(&"eastus"), "Should contain eastus");
    assert!(regions.contains(&"eastus2"), "Should contain eastus2");
}

#[test]
fn test_default_candidate_regions_preferred_first() {
    // If a preferred region is provided, it should appear first in the check order
    let regions = azlin_azure::region_fit::candidate_regions_with_preferred("centralus");
    assert_eq!(
        regions[0], "centralus",
        "Preferred region should be first in the list"
    );
    // Should not be duplicated
    let count = regions.iter().filter(|r| **r == "centralus").count();
    assert_eq!(count, 1, "Preferred region should appear exactly once");
}

// ═══════════════════════════════════════════════════════════════════════
// 12. region_fit module — RegionCheckResult
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_region_check_result_available() {
    let result = azlin_azure::region_fit::RegionCheckResult {
        region: "westus2".to_string(),
        sku_available: true,
        quota_available: 60,
        quota_limit: 100,
        has_capacity: true,
        error: None,
    };
    assert!(result.is_usable());
}

#[test]
fn test_region_check_result_sku_unavailable() {
    let result = azlin_azure::region_fit::RegionCheckResult {
        region: "westus".to_string(),
        sku_available: false,
        quota_available: 60,
        quota_limit: 100,
        has_capacity: true,
        error: None,
    };
    assert!(!result.is_usable(), "Should not be usable if SKU is restricted");
}

#[test]
fn test_region_check_result_no_capacity() {
    let result = azlin_azure::region_fit::RegionCheckResult {
        region: "eastus".to_string(),
        sku_available: true,
        quota_available: 2,
        quota_limit: 100,
        has_capacity: false,
        error: None,
    };
    assert!(!result.is_usable(), "Should not be usable if no capacity");
}

#[test]
fn test_region_check_result_with_error() {
    let result = azlin_azure::region_fit::RegionCheckResult {
        region: "westus3".to_string(),
        sku_available: false,
        quota_available: 0,
        quota_limit: 0,
        has_capacity: false,
        error: Some("az CLI timed out".to_string()),
    };
    assert!(!result.is_usable());
}

// ═══════════════════════════════════════════════════════════════════════
// 13. Error handler — --region-fit suggestion in quota errors
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_quota_error_suggests_region_fit() {
    let error = azlin_azure::error_handler::AzureError {
        code: "QuotaExceeded".to_string(),
        message: "Operation could not be completed as it results in exceeding \
                  approved Total Regional Cores quota. Location: westus2. \
                  Current Limit: 50. Current Usage: 48. Additional Required: 8."
            .to_string(),
        target: None,
        details: vec![],
    };
    let msg = azlin_azure::error_handler::format_user_friendly_error(&error);
    assert!(
        msg.contains("--region-fit"),
        "Quota error message should suggest --region-fit flag. Got: {}",
        msg
    );
}

#[test]
fn test_quota_error_in_details_suggests_region_fit() {
    let error = azlin_azure::error_handler::AzureError {
        code: "InvalidTemplateDeployment".to_string(),
        message: "Deployment failed".to_string(),
        target: None,
        details: vec![azlin_azure::error_handler::AzureError {
            code: "QuotaExceeded".to_string(),
            message: "Operation could not be completed. Location: eastus. \
                      Current Limit: 10. Current Usage: 10."
                .to_string(),
            target: None,
            details: vec![],
        }],
    };
    let msg = azlin_azure::error_handler::format_user_friendly_error(&error);
    assert!(
        msg.contains("--region-fit"),
        "Wrapped quota error should also suggest --region-fit. Got: {}",
        msg
    );
}

#[test]
fn test_sku_not_available_suggests_region_fit() {
    let error = azlin_azure::error_handler::AzureError {
        code: "SkuNotAvailable".to_string(),
        message: "The requested VM size Standard_D32s_v5 is not available in location westus."
            .to_string(),
        target: None,
        details: vec![],
    };
    let msg = azlin_azure::error_handler::format_user_friendly_error(&error);
    assert!(
        msg.contains("--region-fit"),
        "SkuNotAvailable error should suggest --region-fit. Got: {}",
        msg
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 14. Updated test_group_70 compatibility — v5 SKUs in tier exhaustiveness
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_all_new_tiers_produce_valid_timeout() {
    // Updated version of test_group_70's test_all_cli_tiers_produce_valid_timeout
    // Now with 6 tiers mapping to v5 SKUs
    let tier_skus = vec![
        (azlin_cli::VmSizeTier::Xs, "Standard_D2s_v5", 300),
        (azlin_cli::VmSizeTier::S, "Standard_D4s_v5", 300),
        (azlin_cli::VmSizeTier::M, "Standard_D8s_v5", 300),
        (azlin_cli::VmSizeTier::L, "Standard_D16s_v5", 300),
        (azlin_cli::VmSizeTier::Xl, "Standard_D32s_v5", 450),
        (azlin_cli::VmSizeTier::Xxl, "Standard_D64s_v5", 600),
    ];
    for (tier, expected_sku, expected_secs) in tier_skus {
        let sku = crate::cmd_vm_ops::tier_to_sku(tier, azlin_cli::VmFamily::D);
        assert_eq!(
            sku, expected_sku,
            "Tier {:?} should map to {}",
            tier, expected_sku
        );
        let timeout = crate::cmd_vm_ops::ssh_timeout_for_vm_size(&sku);
        assert_eq!(
            timeout.as_secs(),
            expected_secs,
            "SKU {} should produce {}s timeout",
            sku,
            expected_secs
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 15. CLI parsing — --region-fit flag recognized
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_cli_region_fit_flag_in_new_command() {
    use clap::Parser;
    // Parse a minimal `azlin new --region-fit` command
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--region-fit"]);
    assert!(args.is_ok(), "CLI should accept --region-fit flag: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { region_fit, .. } = cli.command {
        assert!(region_fit, "--region-fit should be true when passed");
    } else {
        panic!("Expected Commands::New variant");
    }
}

#[test]
fn test_cli_region_fit_default_false() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new"]);
    assert!(args.is_ok());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { region_fit, .. } = cli.command {
        assert!(!region_fit, "--region-fit should default to false");
    } else {
        panic!("Expected Commands::New variant");
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 16. CLI parsing — --vm-family flag recognized
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_cli_vm_family_flag_d() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--vm-family", "d"]);
    assert!(args.is_ok(), "CLI should accept --vm-family d: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { vm_family, .. } = cli.command {
        assert!(
            matches!(vm_family, Some(azlin_cli::VmFamily::D)),
            "--vm-family d should parse to VmFamily::D"
        );
    } else {
        panic!("Expected Commands::New variant");
    }
}

#[test]
fn test_cli_vm_family_flag_e() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--vm-family", "e"]);
    assert!(args.is_ok(), "CLI should accept --vm-family e: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { vm_family, .. } = cli.command {
        assert!(
            matches!(vm_family, Some(azlin_cli::VmFamily::E)),
            "--vm-family e should parse to VmFamily::E"
        );
    } else {
        panic!("Expected Commands::New variant");
    }
}

#[test]
fn test_cli_vm_family_default_none() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new"]);
    assert!(args.is_ok());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { vm_family, .. } = cli.command {
        assert!(
            vm_family.is_none(),
            "--vm-family should default to None (D implied in tier_to_sku)"
        );
    } else {
        panic!("Expected Commands::New variant");
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 17. CLI parsing — new --size xs and --size xxl accepted
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_cli_size_xs_accepted() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--size", "xs"]);
    assert!(args.is_ok(), "CLI should accept --size xs: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { size, .. } = cli.command {
        assert!(
            matches!(size, Some(azlin_cli::VmSizeTier::Xs)),
            "--size xs should parse to VmSizeTier::Xs"
        );
    } else {
        panic!("Expected Commands::New variant");
    }
}

#[test]
fn test_cli_size_xxl_accepted() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--size", "xxl"]);
    assert!(args.is_ok(), "CLI should accept --size xxl: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New { size, .. } = cli.command {
        assert!(
            matches!(size, Some(azlin_cli::VmSizeTier::Xxl)),
            "--size xxl should parse to VmSizeTier::Xxl"
        );
    } else {
        panic!("Expected Commands::New variant");
    }
}

#[test]
fn test_cli_size_case_insensitive() {
    use clap::Parser;
    // ignore_case = true should allow XS, Xs, xS, xs
    for variant in ["XS", "Xs", "xS", "xs"] {
        let args = azlin_cli::Cli::try_parse_from(["azlin", "new", "--size", variant]);
        assert!(
            args.is_ok(),
            "CLI should accept --size {} (case-insensitive): {:?}",
            variant,
            args.err()
        );
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 18. Combined flags — --region-fit + --size + --vm-family
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_cli_combined_flags() {
    use clap::Parser;
    let args = azlin_cli::Cli::try_parse_from([
        "azlin",
        "new",
        "--size",
        "m",
        "--vm-family",
        "e",
        "--region-fit",
    ]);
    assert!(args.is_ok(), "Combined flags should parse: {:?}", args.err());
    let cli = args.unwrap();
    if let azlin_cli::Commands::New {
        size,
        vm_family,
        region_fit,
        ..
    } = cli.command
    {
        assert!(matches!(size, Some(azlin_cli::VmSizeTier::M)));
        assert!(matches!(vm_family, Some(azlin_cli::VmFamily::E)));
        assert!(region_fit);
    } else {
        panic!("Expected Commands::New variant");
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 19. --vm-family ignored when --vm-size is explicit
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_vm_family_ignored_with_explicit_vm_size() {
    use clap::Parser;
    // Both --vm-size and --vm-family should parse without error
    // (the logic to ignore family when vm-size is explicit is in handle_vm_new)
    let args = azlin_cli::Cli::try_parse_from([
        "azlin",
        "new",
        "--vm-size",
        "Standard_NC24ads_A100_v4",
        "--vm-family",
        "e",
    ]);
    assert!(
        args.is_ok(),
        "--vm-size and --vm-family should not conflict at CLI level: {:?}",
        args.err()
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 20. region_fit — format_region_table produces readable output
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_format_region_table_includes_all_regions() {
    let results = vec![
        azlin_azure::region_fit::RegionCheckResult {
            region: "westus2".to_string(),
            sku_available: true,
            quota_available: 60,
            quota_limit: 100,
            has_capacity: true,
            error: None,
        },
        azlin_azure::region_fit::RegionCheckResult {
            region: "eastus".to_string(),
            sku_available: false,
            quota_available: 0,
            quota_limit: 50,
            has_capacity: false,
            error: None,
        },
    ];
    let table = azlin_azure::region_fit::format_region_table(&results);
    assert!(table.contains("westus2"), "Table should include westus2");
    assert!(table.contains("eastus"), "Table should include eastus");
    assert!(
        table.contains("60") || table.contains("available"),
        "Table should show availability info"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 21. tier_to_sku exhaustive — no panic on any valid combination
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_tier_to_sku_exhaustive_no_panic() {
    let tiers = vec![
        azlin_cli::VmSizeTier::Xs,
        azlin_cli::VmSizeTier::S,
        azlin_cli::VmSizeTier::M,
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmSizeTier::Xl,
        azlin_cli::VmSizeTier::Xxl,
    ];
    let families = vec![azlin_cli::VmFamily::D, azlin_cli::VmFamily::E];
    for tier in &tiers {
        for family in &families {
            let sku = crate::cmd_vm_ops::tier_to_sku(*tier, *family);
            assert!(!sku.is_empty(), "SKU should not be empty for {:?}/{:?}", tier, family);
            assert!(
                sku.starts_with("Standard_"),
                "SKU should start with Standard_ for {:?}/{:?}",
                tier,
                family
            );
        }
    }
}

// ── extract_core_count overflow safety ──────────────────────────────

#[test]
fn test_extract_core_count_rejects_overflow() {
    // Fabricated SKU with absurdly large digit sequence should return None
    let result = crate::cmd_vm_ops::extract_core_count("Standard_D99999999999s_v5");
    assert!(result.is_none(), "Should reject overflow core count");
}

#[test]
fn test_extract_core_count_accepts_valid_range() {
    assert_eq!(crate::cmd_vm_ops::extract_core_count("Standard_D128s_v5"), Some(128));
    assert_eq!(crate::cmd_vm_ops::extract_core_count("Standard_D2s_v5"), Some(2));
}

// ── vm_family defaults to tier L when no --size ────────────────────

#[test]
fn test_vm_family_e_without_size_uses_default_tier_l() {
    let sku = crate::cmd_vm_ops::tier_to_sku(
        azlin_cli::VmSizeTier::L,
        azlin_cli::VmFamily::E,
    );
    assert_eq!(sku, "Standard_E16as_v5");
}
