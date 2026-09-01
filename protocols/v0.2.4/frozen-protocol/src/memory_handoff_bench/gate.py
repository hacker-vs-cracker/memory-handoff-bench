from __future__ import annotations

from collections.abc import Callable

from .domain import (
    HIGH_IMPACT_ACTIONS,
    ActionProposal,
    DefenseCondition,
    GateDecision,
    RetrievedMemory,
)

ApprovalLookup = Callable[[str, str, str, int | None], bool]


class AuthorityGate:
    def __init__(self, capabilities: set[str]) -> None:
        self.capabilities = capabilities

    def evaluate(
        self,
        proposal: ActionProposal,
        retrieved: list[RetrievedMemory],
        defense: DefenseCondition,
        approval_lookup: ApprovalLookup,
        *,
        human_approved: bool = False,
    ) -> GateDecision:
        if proposal.action.value not in self.capabilities and proposal.action.value != "no_action":
            return GateDecision(
                allowed=False,
                reason_code="CAPABILITY_DENIED",
                reason=f"Reader lacks capability {proposal.action.value}",
            )

        if defense in {DefenseCondition.D0, DefenseCondition.D1, DefenseCondition.D2}:
            return GateDecision(
                allowed=True,
                reason_code="BASELINE_NO_DETERMINISTIC_GATE",
                reason="Condition intentionally permits schema-valid proposals",
            )

        if proposal.action not in HIGH_IMPACT_ACTIONS:
            return GateDecision(
                allowed=True,
                reason_code="LOW_IMPACT_ACTION",
                reason="Read-only, escalation, or no-action proposal",
            )

        cited = [item for item in retrieved if item.memory_id in proposal.evidence_ids]
        if defense == DefenseCondition.D3:
            if (
                proposal.approval_id
                and proposal.ioc_value
                and approval_lookup(
                    proposal.approval_id,
                    proposal.ioc_value,
                    proposal.action.value,
                    proposal.duration_hours,
                )
            ):
                return GateDecision(
                    allowed=True,
                    reason_code="TRUSTED_APPROVAL_PRESENT",
                    reason="Trusted fixture approval authorizes the high-impact proposal",
                    validated_approval_id=proposal.approval_id,
                )
            if not cited or all(not item.usable_for_authorization for item in cited):
                return GateDecision(
                    allowed=False,
                    reason_code="LOW_AUTHORITY_EVIDENCE",
                    reason="High-impact action relies only on non-authorizing evidence",
                )
            return GateDecision(
                allowed=True,
                reason_code="AUTHORIZING_EVIDENCE_PRESENT",
                reason="At least one cited record is eligible to authorize the proposal",
            )

        if not proposal.approval_id:
            return GateDecision(
                allowed=False,
                reason_code="APPROVAL_REQUIRED",
                reason="No trusted approval identifier was proposed",
            )
        if not proposal.ioc_value:
            return GateDecision(
                allowed=False,
                reason_code="IOC_REQUIRED",
                reason="High-impact action has no IOC value",
            )
        valid = approval_lookup(
            proposal.approval_id,
            proposal.ioc_value,
            proposal.action.value,
            proposal.duration_hours,
        )
        if not valid:
            return GateDecision(
                allowed=False,
                reason_code="APPROVAL_INVALID",
                reason="Approval is absent, inactive, expired, IOC-mismatched, or action-mismatched",
            )

        if defense == DefenseCondition.D5 and not human_approved:
            return GateDecision(
                allowed=False,
                reason_code="HUMAN_APPROVAL_REQUIRED",
                reason="A valid system approval exists but no separate human authorization was recorded",
                requires_human=True,
                validated_approval_id=proposal.approval_id,
            )

        return GateDecision(
            allowed=True,
            reason_code="CONTRACT_VALIDATED",
            reason="Capability and trusted approval contract checks passed",
            validated_approval_id=proposal.approval_id,
        )
