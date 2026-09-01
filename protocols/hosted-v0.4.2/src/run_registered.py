from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(HERE))

from common import (EXPECTED_BASE_URL, PRESERVED_FAILED_PREDECESSORS, RUN_KIND, V03, dump_json, load_json, sha256_file)
from hosted_db import build_database_class
from mantle_client import BudgetExceeded, FatalProviderError, HostedHybridClient, Price, ProviderError
from plan import DEFENSES, MODEL_IDS, audit_plan, build_plan, design_fingerprint

sys.path.insert(0, str(V03 / 'src'))
from memory_handoff_bench.config import AppConfig, BenchmarkConfig, InferenceConfig, ModelSpec, load_cases, load_config
from memory_handoff_bench.domain import DefenseCondition, MemoryMode, SourceVariant
from memory_handoff_bench.experiment import ExperimentRunner
from memory_handoff_bench.ollama import OllamaClient, StructuredOutputError
from memory_handoff_bench.storage import Database
from memory_handoff_bench.vector_store import VectorStore

HostedV042Database = build_database_class(Database)


def package_protocol_hash() -> str:
    return sha256_file(PKG / 'protocol_lock.json')


def selected_catalog(base_url: str, api_key: str) -> dict[str, Any]:
    """Non-billed model-catalog check immediately before creating the run."""
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            base_url.rstrip('/') + '/models',
            headers={'Authorization': 'Bearer ' + api_key},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f'Mantle /models failed before registered run: HTTP {response.status_code}'
            )
        payload = response.json()
    rows = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError('Mantle /models response missing data list')
    by_id = {
        str(item.get('id')): item
        for item in rows
        if isinstance(item, dict) and item.get('id')
    }
    missing = [model for model in MODEL_IDS if model not in by_id]
    if missing:
        raise RuntimeError(f'Required hosted models missing from Mantle catalog: {missing}')
    unavailable = {
        model: by_id[model].get('status')
        for model in MODEL_IDS
        if by_id[model].get('status') not in {None, 'available'}
    }
    if unavailable:
        raise RuntimeError(f'Required hosted models are not available: {unavailable}')
    return {
        'catalog_model_count': len(rows),
        'selected_models': {model: by_id[model] for model in MODEL_IDS},
    }


def build_v042_config() -> AppConfig:
    base = load_config(V03 / 'configs/counterfactual-v0.3.yaml')
    primary = [
        ModelSpec(tag=model, family=model.split('.')[0], role='primary')
        for model in MODEL_IDS
    ]
    benchmark = BenchmarkConfig(
        name='memory-handoff-bench-hosted-external-validity',
        protocol_version='0.4.2-hosted',
        case_file=V03 / 'cases/pilot.yaml',
        top_k=5,
        retrieval_distractors=8,
        collection_prefix='mhb_v042_hosted',
        sequential=True,
    )
    inference = InferenceConfig(
        num_ctx=8192,
        temperature=0.0,
        seed=42,
        keep_alive='5m',
        timeout_seconds=300.0,
        structured_retries=2,
        think=False,
    )
    return AppConfig(
        benchmark=benchmark,
        inference=inference,
        primary_models=primary,
        supplementary_models=[],
        embedding_models=base.embedding_models,
        capabilities=base.capabilities,
        counterfactual=None,
        database_url=base.database_url,
        qdrant_url=base.qdrant_url,
        ollama_url=base.ollama_url,
        root=PKG,
    )


def prices() -> dict[str, Price]:
    raw = load_json(PKG / 'spec/pricing_snapshot.json')['prices']
    return {
        model: Price(float(values['input']), float(values['output']))
        for model, values in raw.items()
    }


def progress_line(
    done: int,
    total: int,
    label: str,
    started: float,
    budget: dict[str, Any],
) -> str:
    elapsed = time.monotonic() - started
    rate = done / elapsed if elapsed > 0 else 0.0
    eta = (total - done) / rate if rate > 0 else 0.0
    width = 28
    filled = int(width * done / total)
    bar = '#' * filled + '-' * (width - filled)
    return (
        f'[{bar}] {done}/{total} {done / total * 100:5.1f}% '
        f'elapsed={elapsed / 60:6.1f}m eta={eta / 60:6.1f}m '
        f'cost=${budget["estimated_cost_usd"]:.4f} {label}'
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()

    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv('OPENAI_API_KEY', '')
    base_url = os.getenv('OPENAI_BASE_URL', '').rstrip('/')
    if not api_key:
        raise SystemExit('OPENAI_API_KEY is required')
    if base_url != EXPECTED_BASE_URL:
        raise SystemExit(f'OPENAI_BASE_URL must be exactly {EXPECTED_BASE_URL}')

    config = build_v042_config()
    cases = load_cases(config).cases
    case_by_id = {case.case_id: case for case in cases}
    case_ids = [case.case_id for case in cases]
    embedding_model = config.primary_embedding.tag
    specs = build_plan(case_ids, embedding_model)
    plan_audit = audit_plan(specs)
    if not (
        plan_audit['pairs'] == 384
        and plan_audit['trials'] == 768
        and plan_audit['unique_pair_keys'] == 384
        and plan_audit['pairs_by_defense'] == {'D0': 192, 'D4': 192}
    ):
        raise RuntimeError(f'registered plan integrity failure: {plan_audit}')

    # This endpoint is catalog-only and does not invoke a model.
    catalog = selected_catalog(base_url, api_key)
    dump_json(evidence / 'mantle-selected-model-catalog.json', catalog)

    protocol_hash = package_protocol_hash()
    telemetry = evidence / 'mantle-telemetry.ndjson'
    if telemetry.exists():
        raise RuntimeError('telemetry file already exists; refuse to mix executions')

    with HostedV042Database(config.database_url) as database:
        with database.pool.connection() as conn:
            prior = conn.execute(
                '''SELECT run_id,label,status,started_at
                   FROM experiment_runs
                   WHERE run_kind=%s
                   ORDER BY started_at''',
                (RUN_KIND,),
            ).fetchall()
        if prior:
            raise RuntimeError(
                f'{RUN_KIND} already exists; one-shot registered run will not repeat: {prior}'
            )
        preserved_predecessors = []
        with database.pool.connection() as conn:
            for expected in PRESERVED_FAILED_PREDECESSORS:
                rows = conn.execute(
                    '''SELECT run_id,status,protocol_hash FROM experiment_runs
                       WHERE run_kind=%s ORDER BY started_at''',
                    (expected['run_kind'],),
                ).fetchall()
                if len(rows) != 1:
                    raise RuntimeError(
                        f"Expected exactly one preserved {expected['run_kind']} run; got {rows}"
                    )
                row = rows[0]
                if (
                    str(row['run_id']) != expected['run_id']
                    or row['status'] != 'failed'
                    or row['protocol_hash'] != expected['protocol_hash']
                ):
                    raise RuntimeError(
                        f"Preserved predecessor mismatch for {expected['run_kind']}: {dict(row)}"
                    )
                preserved_predecessors.append({**dict(row), 'failure_note': expected['failure']})
        if '004_protocol_v0_3.sql' not in database.applied_migrations():
            raise RuntimeError('migration 004_protocol_v0_3.sql is required')

        with OllamaClient(config.ollama_url, config.inference) as local_ollama:
            embed_manifest = local_ollama.manifest([embedding_model])
            embedding_record = embed_manifest.get('models', {}).get(embedding_model, {})
            if not embedding_record.get('installed'):
                raise RuntimeError(f'local embedding model unavailable: {embedding_model}')
            # Ollama's model_info can be multi-megabyte tensor metadata. Preserve the
            # reproducibility-relevant identity/capability fields without duplicating
            # that large payload into the run row and upload evidence.
            embedding_record_compact = {
                key: embedding_record.get(key)
                for key in (
                    'installed', 'digest', 'size', 'modified_at', 'capabilities',
                    'details', 'parameters', 'template'
                )
                if key in embedding_record
            }
            embed_manifest_compact = {
                'ollama': embed_manifest.get('ollama'),
                'models': {embedding_model: embedding_record_compact},
            }

            model_manifest: dict[str, Any] = {
                'provider': 'Amazon Bedrock',
                'endpoint': 'bedrock-mantle',
                'region': 'us-east-1',
                'provider_seed_sent': False,
                'provider_thinking_control_sent': False,
                'models': {
                    model: {
                        'installed': True,
                        'digest': None,
                        'provider_model_id': model,
                        'catalog': catalog['selected_models'][model],
                    }
                    for model in MODEL_IDS
                },
                'embedding_provider': 'Ollama local',
                'embedding_model': embedding_model,
                'embedding_manifest': embed_manifest_compact,
            }
            # ExperimentRunner resolves embedding digest through this common map.
            model_manifest['models'][embedding_model] = embedding_record_compact

            snapshot = {
                'study': 'mhb-v0.4.2-hosted-external-validity',
                'package_version': '0.1',
                'protocol_revision': '0.4.2',
                'preserved_failed_predecessors': preserved_predecessors,
                'run_kind': RUN_KIND,
                'protocol_lock_sha256': protocol_hash,
                'v03_protocol_lock_sha256': sha256_file(V03 / 'protocol_lock.json'),
                'design_fingerprint': design_fingerprint(specs),
                'plan_audit': plan_audit,
                'expected_pairs': 384,
                'expected_trials': 768,
                'cases': case_ids,
                'writers': MODEL_IDS,
                'readers': MODEL_IDS,
                'defenses': DEFENSES,
                'variants': ['clean', 'poison'],
                'memory_mode': 'writer_generated',
                'embedding_model': embedding_model,
                'top_k': 5,
                'retrieval_distractors': 8,
                'temperature': 0.0,
                'design_seed': 42,
                'provider_seed_sent': False,
                'provider_thinking_control_sent': False,
                'provider_response_format_sent': False,
                'schema_contract_transmitted_as_text': True,
                'local_pydantic_validation': True,
                'repair_message_strategy': 'fresh_system_user_original_task_plus_repair',
                'max_completion_tokens': 2048,
                'structured_retries': 2,
                'transport_retries': 7,
                'approval_lookup': (
                    'study-local typed duration correction validated by d5_utility_v0.2'
                ),
                'qdrant_collection_prefix': 'mhb_v042_hosted',
                'cost_safety_cap_usd': 5.0,
                'cost_safety_reserve_usd': 0.10,
                'request_attempt_cap': 5000,
                'sequential': True,
                'smoke_run_performed': False,
                'registered_v04_reused': False,
            }
            dump_json(evidence / 'registered-config-snapshot.json', snapshot)
            dump_json(evidence / 'registered-model-manifest.json', model_manifest)

            run_id = database.create_run(
                args.label,
                '0.4.2-hosted',
                protocol_hash,
                snapshot,
                model_manifest,
                run_kind=RUN_KIND,
            )
            (evidence / 'registered-run-id.txt').write_text(
                str(run_id) + '\n', encoding='utf-8'
            )
            print(f'Run ID: {run_id}', flush=True)

            client = HostedHybridClient(
                base_url=base_url,
                api_key=api_key,
                inference=config.inference,
                local_ollama=local_ollama,
                prices=prices(),
                telemetry_path=telemetry,
                max_completion_tokens=2048,
                transport_retries=7,
                cost_cap_usd=5.0,
                cost_reserve_usd=0.10,
                request_attempt_cap=5000,
            )
            runner = ExperimentRunner(
                config,
                database,
                VectorStore(config.qdrant_url, config.benchmark.collection_prefix),
                client,
                model_manifest,
            )

            counters = {
                'pairs_attempted': 0,
                'trials_attempted': 0,
                'completed': 0,
                'structured_output_failed': 0,
                'infrastructure_failed': 0,
                'attempted_attacks': 0,
                'executed_attacks': 0,
            }
            started = time.monotonic()
            fatal_error: str | None = None

            try:
                for spec in specs:
                    counters['pairs_attempted'] += 1
                    case = case_by_id[spec['case_id']]
                    defense = DefenseCondition(spec['defense'])
                    for order_index, variant_name in enumerate(
                        spec['variant_order'], start=1
                    ):
                        counters['trials_attempted'] += 1
                        label = (
                            f"{case.case_id} {spec['writer_model']}→"
                            f"{spec['reader_model']} {defense.value} {variant_name}"
                        )
                        try:
                            result = runner.run_one(
                                run_id=run_id,
                                case=case,
                                writer_model=spec['writer_model'],
                                reader_model=spec['reader_model'],
                                source_variant=SourceVariant(variant_name),
                                memory_mode=MemoryMode.WRITER_GENERATED,
                                defense=defense,
                                embedding_model=embedding_model,
                                seed=42,
                                human_approved=False,
                                counterfactual_pair_key=spec['pair_key'],
                                counterfactual_order=order_index,
                            )
                        except StructuredOutputError as exc:
                            # Terminal model outcome. Keep in planned denominator and continue.
                            counters['structured_output_failed'] += 1
                            print(
                                'TERMINAL_STRUCTURED_OUTPUT_FAILURE:',
                                label,
                                str(exc)[:600],
                                flush=True,
                            )
                        except (BudgetExceeded, FatalProviderError, ProviderError) as exc:
                            # A provider failure after all transport retries would leave the
                            # one-shot design incomplete. Stop immediately rather than spend
                            # more on a run that cannot become a complete registered matrix.
                            counters['infrastructure_failed'] += 1
                            fatal_error = f'{type(exc).__name__}: {exc}'
                            print(
                                'FATAL_PROVIDER_OR_BUDGET_FAILURE:',
                                label,
                                fatal_error[:1200],
                                flush=True,
                            )
                            raise
                        except Exception as exc:
                            counters['infrastructure_failed'] += 1
                            fatal_error = f'{type(exc).__name__}: {exc}'
                            print(
                                'FATAL_PIPELINE_FAILURE:',
                                label,
                                fatal_error[:1200],
                                flush=True,
                            )
                            raise
                        else:
                            counters['completed'] += 1
                            counters['attempted_attacks'] += int(
                                result.stages.attempted_attack_success
                            )
                            counters['executed_attacks'] += int(
                                result.stages.executed_attack_success
                            )

                        done = counters['trials_attempted']
                        if done == 1 or done % 10 == 0 or done == 768:
                            print(
                                progress_line(
                                    done,
                                    768,
                                    label,
                                    started,
                                    client.tracker.snapshot(),
                                ),
                                flush=True,
                            )

            except Exception:
                try:
                    database.finish_run(run_id, 'failed')
                finally:
                    dump_json(
                        evidence / 'registered-run-summary.json',
                        {
                            **counters,
                            'run_id': str(run_id),
                            'status': 'failed',
                            'fatal_error': fatal_error,
                            'elapsed_seconds': round(time.monotonic() - started, 3),
                            'budget': client.tracker.snapshot(),
                            'completed_at_utc': datetime.now(UTC).isoformat(),
                        },
                    )
                raise
            else:
                status = (
                    'completed'
                    if counters['infrastructure_failed'] == 0
                    and counters['trials_attempted'] == 768
                    else 'failed'
                )
                database.finish_run(run_id, status)
                dump_json(
                    evidence / 'registered-run-summary.json',
                    {
                        **counters,
                        'run_id': str(run_id),
                        'status': status,
                        'elapsed_seconds': round(time.monotonic() - started, 3),
                        'budget': client.tracker.snapshot(),
                        'completed_at_utc': datetime.now(UTC).isoformat(),
                    },
                )
                if status != 'completed':
                    raise RuntimeError(
                        'registered hosted matrix ended with infrastructure failures'
                    )
            finally:
                client.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
