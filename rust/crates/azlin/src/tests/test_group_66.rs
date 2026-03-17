use std::net::TcpListener;

/// Verify that the port returned by `pick_unused_local_port` can be immediately
/// bound by the caller — i.e. the OS has not reallocated it in the gap between
/// the internal listener drop and this bind.  This is a probabilistic check
/// (there is a tiny TOCTOU window) but it will catch systematic failures.
#[test]
fn test_pick_unused_local_port_returns_bindable_port() {
    let port = crate::pick_unused_local_port().unwrap();
    // If the port is genuinely free we must be able to bind it.
    // Drop the listener immediately to avoid holding the port across parallel tests.
    let bind_ok = TcpListener::bind(("127.0.0.1", port)).is_ok();
    assert!(
        bind_ok,
        "pick_unused_local_port returned port {port} which could not be bound"
    );
}

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

/// Verify that `wait_for_local_port_listener` bails early when the nominated
/// process exits before listening on the port.
///
/// Strategy: spawn a `true` process (exits immediately), grab its PID, wait for
/// it to finish, then call `wait_for_local_port_listener` with a long timeout.
/// The poller should detect the dead process via kill -0 and return an error
/// faster than the timeout.
#[test]
fn test_wait_for_local_port_listener_bails_on_dead_process() {
    // Grab an unbound port — nothing will ever listen on it.
    let port = {
        let l = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        l.local_addr().unwrap().port()
    };

    // Spawn a process that exits immediately.
    let mut child = std::process::Command::new("true")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .expect("failed to spawn 'true'");
    let dead_pid = child.id();
    child.wait().expect("wait failed");

    // The process is now dead. The poller should detect this and bail.
    let result = crate::wait_for_local_port_listener(
        port,
        dead_pid,
        std::time::Duration::from_secs(5), // generous timeout — should bail early
    );

    assert!(
        result.is_err(),
        "expected an error for dead process but got Ok(())"
    );
    let msg = format!("{}", result.unwrap_err());
    assert!(
        msg.contains("exited before listening"),
        "expected 'exited before listening' in error message, got: {msg}"
    );
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
