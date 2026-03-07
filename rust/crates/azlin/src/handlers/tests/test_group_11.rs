use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── Format list CSV ─────────────────────────────────────────────────

#[test]
fn test_format_list_csv_basic() {
    let headers = vec!["Session", "Status", "IP"];
    let rows = vec![ListRow {
        session: "main".to_string(),
        tmux: "-".to_string(),
        vm_name: "vm-1".to_string(),
        os_display: "Linux".to_string(),
        power_state: "Running".to_string(),
        ip_display: "1.2.3.4".to_string(),
        location: "eastus".to_string(),
        cpu: "4".to_string(),
        mem: "16 GB".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        latency: None,
        health: None,
        top_procs: None,
    }];
    let config = ListColumnConfig {
        show_tmux: false,
        wide: false,
        with_latency: false,
        with_health: false,
        show_procs: false,
    };
    let csv = format_list_csv(&headers, &rows, &config);
    assert!(csv.contains("Session,Status,IP"));
    assert!(csv.contains("main"));
}
