use super::common::{make_test_vm, MockAzureOps};
use crate::handlers::{handle_delete, DeleteTarget};
use azlin_core::models::PowerState;

const RG: &str = "synthetic-destroy-rg";
const VM: &str = "synthetic-destroy-vm";

#[test]
fn delete_target_resource_group_selects_only_group_deletion() {
    let mock = MockAzureOps::new(vec![]);

    handle_delete(&mock, DeleteTarget::ResourceGroup { resource_group: RG }).unwrap();

    assert_eq!(mock.call_log(), vec![format!("delete_resource_group:{RG}")]);
}

#[test]
fn delete_target_virtual_machine_selects_only_vm_deletion() {
    let mock = MockAzureOps::new(vec![make_test_vm(VM, PowerState::Running)]);

    handle_delete(
        &mock,
        DeleteTarget::VirtualMachine {
            resource_group: RG,
            vm_name: VM,
        },
    )
    .unwrap();

    let destructive_calls: Vec<String> = mock
        .call_log()
        .into_iter()
        .filter(|call| call.starts_with("delete_"))
        .collect();
    assert_eq!(destructive_calls, vec![format!("delete_vm:{VM}")]);
}

#[test]
fn resource_group_delete_failure_has_operation_and_target_context() {
    let mut mock = MockAzureOps::new(vec![]);
    mock.failing_on_delete.push(RG.to_string());

    let error =
        handle_delete(&mock, DeleteTarget::ResourceGroup { resource_group: RG }).unwrap_err();
    let chain = format!("{error:#}");

    assert!(chain.contains("failed to delete resource group"));
    assert!(chain.contains(RG));
    assert!(chain.contains("OperationNotAllowed"));
    assert_eq!(mock.call_log(), vec![format!("delete_resource_group:{RG}")]);
}

#[test]
fn vm_delete_failure_has_operation_and_both_target_names() {
    let mut mock = MockAzureOps::new(vec![make_test_vm(VM, PowerState::Running)]);
    mock.failing_on_delete.push(VM.to_string());

    let error = handle_delete(
        &mock,
        DeleteTarget::VirtualMachine {
            resource_group: RG,
            vm_name: VM,
        },
    )
    .unwrap_err();
    let chain = format!("{error:#}");

    assert!(chain.contains("failed to delete VM"));
    assert!(chain.contains(VM));
    assert!(chain.contains(RG));
    assert!(chain.contains("OperationNotAllowed"));
    let destructive_calls: Vec<String> = mock
        .call_log()
        .into_iter()
        .filter(|call| call.starts_with("delete_"))
        .collect();
    assert_eq!(destructive_calls, vec![format!("delete_vm:{VM}")]);
}
