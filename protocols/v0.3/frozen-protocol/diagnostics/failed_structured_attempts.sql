SELECT COALESCE(
    jsonb_pretty(
        jsonb_agg(
            jsonb_build_object(
                'run_id', t.run_id,
                'case_id', t.case_id,
                'trial_id', t.trial_id,
                'memory_mode', t.memory_mode,
                'trial_error', t.error,
                'writer_model', t.writer_model,
                'reader_model', t.reader_model,
                'failure_stage', mi.role,
                'model_tag', mi.model_tag,
                'invocation_settings', mi.settings,
                'structured_response', mi.response
            )
            ORDER BY t.case_id, t.memory_mode, t.writer_model, t.reader_model, mi.role
        )
    ),
    '[]'
)
FROM trials t
JOIN model_invocations mi ON mi.trial_id = t.trial_id
WHERE t.run_id = :'run_id'::uuid
  AND t.status = 'structured_output_failed'
  AND mi.role IN ('writer', 'reader')
  AND mi.parsed_output IS NULL
  AND COALESCE((mi.response->>'structured_output_failed')::boolean, false);
