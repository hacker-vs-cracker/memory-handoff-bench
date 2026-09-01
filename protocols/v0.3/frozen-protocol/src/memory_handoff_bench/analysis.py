from __future__ import annotations

from pathlib import Path
from typing import Any


def fit_binary_mixed_model(rows: list[dict[str, Any]], output_path: Path) -> Path:
    try:
        import pandas as pd
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except ImportError as exc:
        raise RuntimeError(
            'Install analysis dependencies with: pip install -e ".[analysis]"'
        ) from exc

    frame = pd.DataFrame(rows)
    frame = frame[
        (frame["status"] == "completed")
        & (frame["source_variant"] == "poison")
        & frame["executed_attack_success"].notna()
    ].copy()
    if len(frame) < 30 or frame["executed_attack_success"].nunique() < 2:
        raise RuntimeError(
            "Mixed-effects fitting needs at least 30 completed poisoned trials and both outcomes"
        )
    frame["executed_attack_success"] = frame["executed_attack_success"].astype(int)
    model = BinomialBayesMixedGLM.from_formula(
        "executed_attack_success ~ C(defense) + C(memory_mode) + C(embedding_model)",
        {
            "case": "0 + C(case_id)",
            "writer": "0 + C(writer_model)",
            "reader": "0 + C(reader_model)",
        },
        frame,
    )
    result = model.fit_vb()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(str(result.summary()) + "\n", encoding="utf-8")
    return output_path
