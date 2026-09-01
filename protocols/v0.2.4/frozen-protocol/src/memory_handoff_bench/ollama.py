from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import InferenceConfig

T = TypeVar("T", bound=BaseModel)


class OllamaError(RuntimeError):
    pass


class StructuredOutputError(OllamaError):
    def __init__(self, model: str, attempts: list[dict[str, Any]]) -> None:
        self.model = model
        self.attempts = attempts
        self.evidence_raw = {
            "final_response": attempts[-1]["response"],
            "final_validation_error": attempts[-1]["validation_error"],
            "invalid_attempts": attempts[:-1],
            "structured_retry_count": len(attempts) - 1,
            "structured_output_failed": True,
        }
        issues = "; ".join(
            f"attempt {item['attempt']}: {item['validation_error']}" for item in attempts
        )
        super().__init__(
            f"Invalid structured output from {model} after {len(attempts)} attempt(s): {issues}"
        )


@dataclass(frozen=True)
class StructuredResponse:
    parsed: BaseModel
    raw: dict[str, Any]
    content: str


REPAIR_INSTRUCTIONS = (
    (
        "Repair pass 1. Start over from the original task and return one compact JSON object "
        "matching the required schema. Keep every descriptive string short and do not copy "
        "long identifiers into prose when a dedicated identifier field exists. Do not add "
        "analysis, markdown, or an execution claim. Validation issue: "
    ),
    (
        "Repair pass 2. Recreate the smallest complete JSON object that preserves your chosen "
        "action and evidence judgment while satisfying every schema constraint. Use identifiers "
        "only in their dedicated fields, keep prose concise, and return no text outside the JSON "
        "object. Do not add an execution claim. Validation issue: "
    ),
)


class OllamaClient:
    def __init__(self, base_url: str, inference: InferenceConfig) -> None:
        self.base_url = base_url.rstrip("/")
        self.inference = inference
        self.client = httpx.Client(base_url=self.base_url, timeout=inference.timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        response = self.client.get("/api/version")
        response.raise_for_status()
        return response.json()

    def tags(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/tags")
        response.raise_for_status()
        return response.json().get("models", [])

    def show(self, model: str) -> dict[str, Any]:
        response = self.client.post("/api/show", json={"model": model, "verbose": True})
        response.raise_for_status()
        return response.json()

    def manifest(self, model_names: list[str]) -> dict[str, Any]:
        tag_map = {item.get("name"): item for item in self.tags()}
        manifest: dict[str, Any] = {"ollama": self.health(), "models": {}}
        for name in model_names:
            tag = tag_map.get(name)
            if tag is None:
                manifest["models"][name] = {"installed": False}
                continue
            detail = self.show(name)
            manifest["models"][name] = {
                "installed": True,
                "digest": tag.get("digest"),
                "size": tag.get("size"),
                "modified_at": tag.get("modified_at"),
                "details": tag.get("details") or detail.get("details"),
                "model_info": detail.get("model_info"),
                "parameters": detail.get("parameters"),
                "template": detail.get("template"),
                "capabilities": detail.get("capabilities"),
            }
        return manifest

    def structured_chat(
        self,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        *,
        seed: int | None = None,
    ) -> StructuredResponse:
        base_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        messages = list(base_messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "format": response_model.model_json_schema(),
            "stream": False,
            "think": self.inference.think,
            "keep_alive": self.inference.keep_alive,
            "options": {
                "num_ctx": self.inference.num_ctx,
                "temperature": self.inference.temperature,
                "seed": self.inference.seed if seed is None else seed,
            },
        }
        invalid_attempts: list[dict[str, Any]] = []
        for attempt_index in range(self.inference.structured_retries + 1):
            payload["messages"] = messages
            try:
                response = self.client.post("/api/chat", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise OllamaError(f"Ollama chat failed for {model}: {exc}") from exc
            raw = response.json()
            content = raw.get("message", {}).get("content", "")
            try:
                if raw.get("done") is not True:
                    raise ValueError(
                        "Ollama returned an incomplete non-streaming structured response "
                        "(done is not true)"
                    )
                parsed_json = self._extract_json(content)
                parsed = response_model.model_validate(parsed_json)
            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                invalid_attempts.append(
                    {
                        "attempt": attempt_index + 1,
                        "validation_error": str(exc),
                        "response": raw,
                    }
                )
                if attempt_index >= self.inference.structured_retries:
                    raise StructuredOutputError(model, invalid_attempts) from exc
                repair_instruction = REPAIR_INSTRUCTIONS[attempt_index]
                messages = [
                    *base_messages,
                    {
                        "role": "user",
                        "content": repair_instruction + str(exc)[:1000],
                    },
                ]
                continue

            evidence_raw = raw
            if invalid_attempts:
                evidence_raw = {
                    "final_response": raw,
                    "invalid_attempts": invalid_attempts,
                    "structured_retry_count": len(invalid_attempts),
                }
            return StructuredResponse(parsed=parsed, raw=evidence_raw, content=content)

        raise AssertionError("structured chat retry loop exited unexpectedly")

    def embed(self, model: str, inputs: list[str]) -> tuple[list[list[float]], dict[str, Any]]:
        try:
            response = self.client.post(
                "/api/embed",
                json={
                    "model": model,
                    "input": inputs,
                    "truncate": False,
                    "keep_alive": self.inference.keep_alive,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama embedding failed for {model}: {exc}") from exc
        payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
            raise OllamaError("Ollama returned an unexpected embedding count")
        return embeddings, payload

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value
