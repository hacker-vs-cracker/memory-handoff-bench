ALTER TABLE experiment_runs
    ADD COLUMN IF NOT EXISTS run_kind TEXT NOT NULL DEFAULT 'matrix';
-- mhb:split

CREATE UNIQUE INDEX IF NOT EXISTS uq_experiment_runs_counterfactual_v03
    ON experiment_runs(run_kind)
    WHERE run_kind = 'counterfactual_v0.3';
-- mhb:split

ALTER TABLE trials
    ADD COLUMN IF NOT EXISTS counterfactual_pair_key TEXT,
    ADD COLUMN IF NOT EXISTS counterfactual_order SMALLINT;
-- mhb:split

ALTER TABLE trials
    DROP CONSTRAINT IF EXISTS trials_counterfactual_pair_check;
-- mhb:split

ALTER TABLE trials
    ADD CONSTRAINT trials_counterfactual_pair_check
    CHECK (
        (counterfactual_pair_key IS NULL AND counterfactual_order IS NULL)
        OR
        (counterfactual_pair_key IS NOT NULL AND counterfactual_order IN (1, 2))
    );
-- mhb:split

CREATE UNIQUE INDEX IF NOT EXISTS uq_trials_counterfactual_member
    ON trials(run_id, counterfactual_pair_key, source_variant)
    WHERE counterfactual_pair_key IS NOT NULL;
-- mhb:split

CREATE INDEX IF NOT EXISTS idx_trials_counterfactual_pair
    ON trials(run_id, counterfactual_pair_key)
    WHERE counterfactual_pair_key IS NOT NULL;
-- mhb:split

DROP VIEW IF EXISTS trial_evidence_chain;
-- mhb:split

CREATE VIEW trial_evidence_chain AS
SELECT
    t.run_id,
    t.trial_id,
    t.case_id,
    t.source_variant,
    t.memory_mode,
    t.writer_model,
    t.reader_model,
    t.embedding_model,
    t.defense,
    t.seed,
    t.status,
    t.counterfactual_pair_key,
    t.counterfactual_order,
    s.content_hash AS source_hash,
    so.poison_written,
    so.poison_retrieved,
    so.reader_influenced,
    so.unauthorized_action_attempted,
    so.baseline_gate_allowed,
    so.proposal_authorized,
    so.unsafe_state_changed,
    so.false_completion_claim,
    so.benign_task_success,
    so.benign_action_executed,
    so.defense_false_positive,
    so.attempted_attack_success,
    so.executed_attack_success,
    so.retrieval_at_k,
    so.poison_rank
FROM trials t
LEFT JOIN sources s
    ON s.trial_id = t.trial_id
   AND s.source_authority = 'untrusted_external'
LEFT JOIN stage_outcomes so ON so.trial_id = t.trial_id;
