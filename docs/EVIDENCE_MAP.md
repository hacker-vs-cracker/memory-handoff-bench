# Evidence map

This map separates registered evidence, read-only derivations, human validation,
and private preservation records. Files from different stages should not be
pooled merely because they share an endpoint name.

| Path | Evidentiary role | Interpretation boundary |
| --- | --- | --- |
| `protocols/v0.3/protocol_lock.json` | Local matched protocol identity | Confirms the frozen v0.3 design and source |
| `protocols/v0.3/frozen-protocol/` | Byte-identical local registered source | Do not edit; local path comments are preserved for lock integrity |
| `results/local-v0.3/` | Local matched registered outcomes and recovery summaries | Primary local clean-poison evidence |
| `protocols/hosted-v0.4.2/` | Hosted adapter, registered configuration, and identity | Hosted extension; earlier failed adapters are engineering history |
| `results/hosted-v0.4.2/` | Hosted registered outcomes and closeout analysis | Use 188 complete D0 pairs for paired D0 claims |
| `results/local-v0.2.4/` | Earlier staged local program and sensitivity evidence | Exploratory or supporting evidence unless a file says otherwise |
| `analysis/methodology/retrospective-three-arm-comparability.csv` | Realized-input comparability audit | Retrospective condition comparison, not prospective provenance ablation |
| `analysis/methodology/corrected-gate-replay-summary.json` | Fixed-proposal D4 replay | Isolates deterministic enforcement on recorded proposals |
| `human-validation/agreement-summary.json` | Independent blinded W and I agreement | Validation layer; does not overwrite registered labels |
| `human-validation/adjudication-summary.csv` | Post-lock disagreement resolution | Applies only to the eight disagreement rows |
| `human-validation/casebook-review-public.csv` | Sanitized executed-chain narrative review | Qualitative and auditability evidence |
| `reproducibility/registered-model-manifest-v0.4.2.json` | Hosted model identity | Supports environment attribution, not model-family causality |
| `reproducibility/OFF_REPO_ARTIFACT_INTEGRITY.tsv` | Hash commitments for private preserved artifacts | Does not make private artifacts public or independently downloadable |
| `FILE_MANIFEST.tsv` and `SHA256SUMS.txt` | Public-tree integrity | Regenerated only for a new release version |

## Registered versus derived

Registered trial records and frozen protocol outputs determine the benchmark's
primary counts. Recovery, comparability, replay, aggregation, and human-review
files are publication layers over preserved evidence. They may clarify or test
an interpretation, but they do not silently rewrite registered database rows.

## Public versus private

Public derivatives omit credentials, environment files, database dumps, vector
snapshots, provider and billing telemetry, raw reviewer returns, reviewer
mappings, sealed human-review archives, and the R12 narrative handoff. The
off-repository ledger supplies neutral identifiers, sizes, and hashes so that a
specific preserved object can be requested without exposing the entire private
archive.
