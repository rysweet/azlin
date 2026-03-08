/// Return the (in-progress, completed) label pair for a stop/deallocate action.
/// E.g. `("Deallocating", "Deallocated")` or `("Stopping", "Stopped")`.
pub fn stop_action_labels(deallocate: bool) -> (&'static str, &'static str) {
    if deallocate {
        ("Deallocating", "Deallocated")
    } else {
        ("Stopping", "Stopped")
    }
}
