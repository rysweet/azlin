//! azlin-azure: Azure SDK integration for VM management, auth, networking, and costs.

pub mod auth;
pub mod vm;

pub use auth::AzureAuth;
pub use azure_core::credentials::TokenCredential;
pub use vm::VmManager;
