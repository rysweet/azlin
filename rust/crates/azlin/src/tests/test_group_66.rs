use std::net::TcpListener;

#[test]
fn test_pick_unused_local_port_skips_occupied_listener() {
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let occupied = listener.local_addr().unwrap().port();

    for _ in 0..8 {
        let candidate = crate::pick_unused_local_port().unwrap();
        assert_ne!(candidate, occupied);
    }
}

#[test]
fn test_wait_for_local_port_listener_detects_ready_socket() {
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = listener.local_addr().unwrap().port();

    crate::wait_for_local_port_listener(
        port,
        std::process::id(),
        std::time::Duration::from_millis(100),
    )
    .unwrap();
}
