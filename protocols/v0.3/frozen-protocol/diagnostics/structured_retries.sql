SELECT
    t.run_id,
    t.memory_mode,
    mi.role,
    mi.model_tag,
    count(*) AS invocation_records,
    count(*) FILTER (WHERE NOT mi.reused_from_cache) AS fresh_records,
    count(*) FILTER (WHERE mi.reused_from_cache) AS cache_reuses,
    count(*) FILTER (
        WHERE NOT mi.reused_from_cache
          AND mi.parsed_output IS NOT NULL
          AND mi.response ? 'invalid_attempts'
    ) AS fresh_repaired_records,
    sum(
        CASE WHEN NOT mi.reused_from_cache
             THEN COALESCE((mi.response->>'structured_retry_count')::integer, 0)
             ELSE 0
        END
    ) AS fresh_retry_attempts,
    count(*) FILTER (
        WHERE NOT mi.reused_from_cache
          AND mi.parsed_output IS NULL
          AND COALESCE((mi.response->>'structured_output_failed')::boolean, false)
    ) AS fresh_failed_structured_records,
    count(*) FILTER (
        WHERE mi.reused_from_cache
          AND mi.response ? 'invalid_attempts'
    ) AS cached_records_carrying_repair_evidence
FROM trials t
JOIN model_invocations mi ON mi.trial_id = t.trial_id
WHERE t.run_id = :'run_id'::uuid
  AND mi.role IN ('writer', 'reader')
GROUP BY t.run_id, t.memory_mode, mi.role, mi.model_tag
ORDER BY t.memory_mode, mi.role, mi.model_tag;
