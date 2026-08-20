//! Detects CLI inputs that reach `--help` but are never read by a handler.
//!
//! # The bug class
//!
//! azlin declares its CLI as clap `Subcommand` enums in `azlin-cli/src/lib.rs`
//! and dispatches by destructuring those variants in `crates/azlin/src`.
//! Handlers destructure with `..`, so a field added to the enum and forgotten
//! in the handler produces no compiler error and no runtime warning: clap
//! accepts the flag, prints it in `--help`, and the handler drops it on the
//! floor. Issue #1089 catalogues ~25 live instances, several of which do the
//! opposite of what the user asked (`restore --dry-run` performed the restore;
//! `batch stop --vm-pattern` stopped every VM in the resource group).
//!
//! # What "wired" means here
//!
//! A declared field is *wired* if some pattern in `crates/azlin/src` binds it
//! to a usable name. These do not count as bindings:
//!
//! - the field is swallowed by `..`,
//! - the field is bound to `_` (`auth_profile: _`),
//! - the field is bound to an underscore-prefixed name (`dry_run: _dry_run`) —
//!   the shape this codebase uses to silence the unused-variable warning.
//!
//! A field that *is* bound to a real name and then left unused is caught by
//! rustc's `unused_variables` lint under the existing `-D warnings` clippy
//! gate, so between the two checks the whole path from `--help` to handler is
//! covered.
//!
//! # Why syn rather than a regex
//!
//! The distinction that matters — `dry_run` versus `dry_run: _dry_run` versus
//! `..` — is a Rust pattern-grammar distinction. It appears inside nested
//! `match` arms, `|`-alternatives and `cmd @ Variant { .. }` bindings that a
//! line-oriented regex reads wrong in both directions. syn parses the same
//! grammar rustc does.
//!
//! # What this does not see
//!
//! - **Global args on the `Cli` struct** (`--verbose`, `--output`,
//!   `--auth-profile`, `--startup-time`). They are read as `cli.field` field
//!   accesses, not as pattern bindings, so a different technique would be
//!   needed. Note that a *per-subcommand* field shadowing a global — such as
//!   `Commands::Show::verbose` — is checked, and is currently unwired.
//! - **`#[command(flatten)]` groups.** None exist today; if one is added, its
//!   fields live on another type and are skipped rather than misattributed.
//! - **Wired-but-wrong.** Binding `dry_run` and then deleting the VM anyway is
//!   a correctness bug no static check of this shape can see. This gate proves
//!   the value reaches the handler, nothing more.
//! - **Bound-then-unused.** Left to rustc's `unused_variables` lint under the
//!   existing `-D warnings` clippy gate.
//! - **Unqualified patterns.** A pattern written `Stop { .. }` rather than
//!   `azlin_cli::BatchAction::Stop { .. }` is matched on variant name alone,
//!   so an unrelated struct of the same name with the same field name could
//!   in principle mask a finding. Every dispatch site today is qualified.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use syn::punctuated::Punctuated;
use syn::visit::Visit;
use syn::{Attribute, Expr, Fields, Item, ItemMod, Lit, Member, Meta, Pat, PatStruct, Token, Type};

// ---------------------------------------------------------------------------
// Declared side: clap enums in azlin-cli/src/lib.rs
// ---------------------------------------------------------------------------

/// One user-supplied input declared on a clap `Subcommand` variant.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Declared {
    /// Enum the variant lives on, e.g. `BatchAction`.
    pub enum_name: String,
    /// Variant the field lives on, e.g. `Stop`.
    pub variant: String,
    /// Rust field name, e.g. `no_deallocate`.
    pub field: String,
    /// How a user types it: `--no-deallocate`, `-y`, or `<QUERY>`.
    pub cli_form: String,
    /// First line of the doc comment, which is what clap prints in `--help`.
    /// Quoting it in the report shows the promise the handler is breaking.
    pub help: String,
}

impl Declared {
    /// Stable identifier used by the allowlist.
    pub fn key(&self) -> String {
        format!("{}::{}::{}", self.enum_name, self.variant, self.field)
    }
}

/// Everything parsed out of the CLI definition file.
#[derive(Debug, Default)]
pub struct CliSurface {
    pub declared: Vec<Declared>,
    /// Child subcommand enum -> (parent enum, parent variant), from
    /// `#[command(subcommand)]` fields. Used to render `azlin batch stop`.
    parents: BTreeMap<String, (String, String)>,
    /// Enum -> variant -> command name as clap spells it.
    command_names: BTreeMap<String, BTreeMap<String, String>>,
}

impl CliSurface {
    /// Human-readable invocation for a declared input, e.g.
    /// `azlin batch stop --no-deallocate`.
    pub fn invocation(&self, d: &Declared) -> String {
        let mut path = Vec::new();
        let mut enum_name = d.enum_name.clone();
        let mut variant = d.variant.clone();
        // Walk up the subcommand tree. The bound guards against a cycle in
        // malformed input rather than any real nesting depth.
        for _ in 0..16 {
            path.push(self.command_name(&enum_name, &variant));
            match self.parents.get(&enum_name) {
                Some((pe, pv)) => {
                    enum_name = pe.clone();
                    variant = pv.clone();
                }
                None => break,
            }
        }
        path.push("azlin".to_string());
        path.reverse();
        format!("{} {}", path.join(" "), d.cli_form)
    }

    fn command_name(&self, enum_name: &str, variant: &str) -> String {
        self.command_names
            .get(enum_name)
            .and_then(|m| m.get(variant))
            .cloned()
            .unwrap_or_else(|| kebab_camel(variant))
    }
}

/// Parse the clap surface out of a single CLI definition file.
pub fn parse_cli_surface(src: &str) -> syn::Result<CliSurface> {
    let file = syn::parse_file(src)?;
    let mut surface = CliSurface::default();

    for item in &file.items {
        let Item::Enum(e) = item else { continue };
        if !derives_subcommand(&e.attrs) {
            continue;
        }
        let enum_name = e.ident.to_string();

        for variant in &e.variants {
            let variant_name = variant.ident.to_string();
            surface
                .command_names
                .entry(enum_name.clone())
                .or_default()
                .insert(
                    variant_name.clone(),
                    command_rename(&variant.attrs).unwrap_or_else(|| kebab_camel(&variant_name)),
                );

            let Fields::Named(named) = &variant.fields else {
                continue;
            };
            for field in &named.named {
                let Some(ident) = &field.ident else { continue };

                // `#[command(subcommand)]` is a link to a child enum, not an
                // input of its own; `#[command(flatten)]` re-exports another
                // struct's args, whose own fields we cannot attribute here.
                if let Some(kind) = nested_command_kind(&field.attrs) {
                    if kind == "subcommand" {
                        if let Some(child) = type_ident(&field.ty) {
                            surface
                                .parents
                                .insert(child, (enum_name.clone(), variant_name.clone()));
                        }
                    }
                    continue;
                }

                surface.declared.push(Declared {
                    enum_name: enum_name.clone(),
                    variant: variant_name.clone(),
                    field: ident.to_string(),
                    cli_form: cli_form(&ident.to_string(), &field.attrs),
                    help: help_text(&field.attrs),
                });
            }
        }
    }

    Ok(surface)
}

fn derives_subcommand(attrs: &[Attribute]) -> bool {
    attrs.iter().any(|attr| {
        attr.path().is_ident("derive")
            && attr
                .parse_args_with(Punctuated::<syn::Path, Token![,]>::parse_terminated)
                .map(|paths| paths.iter().any(|p| p.is_ident("Subcommand")))
                .unwrap_or(false)
    })
}

/// Returns `"subcommand"` or `"flatten"` when the field is a structural link
/// rather than a user-supplied value.
fn nested_command_kind(attrs: &[Attribute]) -> Option<&'static str> {
    for attr in attrs {
        if !attr.path().is_ident("command") {
            continue;
        }
        for meta in parse_meta_list(attr) {
            if let Meta::Path(p) = meta {
                if p.is_ident("subcommand") {
                    return Some("subcommand");
                }
                if p.is_ident("flatten") {
                    return Some("flatten");
                }
            }
        }
    }
    None
}

/// `#[command(name = "...")]` on a variant overrides the derived name.
fn command_rename(attrs: &[Attribute]) -> Option<String> {
    for attr in attrs {
        if !attr.path().is_ident("command") {
            continue;
        }
        for meta in parse_meta_list(attr) {
            if let Meta::NameValue(nv) = meta {
                if nv.path.is_ident("name") {
                    if let Some(s) = lit_string(&nv.value) {
                        return Some(s);
                    }
                }
            }
        }
    }
    None
}

/// Render how the user types this input, following clap's derive defaults.
fn cli_form(field: &str, attrs: &[Attribute]) -> String {
    let mut long: Option<String> = None;
    let mut short: Option<String> = None;

    for attr in attrs {
        if !attr.path().is_ident("arg") {
            continue;
        }
        for meta in parse_meta_list(attr) {
            match meta {
                Meta::Path(p) if p.is_ident("long") => long = Some(field.replace('_', "-")),
                Meta::Path(p) if p.is_ident("short") => {
                    short = field.chars().next().map(|c| c.to_string())
                }
                Meta::NameValue(nv) if nv.path.is_ident("long") => long = lit_string(&nv.value),
                Meta::NameValue(nv) if nv.path.is_ident("short") => short = lit_char(&nv.value),
                _ => {}
            }
        }
    }

    match (long, short) {
        (Some(l), _) => format!("--{l}"),
        (None, Some(s)) => format!("-{s}"),
        // No `long`/`short`: clap makes it a positional argument.
        (None, None) => format!("<{}>", field.to_uppercase()),
    }
}

/// First line of the `///` doc comment, which clap renders as the flag's help.
fn help_text(attrs: &[Attribute]) -> String {
    for attr in attrs {
        if !attr.path().is_ident("doc") {
            continue;
        }
        if let Meta::NameValue(nv) = &attr.meta {
            if let Some(s) = lit_string(&nv.value) {
                return s.trim().to_string();
            }
        }
    }
    String::new()
}

fn parse_meta_list(attr: &Attribute) -> Vec<Meta> {
    attr.parse_args_with(Punctuated::<Meta, Token![,]>::parse_terminated)
        .map(|m| m.into_iter().collect())
        .unwrap_or_default()
}

fn lit_string(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Lit(l) => match &l.lit {
            Lit::Str(s) => Some(s.value()),
            _ => None,
        },
        _ => None,
    }
}

fn lit_char(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Lit(l) => match &l.lit {
            Lit::Char(c) => Some(c.value().to_string()),
            _ => None,
        },
        _ => None,
    }
}

/// Last path segment of a type, unwrapping one level of `Option<..>`.
fn type_ident(ty: &Type) -> Option<String> {
    let Type::Path(tp) = ty else { return None };
    let seg = tp.path.segments.last()?;
    if seg.ident == "Option" {
        if let syn::PathArguments::AngleBracketed(args) = &seg.arguments {
            for arg in &args.args {
                if let syn::GenericArgument::Type(inner) = arg {
                    return type_ident(inner);
                }
            }
        }
    }
    Some(seg.ident.to_string())
}

/// `OsUpdate` -> `os-update`, matching clap's default verbatim-to-kebab rename.
fn kebab_camel(s: &str) -> String {
    let mut out = String::new();
    for (i, c) in s.chars().enumerate() {
        if c.is_uppercase() {
            if i != 0 {
                out.push('-');
            }
            out.extend(c.to_lowercase());
        } else {
            out.push(c);
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Handler side: struct patterns under crates/azlin/src
// ---------------------------------------------------------------------------

/// Field names really bound by handler patterns, keyed by
/// `(enum name, variant)`. An empty enum name means the pattern named the
/// variant without qualification, so it matches any enum.
#[derive(Debug, Default)]
pub struct BoundFields {
    map: BTreeMap<(String, String), BTreeSet<String>>,
}

impl BoundFields {
    pub fn is_bound(&self, d: &Declared) -> bool {
        let qualified = (d.enum_name.clone(), d.variant.clone());
        let unqualified = (String::new(), d.variant.clone());
        [qualified, unqualified]
            .iter()
            .any(|k| self.map.get(k).is_some_and(|f| f.contains(&d.field)))
    }

    fn record(&mut self, enum_name: String, variant: String, field: String) {
        self.map
            .entry((enum_name, variant))
            .or_default()
            .insert(field);
    }

    /// Merge everything bound in one parsed file.
    pub fn absorb(&mut self, file: &syn::File) {
        let mut visitor = PatternVisitor { bound: self };
        visitor.visit_file(file);
    }
}

struct PatternVisitor<'a> {
    bound: &'a mut BoundFields,
}

impl<'ast> Visit<'ast> for PatternVisitor<'_> {
    fn visit_item_mod(&mut self, node: &'ast ItemMod) {
        // A `#[cfg(test)]` module can destructure a variant exhaustively
        // without the shipped binary ever reading the field, which would mask
        // exactly the bug we are looking for.
        if has_cfg_test(&node.attrs) {
            return;
        }
        syn::visit::visit_item_mod(self, node);
    }

    fn visit_item_fn(&mut self, node: &'ast syn::ItemFn) {
        if has_cfg_test(&node.attrs) {
            return;
        }
        syn::visit::visit_item_fn(self, node);
    }

    fn visit_pat_struct(&mut self, node: &'ast PatStruct) {
        let segs: Vec<String> = node
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .collect();
        let (enum_name, variant) = match segs.len() {
            0 => return,
            1 => (String::new(), segs[0].clone()),
            n => (segs[n - 2].clone(), segs[n - 1].clone()),
        };

        for fp in &node.fields {
            let Member::Named(ident) = &fp.member else {
                continue;
            };
            if is_real_binding(&fp.pat) {
                self.bound
                    .record(enum_name.clone(), variant.clone(), ident.to_string());
            }
        }

        syn::visit::visit_pat_struct(self, node);
    }
}

/// Does this sub-pattern give the handler a usable value?
fn is_real_binding(pat: &Pat) -> bool {
    match pat {
        Pat::Wild(_) => false,
        Pat::Ident(pi) => !pi.ident.to_string().starts_with('_'),
        // Anything else (`Some(x)`, a nested struct pattern, a literal guard)
        // means the handler is actually looking at the value.
        _ => true,
    }
}

fn has_cfg_test(attrs: &[Attribute]) -> bool {
    attrs.iter().any(|attr| {
        attr.path().is_ident("cfg")
            && parse_meta_list(attr)
                .iter()
                .any(|m| matches!(m, Meta::Path(p) if p.is_ident("test")))
    })
}

// ---------------------------------------------------------------------------
// Allowlist
// ---------------------------------------------------------------------------

/// A temporarily tolerated unwired flag, from the allowlist file.
#[derive(Debug, Clone)]
pub struct AllowEntry {
    pub key: String,
    pub reason: String,
}

/// Parse the allowlist. Format, one entry per line:
///
/// ```text
/// # free-form comment
/// Enum::Variant::field = why this is temporarily tolerated
/// ```
///
/// The reason is mandatory: an entry cannot be added without saying why.
pub fn parse_allowlist(src: &str) -> Result<Vec<AllowEntry>, Vec<String>> {
    let mut entries = Vec::new();
    let mut errors = Vec::new();
    let mut seen = BTreeSet::new();

    for (i, raw) in src.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((key, reason)) = line.split_once('=') else {
            errors.push(format!(
                "allowlist line {}: expected `Enum::Variant::field = reason`, got `{line}`",
                i + 1
            ));
            continue;
        };
        let key = key.trim().to_string();
        let reason = reason.trim().to_string();
        if key.split("::").count() != 3 {
            errors.push(format!(
                "allowlist line {}: key must be `Enum::Variant::field`, got `{key}`",
                i + 1
            ));
            continue;
        }
        if reason.is_empty() {
            errors.push(format!(
                "allowlist line {}: `{key}` has no reason. Every entry must say why it is tolerated.",
                i + 1
            ));
            continue;
        }
        if !seen.insert(key.clone()) {
            errors.push(format!("allowlist line {}: duplicate entry `{key}`", i + 1));
            continue;
        }
        entries.push(AllowEntry { key, reason });
    }

    if let Some(err) = header_count_mismatch(src, entries.len()) {
        errors.push(err);
    }

    if errors.is_empty() {
        Ok(entries)
    } else {
        Err(errors)
    }
}

/// The ledger's own header states how many entries it holds. Nothing enforced
/// it, so it drifted: the file said 25 while holding 22, which is the same
/// class of bug the whole check exists for — a stated number that stopped
/// being true and nothing noticed. A header with no count is fine; a header
/// with a wrong one is not.
fn header_count_mismatch(src: &str, actual: usize) -> Option<String> {
    for (i, raw) in src.lines().enumerate() {
        let line = raw.trim();
        if !line.starts_with('#') || !line.contains("accepted and discarded") {
            continue;
        }
        let stated = line
            .split_once('(')
            .and_then(|(_, rest)| rest.split_once(')'))
            .and_then(|(n, _)| n.trim().parse::<usize>().ok())?;
        if stated != actual {
            return Some(format!(
                "allowlist line {}: the header says {stated} entries and the file has {actual}. \
                 The count is derived, not authored — read it off the file with \
                 `grep -cE '^[A-Za-z].*::.* = ' crates/xtask/unwired-flags-allowlist.txt`.",
                i + 1
            ));
        }
        return None;
    }
    None
}

// ---------------------------------------------------------------------------
// Driver
// ---------------------------------------------------------------------------

/// Where the check reads from, relative to the Rust workspace root.
pub const CLI_DEF: &str = "crates/azlin-cli/src/lib.rs";
pub const HANDLER_DIR: &str = "crates/azlin/src";
pub const ALLOWLIST: &str = "crates/xtask/unwired-flags-allowlist.txt";

/// One flag that reaches `--help` but is never read.
#[derive(Debug, Clone)]
pub struct Finding {
    /// `azlin batch stop --no-deallocate`
    pub invocation: String,
    /// `BatchAction::Stop::no_deallocate`
    pub key: String,
    /// What `--help` promises this flag does.
    pub help: String,
}

#[derive(Debug)]
pub struct Report {
    pub declared_count: usize,
    pub enum_count: usize,
    pub scanned_files: usize,
    /// Unwired and not allowlisted. Non-empty means the check fails.
    pub unwired: Vec<Finding>,
    /// Unwired but tolerated, with the reason given in the allowlist.
    pub allowed: Vec<(Finding, String)>,
    /// Allowlist entries that no longer match an unwired flag.
    pub stale_allow: Vec<String>,
}

impl Report {
    pub fn ok(&self) -> bool {
        self.unwired.is_empty() && self.stale_allow.is_empty()
    }
}

/// Run the check against a Rust workspace root (the `rust/` directory).
pub fn run(workspace: &Path) -> Result<Report, String> {
    let cli_path = workspace.join(CLI_DEF);
    let cli_src = std::fs::read_to_string(&cli_path)
        .map_err(|e| format!("cannot read {}: {e}", cli_path.display()))?;
    let surface = parse_cli_surface(&cli_src)
        .map_err(|e| format!("cannot parse {}: {e}", cli_path.display()))?;

    let enum_count = surface
        .declared
        .iter()
        .map(|d| d.enum_name.clone())
        .collect::<BTreeSet<_>>()
        .len();

    let handler_root = workspace.join(HANDLER_DIR);
    let files = handler_sources(&handler_root)?;
    let mut bound = BoundFields::default();
    for path in &files {
        let src = std::fs::read_to_string(path)
            .map_err(|e| format!("cannot read {}: {e}", path.display()))?;
        let parsed =
            syn::parse_file(&src).map_err(|e| format!("cannot parse {}: {e}", path.display()))?;
        bound.absorb(&parsed);
    }

    let allow_path = workspace.join(ALLOWLIST);
    let allow_src = std::fs::read_to_string(&allow_path)
        .map_err(|e| format!("cannot read {}: {e}", allow_path.display()))?;
    let allow = parse_allowlist(&allow_src).map_err(|errs| errs.join("\n"))?;
    let allow_by_key: BTreeMap<String, String> = allow
        .iter()
        .map(|e| (e.key.clone(), e.reason.clone()))
        .collect();

    let mut unwired = Vec::new();
    let mut allowed = Vec::new();
    let mut hit_keys = BTreeSet::new();

    for d in &surface.declared {
        if bound.is_bound(d) {
            continue;
        }
        let finding = Finding {
            invocation: surface.invocation(d),
            key: d.key(),
            help: d.help.clone(),
        };
        match allow_by_key.get(&finding.key) {
            Some(reason) => {
                hit_keys.insert(finding.key.clone());
                allowed.push((finding, reason.clone()));
            }
            None => unwired.push(finding),
        }
    }

    // An allowlist entry that no longer matches an unwired flag is either
    // fixed (delete the line) or renamed (fix the line). Either way it must
    // not sit there silently granting a permission nothing needs.
    let stale_allow: Vec<String> = allow
        .iter()
        .filter(|e| !hit_keys.contains(&e.key))
        .map(|e| e.key.clone())
        .collect();

    Ok(Report {
        declared_count: surface.declared.len(),
        enum_count,
        scanned_files: files.len(),
        unwired,
        allowed,
        stale_allow,
    })
}

/// Handler sources to scan: every `.rs` file that ships in the binary.
///
/// Test files are skipped. A test that destructures a variant exhaustively
/// would register the field as "wired" while the shipped code still ignores
/// it, which is precisely the failure mode this check exists to catch.
fn handler_sources(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut out = Vec::new();
    collect_rs(root, &mut out)?;
    out.retain(|p| !is_test_source(p));
    out.sort();
    Ok(out)
}

fn collect_rs(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), String> {
    let entries =
        std::fs::read_dir(dir).map_err(|e| format!("cannot read dir {}: {e}", dir.display()))?;
    for entry in entries {
        let entry =
            entry.map_err(|e| format!("cannot read dir entry in {}: {e}", dir.display()))?;
        let path = entry.path();
        if path.is_dir() {
            collect_rs(&path, out)?;
        } else if path.extension().is_some_and(|e| e == "rs") {
            out.push(path);
        }
    }
    Ok(())
}

fn is_test_source(path: &Path) -> bool {
    let in_tests_dir = path
        .components()
        .any(|c| c.as_os_str() == "tests" || c.as_os_str() == "benches");
    let test_stem = path
        .file_stem()
        .and_then(|s| s.to_str())
        .is_some_and(|s| s.contains("test"));
    in_tests_dir || test_stem
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bound_from(src: &str) -> BoundFields {
        let file = syn::parse_file(src).expect("test source parses");
        let mut b = BoundFields::default();
        b.absorb(&file);
        b
    }

    fn decl(enum_name: &str, variant: &str, field: &str) -> Declared {
        Declared {
            enum_name: enum_name.into(),
            variant: variant.into(),
            field: field.into(),
            cli_form: String::new(),
            help: String::new(),
        }
    }

    #[test]
    fn declares_flags_positionals_and_renames() {
        let surface = parse_cli_surface(
            r#"
            #[derive(Subcommand, Debug)]
            pub enum Commands {
                Ask {
                    query: Option<String>,
                    #[arg(long)]
                    dry_run: bool,
                    #[arg(short = 'y', long)]
                    yes: bool,
                    #[arg(long = "type")]
                    log_type: String,
                    #[arg(short)]
                    number: u32,
                },
            }
            "#,
        )
        .unwrap();

        let forms: Vec<_> = surface
            .declared
            .iter()
            .map(|d| (d.field.as_str(), d.cli_form.as_str()))
            .collect();
        assert_eq!(
            forms,
            vec![
                ("query", "<QUERY>"),
                ("dry_run", "--dry-run"),
                ("yes", "--yes"),
                ("log_type", "--type"),
                ("number", "-n"),
            ]
        );
    }

    #[test]
    fn captures_the_help_line_clap_prints() {
        let surface = parse_cli_surface(
            r#"
            #[derive(Subcommand, Debug)]
            pub enum Commands {
                Restore {
                    /// Show what would be restored without doing it
                    ///
                    /// Longer explanation that clap puts in long help.
                    #[arg(long)]
                    dry_run: bool,
                },
            }
            "#,
        )
        .unwrap();
        assert_eq!(
            surface.declared[0].help,
            "Show what would be restored without doing it"
        );
    }

    #[test]
    fn skips_non_subcommand_enums_and_structural_fields() {
        let surface = parse_cli_surface(
            r#"
            #[derive(ValueEnum, Debug)]
            pub enum OutputFormat { Table, Json }

            #[derive(Subcommand, Debug)]
            pub enum Commands {
                Batch {
                    #[command(subcommand)]
                    action: BatchAction,
                },
            }
            "#,
        )
        .unwrap();
        assert!(surface.declared.is_empty());
    }

    #[test]
    fn builds_the_invocation_path_through_nested_subcommands() {
        let surface = parse_cli_surface(
            r#"
            #[derive(Subcommand, Debug)]
            pub enum Commands {
                Batch {
                    #[command(subcommand)]
                    action: BatchAction,
                },
                OsUpdate {
                    #[arg(long)]
                    force: bool,
                },
            }

            #[derive(Subcommand, Debug)]
            pub enum BatchAction {
                Stop {
                    #[arg(long)]
                    no_deallocate: bool,
                },
            }
            "#,
        )
        .unwrap();

        let stop = surface
            .declared
            .iter()
            .find(|d| d.field == "no_deallocate")
            .unwrap();
        assert_eq!(surface.invocation(stop), "azlin batch stop --no-deallocate");

        let os_update = surface
            .declared
            .iter()
            .find(|d| d.field == "force")
            .unwrap();
        assert_eq!(surface.invocation(os_update), "azlin os-update --force");
    }

    #[test]
    fn plain_and_nested_bindings_count_as_wired() {
        let bound = bound_from(
            r#"
            fn f(c: Commands) {
                match c {
                    azlin_cli::Commands::Restore { resource_group, exclude: Some(e), .. } => {}
                }
            }
            "#,
        );
        assert!(bound.is_bound(&decl("Commands", "Restore", "resource_group")));
        assert!(bound.is_bound(&decl("Commands", "Restore", "exclude")));
    }

    #[test]
    fn rest_pattern_underscore_and_underscore_prefix_are_not_wired() {
        let bound = bound_from(
            r#"
            fn f(c: Commands) {
                match c {
                    azlin_cli::Commands::Restore {
                        force,
                        dry_run: _dry_run,
                        auth_profile: _,
                        ..
                    } => {}
                }
            }
            "#,
        );
        assert!(bound.is_bound(&decl("Commands", "Restore", "force")));
        assert!(!bound.is_bound(&decl("Commands", "Restore", "dry_run")));
        assert!(!bound.is_bound(&decl("Commands", "Restore", "auth_profile")));
        // Swallowed by `..` and never mentioned at all.
        assert!(!bound.is_bound(&decl("Commands", "Restore", "no_multi_tab")));
    }

    #[test]
    fn routing_arm_alone_does_not_wire_but_a_later_handler_does() {
        // Mirrors the real two-stage dispatch: dispatch.rs routes with
        // `cmd @ Variant { .. }`, the cmd_* module destructures for real.
        let bound = bound_from(
            r#"
            fn route(c: Commands) {
                match c {
                    cmd @ azlin_cli::Commands::Env { .. } => cmd_env::dispatch(cmd),
                }
            }
            fn handle(c: Commands) {
                match c {
                    azlin_cli::Commands::Env { action } => match action {
                        azlin_cli::EnvAction::List { show_values, .. } => {}
                    },
                }
            }
            "#,
        );
        assert!(bound.is_bound(&decl("Commands", "Env", "action")));
        assert!(bound.is_bound(&decl("EnvAction", "List", "show_values")));
        assert!(!bound.is_bound(&decl("EnvAction", "List", "resource_group")));
    }

    #[test]
    fn test_only_destructuring_does_not_count_as_wired() {
        let bound = bound_from(
            r#"
            #[cfg(test)]
            mod tests {
                fn t(c: Commands) {
                    match c {
                        azlin_cli::Commands::Restore { dry_run, .. } => {}
                    }
                }
            }
            "#,
        );
        assert!(!bound.is_bound(&decl("Commands", "Restore", "dry_run")));
    }

    #[test]
    fn a_variant_named_the_same_on_two_enums_is_not_confused() {
        let bound = bound_from(
            r#"
            fn f(c: Commands) {
                match c {
                    azlin_cli::Commands::Stop { name, .. } => {}
                }
            }
            "#,
        );
        assert!(bound.is_bound(&decl("Commands", "Stop", "name")));
        assert!(!bound.is_bound(&decl("BatchAction", "Stop", "name")));
    }

    #[test]
    fn a_header_that_miscounts_the_entries_is_an_error() {
        let src = "# ── Other flags accepted and discarded (2) ──\nA::B::c = one\n";
        let err = parse_allowlist(src).unwrap_err().join("\n");
        assert!(err.contains("says 2 entries and the file has 1"), "{err}");

        let right = "# ── Other flags accepted and discarded (1) ──\nA::B::c = one\n";
        assert!(parse_allowlist(right).is_ok());

        // A ledger with no count in its header is not required to grow one.
        assert!(parse_allowlist("# just a comment\nA::B::c = one\n").is_ok());
    }

    #[test]
    fn allowlist_requires_a_reason_and_a_three_part_key() {
        let ok = parse_allowlist(
            "# comment\n\nCommands::Restore::dry_run = tracked in #1089, restore ignores it\n",
        )
        .unwrap();
        assert_eq!(ok.len(), 1);
        assert_eq!(ok[0].key, "Commands::Restore::dry_run");

        let no_reason = parse_allowlist("Commands::Restore::dry_run =\n").unwrap_err();
        assert!(no_reason[0].contains("no reason"));

        let bad_key = parse_allowlist("Restore::dry_run = x\n").unwrap_err();
        assert!(bad_key[0].contains("Enum::Variant::field"));

        let dup = parse_allowlist("A::B::c = one\nA::B::c = two\n").unwrap_err();
        assert!(dup[0].contains("duplicate"));
    }

    #[test]
    fn test_sources_are_excluded_from_the_handler_scan() {
        assert!(is_test_source(Path::new("crates/azlin/src/tests/mod.rs")));
        assert!(is_test_source(Path::new(
            "crates/azlin/src/azdoit_tests.rs"
        )));
        assert!(!is_test_source(Path::new("crates/azlin/src/cmd_batch.rs")));
    }
}
