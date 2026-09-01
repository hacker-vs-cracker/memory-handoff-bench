SELECT
    t.run_id,
    t.case_id,
    t.memory_mode,
    t.writer_model,
    t.reader_model,
    t.defense,
    mi.role AS failure_stage,
    count(*) AS structured_output_failures,
    sum(COALESCE((mi.response->>'structured_retry_count')::integer, 0)) AS retries,
    min(
        jsonb_array_length(COALESCE(mi.response->'invalid_attempts', '[]'::jsonb)) + 1
    ) AS minimum_attempts_preserved,
    max(
        jsonb_array_length(COALESCE(mi.response->'invalid_attempts', '[]'::jsonb)) + 1
    ) AS maximum_attempts_preserved,
    count(*) FILTER (
        WHERE mi.response->'final_response'->>'done' = 'false'
    ) AS final_responses_with_done_false
FROM trials t
JOIN model_invocations mi ON mi.trial_id = t.trial_id
WHERE t.run_id = :'run_id'::uuid
  AND t.status = 'structured_output_failed'
  AND mi.role IN ('writer', 'reader')
  AND mi.parsed_output IS NULL
  AND COALESCE((mi.response->>'structured_output_failed')::boolean, false)
GROUP BY
    t.run_id,
    t.case_id,
    t.memory_mode,
    t.writer_model,
    t.reader_model,
    t.defense,
    mi.role
ORDER BY
    t.case_id,
    t.memory_mode,
    t.writer_model,
    t.reader_model,
    t.defense,
    mi.role;
