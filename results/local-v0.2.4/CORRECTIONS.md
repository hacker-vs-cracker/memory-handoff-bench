# Publication package corrections

The original final-study archive remains preserved and is the input to this package.

`superseded/scenario-breakdown-v1.csv` grouped trials without `source_variant`. That merged Stage B clean and poison rows and placed clean model-safety fields beside attack fields without identifying them as clean observations. No trial, report, audit, mixed-effects result, Stage G seed table, or database record was affected.

The replacement `scenario-breakdown.csv` includes `source_variant`, separates clean utility from poison attack outcomes, and renames the raw ground-truth field to `unauthorized_action_proposed`. W/R results are provided separately in `writer-memory-stage-summary.csv` because their analysis unit is a shared writer-memory condition, not a duplicated reader or defense cell.

This package also copies and verifies every file named in `protocol_lock.json`. These are packaging and analysis corrections only; the frozen protocol and all results remain unchanged.
