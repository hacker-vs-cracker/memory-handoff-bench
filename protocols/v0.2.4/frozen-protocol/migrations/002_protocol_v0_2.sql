ALTER TABLE stage_outcomes
    ADD COLUMN IF NOT EXISTS proposal_authorized BOOLEAN;
-- mhb:split

ALTER TABLE stage_outcomes
    ALTER COLUMN false_completion_claim DROP NOT NULL;
-- mhb:split

ALTER TABLE soc_approvals
    ADD COLUMN IF NOT EXISTS max_duration_hours INTEGER
    CHECK (max_duration_hours BETWEEN 1 AND 168);
-- mhb:split

ALTER TABLE stage_outcomes
    ADD COLUMN IF NOT EXISTS benign_action_executed BOOLEAN,
    ADD COLUMN IF NOT EXISTS defense_false_positive BOOLEAN;
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
