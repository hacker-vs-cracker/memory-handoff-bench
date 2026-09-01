from pathlib import Path

from memory_handoff_bench.config import load_cases, load_config
from memory_handoff_bench.experiment import retrieval_distractor_texts
from memory_handoff_bench.metrics import harmful_meaning_preserved

ROOT = Path(__file__).resolve().parents[1]


def test_retrieval_distractors_are_neutral_and_exceed_top_k() -> None:
    config = load_config(ROOT / "configs/default.yaml")
    assert config.benchmark.retrieval_distractors > config.benchmark.top_k
    for case in load_cases(config).cases:
        records = retrieval_distractor_texts(case, config.benchmark.retrieval_distractors)
        assert len(records) == config.benchmark.retrieval_distractors
        assert all(not harmful_meaning_preserved(text, case) for text in records)


def test_terminal_writer_failure_is_cached_across_readers() -> None:
    from memory_handoff_bench.domain import MemoryMode, SourceVariant
    from memory_handoff_bench.experiment import ExperimentRunner
    from memory_handoff_bench.ollama import StructuredOutputError

    class FailingOllama:
        def __init__(self) -> None:
            self.calls = 0

        def structured_chat(self, *args: object, **kwargs: object) -> object:
            self.calls += 1
            attempts = [
                {
                    "attempt": index,
                    "validation_error": "invalid",
                    "response": {"done": False, "message": {"content": "{"}},
                }
                for index in (1, 2, 3)
            ]
            raise StructuredOutputError("writer", attempts)

    config = load_config(ROOT / "configs/counterfactual-v0.3.yaml")
    case = load_cases(config).cases[0]
    ollama = FailingOllama()
    runner = ExperimentRunner(config, None, None, ollama, {})  # type: ignore[arg-type]

    for _ in range(2):
        try:
            runner._writer_result(
                case,
                case.source.poison,
                SourceVariant.POISON,
                MemoryMode.WRITER_GENERATED,
                "llama3.1:latest",
                42,
            )
        except StructuredOutputError:
            pass
        else:
            raise AssertionError("expected terminal writer structured-output failure")

    assert ollama.calls == 1
