//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Context handlers ────────────────────────────────────────────────────

/// Format context list output for table display.
pub fn format_context_list_table(contexts: &[(String, bool)]) -> String {
    let mut out = String::new();
    for (name, is_active) in contexts {
        if *is_active {
            out.push_str(&format!("* {}\n", name));
        } else {
            out.push_str(&format!("  {}\n", name));
        }
    }
    out
}

/// Format the "no contexts" message.
pub fn format_no_contexts() -> &'static str {
    "No contexts found. Create one with: azlin context create <name>"
}

/// Format the context show output.
pub fn format_context_show(name: &str, content: Option<&str>) -> String {
    let mut out = format!("Current context: {}", name);
    if let Some(c) = content {
        out.push_str(&format!("\n{}", c.trim()));
    }
    out
}

/// What `az account show` reports right now, or why it could not be asked.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EffectiveSubscription {
    /// The subscription the Azure CLI is currently on.
    Known(String),
    /// `az account show` could not be run or parsed; carries the reason.
    Unavailable(String),
}

/// Format the effective-subscription block appended to `azlin context show`.
///
/// The point of this block is that a mismatch is *visible* rather than assumed.
/// Before #1090 `context show` printed the context file and nothing else, so a
/// context claiming `subscription_id = <prod>` looked authoritative while every
/// command ran somewhere else.
pub fn format_context_effective(
    context_subscription: Option<&str>,
    effective: &EffectiveSubscription,
) -> String {
    let mut out = String::new();
    match effective {
        EffectiveSubscription::Known(effective) => {
            out.push_str(&format!(
                "\n\nEffective subscription (az account show): {effective}"
            ));
            match context_subscription {
                Some(want) if want == effective => {
                    out.push_str("\nThe Azure CLI is already on this context's subscription.");
                }
                Some(want) => {
                    out.push_str(&format!(
                        "\nMISMATCH: this context pins {want}, but the Azure CLI is on \
                         {effective}.\n\
                         azlin will switch the CLI to {want} before running any Azure \
                         command, and will refuse to run if the switch does not take effect."
                    ));
                }
                None => {
                    out.push_str(
                        "\nThis context pins no subscription_id, so commands run against \
                         whatever\nsubscription the Azure CLI is on — selecting it does not \
                         change that.\nPin one with: azlin context create <name> \
                         --subscription-id <sub>",
                    );
                }
            }
        }
        EffectiveSubscription::Unavailable(reason) => {
            out.push_str(&format!(
                "\n\nEffective subscription (az account show): unknown — {reason}"
            ));
            if context_subscription.is_some() {
                out.push_str(
                    "\nazlin cannot confirm which subscription commands would run against. \
                     Run 'az login'.",
                );
            }
        }
    }
    out
}

/// Format the context switch message.
pub fn format_context_switched(name: &str) -> String {
    format!("Switched to context '{}'", name)
}

/// Format the switch message for a context that pins a subscription.
///
/// Names the subscription the Azure CLI was actually moved to, so the
/// confirmation reports something that happened rather than something assumed.
pub fn format_context_switched_to_subscription(name: &str, subscription_id: &str) -> String {
    format!(
        "Switched to context '{name}' (Azure CLI subscription: {subscription_id})\n\
         Note: this sets the Azure CLI's default subscription, which also affects \
         plain 'az' commands."
    )
}

/// Format the switch message for a context that pins no subscription.
pub fn format_context_switched_no_subscription(name: &str) -> String {
    format!(
        "Switched to context '{name}'\n\
         Warning: '{name}' pins no subscription_id, so commands still run against the \
         Azure CLI's current subscription.\n\
         Pin one with: azlin context create {name} --subscription-id <sub>"
    )
}

/// Format the context create message.
pub fn format_context_created(name: &str) -> String {
    format!("Created context '{}'", name)
}

/// Format the context delete message.
pub fn format_context_deleted(name: &str) -> String {
    format!("Deleted context '{}'", name)
}

/// Format the context rename message.
pub fn format_context_renamed(old_name: &str, new_name: &str) -> String {
    format!("Renamed context '{}' -> '{}'", old_name, new_name)
}
