//! The two requirements of issue #1092 that were inline in `handle_vm_new`.
//!
//! Both are about the same failure: a VM that exists, bills, answers SSH and
//! reports "created successfully" while having no route to the internet. And
//! both were the only logic in #1097 without direct test coverage, for the
//! same reason — they lived inside a ~700-line function that no test can call
//! without an Azure subscription (#1102).
//!
//! - **R4** — never fall through to `az vm create` without egress.
//!   [`resolve_private_vm_egress`] takes the subnet read, the prompt and the
//!   provisioning step as parameters, so every branch of the gate can be
//!   driven from a unit test. The property that matters is total: for a
//!   private VM the function returns either "this VM has egress", or "this VM
//!   is switching to a public IP", or an error. There is no fourth outcome,
//!   and no path that reaches VM creation without one of the first two.
//!
//! - **R5** — a VM created without egress must not be reported as a success.
//!   [`DegradedVms`] accumulates them and produces the failure only when the
//!   caller consumes it, which is what keeps the non-zero exit *after* the
//!   loop that prints each VM's connection details.

use anyhow::{Context, Result};

use crate::cmd_vm_ops::{nat_abort_message, nat_provisioning_failed_message, NatMissingAction};
use crate::nat_helpers::NatStatus;

/// The outcome of the R4 gate for one `azlin new` invocation.
///
/// Deliberately has no "proceed anyway" variant. The gate exists because a
/// private VM with no NAT gateway installs nothing and says nothing, so
/// "carry on and hope" is the state that must be unrepresentable.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum EgressDecision {
    /// A NAT gateway provides egress for the region. `name` is `Some` when the
    /// gateway already existed, `None` when this run provisioned it.
    NatGateway { name: Option<String> },
    /// The user chose an instance public IP instead, which carries its own
    /// egress. The caller must set `want_public_ip`.
    SwitchToPublicIp,
}

/// Decide whether a private VM in `region` will have outbound internet, and
/// make it so if the user asks for that.
///
/// `detect`, `prompt` and `provision` are parameters rather than direct calls
/// so the gate is testable: each one is an Azure round-trip or a terminal
/// prompt, and #1097 shipped this logic asserted only indirectly because it
/// was inline in `handle_vm_new` (#1102).
///
/// A failed subnet read is an error, never a decision. The final provisioning
/// step *replaces* the subnet's NAT association rather than appending to it,
/// so proceeding on a transient ARM failure could silently repoint a hand-made
/// or corporate gateway and start billing a second gateway plus a second
/// Standard public IP.
pub(crate) fn resolve_private_vm_egress<D, P, E>(
    resource_group: &str,
    region: &str,
    detect: D,
    prompt: P,
    provision: E,
) -> Result<EgressDecision>
where
    D: FnOnce() -> Result<NatStatus>,
    P: FnOnce() -> Result<NatMissingAction>,
    E: FnOnce() -> Result<()>,
{
    let status = detect().with_context(|| {
        format!(
            "Could not determine whether the VM subnet in {region} has outbound \
             internet. Refusing to create a private VM that may silently have no \
             egress. Re-run with --public to give this VM its own public IP instead."
        )
    })?;

    if let NatStatus::Attached { name } = status {
        return Ok(EgressDecision::NatGateway { name: Some(name) });
    }

    match prompt()? {
        NatMissingAction::CreateNatGateway => {
            // R4: never fall through to `az vm create` without egress. A
            // failed provisioning step is fatal here rather than a warning.
            provision().with_context(|| nat_provisioning_failed_message(resource_group, region))?;
            Ok(EgressDecision::NatGateway { name: None })
        }
        NatMissingAction::SwitchToPublicIp => Ok(EgressDecision::SwitchToPublicIp),
        NatMissingAction::Abort => {
            anyhow::bail!("{}", nat_abort_message(resource_group, region))
        }
    }
}

/// VMs whose egress probe reported failure, collected across the creation loop.
///
/// R5. The exit has to come *after* the loop: each VM that reached this state
/// exists and is billing, so its name and connection details must be printed
/// before the run fails. Aborting mid-loop strands a VM the user cannot find.
///
/// The failure is produced by consuming the accumulator, so the only way to
/// raise it is to be finished collecting.
#[derive(Debug, Default)]
pub(crate) struct DegradedVms(Vec<String>);

impl DegradedVms {
    pub(crate) fn new() -> Self {
        Self::default()
    }

    /// Record a VM that was created without outbound internet.
    pub(crate) fn record(&mut self, vm_name: &str) {
        self.0.push(vm_name.to_string());
    }

    /// The error the run must end with, or `None` when every VM has egress.
    ///
    /// Reporting a VM with no egress as a success is the silent degradation
    /// this whole change exists to remove, so this returning `None` is the
    /// only path to exit 0.
    pub(crate) fn into_failure(self, region: &str) -> Option<anyhow::Error> {
        if self.0.is_empty() {
            return None;
        }
        Some(anyhow::anyhow!(
            "{} VM(s) were created but have NO outbound internet: {}. \
             They are reachable but their toolchain install is incomplete. \
             See the warnings above for how to provision a NAT gateway in {}.",
            self.0.len(),
            self.0.join(", "),
            region
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const RG: &str = "rysweet-linux-vm-pool";
    const REGION: &str = "southcentralus";

    /// Records which of the injected effects ran, so a test can assert that a
    /// branch did *not* prompt or provision.
    #[derive(Default)]
    struct Calls {
        prompted: std::cell::Cell<bool>,
        provisioned: std::cell::Cell<bool>,
    }

    fn attached() -> Result<NatStatus> {
        Ok(NatStatus::Attached {
            name: "azlin-natgw-southcentralus".to_string(),
        })
    }

    // ── R4: never fall through to `az vm create` without egress ──────

    /// The read failing is not a verdict. Downgrading it to "no gateway" is
    /// what could repoint someone else's gateway, and downgrading it to
    /// "proceed" is what creates a VM with no internet.
    #[test]
    fn an_unreadable_subnet_is_an_error_and_asks_nothing() {
        let calls = Calls::default();
        let result = resolve_private_vm_egress(
            RG,
            REGION,
            || Err(anyhow::anyhow!("429 TooManyRequests")),
            || {
                calls.prompted.set(true);
                Ok(NatMissingAction::CreateNatGateway)
            },
            || {
                calls.provisioned.set(true);
                Ok(())
            },
        );
        let err = format!("{:#}", result.unwrap_err());
        assert!(err.contains("Refusing to create a private VM"), "{err}");
        assert!(err.contains("429 TooManyRequests"), "{err}");
        assert!(
            err.contains("--public"),
            "the error must offer a way out: {err}"
        );
        assert!(
            !calls.prompted.get(),
            "an unreadable subnet must not prompt"
        );
        assert!(!calls.provisioned.get(), "and must not provision");
    }

    /// An existing gateway — including one azlin did not create — is reused.
    /// A NAT gateway plus its Standard public IP cost real money.
    #[test]
    fn an_existing_gateway_is_reused_without_prompting_or_provisioning() {
        let calls = Calls::default();
        let decision = resolve_private_vm_egress(
            RG,
            REGION,
            attached,
            || {
                calls.prompted.set(true);
                Ok(NatMissingAction::CreateNatGateway)
            },
            || {
                calls.provisioned.set(true);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(
            decision,
            EgressDecision::NatGateway {
                name: Some("azlin-natgw-southcentralus".to_string())
            }
        );
        assert!(!calls.prompted.get());
        assert!(
            !calls.provisioned.get(),
            "a second gateway would double-bill"
        );
    }

    #[test]
    fn choosing_to_provision_reports_a_gateway_once_it_succeeds() {
        let decision = resolve_private_vm_egress(
            RG,
            REGION,
            || Ok(NatStatus::Absent),
            || Ok(NatMissingAction::CreateNatGateway),
            || Ok(()),
        )
        .unwrap();
        assert_eq!(decision, EgressDecision::NatGateway { name: None });
    }

    /// The requirement, stated directly: provisioning failed, so the run must
    /// not continue to `az vm create`.
    #[test]
    fn failed_provisioning_never_returns_a_decision() {
        let result = resolve_private_vm_egress(
            RG,
            REGION,
            || Ok(NatStatus::Absent),
            || Ok(NatMissingAction::CreateNatGateway),
            || Err(anyhow::anyhow!("AuthorizationFailed")),
        );
        assert!(result.is_err(), "R4: no egress means no VM");
        let err = format!("{:#}", result.unwrap_err());
        assert!(err.contains("AuthorizationFailed"), "{err}");
        // The context names the resource group and region so the user can act.
        assert!(err.contains(REGION), "{err}");
    }

    #[test]
    fn switching_to_a_public_ip_is_a_decision_not_an_error() {
        let decision = resolve_private_vm_egress(
            RG,
            REGION,
            || Ok(NatStatus::Absent),
            || Ok(NatMissingAction::SwitchToPublicIp),
            || panic!("must not provision when the user opted out"),
        )
        .unwrap();
        assert_eq!(decision, EgressDecision::SwitchToPublicIp);
    }

    #[test]
    fn aborting_fails_with_the_abort_message() {
        let result = resolve_private_vm_egress(
            RG,
            REGION,
            || Ok(NatStatus::Absent),
            || Ok(NatMissingAction::Abort),
            || panic!("must not provision after an abort"),
        );
        let err = result.unwrap_err().to_string();
        assert_eq!(err, nat_abort_message(RG, REGION));
    }

    /// A prompt that cannot be answered — no TTY, no `--yes` — is an error,
    /// and must not be treated as consent to proceed without egress.
    #[test]
    fn an_unanswerable_prompt_is_an_error() {
        let result = resolve_private_vm_egress(
            RG,
            REGION,
            || Ok(NatStatus::Absent),
            || Err(anyhow::anyhow!("stdin is not a terminal")),
            || panic!("must not provision without an answer"),
        );
        assert!(result.is_err());
    }

    /// The exhaustive statement of R4, as a table.
    ///
    /// Every combination of subnet state, user answer and provisioning outcome
    /// is mapped to the outcome it must produce. The compiler already
    /// guarantees there is no third `EgressDecision` variant; what this checks
    /// is that no *input* combination reaches the wrong one of the two.
    #[test]
    fn every_combination_maps_to_the_required_outcome() {
        /// What the gate must produce.
        #[derive(Debug, PartialEq, Eq)]
        enum Want {
            Gateway,
            PublicIp,
            Refused,
        }
        let read_failed = || Err(anyhow::anyhow!("read failed"));
        let absent = || Ok(NatStatus::Absent);
        let cases: [(fn() -> Result<NatStatus>, NatMissingAction, bool, Want); 14] = [
            // An unreadable subnet refuses whatever the user would have said.
            (
                read_failed,
                NatMissingAction::CreateNatGateway,
                true,
                Want::Refused,
            ),
            (
                read_failed,
                NatMissingAction::CreateNatGateway,
                false,
                Want::Refused,
            ),
            (
                read_failed,
                NatMissingAction::SwitchToPublicIp,
                true,
                Want::Refused,
            ),
            (read_failed, NatMissingAction::Abort, true, Want::Refused),
            // An attached gateway short-circuits before the prompt, so the
            // answer and the provisioning outcome cannot change the verdict.
            (
                attached,
                NatMissingAction::CreateNatGateway,
                false,
                Want::Gateway,
            ),
            (
                attached,
                NatMissingAction::SwitchToPublicIp,
                false,
                Want::Gateway,
            ),
            (attached, NatMissingAction::Abort, false, Want::Gateway),
            // No gateway: the answer decides, and provisioning can still fail.
            (
                absent,
                NatMissingAction::CreateNatGateway,
                true,
                Want::Gateway,
            ),
            (
                absent,
                NatMissingAction::CreateNatGateway,
                false,
                Want::Refused,
            ),
            (
                absent,
                NatMissingAction::SwitchToPublicIp,
                true,
                Want::PublicIp,
            ),
            (
                absent,
                NatMissingAction::SwitchToPublicIp,
                false,
                Want::PublicIp,
            ),
            (absent, NatMissingAction::Abort, true, Want::Refused),
            (absent, NatMissingAction::Abort, false, Want::Refused),
            // A gateway that exists is reused even when the user would have
            // said "abort" — the prompt never happens.
            (attached, NatMissingAction::Abort, true, Want::Gateway),
        ];
        for (state, answer, provisioning_ok, want) in cases {
            let got = match resolve_private_vm_egress(
                RG,
                REGION,
                state,
                || Ok(answer),
                || {
                    if provisioning_ok {
                        Ok(())
                    } else {
                        Err(anyhow::anyhow!("provisioning failed"))
                    }
                },
            ) {
                Ok(EgressDecision::NatGateway { .. }) => Want::Gateway,
                Ok(EgressDecision::SwitchToPublicIp) => Want::PublicIp,
                Err(_) => Want::Refused,
            };
            assert_eq!(
                got, want,
                "state/answer {answer:?} with provisioning_ok={provisioning_ok}"
            );
        }
    }

    // ── R5: a degraded VM is never reported as a success ─────────────

    #[test]
    fn no_degraded_vms_is_the_only_path_to_success() {
        assert!(DegradedVms::new().into_failure(REGION).is_none());
    }

    #[test]
    fn every_degraded_vm_is_named_in_the_failure() {
        let mut degraded = DegradedVms::new();
        degraded.record("azlin-vm-1");
        degraded.record("azlin-vm-3");
        let err = degraded.into_failure(REGION).unwrap().to_string();
        assert!(err.contains("azlin-vm-1"), "{err}");
        assert!(err.contains("azlin-vm-3"), "{err}");
        assert!(err.starts_with("2 VM(s)"), "{err}");
        assert!(err.contains(REGION), "{err}");
        // The user has to know these exist and are billing.
        assert!(err.contains("were created"), "{err}");
    }

    #[test]
    fn one_degraded_vm_among_many_still_fails_the_run() {
        let mut degraded = DegradedVms::new();
        degraded.record("azlin-vm-7");
        assert!(degraded.into_failure(REGION).is_some());
    }
}
