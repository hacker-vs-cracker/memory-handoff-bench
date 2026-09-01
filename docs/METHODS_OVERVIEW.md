# Methods overview

## Threat model

MHB studies persistent memory poisoning across a delayed Writer and Reader
handoff. An untrusted source can preserve a false approval, fabricated analyst
precedent, or unsafe operating rule in durable memory. A later Reader may
retrieve the record during an otherwise clean task and propose a consequential
action.

The recorded chain is `W -> R -> I -> A -> G -> S`:

- `W`: harmful meaning is preserved in Writer-generated memory;
- `R`: the relevant record appears in trial-isolated top-five retrieval;
- `I`: the Reader cites W-positive memory while selecting the registered
  unauthorized action;
- `A`: the Reader proposes the registered unauthorized action;
- `G`: the deterministic gate admits the proposal;
- `S`: the reversible mock environment records an unsafe state change.

`I` is an operational attribution indicator, not a counterfactual measure of
psychological influence. In the frozen poison-trial definition, `I` entails
`A`. The broader `A` endpoint remains separately useful on both clean and poison
trials.

## Primary matched design

Local v0.3 assigns clean and poisoned source variants within a fixed
case-Writer-Reader-D0 key. Twelve cases, four Writers, and four Readers produce
192 matched pairs and 384 trials. Pair and Writer-generation order are balanced.
Writer-level units are not counted again as independent observations merely
because four Readers consume them.

The hosted v0.4.2 extension uses the same twelve cases and matched structure
with hosted model families. Four D0 pairs were incomplete, leaving 188 complete
pairs for paired D0 analysis. The hosted and local estimates are not pooled.

## Retrieval and state

Each trial uses isolated retrieval with a fixed distractor construction and a
recorded top-five result. PostgreSQL retains trial, proposal, gate, and state
evidence. Qdrant supplies vector retrieval. Consequential actions execute only
against a reversible mock SIEM state.

## Defense interpretation

The registered defense matrix changes both Reader context and enforcement, so
its D0 to D4 contrast is not a pure gate ablation. The fixed-proposal replay
provides the enforcement mechanism test: it applies the frozen D4 gate to
already-recorded D0 proposals without rerunning a Writer or Reader and without
mutating the database or vector store.

Provenance-visible and D2 historical comparisons are retrospective condition
contrasts. Raw RAG is a whole-pipeline condition. Neither should be interpreted
as an isolated one-factor causal effect.

## Human review

Two independent blinded reviewers labeled the complete planned Phase 1
population: 48 W units and 192 I trials. Original decisions were preserved.
Eight disagreements were adjudicated after locking. A later Phase 2 review
covered all 114 executed-attack casebook narratives. Public files are sanitized
derivatives; raw returns, reviewer mappings, and sealed evidence remain private.

Registered machine labels remain the benchmark outcomes. Human labels provide
construct-validity and sensitivity evidence.

## Statistical boundary

The paper reports matched differences, pair transitions, and a 10,000-replicate
whole-case bootstrap that resamples all observations within each of the twelve
case clusters. These intervals measure sensitivity to the case composition and
must not be read as production-prevalence intervals.
