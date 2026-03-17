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

/// Verify that `wait_for_local_port_listener` returns a "Timed out" error when no
/// process binds the nominated port within the deadline.
///
/// Strategy: allocate an OS port, immediately drop the listener to release it, then
/// call the function with a 50 ms deadline.  Nothing will bind the port in that
/// window, so the poller must reach the deadline and return `Err`.
///
/// Using `std::process::id()` as the pid keeps the alive-process sentinel satisfied
/// (kill -0 succeeds), so the only exit path is the timeout branch — exactly the
/// one this test is probing.
#[test]
fn test_wait_for_local_port_listener_times_out_when_no_listener() {
    // Grab a free port from the OS, then release it immediately so nobody is listening.
    let port = {
        let l = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        l.local_addr().unwrap().port()
        // `l` is dropped here; the port is now unbound.
    };

    let result = crate::wait_for_local_port_listener(
        port,
        std::process::id(), // current process is alive → no early-exit via kill -0
        std::time::Duration::from_millis(50),
    );

    assert!(result.is_err(), "expected a timeout error but got Ok(())");
    let msg = format!("{}", result.unwrap_err());
    assert!(
        msg.contains("Timed out"),
        "expected 'Timed out' in error message, got: {msg}"
    );
}
