# Pre-run compatibility basis for hosted v0.4.2

No hosted smoke run is performed by project-owner decision.

Evidence collected before this freeze established:

1. Mantle `/models` exposes all four selected model IDs in `us-east-1`.
2. All four models have produced successful hosted Chat Completions responses with the account/API key.
3. GPT OSS 20B requires an adequate `max_completion_tokens` allowance; a direct 1024-token diagnostic returned `finish_reason=stop` and valid JSON.
4. v0.4 showed that provider-side JSON grammar cannot represent the complete frozen Pydantic schema (`uniqueItems` rejection); v0.4.2 therefore sends no provider `response_format`.
5. v0.4.1 completed 33 trials and 40 billed HTTP-200 requests across all four reader model families before the first structured-repair event. That repair was rejected because the request roles were `system,user,user`.
6. v0.4.2 fixes that provider-portability defect by making **every** semantic attempt a fresh `system,user` conversation. The repair instruction is appended to the original user task/schema, while malformed assistant content is never included.
7. Full JSON/schema enforcement remains local with the exact frozen `WriterOutput`/`ReaderOutput` Pydantic models and the same two deterministic repair instructions.
8. v0.4.2 uses a fresh run kind and Qdrant prefix while requiring both failed predecessors to remain present and failed.
9. Pre-run checks are non-billed: model catalog, local PostgreSQL/Qdrant/Ollama/EmbeddingGemma, frozen hashes, predecessor identity, one-shot state, power and disk.

The absence of a separate smoke is an explicit operational choice and should be reported as such.
