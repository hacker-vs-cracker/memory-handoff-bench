import pytest
from pydantic import ValidationError

from memory_handoff_bench.domain import ActionProposal, ReaderOutput


def reader_payload() -> dict:
    return {
        "decision_summary": "Escalate because authority is missing",
        "evidence_assessments": [],
        "proposal": {
            "action": "escalate_to_analyst",
            "alert_id": "ALT-01",
            "reason": "Unverified evidence",
            "evidence_ids": [],
        },
        "claimed_execution_status": "not_attempted",
    }


def test_reader_schema_advertises_bounded_unique_evidence_arrays() -> None:
    schema = ReaderOutput.model_json_schema()
    assessments = schema["properties"]["evidence_assessments"]
    proposal_ids = schema["$defs"]["ActionProposal"]["properties"]["evidence_ids"]
    assert assessments["maxItems"] == 5
    assert assessments["uniqueItems"] is True
    assert proposal_ids["maxItems"] == 5
    assert proposal_ids["uniqueItems"] is True


def test_reader_rejects_duplicate_assessments_and_proposal_ids() -> None:
    duplicated_assessment = reader_payload()
    duplicated_assessment["evidence_assessments"] = [
        {
            "evidence_id": "MEM-01",
            "stance": "supports",
            "authority_interpretation": "untrusted",
        },
        {
            "evidence_id": "MEM-01",
            "stance": "context_only",
            "authority_interpretation": "unknown",
        },
    ]
    with pytest.raises(ValidationError, match="must not repeat"):
        ReaderOutput.model_validate(duplicated_assessment)

    duplicated_proposal = reader_payload()
    duplicated_proposal["proposal"]["evidence_ids"] = ["MEM-01", "MEM-01"]
    with pytest.raises(ValidationError, match="must be unique"):
        ReaderOutput.model_validate(duplicated_proposal)


def test_reader_rejects_more_than_top_k_evidence_items() -> None:
    payload = reader_payload()
    payload["proposal"]["evidence_ids"] = [f"MEM-{index}" for index in range(6)]
    with pytest.raises(ValidationError, match="at most 5"):
        ActionProposal.model_validate(payload["proposal"])
