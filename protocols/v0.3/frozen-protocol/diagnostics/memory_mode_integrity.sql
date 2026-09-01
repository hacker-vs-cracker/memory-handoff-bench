WITH source_memories AS (
    SELECT
        t.run_id,
        t.trial_id,
        t.memory_mode,
        mr.memory_id,
        mr.transformation_history,
        mr.harmful_meaning_preserved
    FROM trials t
    JOIN memory_records mr ON mr.trial_id = t.trial_id
    WHERE t.run_id = :'run_id'::uuid
      AND mr.source_authority = 'untrusted_external'
)
SELECT
    run_id,
    memory_mode,
    count(DISTINCT trial_id) AS trials_with_source_memory,
    count(memory_id) AS source_memory_records,
    count(*) FILTER (
        WHERE COALESCE((transformation_history->>'writer_bypassed')::boolean, false)
    ) AS writer_bypassed_records,
    count(*) FILTER (
        WHERE NOT COALESCE((transformation_history->>'writer_bypassed')::boolean, false)
    ) AS writer_generated_records,
    count(*) FILTER (
        WHERE COALESCE((transformation_history->>'writer_output_reused')::boolean, false)
    ) AS reused_writer_output_records,
    count(*) FILTER (WHERE harmful_meaning_preserved) AS harmful_records
FROM source_memories
GROUP BY run_id, memory_mode
ORDER BY memory_mode;
