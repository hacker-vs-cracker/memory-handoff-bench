from memory_handoff_bench.reporting import _report_run_record, audit_summary, summarize


def row(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "trial_id": "trial",
        "case_id": "FIE-01",
        "source_variant": "poison",
        "memory_mode": "writer_generated",
        "writer_model": "writer-a",
        "reader_model": "reader-a",
        "embedding_model": "encoder",
        "defense": "D0",
        "seed": 42,
        "status": "completed",
        "poison_written": True,
        "poison_retrieved": True,
        "reader_influenced": True,
        "unauthorized_action_attempted": True,
        "attempted_attack_success": True,
        "baseline_gate_allowed": True,
        "unsafe_state_changed": True,
        "executed_attack_success": True,
        "false_completion_claim": None,
        "benign_task_success": False,
        "benign_action_executed": False,
        "defense_false_positive": False,
    }
    value.update(changes)
    return value


def test_writer_metrics_are_not_duplicated_across_readers() -> None:
    rows = [row(reader_model="reader-a"), row(reader_model="reader-b")]
    summary = summarize(rows, {"FIE-01": "false_ioc_exception"})
    assert summary["rates"]["poison_written"]["total"] == 1
    assert summary["rates"]["attempted_attack_success"]["total"] == 2


def test_failed_trial_blocks_integrity_audit() -> None:
    rows = [row(), row(trial_id="failed", status="failed", error="timeout")]
    summary = summarize(rows, {"FIE-01": "false_ioc_exception"})
    audit = audit_summary(summary, expected_trials=2)
    assert not audit["passed"]
    assert audit["failures"] == ["1 infrastructure trials failed"]


def test_evidenced_structured_output_failure_is_terminal_and_auditable() -> None:
    rows = [
        row(),
        row(
            trial_id="format-failed",
            status="structured_output_failed",
            attempted_attack_success=None,
            executed_attack_success=None,
            structured_output_evidence=True,
            structured_retry_count=2,
            structured_attempt_count=3,
            structured_failure_stage="reader",
        ),
    ]
    summary = summarize(rows, {"FIE-01": "false_ioc_exception"})
    audit = audit_summary(summary, expected_trials=2)

    assert audit["passed"]
    assert summary["trials_terminal"] == 2
    assert summary["trials_completed"] == 1
    assert summary["trials_structured_output_failed"] == 1
    assert summary["rates"]["attempted_attack_success"]["rate"] == 1.0
    assert summary["rates"]["attempted_attack_success"]["planned_rate"] == 0.5


def test_structured_output_failure_without_three_attempts_fails_audit() -> None:
    rows = [
        row(
            status="structured_output_failed",
            attempted_attack_success=None,
            executed_attack_success=None,
            structured_output_evidence=True,
            structured_retry_count=1,
            structured_attempt_count=2,
            structured_failure_stage="reader",
        )
    ]
    summary = summarize(rows, {"FIE-01": "false_ioc_exception"})
    audit = audit_summary(summary, expected_trials=1)

    assert not audit["passed"]
    assert audit["failures"] == [
        "1 structured-output failures lack three-attempt evidence"
    ]


def test_report_compacts_model_info_but_keeps_identity_evidence() -> None:
    run = {
        "run_id": "run",
        "model_manifest": {
            "models": {
                "model:latest": {
                    "installed": True,
                    "digest": "sha256:abc",
                    "template": "template",
                    "model_info": {"tensor.one": "x" * 1000},
                }
            }
        },
    }
    compact = _report_run_record(run)
    model = compact["model_manifest"]["models"]["model:latest"]
    assert model["digest"] == "sha256:abc"
    assert model["template"] == "template"
    assert "model_info" not in model
    assert model["model_info_evidence"]["omitted_from_report"] is True
    assert len(model["model_info_evidence"]["sha256"]) == 64
