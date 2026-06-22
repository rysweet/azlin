//! Re-export table rendering from azlin-cli.
//!
//! The canonical implementation lives in `azlin_cli::table_render`.
//! This module re-exports everything so existing `crate::table_render::*` usage
//! continues to work without changing every call site.

pub(crate) use azlin_cli::table_render::border_line;
pub(crate) use azlin_cli::table_render::render_row;
pub(crate) use azlin_cli::table_render::trunc;
pub(crate) use azlin_cli::table_render::trunc_right;
pub(crate) use azlin_cli::table_render::SimpleTable;
