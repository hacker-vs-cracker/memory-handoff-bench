# MHB v0.4.2 Hosted Registered Execution

Final one-shot Amazon Bedrock Mantle external-validity package. There is deliberately **no smoke stage**.

This version preserves both earlier failed hosted runs rather than rewriting them:

- v0.4 run `481b8152-da81-461f-8723-3846f1d3c083`: provider JSON grammar rejected the frozen schema keyword `uniqueItems`.
- v0.4.1 run `9fa0e1f9-38b2-447f-8c53-eb64a048a750`: 33 trials completed; the first required structured repair failed because the local Ollama repair message shape produced `system,user,user`, while Gemma on Mantle requires role alternation.

v0.4.2 keeps the research matrix unchanged and changes only hosted adapter mechanics. Every semantic attempt is now a fresh two-message `system,user` conversation. Repairs restart from the original task + full textual schema + deterministic repair instruction; malformed assistant output is never replayed. Full validation remains local with the frozen Pydantic models. No provider `response_format` is sent.

Install as a sibling of `memory-handoff-bench-v0.3` under:

`<MHB_RESEARCH_ROOT>/`

Required shell environment:

- `OPENAI_API_KEY` = existing Amazon Bedrock API key.
- `OPENAI_BASE_URL=https://bedrock-mantle.us-east-1.api.aws/v1`

Run only:

`./run-registered-and-collect.sh`

The wrapper performs non-billed checks, verifies both preserved failed predecessors, verifies frozen v0.3 hashes, makes a new PostgreSQL backup, records Qdrant/source state, asks for the exact confirmation phrase, and then starts the 768-trial registered matrix under `caffeinate`.

Do not delete the v0.4/v0.4.1 run rows, partial Qdrant collections, or evidence before v0.4.2. v0.4.2 has a distinct run kind and fresh Qdrant prefix.

After a v0.4.2 run ID exists, do not launch v0.4.2 again. If all inference completes but only post-processing fails, use `./recover-postrun.sh`, which has no model-call path.

A successful evidence package includes actual hosted tokens, price-snapshot cost, API latency, structured-repair counts, D0/D4 outcomes, Qdrant/DB reconciliation, and post-hoc hosted cost/time estimates for the completed A-G and v0.3 designs.

## Evidence packaging note

The upload/recovery ZIPs include the exact protocol-locked source, tests, wrappers, specs and documentation in `frozen-package/`, while large PostgreSQL dumps remain local and are referenced by path/size/SHA-256. Large Ollama tensor metadata is compacted to identity/capability fields to keep evidence reviewable without losing the embedding model digest.
