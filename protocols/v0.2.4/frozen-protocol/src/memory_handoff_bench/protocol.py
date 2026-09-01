from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import sha256_file

PROTOCOL_FILES = [
    "research_protocol_v0.1.md",
    "research_protocol_v0.2.md",
    "research_protocol_v0.2.1.md",
    "research_protocol_v0.2.2.md",
    "research_protocol_v0.2.3.md",
    "research_protocol_v0.2.4.md",
    "diagnostics/structured_retries.sql",
    "diagnostics/memory_mode_integrity.sql",
    "diagnostics/structured_failures.sql",
    "diagnostics/failed_structured_attempts.sql",
    "cases/pilot.yaml",
    "schemas/case.schema.json",
    "schemas/evidence.schema.json",
    "configs/default.yaml",
    "configs/stochastic-v0.2.4.yaml",
    "migrations/001_initial.sql",
    "migrations/002_protocol_v0_2.sql",
    "migrations/003_protocol_v0_2_3.sql",
    "src/memory_handoff_bench/config.py",
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
    "pyproject.toml",
    "uv.lock",
]


def build_protocol_lock(root: Path) -> dict[str, Any]:
    return {
        "protocol_version": "0.2.4",
        "algorithm": "sha256",
        "files": {name: sha256_file(root / name) for name in PROTOCOL_FILES},
    }


def load_protocol_lock(root: Path) -> dict[str, Any]:
    path = root / "protocol_lock.json"
    if not path.exists():
        raise FileNotFoundError("protocol_lock.json is missing; freeze the protocol before running")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_protocol_lock(root: Path) -> tuple[bool, list[str], str]:
    expected = load_protocol_lock(root)
    current = build_protocol_lock(root)
    mismatches = [
        name
        for name, digest in expected.get("files", {}).items()
        if current.get("files", {}).get(name) != digest
    ]
    missing = [name for name in PROTOCOL_FILES if name not in expected.get("files", {})]
    mismatches.extend(missing)
    combined_hash = sha256_file(root / "protocol_lock.json")
    return not mismatches, sorted(set(mismatches)), combined_hash


def write_protocol_lock(root: Path) -> Path:
    path = root / "protocol_lock.json"
    payload = build_protocol_lock(root)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
