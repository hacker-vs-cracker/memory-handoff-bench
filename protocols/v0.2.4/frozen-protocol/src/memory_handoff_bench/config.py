from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import ModelSpec, PilotCorpus


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
    database_url: str
    qdrant_url: str
    ollama_url: str
    root: Path

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
