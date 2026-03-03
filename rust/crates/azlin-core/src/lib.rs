//! azlin-core: Core types, configuration, models, and error handling.

pub mod config;
pub mod error;
pub mod models;

pub use config::AzlinConfig;
pub use error::{AzlinError, Result};
