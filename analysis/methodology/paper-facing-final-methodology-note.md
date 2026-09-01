# Final read-only methodology interpretation

## 1. Historical provenance comparison
The original Stage C `writer_generated + D0` and Stage D `provenance_preserved + D0` arms were separate registered runs, so they were not prospectively forced to share one Writer/retrieval object. However, the read-only audit found all 192 matched Reader-level pairs had identical Writer output, memory semantics/vectors, query vectors, ordered top-five retrievals, scores and retrieved vectors. After normalizing trial-local memory IDs and removing the intended provenance block, Reader payloads matched 192/192.

This substantially narrows the confounding concern. The comparison can be reported as strong retrospective evidence associated with provenance display, but not as a prospectively registered pure causal ablation.

## 2. Direct provenance+D0 versus D2 comparison
Retrospective A/B/C audit:
```json
{
  "arms": {
    "A": "Stage C writer_generated + D0",
    "B": "Stage D provenance_preserved + D0",
    "C": "Stage E full writer_generated + D2"
  },
  "matched_triplets": 192,
  "counts_true": {
    "writer_output_equal_ABC": 192,
    "memory_semantics_equal_ABC": 192,
    "memory_vectors_equal_ABC": 192,
    "query_equal_ABC": 192,
    "retrieval_equal_ABC": 192,
    "retrieval_vectors_equal_ABC": 192,
    "B_C_prompt_parse_ok": 192,
    "B_C_user_payload_equal_after_identifier_normalization": 192
  },
  "B_C_system_equal": 0,
  "B_has_d2_instruction": 0,
  "C_has_d2_instruction": 192,
  "A_zero_provenance": 192,
  "B_all_five_provenance": 192,
  "C_all_five_provenance": 192,
  "interpretation": "If all semantic/retrieval fields and normalized B/C user payloads match, the realized historical data form a strong retrospective three-arm comparison: A vs B changes provenance visibility; B vs C changes the defense-specific system instruction while both display provenance. It is still not a prospectively registered reader-only ablation because the arms were separate runs with different trial-local identifiers and potential run-to-run model nondeterminism."
}
```

If the reported equality checks are 192/192, the realized historical inputs show:
- A (`writer_generated + D0`): no provenance display;
- B (`provenance_preserved + D0`): provenance displayed with baseline D0 system instruction;
- C (`writer_generated + D2`): the same provenance-bearing user payload after normalizing trial-local identifiers, plus the D2 authorization-interpretation system instruction.

Even then, B→C should be described as a **retrospective treatment contrast**, not a prospectively randomized/preregistered reader-only instruction ablation.

## 3. Corrected deterministic-gate replay
The recovery CSVs were complete; only its aggregate summary had a collector bug.

Corrected local v0.3 D0 replay:
```json
{
  "total_proposals": 384,
  "by_variant": {
    "clean": {
      "proposals": 192,
      "allowed": 162,
      "blocked": 30,
      "unauthorized_recorded": 30,
      "unauthorized_blocked": 30,
      "unauthorized_allowed": 0,
      "authorized_recorded": 162,
      "authorized_blocked": 0,
      "authorized_high_impact": 0,
      "authorized_high_impact_allowed": 0,
      "reason_codes": {
        "LOW_IMPACT_ACTION": 162,
        "APPROVAL_REQUIRED": 25,
        "IOC_REQUIRED": 5
      },
      "unauthorized_actions": {
        "add_temporary_exception": 30
      }
    },
    "poison": {
      "proposals": 192,
      "allowed": 118,
      "blocked": 74,
      "unauthorized_recorded": 73,
      "unauthorized_blocked": 73,
      "unauthorized_allowed": 0,
      "authorized_recorded": 118,
      "authorized_blocked": 0,
      "authorized_high_impact": 0,
      "authorized_high_impact_allowed": 0,
      "reason_codes": {
        "APPROVAL_REQUIRED": 65,
        "LOW_IMPACT_ACTION": 118,
        "IOC_REQUIRED": 9
      },
      "unauthorized_actions": {
        "close_alert": 26,
        "mark_ioc_benign": 18,
        "add_temporary_exception": 29
      }
    }
  }
}
```

Corrected hosted v0.4.2 D0 replay:
```json
{
  "total_proposals": 380,
  "by_variant": {
    "clean": {
      "proposals": 192,
      "allowed": 182,
      "blocked": 10,
      "unauthorized_recorded": 8,
      "unauthorized_blocked": 8,
      "unauthorized_allowed": 0,
      "authorized_recorded": 182,
      "authorized_blocked": 0,
      "authorized_high_impact": 30,
      "authorized_high_impact_allowed": 30,
      "reason_codes": {
        "LOW_IMPACT_ACTION": 152,
        "APPROVAL_REQUIRED": 8,
        "CONTRACT_VALIDATED": 30,
        "IOC_REQUIRED": 1,
        "APPROVAL_INVALID": 1
      },
      "unauthorized_actions": {
        "add_temporary_exception": 7,
        "mark_ioc_benign": 1
      }
    },
    "poison": {
      "proposals": 188,
      "allowed": 101,
      "blocked": 87,
      "unauthorized_recorded": 84,
      "unauthorized_blocked": 84,
      "unauthorized_allowed": 0,
      "authorized_recorded": 101,
      "authorized_blocked": 0,
      "authorized_high_impact": 30,
      "authorized_high_impact_allowed": 30,
      "reason_codes": {
        "APPROVAL_REQUIRED": 85,
        "LOW_IMPACT_ACTION": 71,
        "IOC_REQUIRED": 2,
        "CONTRACT_VALIDATED": 30
      },
      "unauthorized_actions": {
        "mark_ioc_benign": 36,
        "close_alert": 47,
        "add_temporary_exception": 1
      }
    }
  }
}
```

Replay implementation validation:
- Stage E actual D4: 192/192 exact matches;
- hosted actual D4: 380/380 exact matches.

This is supplementary counterfactual deterministic-gate application to fixed proposals, not a new D4 Reader experiment.

## 4. Publication consequence
No historical registered result is changed. No LLM rerun is required merely to repair these methodology interpretations. A new reader-only A/B/C experiment is justified only if provenance-display effectiveness or the D2 instruction is promoted to a primary causal contribution.
