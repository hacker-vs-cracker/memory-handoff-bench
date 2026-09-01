from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import DefenseCondition, MemoryMode, ModelSpec, PilotCorpus, SourceVariant


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    protocol_version: str
    case_file: Path
    top_k: int = Field(ge=1, le=20)
    retrieval_distractors: int = Field(default=8, ge=0, le=50)
    collection_prefix: str
    sequential: bool = True

    @model_validator(mode="after")
    def retrieval_has_competition(self) -> BenchmarkConfig:
        if self.retrieval_distractors <= self.top_k:
            raise ValueError("retrieval_distractors must exceed top_k in protocol v0.2+")
        return self


class InferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    num_ctx: int = Field(ge=2048)
    temperature: float = Field(ge=0, le=2)
    seed: int
    keep_alive: str = "5m"
    timeout_seconds: float = Field(gt=0)
    structured_retries: int = Field(default=2, ge=0, le=2)
    think: bool | str = False


class CounterfactualConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    memory_mode: MemoryMode = MemoryMode.WRITER_GENERATED
    defense: DefenseCondition = DefenseCondition.D0
    variants: list[SourceVariant] = Field(
        default_factory=lambda: [SourceVariant.CLEAN, SourceVariant.POISON]
    )
    pairing: Literal["all"] = "all"
    seeds: list[int] = Field(default_factory=lambda: [42], min_length=1)
    order_strategy: Literal["blocked_alternating"] = "blocked_alternating"
    expected_cases: int = Field(default=12, ge=1)
    expected_pairs: int = Field(default=192, ge=1)
    expected_trials: int = Field(default=384, ge=2)
    bootstrap_replicates: int = Field(default=10000, ge=0, le=100000)
    bootstrap_seed: int = 20260818

    @model_validator(mode="after")
    def validate_confirmatory_design(self) -> CounterfactualConfig:
        if self.memory_mode != MemoryMode.WRITER_GENERATED:
            raise ValueError("v0.3 counterfactual design requires writer_generated memory")
        if self.defense != DefenseCondition.D0:
            raise ValueError("v0.3 counterfactual design requires D0 to isolate the handoff effect")
        if self.variants != [SourceVariant.CLEAN, SourceVariant.POISON]:
            raise ValueError("v0.3 requires variants in canonical [clean, poison] design set")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("counterfactual seeds must be unique")
        if self.expected_trials != self.expected_pairs * 2:
            raise ValueError("expected_trials must equal exactly two members per expected pair")
        return self


class CapabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reader: list[str]


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benchmark: BenchmarkConfig
    inference: InferenceConfig
    primary_models: list[ModelSpec]
    supplementary_models: list[ModelSpec] = Field(default_factory=list)
    embedding_models: list[ModelSpec]
    capabilities: CapabilityConfig
    counterfactual: CounterfactualConfig | None = None
    database_url: str
    qdrant_url: str
    ollama_url: str
    root: Path

    @model_validator(mode="after")
    def validate_protocol_specific_settings(self) -> AppConfig:
        if self.benchmark.protocol_version == "0.3":
            if self.counterfactual is None or not self.counterfactual.enabled:
                raise ValueError("protocol v0.3 requires an enabled counterfactual section")
            if self.inference.temperature != 0.0:
                raise ValueError("protocol v0.3 confirmatory run requires temperature=0.0")
            if not self.benchmark.sequential:
                raise ValueError("protocol v0.3 confirmatory run must remain sequential")
        return self

    @property
    def primary_embedding(self) -> ModelSpec:
        return next(model for model in self.embedding_models if model.role == "primary")


def _load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_config(config_path: str | Path | None = None) -> AppConfig:
    requested = Path(config_path or os.getenv("MHB_CONFIG", "configs/default.yaml"))
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = requested.resolve()
    root = requested.parent.parent
    _load_local_env(root / ".env")
    data: dict[str, Any] = yaml.safe_load(requested.read_text(encoding="utf-8"))
    case_file = Path(data["benchmark"]["case_file"])
    if not case_file.is_absolute():
        data["benchmark"]["case_file"] = root / case_file
    data.update(
        {
            "database_url": os.getenv(
                "DATABASE_URL", "postgresql://localhost:5432/memory_handoff_bench"
            ),
            "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
            "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
            "root": root,
        }
    )
    return AppConfig.model_validate(data)


def load_cases(config: AppConfig) -> PilotCorpus:
    payload = yaml.safe_load(config.benchmark.case_file.read_text(encoding="utf-8"))
    return PilotCorpus.model_validate(payload)
