//! Teardown handler tests.
//!
//! Regression coverage for the resource leak where `destroy`/`delete`/`kill`
//! removed the VM, its disks and its NIC but left the session's Public IP and
//! NSG orphaned in Azure, billing indefinitely.

use super::super::*;
use super::common::*;
use azlin_core::models::PowerState;

const VM: &str = "copilot-test2-1784625385";
const SIBLING: &str = "copilot-test-1783435804";
const RG: &str = "test-rg";

fn vm_id(name: &str) -> String {
    format!("/subscriptions/s/resourceGroups/{RG}/providers/Microsoft.Compute/virtualMachines/{name}")
}

fn nic_id(name: &str) -> String {
    format!("/subscriptions/s/resourceGroups/{RG}/providers/Microsoft.Network/networkInterfaces/{name}")
}

/// A mock populated to mirror the real leaked session: a tagged VM with an OS
/// disk, a home disk, a NIC, a Public IP and an NSG, plus a prefix-adjacent
/// sibling session's IP and NSG that must never be touched.
fn mock_with_full_session() -> MockAzureOps {
    let mut vm = make_test_vm(VM, PowerState::Running);
    vm.tags
        .insert("azlin-session".to_string(), VM.to_string());
    let mut mock = MockAzureOps::new(vec![vm]);

    mock.disk_json = format!(
        r#"[
          {{"name":"{VM}_OsDisk_1_ab65","managedBy":"{}","resourceGroup":"{RG}","diskSizeGb":5}},
          {{"name":"{VM}_home","managedBy":"{}","resourceGroup":"{RG}","diskSizeGb":100}}
        ]"#,
        vm_id(VM),
        vm_id(VM)
    );
    mock.nic_json = format!(
        r#"[{{"name":"{VM}VMNic","resourceGroup":"{RG}","virtualMachine":{{"id":"{}"}}}}]"#,
        vm_id(VM)
    );
    mock.pip_json = format!(
        r#"[
          {{"name":"{VM}PublicIP","resourceGroup":"{RG}",
            "ipConfiguration":{{"id":"{}/ipConfigurations/ipconfig1"}},
            "tags":{{"azlin-session":"{VM}"}}}},
          {{"name":"{SIBLING}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
            "tags":{{"azlin-session":"{SIBLING}"}}}}
        ]"#,
        nic_id(&format!("{VM}VMNic"))
    );
    mock.nsg_json = format!(
        r#"[
          {{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":[],
            "networkInterfaces":[{{"id":"{}"}}],
            "tags":{{"azlin-session":"{VM}"}}}},
          {{"name":"{SIBLING}NSG","resourceGroup":"{RG}","subnets":[],
            "networkInterfaces":[],"tags":{{"azlin-session":"{SIBLING}"}}}}
        ]"#,
        nic_id(&format!("{VM}VMNic"))
    );
    mock
}

// ── The leak itself ─────────────────────────────────────────────────

#[test]
fn test_teardown_deletes_public_ip_and_nsg() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        log.contains(&format!("delete_public_ip:{VM}PublicIP")),
        "public IP must be deleted, else it leaks and keeps billing: {log:?}"
    );
    assert!(
        log.contains(&format!("delete_nsg:{VM}NSG")),
        "NSG must be deleted: {log:?}"
    );
}

#[test]
fn test_teardown_deletes_vm_disks_and_nic() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(log.contains(&format!("delete_vm:{VM}")));
    assert!(log.contains(&format!("delete_disk:{VM}_OsDisk_1_ab65")));
    assert!(log.contains(&format!("delete_disk:{VM}_home")));
    assert!(log.contains(&format!("delete_nic:{VM}VMNic")));
}

#[test]
fn test_teardown_reports_reclaimed_cost() {
    let mock = mock_with_full_session();
    let msg = handle_delete(&mock, RG, VM).unwrap();
    assert!(msg.contains(VM));
    assert!(
        msg.contains("month"),
        "user should see the saving: {msg}"
    );
}

// ── Ordering: NIC before IP and NSG ─────────────────────────────────

#[test]
fn test_nic_deleted_before_public_ip() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let nic = mock.call_index(&format!("delete_nic:{VM}VMNic")).unwrap();
    let ip = mock
        .call_index(&format!("delete_public_ip:{VM}PublicIP"))
        .unwrap();
    assert!(
        nic < ip,
        "Azure rejects deleting a public IP while its NIC still references it"
    );
}

#[test]
fn test_nic_deleted_before_nsg() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let nic = mock.call_index(&format!("delete_nic:{VM}VMNic")).unwrap();
    let nsg = mock.call_index(&format!("delete_nsg:{VM}NSG")).unwrap();
    assert!(
        nic < nsg,
        "Azure rejects deleting an NSG while a NIC still references it"
    );
}

#[test]
fn test_vm_deleted_before_its_nic() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let vm = mock.call_index(&format!("delete_vm:{VM}")).unwrap();
    let nic = mock.call_index(&format!("delete_nic:{VM}VMNic")).unwrap();
    assert!(vm < nic, "the NIC is in use until the VM is gone");
}

// ── Sibling-session safety ──────────────────────────────────────────

#[test]
fn test_sibling_session_resources_are_never_deleted() {
    // `copilot-test-1783435804` is a prefix-adjacent sibling of
    // `copilot-test2-1784625385`. Prefix matching would destroy it.
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        !log.iter().any(|c| c.contains(SIBLING)),
        "sibling session's resources must be untouched: {log:?}"
    );
}

// ── Untagged resources are left alone ───────────────────────────────

#[test]
fn test_untagged_public_ip_is_not_deleted_but_is_reported() {
    let mut mock = mock_with_full_session();
    // A hand-made, unassociated IP sharing the resource group.
    mock.pip_json = format!(
        r#"[{{"name":"myvm-ip","resourceGroup":"{RG}","ipConfiguration":null}}]"#
    );
    mock.nsg_json = "[]".to_string();
    let msg = handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        !log.iter().any(|c| c.contains("myvm-ip")),
        "ownership is unproven without a tag — must never auto-delete"
    );
    assert!(msg.contains("myvm-ip"), "user must be told: {msg}");
    assert!(msg.contains("cleanup"), "point at the remedy: {msg}");
}

#[test]
fn test_in_use_public_ip_of_another_vm_is_not_deleted_or_warned() {
    let mut mock = mock_with_full_session();
    mock.pip_json = format!(
        r#"[{{"name":"myvm-ip","resourceGroup":"{RG}",
              "ipConfiguration":{{"id":"{}/ipConfigurations/ipconfig1"}}}}]"#,
        nic_id("myvm693_z1")
    );
    mock.nsg_json = "[]".to_string();
    let msg = handle_delete(&mock, RG, VM).unwrap();
    assert!(!mock.call_log().iter().any(|c| c.contains("myvm-ip")));
    assert!(
        !msg.contains("myvm-ip"),
        "healthy in-use infrastructure is not a leak warning: {msg}"
    );
}

// ── Idempotency ─────────────────────────────────────────────────────

#[test]
fn test_already_deleted_resources_do_not_fail_teardown() {
    let mut mock = mock_with_full_session();
    // The VmManager layer maps Azure 404s to success; the mock mirrors that.
    mock.missing_on_delete = vec![
        format!("{VM}PublicIP"),
        format!("{VM}VMNic"),
        format!("{VM}_home"),
    ];
    assert!(
        handle_delete(&mock, RG, VM).is_ok(),
        "an already-deleted resource must not abort the rest of the teardown"
    );
}

#[test]
fn test_teardown_of_absent_vm_is_not_an_error() {
    let mock = MockAzureOps::new(vec![]);
    let msg = handle_delete(&mock, RG, "ghost-vm").unwrap();
    assert!(msg.contains("not found"), "{msg}");
}

#[test]
fn test_teardown_continues_after_one_failure_then_reports() {
    let mut mock = mock_with_full_session();
    mock.failing_on_delete = vec![format!("{VM}_home")];
    let err = handle_delete(&mock, RG, VM).unwrap_err().to_string();
    let log = mock.call_log();
    assert!(
        log.contains(&format!("delete_public_ip:{VM}PublicIP")),
        "one stuck resource must not strand the rest and re-leak them: {log:?}"
    );
    assert!(err.contains("_home"), "the failure must be reported: {err}");
}

// ── Dry-run ─────────────────────────────────────────────────────────

#[test]
fn test_dry_run_enumerates_every_resource() {
    let mock = mock_with_full_session();
    let out = format_destroy_dry_run_live(&mock, RG, VM).unwrap();
    for expected in [
        VM,
        &format!("{VM}_OsDisk_1_ab65"),
        &format!("{VM}_home"),
        &format!("{VM}VMNic"),
        &format!("{VM}PublicIP"),
        &format!("{VM}NSG"),
    ] {
        assert!(out.contains(expected), "dry-run must list {expected}: {out}");
    }
}

#[test]
fn test_dry_run_makes_no_deletions() {
    let mock = mock_with_full_session();
    format_destroy_dry_run_live(&mock, RG, VM).unwrap();
    assert!(
        !mock.call_log().iter().any(|c| c.starts_with("delete_")),
        "dry-run must never mutate Azure"
    );
}

#[test]
fn test_dry_run_reports_absent_vm_instead_of_confident_would_delete() {
    // The original bug: dry-run echoed "would delete" for a VM that had
    // already been fully deleted, masking the leak.
    let mock = MockAzureOps::new(vec![]);
    let out = format_destroy_dry_run_live(&mock, RG, VM).unwrap();
    assert!(out.contains("not found"), "{out}");
    assert!(
        !out.contains("would delete"),
        "must not claim it would delete a nonexistent VM: {out}"
    );
}

#[test]
fn test_dry_run_of_absent_vm_still_lists_leftover_tagged_resources() {
    // The exact reproduction case: the VM is fully deleted but its tagged
    // Public IP and NSG are still orphaned and billing. Destroy should be able
    // to finish the interrupted teardown.
    let mut mock = mock_with_full_session();
    mock.vms = vec![];
    mock.pip_json = format!(
        r#"[
          {{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
            "tags":{{"azlin-session":"{VM}"}}}},
          {{"name":"{SIBLING}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
            "tags":{{"azlin-session":"{SIBLING}"}}}}
        ]"#
    );
    let out = format_destroy_dry_run_live(&mock, RG, VM).unwrap();
    assert!(out.contains("not found"), "{out}");
    assert!(
        out.contains(&format!("{VM}PublicIP")),
        "leftover resources must still be surfaced: {out}"
    );
    assert!(
        !out.contains(SIBLING),
        "even with no VM to read a tag from, the sibling must not be matched: {out}"
    );
}

#[test]
fn test_destroy_can_reclaim_leftovers_after_vm_already_deleted() {
    // Reproduces the reported state exactly: VM, disks and NIC already gone;
    // the Public IP and NSG left orphaned, unassociated, and still billing.
    let mut mock = mock_with_full_session();
    mock.vms = vec![];
    mock.disk_json = "[]".to_string();
    mock.nic_json = "[]".to_string();
    mock.pip_json = format!(
        r#"[
          {{"name":"{VM}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
            "tags":{{"azlin-session":"{VM}"}}}},
          {{"name":"{SIBLING}PublicIP","resourceGroup":"{RG}","ipConfiguration":null,
            "tags":{{"azlin-session":"{SIBLING}"}}}}
        ]"#
    );
    mock.nsg_json = format!(
        r#"[
          {{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":[],"networkInterfaces":[],
            "tags":{{"azlin-session":"{VM}"}}}},
          {{"name":"{SIBLING}NSG","resourceGroup":"{RG}","subnets":[],"networkInterfaces":[],
            "tags":{{"azlin-session":"{SIBLING}"}}}}
        ]"#
    );
    let msg = handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        log.contains(&format!("delete_public_ip:{VM}PublicIP")),
        "re-running destroy must reclaim the leaked IP: {log:?}"
    );
    assert!(log.contains(&format!("delete_nsg:{VM}NSG")), "{log:?}");
    assert!(
        !log.iter().any(|c| c.contains(SIBLING)),
        "sibling leftovers must survive: {log:?}"
    );
    assert!(!log.iter().any(|c| c.starts_with("delete_vm:")));
    assert!(msg.contains("month"), "{msg}");
}

#[test]
fn test_dry_run_does_not_list_sibling_resources() {
    let mock = mock_with_full_session();
    let out = format_destroy_dry_run_live(&mock, RG, VM).unwrap();
    assert!(
        !out.contains(SIBLING),
        "sibling session must not appear in the plan: {out}"
    );
}

// ── --delete-rg guard ───────────────────────────────────────────────

#[test]
fn test_delete_rg_rejection_explains_the_danger() {
    let msg = crate::lifecycle_helpers::delete_rg_rejected_message("myvm_group");
    assert!(msg.contains("myvm_group"));
    assert!(msg.contains("not supported"));
    assert!(
        msg.contains("cleanup"),
        "offer the targeted alternative: {msg}"
    );
}

// ── The NSG that survived the live provision test ───────────────────

/// Reproduces the leak observed against real Azure: `destroy` removed the VM,
/// disks, NIC and Public IP, but reported
/// `skipping <vm>NSG: still associated with another resource` — and an
/// independent `az network nsg show` immediately afterwards returned
/// `networkInterfaces: null, subnets: null`, proving the NSG was by then
/// associated with nothing at all.
///
/// The plan is computed from one snapshot taken before anything is deleted, so
/// whenever that snapshot makes an NSG look in-use, the resource is skipped
/// permanently and leaks. Here the snapshot reports an association the plan
/// cannot attribute to this teardown (a NIC in another resource group), which
/// is the conservative, correct first-pass answer; deleting the NIC then frees
/// the NSG, and the re-check pass must notice and remove it.
fn mock_with_nsg_that_only_looks_in_use() -> MockAzureOps {
    let mut mock = mock_with_full_session();
    // First snapshot: the NSG reports an association the planner cannot match
    // to a NIC it is deleting, so it is (correctly) skipped as in-use.
    mock.nsg_json = format!(
        r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
              "networkInterfaces":[{{"id":"{}"}}],
              "tags":{{"azlin-session":"{VM}"}}}}]"#,
        "/subscriptions/s/resourceGroups/other-rg/providers/Microsoft.Network/networkInterfaces/unknown-nic"
    );
    // After the NIC is deleted, Azure reports the NSG as free — the exact
    // state observed live.
    mock.nsg_json_after_nic_delete = Some(format!(
        r#"[{{"name":"{VM}NSG","resourceGroup":"{RG}","subnets":null,
              "networkInterfaces":null,"tags":{{"azlin-session":"{VM}"}}}}]"#
    ));
    mock
}

#[test]
fn test_nsg_freed_by_nic_deletion_is_deleted_by_recheck() {
    let mock = mock_with_nsg_that_only_looks_in_use();
    let msg = handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        log.contains(&format!("delete_nsg:{VM}NSG")),
        "NSG freed by the NIC deletion must be deleted, not leaked: {log:?}"
    );
    assert!(
        !msg.contains("still associated"),
        "a resource the re-check deleted must not still be reported as skipped: {msg}"
    );
}

#[test]
fn test_recheck_runs_only_after_nic_deletion() {
    let mock = mock_with_nsg_that_only_looks_in_use();
    handle_delete(&mock, RG, VM).unwrap();
    let nic_delete = mock
        .call_index(&format!("delete_nic:{VM}VMNic"))
        .expect("NIC must be deleted");
    let nsg_delete = mock
        .call_index(&format!("delete_nsg:{VM}NSG"))
        .expect("NSG must be deleted");
    assert!(
        nic_delete < nsg_delete,
        "Azure refuses to delete an NSG while a NIC still references it"
    );
}

#[test]
fn test_recheck_never_deletes_another_sessions_nsg() {
    let mut mock = mock_with_nsg_that_only_looks_in_use();
    // A sibling session's NSG, free after our NIC goes but not ours to delete.
    mock.nsg_json_after_nic_delete = Some(format!(
        r#"[{{"name":"{SIBLING}NSG","resourceGroup":"{RG}","subnets":null,
              "networkInterfaces":null,"tags":{{"azlin-session":"{SIBLING}"}}}}]"#
    ));
    handle_delete(&mock, RG, VM).unwrap();
    let log = mock.call_log();
    assert!(
        !log.contains(&format!("delete_nsg:{SIBLING}NSG")),
        "the re-check must not widen ownership beyond the target session: {log:?}"
    );
}

#[test]
fn test_no_recheck_when_nothing_was_skipped_as_in_use() {
    let mock = mock_with_full_session();
    handle_delete(&mock, RG, VM).unwrap();
    // Two list calls per resource kind would mean a needless second round-trip
    // to Azure on the common path where the plan already covered everything.
    let nsg_lists = mock
        .call_log()
        .iter()
        .filter(|c| *c == "list_nsgs_json")
        .count();
    assert_eq!(
        nsg_lists, 1,
        "the re-check must not re-read Azure when no resource was skipped as in-use"
    );
}
