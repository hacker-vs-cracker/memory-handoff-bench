from __future__ import annotations

from typing import Any

ADD_TEMPORARY_EXCEPTION = 'add_temporary_exception'


def requested_duration_hours(action: str, duration_hours: int | None) -> int | None:
    """Preserve frozen semantics; only the SQL placeholder typing is corrected."""
    if action == ADD_TEMPORARY_EXCEPTION:
        return duration_hours or 24
    return None


def approval_valid_typed(
    database: Any,
    trial_id: Any,
    approval_id: str,
    ioc_value: str,
    action: str,
    duration_hours: int | None = None,
) -> bool:
    requested = requested_duration_hours(action, duration_hours)
    with database.pool.connection() as conn:
        row = conn.execute(
            '''SELECT 1 FROM soc_approvals
               WHERE trial_id=%s AND approval_id=%s AND ioc_value=%s AND active=true
                 AND (expires_at IS NULL OR expires_at > now())
                 AND %s = ANY(allowed_actions)
                 AND (
                     max_duration_hours IS NULL
                     OR %s::integer IS NULL
                     OR %s::integer <= max_duration_hours
                 )''',
            (trial_id, approval_id, ioc_value, action, requested, requested),
        ).fetchone()
    return row is not None


def build_database_class(base_database: type) -> type:
    """Build the v0.4.2 DB adapter without modifying frozen v0.3 source."""

    class HostedV04Database(base_database):
        def approval_valid(self, trial_id, approval_id, ioc_value, action, duration_hours=None):
            return approval_valid_typed(
                self, trial_id, approval_id, ioc_value, action, duration_hours
            )

        def record_invocation(self, trial_id, **kwargs):
            # ExperimentRunner records the frozen InferenceConfig. For hosted chat,
            # seed=42 is a DESIGN/order/cache seed and `think=False` is not sent as a
            # provider control. Annotate this explicitly so the persisted evidence
            # cannot be misread as provider-level deterministic seed/thinking control.
            settings = dict(kwargs.get('settings') or {})
            if kwargs.get('role') in {'writer', 'reader'}:
                settings['provider_seed_sent'] = False
                settings['provider_thinking_control_sent'] = False
                settings['seed_semantics'] = 'design_pair_order_and_writer_cache_only'
                settings['provider_endpoint'] = 'bedrock-mantle'
            kwargs['settings'] = settings
            return super().record_invocation(trial_id, **kwargs)

    HostedV04Database.__name__ = 'HostedV04Database'
    return HostedV04Database
