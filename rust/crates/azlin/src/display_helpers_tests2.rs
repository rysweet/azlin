use super::*;

#[test]
fn test_format_ip_display_with_public() {
    assert_eq!(
        format_ip_display(Some("1.2.3.4"), Some("10.0.0.1")),
        "1.2.3.4 (Pub)"
    );
}

#[test]
fn test_format_ip_display_private_only() {
    assert_eq!(format_ip_display(None, Some("10.0.0.1")), "10.0.0.1 (Bast)");
}

#[test]
fn test_format_ip_display_none() {
    assert_eq!(format_ip_display(None, None), "N/A");
}

#[test]
fn test_parse_vm_size_specs_d4s() {
    let (cpu, mem) = parse_vm_size_specs("Standard_D4s_v3");
    assert_eq!(cpu, "4");
    assert_eq!(mem, "16 GB");
}

#[test]
fn test_parse_vm_size_specs_e16() {
    let (cpu, mem) = parse_vm_size_specs("Standard_E16as_v5");
    assert_eq!(cpu, "16");
    assert_eq!(mem, "128 GB"); // E-series: 16 * 8
}

#[test]
fn test_parse_vm_size_specs_f2() {
    let (cpu, mem) = parse_vm_size_specs("Standard_F2s_v2");
    assert_eq!(cpu, "2");
    assert_eq!(mem, "4 GB"); // F-series: 2 * 2
}

#[test]
fn test_parse_vm_size_specs_b1() {
    let (cpu, mem) = parse_vm_size_specs("Standard_B1s");
    assert_eq!(cpu, "1");
    assert_eq!(mem, "4 GB"); // B-series: 1 * 4
}

#[test]
fn test_parse_vm_size_specs_unknown() {
    let (cpu, mem) = parse_vm_size_specs("weird");
    assert_eq!(cpu, "-");
    assert_eq!(mem, "-");
}

#[test]
fn test_parse_vm_size_specs_m_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_M8ms_v2");
    assert_eq!(cpu, "8");
    assert_eq!(mem, "128 GB"); // M-series: 8 * 16
}

#[test]
fn test_parse_vm_size_specs_n_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_N6");
    assert_eq!(cpu, "6");
    assert_eq!(mem, "36 GB"); // N-series: 6 * 6
}

#[test]
fn test_parse_vm_size_specs_l_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_L8s_v3");
    assert_eq!(cpu, "8");
    assert_eq!(mem, "64 GB"); // L-series: 8 * 8
}
