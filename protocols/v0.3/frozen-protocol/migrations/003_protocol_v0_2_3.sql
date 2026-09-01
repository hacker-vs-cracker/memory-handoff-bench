ALTER TABLE trials
    DROP CONSTRAINT IF EXISTS trials_status_check;
-- mhb:split

ALTER TABLE trials
    ADD CONSTRAINT trials_status_check
    CHECK (
        status IN (
            'running',
            'completed',
            'structured_output_failed',
            'failed',
            'rolled_back'
        )
    );
