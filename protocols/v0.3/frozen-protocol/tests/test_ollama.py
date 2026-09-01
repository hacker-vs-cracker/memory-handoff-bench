import json

import httpx
import pytest
from pydantic import BaseModel

from memory_handoff_bench.config import InferenceConfig
from memory_handoff_bench.ollama import OllamaClient, StructuredOutputError


class ResponseShape(BaseModel):
    value: int


def test_structured_chat_repairs_twice_and_keeps_invalid_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = '{"value":' if len(requests) < 3 else '{"value": 7}'
        return httpx.Response(200, json={"done": True, "message": {"content": content}})

    inference = InferenceConfig(
        num_ctx=8192,
        temperature=0,
        seed=42,
        timeout_seconds=30,
        structured_retries=2,
    )
    client = OllamaClient("http://ollama.invalid", inference)
    client.client.close()
    client.client = httpx.Client(
        base_url="http://ollama.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = client.structured_chat(
            "model:latest",
            "system",
            "user",
            ResponseShape,
        )
    finally:
        client.close()

    assert response.parsed.value == 7
    assert response.raw["structured_retry_count"] == 2
    assert response.raw["invalid_attempts"][0]["response"]["message"]["content"] == '{"value":'
    assert len(response.raw["invalid_attempts"]) == 2
    assert len(requests) == 3
    assert len(requests[1]["messages"]) == 3
    assert len(requests[2]["messages"]) == 3
    assert all(message["role"] != "assistant" for message in requests[1]["messages"])


def test_structured_chat_failed_retries_keep_every_raw_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "done": True,
                "message": {"content": f'{{"value": invalid-{len(requests)}'},
            },
        )

    inference = InferenceConfig(
        num_ctx=8192,
        temperature=0,
        seed=42,
        timeout_seconds=30,
        structured_retries=2,
    )
    client = OllamaClient("http://ollama.invalid", inference)
    client.client.close()
    client.client = httpx.Client(
        base_url="http://ollama.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(StructuredOutputError) as captured:
            client.structured_chat("model:latest", "system", "user", ResponseShape)
    finally:
        client.close()

    evidence = captured.value.evidence_raw
    assert len(requests) == 3
    assert evidence["structured_retry_count"] == 2
    assert evidence["structured_output_failed"] is True
    assert len(evidence["invalid_attempts"]) == 2
    assert evidence["final_response"]["message"]["content"] == '{"value": invalid-3'


def test_structured_chat_treats_done_false_as_incomplete_and_varies_repairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(name, raising=False)
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"done": False, "message": {"content": '{"value":'}},
        )

    inference = InferenceConfig(
        num_ctx=8192,
        temperature=0,
        seed=42,
        timeout_seconds=30,
        structured_retries=2,
    )
    client = OllamaClient("http://ollama.invalid", inference)
    client.client.close()
    client.client = httpx.Client(
        base_url="http://ollama.invalid",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(StructuredOutputError) as captured:
            client.structured_chat("model:latest", "system", "user", ResponseShape)
    finally:
        client.close()

    evidence = captured.value.evidence_raw
    assert evidence["structured_output_failed"] is True
    assert evidence["structured_retry_count"] == 2
    assert all(
        "done is not true" in item["validation_error"]
        for item in [*evidence["invalid_attempts"], {"validation_error": evidence["final_validation_error"]}]
    )
    assert requests[1]["messages"][-1]["content"] != requests[2]["messages"][-1]["content"]
    assert requests[1]["messages"][-1]["content"].startswith("Repair pass 1")
    assert requests[2]["messages"][-1]["content"].startswith("Repair pass 2")
