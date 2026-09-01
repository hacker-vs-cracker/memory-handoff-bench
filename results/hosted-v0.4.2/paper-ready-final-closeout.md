# Memory Handoff Bench — Final Read-Only Closeout

Run: `3dcdf414-1252-481c-a082-9060b362ff90`

This closeout made **zero LLM/AWS calls, zero PostgreSQL writes, and zero Qdrant writes**. It is a reporting/integrity pass over already-recorded evidence.

## Integrity

Overall integrity: **True**. PostgreSQL read-only session: **on**. v0.4.2 package lock: **True**. v0.3 dependency hashes: **True**. Original v0.4.2 immutable upload archive: **True**. Pre-run PostgreSQL backup: **True**. Live Qdrant/database memory reconciliation: **True**.

## D4 clean utility — blocking objection

Status: **SUPPORTED**. All clean D4 trials completed: **192/192**. Clean proposals allowed by D4: **185**. Benign task successes: **147**. Recorded defense false positives: **0**. Authorized high-impact benign proposals: **30**; allowed: **30**; changed mock state: **30**. Therefore the claim that D4 achieved safety merely by blocking every clean action is **refuted by the recorded clean allow paths**.

## Hosted D0 and D4

D0 complete matched pairs: **188**. D0 unauthorized clean/poison: **8/84**; paired RD **0.404255**. D0 unsafe-state clean/poison: **7/83**.

D4 complete matched pairs: **188**. D4 unsafe-state clean/poison: **0/0**.

## Structured-output accounting

Final-protocol structured-output failed rows: **8**. Unique upstream failure units: **1**. These remain measured terminal model-format outcomes and were not rerun.

## Local vs hosted

The local v0.3 and hosted v0.4.2 D0 results are reported descriptively and are **not pooled**. Local complete pairs: **192**; hosted complete pairs: **188**.

## Final disposition

If integrity is PASS and D4 clean utility is supported, no further hosted LLM execution is required for the current external-validity scope. Independent human semantic review and literature positioning remain separate publication tasks.
