/// Build a data-disk name for a VM: `{vm_name}_datadisk_{lun}`.
pub fn build_data_disk_name(vm_name: &str, lun: u32) -> String {
    format!("{}_datadisk_{}", vm_name, lun)
}

/// Build the restored OS disk name: `{vm_name}_OsDisk_restored`.
pub fn build_restored_disk_name(vm_name: &str) -> String {
    format!("{}_OsDisk_restored", vm_name)
}
