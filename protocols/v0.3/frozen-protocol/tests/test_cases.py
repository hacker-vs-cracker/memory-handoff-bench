from pathlib import Path

from memory_handoff_bench.config import load_cases, load_config
from memory_handoff_bench.metrics import harmful_meaning_preserved

ROOT = Path(__file__).resolve().parents[1]


def test_pilot_has_twelve_balanced_synthetic_cases() -> None:
    config = load_config(ROOT / "configs/default.yaml")
    corpus = load_cases(config)
    assert len(corpus.cases) == 12
    categories: dict[str, int] = {}
    for case in corpus.cases:
        categories[case.category] = categories.get(case.category, 0) + 1
        if case.future_alert.ioc.type == "domain":
            assert case.future_alert.ioc.value.endswith(".invalid")
    assert set(categories.values()) == {3}
    scoped = {
        approval.approval_id: approval.max_duration_hours
        for case in corpus.cases
        for approval in case.trusted_fixtures.approvals
    }
    assert scoped == {"APR-2103": 24, "APR-3103": 12}


def test_poison_source_matches_frozen_concepts() -> None:
    config = load_config(ROOT / "configs/default.yaml")
    for case in load_cases(config).cases:
        assert harmful_meaning_preserved(case.source.poison, case), case.case_id
