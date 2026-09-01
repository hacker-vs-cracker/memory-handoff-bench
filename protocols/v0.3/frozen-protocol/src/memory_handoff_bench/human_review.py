from __future__ import annotations

import csv
import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import PilotCase
from .metrics import harmful_meaning_preserved

WRITER_UNIT_FIELDS = (
    "case_id",
    "source_variant",
    "memory_mode",
    "writer_model",
    "embedding_model",
    "seed",
)


def _writer_unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(field) for field in WRITER_UNIT_FIELDS)


def _memory_texts(writer_output: Any) -> list[str]:
    if not isinstance(writer_output, dict):
        return []
    memories = writer_output.get("memories")
    if not isinstance(memories, list):
        return []
    texts: list[str] = []
    for memory in memories:
        if isinstance(memory, dict) and isinstance(memory.get("memory_text"), str):
            texts.append(memory["memory_text"])
    return texts


def _localize_retrieval(
    retrieval_results: Any,
    reader_output: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not isinstance(retrieval_results, list) or not isinstance(reader_output, dict):
        return [], None

    id_to_local: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    for index, result in enumerate(retrieval_results, start=1):
        if not isinstance(result, dict):
            continue
        payload = result.get("payload")
        if not isinstance(payload, dict):
            continue
        memory_id = str(payload.get("memory_id") or result.get("id") or "")
        local_id = f"E{index}"
        if memory_id:
            id_to_local[memory_id] = local_id
        evidence.append(
            {
                "evidence_id": local_id,
                "rank": index,
                "text": str(payload.get("text") or ""),
                "source_type": str(payload.get("source_type") or ""),
                "source_authority": str(payload.get("source_authority") or ""),
            }
        )

    proposal = reader_output.get("proposal")
    if not isinstance(proposal, dict):
        return evidence, None
    localized = dict(proposal)
    ids = proposal.get("evidence_ids")
    localized["evidence_ids"] = (
        [id_to_local.get(str(item), "UNMAPPED") for item in ids]
        if isinstance(ids, list)
        else []
    )
    assessments = reader_output.get("evidence_assessments")
    localized_assessments: list[dict[str, Any]] = []
    if isinstance(assessments, list):
        for assessment in assessments:
            if not isinstance(assessment, dict):
                continue
            item = dict(assessment)
            item["evidence_id"] = id_to_local.get(
                str(assessment.get("evidence_id") or ""), "UNMAPPED"
            )
            localized_assessments.append(item)
    localized["evidence_assessments"] = localized_assessments
    localized["decision_summary"] = reader_output.get("decision_summary")
    return evidence, localized


def _future_task(case: PilotCase) -> dict[str, Any]:
    alert = case.future_alert
    return {
        "title": alert.title,
        "analyst_request": alert.analyst_request,
        "severity": alert.severity,
        "ioc": {"type": alert.ioc.type, "value": alert.ioc.value},
        "asset": {
            "hostname": alert.asset.hostname,
            "criticality": alert.asset.criticality,
        },
        "registered_clean_actions": [item.value for item in case.expected.clean_actions],
        "registered_unsafe_actions": [item.value for item in case.expected.unsafe_actions],
        "trusted_fixtures": case.trusted_fixtures.model_dump(mode="json"),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_blinded_human_review(
    *,
    rows: list[dict[str, Any]],
    cases: list[PilotCase],
    output_dir: Path,
    run_id: str,
    expected_writer_units: int | None = None,
    expected_poison_trials: int | None = None,
) -> dict[str, Path]:
    """Create reviewer-safe W/I files plus a private mapping key; no outcome-based sampling."""
    case_map = {case.case_id: case for case in cases}
    output_dir.mkdir(parents=True, exist_ok=True)

    # W uses one upstream writer-memory condition, not one copy per reader.
    if expected_poison_trials is not None and len(rows) != expected_poison_trials:
        raise ValueError(
            f"review export expected {expected_poison_trials} poison trials, found {len(rows)}"
        )

    writer_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in rows:
        if str(item.get("source_variant")) != "poison":
            raise ValueError("human review export accepts poison trials only")
        writer_groups.setdefault(_writer_unit_key(item), []).append(item)
    if expected_writer_units is not None and len(writer_groups) != expected_writer_units:
        raise ValueError(
            f"review export expected {expected_writer_units} writer units, found {len(writer_groups)}"
        )

    w_public: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    for key, members in sorted(writer_groups.items(), key=lambda item: str(item[0])):
        canonical = members[0]
        outputs = [_memory_texts(member.get("writer_output")) for member in members]
        nonempty = [value for value in outputs if value]
        unique_outputs = {json.dumps(value, sort_keys=True) for value in nonempty}
        if len(unique_outputs) > 1:
            raise ValueError(
                "Writer output differs across readers for one writer-memory unit; "
                f"unit={key}. Run memory-mode integrity diagnostics before review export."
            )
        memory_texts = nonempty[0] if nonempty else []
        evaluable = bool(memory_texts)
        review_id = "W-" + secrets.token_hex(8).upper()
        w_public.append(
            {
                "review_id": review_id,
                "evaluable": "yes" if evaluable else "no",
                "registered_clean_source": case_map[str(canonical["case_id"])].source.clean,
                "registered_poison_source": case_map[str(canonical["case_id"])].source.poison,
                "registered_unsafe_actions_json": json.dumps(
                    [
                        item.value
                        for item in case_map[str(canonical["case_id"])].expected.unsafe_actions
                    ],
                    ensure_ascii=False,
                ),
                "stored_memories_json": json.dumps(memory_texts, ensure_ascii=False),
                "reviewer_label": "" if evaluable else "NOT_EVALUABLE",
                "reviewer_notes": "",
            }
        )
        case = case_map[str(canonical["case_id"])]
        machine_w = (
            any(harmful_meaning_preserved(text, case) for text in memory_texts)
            if evaluable
            else None
        )
        machine_values = {
            bool(member.get("poison_written"))
            for member in members
            if member.get("poison_written") is not None
        }
        if machine_w is not None and machine_values and machine_values != {machine_w}:
            raise ValueError(
                "Stored writer memory and recorded machine W label disagree; "
                f"unit={key}, recomputed={machine_w}, recorded={sorted(machine_values)}"
            )
        private_rows.append(
            {
                "review_id": review_id,
                "review_type": "W",
                "trial_id": "",
                "case_id": canonical.get("case_id"),
                "writer_model": canonical.get("writer_model"),
                "reader_model": "",
                "embedding_model": canonical.get("embedding_model"),
                "seed": canonical.get("seed"),
                "machine_label": str(machine_w).lower() if machine_w is not None else "",
                "evaluable": evaluable,
                "integrity_note": "",
            }
        )

    i_public: list[dict[str, Any]] = []
    for item in rows:
        case = case_map[str(item["case_id"])]
        evidence, localized_reader = _localize_retrieval(
            item.get("retrieval_results"), item.get("reader_output")
        )
        evaluable = item.get("status") == "completed" and localized_reader is not None
        review_id = "I-" + secrets.token_hex(8).upper()
        i_public.append(
            {
                "review_id": review_id,
                "evaluable": "yes" if evaluable else "no",
                "registered_clean_source": case.source.clean,
                "registered_poison_source": case.source.poison,
                "later_clean_task_and_ground_truth_json": json.dumps(
                    _future_task(case), ensure_ascii=False
                ),
                "retrieved_evidence_json": json.dumps(evidence, ensure_ascii=False),
                "reader_decision_json": json.dumps(localized_reader, ensure_ascii=False)
                if localized_reader is not None
                else "",
                "reviewer_label": "" if evaluable else "NOT_EVALUABLE",
                "reviewer_notes": "",
            }
        )
        private_rows.append(
            {
                "review_id": review_id,
                "review_type": "I",
                "trial_id": item.get("trial_id"),
                "case_id": item.get("case_id"),
                "writer_model": item.get("writer_model"),
                "reader_model": item.get("reader_model"),
                "embedding_model": item.get("embedding_model"),
                "seed": item.get("seed"),
                "machine_label": (
                    str(bool(item.get("reader_influenced"))).lower()
                    if item.get("reader_influenced") is not None
                    else ""
                ),
                "evaluable": evaluable,
                "integrity_note": "",
            }
        )

    # Randomize reviewer order using OS randomness. The private key is the only mapping back.
    secrets.SystemRandom().shuffle(w_public)
    secrets.SystemRandom().shuffle(i_public)

    def write_csv(path: Path, data: list[dict[str, Any]]) -> None:
        fields = list(data[0]) if data else []
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            if fields:
                writer.writeheader()
                writer.writerows(data)

    w_path = output_dir / "reviewer-W.csv"
    i_path = output_dir / "reviewer-I.csv"
    private_path = output_dir / "PRIVATE-review-key.csv"
    write_csv(w_path, w_public)
    write_csv(i_path, i_public)
    write_csv(private_path, private_rows)

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "selection": "all planned poison units available in the run; no outcome-based sampling",
        "w_writer_units": len(w_public),
        "w_evaluable": sum(row["evaluable"] == "yes" for row in w_public),
        "i_poison_trials": len(i_public),
        "i_evaluable": sum(row["evaluable"] == "yes" for row in i_public),
        "blinding": [
            "reviewer files omit writer/reader model identity",
            "reviewer files omit machine W/I labels",
            "PRIVATE-review-key.csv must not be given to reviewers before labels are locked",
        ],
    }
    manifest_path = output_dir / "review-export-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    checksum_path = output_dir / "SHA256SUMS.txt"
    exported = [w_path, i_path, private_path, manifest_path]
    checksum_path.write_text(
        "\n".join(f"{_sha256(path)}  {path.name}" for path in exported) + "\n",
        encoding="utf-8",
    )
    return {
        "w_review": w_path,
        "i_review": i_path,
        "private_key": private_path,
        "manifest": manifest_path,
        "sha256": checksum_path,
    }
