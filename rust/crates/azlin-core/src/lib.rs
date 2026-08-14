//! azlin-core: Core types, configuration, models, and error handling.

pub mod config;
pub mod error;
pub mod gui_container;
pub mod models;
pub mod sanitizer;

pub use config::{AzlinConfig, RestoreMode, SshSyncMethod};
pub use error::{AzlinError, Result};
