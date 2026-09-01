from pathlib import Path

from memory_handoff_bench.protocol import verify_protocol_lock


def test_protocol_lock_matches() -> None:
    root = Path(__file__).resolve().parents[1]
    valid, mismatches, _ = verify_protocol_lock(root)
    assert valid, mismatches
