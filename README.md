# Memory Handoff Bench

Memory Handoff Bench, or MHB, is the publication-safe artifact for the study
**Authority Without Authorization: A Matched Study of Persistent Memory
Poisoning Across LLM Handoffs**.

MHB tests a delayed attack path. An untrusted email or ticket is transformed
into durable memory by a Writer model. A later Reader retrieves that memory
during a clean task and may treat a stored claim as operational authority. The
benchmark records writing, retrieval, interpretation, proposal, deterministic
gate admission, and reversible mock-state mutation as separate endpoints.

## Headline results

| Registered comparison | Clean | Poison | Paired difference |
| --- | ---: | ---: | ---: |
| Local v0.3 unauthorized proposal | 30/192 | 73/192 | +22.396 percentage points |
| Local v0.3 unsafe state change | 8/192 | 34/192 | +13.542 percentage points |
| Hosted v0.4.2 unauthorized proposal | 8/188 | 84/188 | +40.426 percentage points |
| Hosted v0.4.2 unsafe state change | 7/188 | 83/188 | +40.426 percentage points |

The hosted figures use 188 complete D0 pairs, not the 192 planned pairs. Local
and hosted protocols are reported separately and are not pooled. Whole-case
bootstrap sensitivity intervals and pair-transition counts are preserved in
the paper-facing result files.

The fixed-proposal D4 replay held recorded Reader proposals constant. The gate
blocked every recorded proposal carrying the registered unauthorized endpoint:
30/30 local-clean, 73/73 local-poison, 8/8 hosted-clean, and 84/84 hosted-poison.
It did not block a recorded proposal marked `proposal_authorized=true`. This is
evidence about deterministic enforcement, not evidence that the Reader became
correct.

## Human validation

The planned human review is complete. Two independent reviewers assessed all
48 poisoned Writer-memory units and all 192 poisoned Reader trials under
blinding. Raw agreement was 44/48, or 91.667%, for W and 188/192, or 97.917%,
for I. Eight disagreements were adjudicated only after independent labels were
locked. All 114 executed-attack casebook narratives also received human review.

Human judgments are a separate validation and sensitivity layer. They do not
replace or rewrite the registered machine outcomes.

## Repository map

| Path | Contents |
| --- | --- |
| `protocols/` | Frozen local and hosted protocol source, configurations, locks, and validation material |
| `results/` | Publication-safe registered and derived result summaries |
| `analysis/methodology/` | Read-only comparability audit and fixed-proposal gate replay evidence |
| `human-validation/` | Sanitized agreement, adjudication, and casebook-review derivatives |
| `reproducibility/` | Model identity and off-repository artifact integrity records |
| `docs/` | Methods overview and evidence map |
| `FILE_MANIFEST.tsv` | File sizes and SHA-256 digests |
| `SHA256SUMS.txt` | Integrity checks for the public tree |

See `docs/EVIDENCE_MAP.md` before interpreting files from different stages as
one pooled experiment.

## Integrity check

On macOS:

```bash
shasum -a 256 -c SHA256SUMS.txt
```

On Linux:

```bash
sha256sum -c SHA256SUMS.txt
```

`SHA256SUMS.txt` intentionally excludes itself. `FILE_MANIFEST.tsv` records all
other publication files except the two recursively generated integrity files.

## Protocol inspection

The protocol trees are preserved byte-for-byte. A basic local inspection can
be run from the v0.3 protocol directory:

```bash
cd protocols/v0.3/frozen-protocol
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,analysis]"
pytest -q
mhb verify-protocol -c configs/counterfactual-v0.3.yaml
mhb validate-counterfactual-design -c configs/counterfactual-v0.3.yaml
```

Full registered execution additionally requires the frozen model identities,
PostgreSQL, Qdrant, Ollama or the documented hosted adapter, and the original
runtime assumptions. Do not casually rerun inference and mix it with the
registered evidence.

## Evidence boundaries

The public repository excludes PostgreSQL dumps, Qdrant snapshots, credentials,
environment files, provider and billing telemetry, raw invalid responses, raw
Reviewer A and B returns, reviewer mapping material, sealed human-review ZIPs,
and the internal R12 handoff. Their preservation status is represented only by
checksums and neutral artifact identifiers where useful.

Two frozen documentation files retain a generic workstation root used during
registered execution. Those strings contain no username, hostname, credential,
or secret and remain unchanged to preserve byte identity with the registered
protocol locks.

## Limits on interpretation

MHB uses twelve synthetic SOC cases. It does not estimate attack prevalence in
production, isolate a field-level causal effect of provenance, or test an
adaptive adversary against D4. The hosted study is a supplementary
external-validity extension. Historical memory-mode and defense matrices should
not be treated as single-factor causal ablations unless the corresponding
analysis explicitly holds the remaining inputs fixed.

## Citation and paper

Artifact DOI: [10.5281/zenodo.22139124](https://doi.org/10.5281/zenodo.22139124)

Machine-readable artifact citation metadata is available in `CITATION.cff`.
The arXiv identifier and paper URL will be added after assignment and before
the repository becomes public.

## Licensing

Original code is licensed under Apache-2.0. Author-created documentation,
aggregate research outputs, and sanitized validation derivatives are licensed
under CC BY 4.0, subject to the exclusions in `LICENSES.md`.

## Acknowledgments

Nirmal Singh provided independent research validation and technical review. Priyanka Bhati assisted with manuscript preparation.
