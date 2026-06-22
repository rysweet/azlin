//! Extracted command handler logic for testability.
//!
//! Each handler function accepts `&dyn AzureOps` instead of `&VmManager`,
//! enabling mock-based testing without live Azure credentials.
//!
//! Some functions are only called from tests currently — they provide
//! covered logic that mirrors main.rs command handlers.
#![allow(dead_code)]
//!
//! The handlers produce structured output (strings, data) rather than directly
//! printing, so tests can assert on return values.
//!
//! Functions are being wired into dispatch_command incrementally. Those not yet
//! wired are still exercised via tests and will be integrated in follow-up PRs.

mod autopilot;
mod batch;
mod cleanup;
mod connect;
mod context;
mod costs;
mod create;
mod health;
mod help;
mod keys;
mod list;
mod show;
mod snapshot;
mod storage;
mod tags;

pub use autopilot::*;
pub use cleanup::*;
pub use connect::*;
pub use context::*;
pub use costs::*;
pub use help::*;
pub use keys::*;
pub use show::*;
pub use snapshot::*;
pub use storage::*;
pub use tags::*;

// Re-exported for test modules only (handler functions used in test assertions)
#[allow(unused_imports)]
pub use batch::*;
#[allow(unused_imports)]
pub use create::*;
#[allow(unused_imports)]
pub use health::*;
#[allow(unused_imports)]
pub use list::*;

#[cfg(test)]
mod tests;
