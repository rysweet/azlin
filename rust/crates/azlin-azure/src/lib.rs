//! azlin-azure: Azure operations for VM management, auth, networking, and costs.
//!
//! All Azure operations use the `az` CLI, matching the Python reference.

pub mod auth;
pub mod cloud_init;
pub mod costs;
pub mod error_handler;
pub mod orphan_detector;
pub mod rate_limiter;
pub mod retry;
pub mod subprocess;
pub mod vm;

pub use auth::AzureAuth;
pub use costs::get_cost_summary;
pub use subprocess::run_with_timeout;
pub use vm::az_cli_with_timeout;
pub use vm::VmManager;
