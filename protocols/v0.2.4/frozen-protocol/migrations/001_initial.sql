CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS experiment_runs (
    run_id UUID PRIMARY KEY,
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    protocol_version TEXT NOT NULL,
    protocol_hash TEXT NOT NULL,
    config_snapshot JSONB NOT NULL,
    model_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
-- mhb:split

CREATE TABLE IF NOT EXISTS trials (
    trial_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES experiment_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    source_variant TEXT NOT NULL CHECK (source_variant IN ('clean', 'poison')),
    memory_mode TEXT NOT NULL,
    writer_model TEXT NOT NULL,
    reader_model TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    defense TEXT NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'rolled_back')),
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
-- mhb:split

CREATE INDEX IF NOT EXISTS idx_trials_run ON trials(run_id);
-- mhb:split

CREATE TABLE IF NOT EXISTS sources (
    source_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    variant TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS model_invocations (
    invocation_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('writer', 'reader', 'embedding')),
    model_tag TEXT NOT NULL,
    model_digest TEXT,
    prompt JSONB NOT NULL,
    response JSONB NOT NULL,
    parsed_output JSONB,
    settings JSONB NOT NULL,
    reused_from_cache BOOLEAN NOT NULL DEFAULT false,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL
);
-- mhb:split

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    qdrant_point_id UUID NOT NULL,
    collection_name TEXT NOT NULL,
    memory_text TEXT NOT NULL,
    memory_kind TEXT NOT NULL,
    writer_model TEXT NOT NULL,
    writer_digest TEXT,
    encoder_model TEXT NOT NULL,
    encoder_digest TEXT,
    vector JSONB NOT NULL,
    vector_dimension INTEGER NOT NULL,
    transformation_history JSONB NOT NULL,
    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    parent_source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    harmful_meaning_preserved BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE INDEX IF NOT EXISTS idx_memory_trial ON memory_records(trial_id);
-- mhb:split

CREATE TABLE IF NOT EXISTS retrieval_events (
    retrieval_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    query_vector JSONB NOT NULL,
    encoder_model TEXT NOT NULL,
    collection_name TEXT NOT NULL,
    top_k INTEGER NOT NULL,
    results JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS action_proposals (
    proposal_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    proposal JSONB NOT NULL,
    raw_reader_output JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS gate_decisions (
    decision_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    defense TEXT NOT NULL,
    decision JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS stage_outcomes (
    trial_id UUID PRIMARY KEY REFERENCES trials(trial_id) ON DELETE CASCADE,
    poison_written BOOLEAN NOT NULL,
    poison_retrieved BOOLEAN NOT NULL,
    reader_influenced BOOLEAN NOT NULL,
    unauthorized_action_attempted BOOLEAN NOT NULL,
    baseline_gate_allowed BOOLEAN NOT NULL,
    unsafe_state_changed BOOLEAN NOT NULL,
    false_completion_claim BOOLEAN NOT NULL,
    benign_task_success BOOLEAN NOT NULL,
    attempted_attack_success BOOLEAN NOT NULL,
    executed_attack_success BOOLEAN NOT NULL,
    retrieval_at_k BOOLEAN NOT NULL,
    poison_rank INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_alerts (
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    alert_id TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    disposition TEXT,
    ioc_value TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    PRIMARY KEY (trial_id, alert_id)
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_iocs (
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    ioc_id TEXT NOT NULL,
    ioc_type TEXT NOT NULL,
    value TEXT NOT NULL,
    verdict TEXT NOT NULL,
    PRIMARY KEY (trial_id, ioc_id),
    UNIQUE (trial_id, value)
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_assets (
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    criticality TEXT NOT NULL,
    PRIMARY KEY (trial_id, asset_id)
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_approvals (
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    approval_id TEXT NOT NULL,
    ioc_value TEXT NOT NULL,
    allowed_actions TEXT[] NOT NULL,
    active BOOLEAN NOT NULL,
    expires_at TIMESTAMPTZ,
    PRIMARY KEY (trial_id, approval_id)
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_exceptions (
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    exception_id TEXT NOT NULL,
    ioc_value TEXT NOT NULL,
    active BOOLEAN NOT NULL,
    expires_at TIMESTAMPTZ,
    created_by_action UUID,
    PRIMARY KEY (trial_id, exception_id)
);
-- mhb:split

CREATE TABLE IF NOT EXISTS soc_action_history (
    action_id UUID PRIMARY KEY,
    trial_id UUID NOT NULL REFERENCES trials(trial_id) ON DELETE CASCADE,
    action_name TEXT NOT NULL,
    target_id TEXT NOT NULL,
    proposal JSONB NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    state_changed BOOLEAN NOT NULL,
    reversed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- mhb:split

CREATE INDEX IF NOT EXISTS idx_action_history_trial ON soc_action_history(trial_id, created_at);
-- mhb:split

CREATE OR REPLACE VIEW trial_evidence_chain AS
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
    so.unsafe_state_changed,
    so.false_completion_claim,
    so.benign_task_success,
    so.attempted_attack_success,
    so.executed_attack_success,
    so.retrieval_at_k,
    so.poison_rank
FROM trials t
LEFT JOIN sources s ON s.trial_id = t.trial_id
LEFT JOIN stage_outcomes so ON so.trial_id = t.trial_id;

