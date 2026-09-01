# Protocol Amendment v0.2.1 — Structured-Output Compatibility

## Status and scope

Protocol v0.2.1 is frozen after reviewing the v0.1 smoke runs and Stages A–C, and before any
v0.2 or v0.2.1 model result. It supersedes v0.2 for new runs. Historical v0.1 evidence remains
immutable and must not be pooled with v0.2.1 evidence.

The threat model, case corpus, poison text, concept groups, four-model matrix, EmbeddingGemma
primary encoder, inference temperature, seed, top-k, retrieval distractors, D0–D5 definitions,
mock-SIEM behavior, and `W → R → I → A → G → S` outcome rules are unchanged.

## Evidence that required this amendment

Regenerated v0.1 reports exposed one systematic compatibility defect and one isolated formatting
failure:

- Stage A: 8/48 trials failed. All eight were Mistral writer responses using confidence scales
  above the registered 0–1 range.
- Stage B: 14/96 trials failed. All fourteen had the same Mistral confidence-scale cause.
- Stage C: 25/192 trials failed. Twenty-four were the same Mistral writer condition fanning out
  across four readers; one was a truncated Gemma reader JSON response.

No PostgreSQL, Qdrant, embedding, timeout, or model-identity failure was present in these runs.

## Registered operational corrections

### Confidence compatibility

The writer prompt now explicitly requires a decimal from 0.0 through 1.0. The host also
deterministically normalizes common non-compliant scales before schema validation:

- values greater than 1 and at most 10 are divided by 10;
- values greater than 10 and at most 100 are divided by 100;
- all other values remain subject to the frozen 0–1 schema constraint.

The original model response is retained unchanged in invocation evidence. The normalized value is
stored only in parsed output. Writer confidence is metadata: it is not used by retrieval, harmful
meaning scoring, reader influence scoring, authorization, gate behavior, or any attack outcome.

### One schema-only retry

Each structured writer or reader call may receive at most one repair attempt after invalid JSON or
schema validation failure. The repair instruction asks only for complete schema-valid JSON and
does not reveal gate, authorization, executor, state-change, or attack-scoring results. Both the
invalid attempt and final response are retained in invocation evidence. If the repair also fails,
the trial remains failed.

The retry count is frozen as `inference.structured_retries: 1`.

### Qdrant client compatibility

The Python client is pinned to `qdrant-client==1.17.1`, matching the observed Qdrant server
version 1.17.1. No collection, vector, distance, filtering, or top-k behavior changes.

### Compact reports

JSON reports no longer duplicate Ollama's multi-megabyte `model_info` tensor metadata for every
run. Each omitted object is represented by SHA-256, byte length, and key count. The complete
manifest remains in PostgreSQL and `evidence/model_manifest.json`; model digest, parameters,
template, details, and capabilities remain directly in the report.

## Required order

1. Install v0.2.1 and verify its protocol lock.
2. Re-run preflight with the pinned Qdrant client and exact model digests.
3. Run the clean and poison smoke trials plus the two compatibility smoke trials registered in
   the README.
4. Audit all four smoke runs for one planned/completed trial and zero failures.
5. Repeat Stages A, B, and C under new v0.2.1 run IDs.
6. Continue to Stage D only after A–C pass their registered integrity and stop/go audits.

No further model, prompt, schema, retry, case, defense, temperature, top-k, or scoring change may
be made after the first v0.2.1 result is inspected without another protocol version.
