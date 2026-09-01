from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(HERE))

from common import (
    EXPECTED_BASE_URL,
    PRESERVED_FAILED_PREDECESSORS,
    RUN_KIND,
    V03,
    dump_json,
    load_json,
    sha256_file,
)
from plan import MODEL_IDS, audit_plan, build_plan

sys.path.insert(0, str(V03 / 'src'))
from memory_handoff_bench.config import load_cases, load_config
from memory_handoff_bench.ollama import OllamaClient
from memory_handoff_bench.storage import Database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)

    deps = load_json(PKG / 'spec/v03-dependency-hashes.json')
    mismatches: dict[str, dict[str, str | None]] = {}
    for rel, expected in deps.items():
        path = V03 / rel
        actual = sha256_file(path) if path.exists() else None
        if actual != expected:
            mismatches[rel] = {'expected': expected, 'actual': actual}

    config = load_config(V03 / 'configs/counterfactual-v0.3.yaml')
    cases = load_cases(config).cases
    plan = audit_plan(build_plan([c.case_id for c in cases], config.primary_embedding.tag))

    api_key = os.getenv('OPENAI_API_KEY', '')
    base_url = os.getenv('OPENAI_BASE_URL', '').rstrip('/')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY missing')
    if base_url != EXPECTED_BASE_URL:
        raise RuntimeError(f'OPENAI_BASE_URL must equal {EXPECTED_BASE_URL}')

    # Catalog-only call: this does not invoke/bill a model.
    with httpx.Client(timeout=30) as client:
        response = client.get(
            base_url + '/models',
            headers={'Authorization': 'Bearer ' + api_key},
        )
        if response.status_code != 200:
            raise RuntimeError(f'Mantle /models HTTP {response.status_code}')
        payload = response.json()
        ids = {
            str(item.get('id'))
            for item in payload.get('data', [])
            if isinstance(item, dict) and item.get('id')
        }
    missing = sorted(set(MODEL_IDS) - ids)
    if missing:
        raise RuntimeError(f'Missing hosted models: {missing}')
    by_id = {
        str(item.get('id')): item
        for item in payload.get('data', [])
        if isinstance(item, dict) and item.get('id')
    }
    unavailable = {
        model: by_id[model].get('status')
        for model in MODEL_IDS
        if by_id[model].get('status') not in {None, 'available'}
    }
    if unavailable:
        raise RuntimeError(f'Hosted models not currently available: {unavailable}')

    with Database(config.database_url) as db:
        with db.pool.connection() as conn:
            current_runs = [
                dict(row)
                for row in conn.execute(
                    'SELECT run_id,label,status,protocol_hash,started_at FROM experiment_runs '
                    'WHERE run_kind=%s ORDER BY started_at',
                    (RUN_KIND,),
                ).fetchall()
            ]
            predecessor_rows_by_kind = {}
            for expected in PRESERVED_FAILED_PREDECESSORS:
                predecessor_rows_by_kind[expected['run_kind']] = [
                    dict(row)
                    for row in conn.execute(
                        'SELECT run_id,label,status,protocol_hash,started_at FROM experiment_runs '
                        'WHERE run_kind=%s ORDER BY started_at',
                        (expected['run_kind'],),
                    ).fetchall()
                ]
        health = db.health()
        migrations = sorted(db.applied_migrations())

    if current_runs:
        raise RuntimeError(f'One-shot {RUN_KIND} run already exists: {current_runs}')

    # v0.4.2 requires both earlier failed hosted runs to remain present and unchanged.
    # This prevents history rewriting through a restored pre-hosted database.
    preserved_predecessors = []
    for expected in PRESERVED_FAILED_PREDECESSORS:
        rows = predecessor_rows_by_kind[expected['run_kind']]
        if len(rows) != 1:
            raise RuntimeError(
                f"Expected exactly one preserved {expected['run_kind']} predecessor; "
                f"found {len(rows)}: {rows}"
            )
        row = rows[0]
        if str(row['run_id']) != expected['run_id']:
            raise RuntimeError(
                f"Unexpected predecessor run ID for {expected['run_kind']}: "
                f"{row['run_id']}; expected {expected['run_id']}"
            )
        if row['status'] != 'failed':
            raise RuntimeError(
                f"Predecessor {expected['run_kind']} must remain failed/preserved; "
                f"observed {row['status']}"
            )
        if row['protocol_hash'] != expected['protocol_hash']:
            raise RuntimeError(
                f"Predecessor protocol hash mismatch for {expected['run_kind']}"
            )
        preserved_predecessors.append({**row, 'failure_note': expected['failure']})

    if '004_protocol_v0_3.sql' not in migrations:
        raise RuntimeError('migration 004 missing')

    with OllamaClient(config.ollama_url, config.inference) as ollama:
        embedding = ollama.manifest([config.primary_embedding.tag])
    embedding_record = embedding['models'][config.primary_embedding.tag]
    if not embedding_record.get('installed'):
        raise RuntimeError('embeddinggemma unavailable')
    embedding_compact = {
        'ollama': embedding.get('ollama'),
        'models': {
            config.primary_embedding.tag: {
                key: embedding_record.get(key)
                for key in (
                    'installed', 'digest', 'size', 'modified_at', 'capabilities',
                    'details', 'parameters', 'template'
                )
                if key in embedding_record
            }
        },
    }

    with httpx.Client(timeout=30) as client:
        qr = client.get(config.qdrant_url.rstrip('/') + '/collections')
        qr.raise_for_status()
        qpayload = qr.json()
    result_obj = qpayload.get('result', {})
    names: list[str] = []
    if isinstance(result_obj, dict):
        names = [
            str(item.get('name'))
            for item in result_obj.get('collections', [])
            if isinstance(item, dict) and item.get('name')
        ]

    prior_failed_v04_collections = sorted(
        n for n in names if n.startswith('mhb_v04_hosted')
    )
    prior_failed_v041_collections = sorted(
        n for n in names if n.startswith('mhb_v041_hosted')
    )
    current_collections = sorted(
        n for n in names if n.startswith('mhb_v042_hosted')
    )
    if current_collections:
        raise RuntimeError(
            f'v0.4.2 Qdrant collection already exists before registered run: '
            f'{current_collections}'
        )

    result = {
        'passed': (
            not mismatches
            and plan['pairs'] == 384
            and plan['trials'] == 768
            and plan['unique_pair_keys'] == 384
            and len(preserved_predecessors) == len(PRESERVED_FAILED_PREDECESSORS)
            and not current_runs
            and not current_collections
        ),
        'v03_dependency_mismatches': mismatches,
        'plan': plan,
        'mantle_catalog_model_count': len(ids),
        'required_models_present': sorted(set(MODEL_IDS) & ids),
        'required_model_statuses': {model: by_id[model].get('status') for model in MODEL_IDS},
        'database_health': health,
        'migration_004_present': '004_protocol_v0_3.sql' in migrations,
        'prior_v042_runs': current_runs,
        'preserved_failed_predecessors': preserved_predecessors,
        'embedding_manifest': embedding_compact,
        'qdrant_collection_count': len(names),
        'preserved_failed_v04_collections': prior_failed_v04_collections,
        'preserved_failed_v041_collections': prior_failed_v041_collections,
        'preexisting_v042_collections': current_collections,
        'billable_model_calls_made': 0,
        'provider_response_format_preflight_call_made': False,
    }
    dump_json(output, result)
    if not result['passed']:
        raise RuntimeError('pre-run validation failed')

    print(json.dumps({
        'status': 'PASS_READY_FOR_ONE_SHOT_REGISTERED_HOSTED_V042_RUN',
        'pairs': 384,
        'trials': 768,
        'billable_model_calls_made': 0,
        'design_fingerprint': plan['fingerprint'],
        'preserved_failed_run_ids': [x['run_id'] for x in PRESERVED_FAILED_PREDECESSORS],
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
