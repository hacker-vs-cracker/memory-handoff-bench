from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_file

CURRENT_PROTOCOL_VERSION = "0.3"

# Explicit rather than globbed: adding a new runtime/scoring file must be a conscious
# protocol change. The v0.2.4 frozen snapshot is protected by its own SHA256SUMS manifest.
PROTOCOL_FILES = [
    "research_protocol_v0.1.md",
    "research_protocol_v0.2.md",
    "research_protocol_v0.2.1.md",
    "research_protocol_v0.2.2.md",
    "research_protocol_v0.2.3.md",
    "research_protocol_v0.2.4.md",
    "research_protocol_v0.3.md",
    "HUMAN_VALIDATION_PLAN_v0.3.md",
    "V0.3_PRE_RUN_CHECKLIST.md",
    "diagnostics/structured_retries.sql",
    "diagnostics/memory_mode_integrity.sql",
    "diagnostics/structured_failures.sql",
    "diagnostics/failed_structured_attempts.sql",
    "cases/pilot.yaml",
    "schemas/case.schema.json",
    "schemas/evidence.schema.json",
    "configs/default.yaml",
    "configs/stochastic-v0.2.4.yaml",
    "configs/counterfactual-v0.3.yaml",
    "migrations/001_initial.sql",
    "migrations/002_protocol_v0_2.sql",
    "migrations/003_protocol_v0_2_3.sql",
    "migrations/004_protocol_v0_3.sql",
    "src/memory_handoff_bench/config.py",
    "src/memory_handoff_bench/counterfactual.py",
    "src/memory_handoff_bench/human_review.py",
    "src/memory_handoff_bench/domain.py",
    "src/memory_handoff_bench/hashing.py",
    "src/memory_handoff_bench/prompts.py",
    "src/memory_handoff_bench/gate.py",
    "src/memory_handoff_bench/metrics.py",
    "src/memory_handoff_bench/ollama.py",
    "src/memory_handoff_bench/storage.py",
    "src/memory_handoff_bench/vector_store.py",
    "src/memory_handoff_bench/experiment.py",
    "src/memory_handoff_bench/reporting.py",
    "src/memory_handoff_bench/analysis.py",
    "src/memory_handoff_bench/cli.py",
    "src/memory_handoff_bench/protocol.py",
    "src/memory_handoff_bench/__init__.py",
    "tests/test_cases.py",
    "tests/test_cli_v03.py",
    "tests/test_counterfactual.py",
    "tests/test_domain.py",
    "tests/test_experiment.py",
    "tests/test_gate.py",
    "tests/test_human_review.py",
    "tests/test_metrics.py",
    "tests/test_ollama.py",
    "tests/test_protocol.py",
    "tests/test_reporting.py",
    "pyproject.toml",
    "uv.lock",
    "reproducibility/frozen-protocol-v0.2.4/protocol_lock.json",
    "reproducibility/frozen-protocol-v0.2.4/SHA256SUMS.txt",
]


def build_protocol_lock(root: Path) -> dict[str, Any]:
    missing = [name for name in PROTOCOL_FILES if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError("Protocol files missing: " + ", ".join(missing))
    return {
        "protocol_version": CURRENT_PROTOCOL_VERSION,
        "algorithm": "sha256",
        "files": {name: sha256_file(root / name) for name in PROTOCOL_FILES},
    }


def load_protocol_lock(root: Path) -> dict[str, Any]:
    path = root / "protocol_lock.json"
    if not path.exists():
        raise FileNotFoundError("protocol_lock.json is missing; freeze the protocol before running")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_protocol_lock(
    root: Path, expected_version: str | None = None
) -> tuple[bool, list[str], str]:
    expected = load_protocol_lock(root)
    current = build_protocol_lock(root)
    mismatches = [
        name
        for name, digest in expected.get("files", {}).items()
        if current.get("files", {}).get(name) != digest
    ]
    missing_from_lock = [name for name in PROTOCOL_FILES if name not in expected.get("files", {})]
    unexpected_in_lock = [name for name in expected.get("files", {}) if name not in PROTOCOL_FILES]
    mismatches.extend(missing_from_lock)
    mismatches.extend(f"unexpected:{name}" for name in unexpected_in_lock)

    lock_version = str(expected.get("protocol_version", ""))
    if lock_version != CURRENT_PROTOCOL_VERSION:
        mismatches.append(
            f"protocol_version(lock={lock_version},source={CURRENT_PROTOCOL_VERSION})"
        )
    if expected_version is not None and lock_version != expected_version:
        mismatches.append(
            f"protocol_version(lock={lock_version},config={expected_version})"
        )

    combined_hash = sha256_file(root / "protocol_lock.json")
    return not mismatches, sorted(set(mismatches)), combined_hash


def write_protocol_lock(root: Path, protocol_version: str = CURRENT_PROTOCOL_VERSION) -> Path:
    if protocol_version != CURRENT_PROTOCOL_VERSION:
        raise ValueError(
            f"Active source tree is protocol v{CURRENT_PROTOCOL_VERSION}; "
            f"cannot freeze it as v{protocol_version}. Use the frozen historical snapshot instead."
        )
    path = root / "protocol_lock.json"
    payload = build_protocol_lock(root)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
