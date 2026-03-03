//! azlin-azure: Azure SDK integration for VM management, auth, networking, and costs.

pub mod auth;
pub mod costs;
pub mod rate_limiter;
pub mod retry;
pub mod vm;

pub use auth::AzureAuth;
pub use azure_core::credentials::TokenCredential;
pub use costs::get_cost_summary;
pub use vm::VmManager;
