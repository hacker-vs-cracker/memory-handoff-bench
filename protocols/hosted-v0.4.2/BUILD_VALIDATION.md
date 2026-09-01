# Build validation — hosted v0.4.2

The delivered package is validated offline before use. Final delivered-byte validation runs **79 unit/regression/failure tests** plus shell/Python syntax, package-lock and frozen-v0.3 hash checks. The validation suite covers:

- shell syntax for registered and recovery wrappers;
- Python compilation for all source/tests;
- exact 384-pair / 768-trial design and order balance;
- four exact hosted model IDs and price entries;
- GPT OSS `max_completion_tokens`; other models `max_tokens`;
- no provider-side `response_format` in execution code;
- full frozen schema transmitted as ordinary text and enforced locally;
- **repair regression:** every initial/repair semantic attempt has exactly roles `system,user`;
- no malformed assistant output replayed during repair;
- simulated Gemma role-alternation guard accepts the repair shape;
- exact v0.4.1 regression: a 321-character `decision_summary` fails local validation, then succeeds through a fresh `system,user` repair request;
- repair-path portability is exercised for all four hosted model IDs;
- malformed JSON, Pydantic violations, duplicate evidence IDs, refusals and `finish_reason=length` use only the two deterministic semantic repairs;
- provider envelope errors and returned-model mismatch stop immediately, with billed malformed HTTP-200 envelopes explicitly recorded after usage accounting;
- HTTP 400/401/403 remain fatal;
- 408/409/425/429/500/502/503/504/529 plus network/timeouts use transport retries, independent of semantic repairs;
- numeric `Retry-After` honored with a bounded wait;
- missing usage is fatal so spend cannot become unaccounted;
- cost cap, reserve and request-attempt cap;
- API-key/Bearer redaction and evidence secret scan;
- study-local typed D4 approval SQL correction preserved;
- both failed predecessor run IDs/protocol hashes required;
- fresh `hosted_external_validity_v0.4.2` run kind;
- fresh `mhb_v042_hosted` Qdrant prefix while old v0.4/v0.4.1 collections are preserved;
- recovery script contains no inference entry point;
- atomic local concurrency lock, exact one-shot confirmation and no smoke path;
- shell interruption after run creation marks a still-running run row failed before evidence packaging;
- frozen v0.3 dependency hashes.

No live Bedrock model request is made by this offline suite.
