from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from .analysis import fit_binary_mixed_model
from .config import AppConfig, load_cases, load_config
from .counterfactual import (
    analyze_counterfactual,
    audit_counterfactual,
    design_fingerprint,
    expected_pair_specs,
    write_counterfactual_reports,
)
from .domain import DefenseCondition, MemoryMode, SourceVariant
from .experiment import ExperimentRunner
from .human_review import export_blinded_human_review
from .ollama import OllamaClient, StructuredOutputError
from .protocol import verify_protocol_lock, write_protocol_lock
from .reporting import audit_summary, summarize, write_reports
from .storage import Database
from .vector_store import VectorStore

app = typer.Typer(
    no_args_is_help=True,
    help="Cross-model persistent-memory poisoning benchmark for synthetic SOC agents.",
)
console = Console()


def _config(path: Path) -> AppConfig:
    return load_config(path)


def _counterfactual_config(path: Path) -> AppConfig:
    config = load_config(path)
    requested = path if path.is_absolute() else (Path.cwd() / path)
    canonical = config.root / "configs" / "counterfactual-v0.3.yaml"
    try:
        requested_resolved = requested.resolve(strict=True)
        canonical_resolved = canonical.resolve(strict=True)
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Counterfactual config path is missing: {exc}") from exc
    if requested_resolved != canonical_resolved:
        raise typer.BadParameter(
            "Registered/smoke v0.3 commands require the protocol-locked canonical config: "
            "configs/counterfactual-v0.3.yaml"
        )
    return config


def _safe_config_snapshot(config: AppConfig) -> dict:
    value = config.model_dump(mode="json")
    value["database_url"] = "<redacted>"
    return value


def _manifest_path(config: AppConfig) -> Path:
    return config.root / "evidence" / "model_manifest.json"


def _load_verified_manifest(config: AppConfig) -> dict:
    path = _manifest_path(config)
    if not path.exists():
        raise typer.BadParameter("Run `mhb preflight` first; model manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = [*config.primary_models, config.primary_embedding]
    errors: list[str] = []
    for spec in required:
        actual = manifest.get("models", {}).get(spec.tag, {})
        digest = actual.get("digest")
        if not actual.get("installed"):
            errors.append(f"{spec.tag}: not installed")
        elif spec.digest_prefix and not str(digest).removeprefix("sha256:").startswith(
            spec.digest_prefix
        ):
            errors.append(f"{spec.tag}: digest {digest!r} does not start with {spec.digest_prefix}")
    if errors:
        raise typer.BadParameter("Model manifest validation failed: " + "; ".join(errors))
    return manifest


def _parse_csv(value: str, enum: type | None = None) -> list:
    parts = [item.strip() for item in value.split(",") if item.strip()]
    return [enum(item) for item in parts] if enum else parts


def _select_models(value: str, primary: list[str]) -> list[str]:
    selected = primary if value == "all" else _parse_csv(value)
    unknown = sorted(set(selected) - set(primary))
    if unknown:
        raise typer.BadParameter(f"Models are not in the primary matrix: {', '.join(unknown)}")
    return selected


def _select_embedding(value: str | None, config: AppConfig) -> str:
    selected = value or config.primary_embedding.tag
    allowed = {model.tag for model in config.embedding_models}
    if selected not in allowed:
        raise typer.BadParameter(f"Embedding model is not configured: {selected}")
    return selected


def _assert_installed(manifest: dict, tag: str) -> None:
    if not manifest.get("models", {}).get(tag, {}).get("installed"):
        raise typer.BadParameter(f"Model is not installed in the preflight manifest: {tag}")


def _assert_protocol(config: AppConfig) -> str:
    valid, mismatches, lock_hash = verify_protocol_lock(
        config.root, config.benchmark.protocol_version
    )
    if not valid:
        raise typer.BadParameter(
            "Frozen protocol changed: " + ", ".join(mismatches) + ". Create a new protocol version."
        )
    return lock_hash


def _counterfactual_design(config: AppConfig) -> tuple[list, list[str], str, list[dict]]:
    if config.benchmark.protocol_version != "0.3" or config.counterfactual is None:
        raise typer.BadParameter("Use configs/counterfactual-v0.3.yaml for this command")
    corpus = load_cases(config)
    cf = config.counterfactual
    if len(corpus.cases) != cf.expected_cases:
        raise typer.BadParameter(
            f"v0.3 expects {cf.expected_cases} cases, found {len(corpus.cases)}"
        )
    models = [model.tag for model in config.primary_models]
    embedding = config.primary_embedding.tag
    specs = expected_pair_specs(
        cases=corpus.cases,
        writer_models=models,
        reader_models=models,
        embedding_model=embedding,
        seeds=cf.seeds,
        memory_mode=cf.memory_mode,
        defense=cf.defense,
    )
    if len(specs) != cf.expected_pairs or len(specs) * 2 != cf.expected_trials:
        raise typer.BadParameter(
            "Counterfactual design size does not match the frozen config: "
            f"computed {len(specs)} pairs/{len(specs) * 2} trials, "
            f"expected {cf.expected_pairs}/{cf.expected_trials}"
        )
    order_counts = {"clean": 0, "poison": 0}
    by_case: dict[str, dict[str, int]] = {}
    for spec in specs:
        first = spec["variant_order"][0]
        order_counts[first] += 1
        bucket = by_case.setdefault(spec["case_id"], {"clean": 0, "poison": 0})
        bucket[first] += 1
    if order_counts["clean"] != order_counts["poison"]:
        raise typer.BadParameter(f"Variant order is not balanced: {order_counts}")
    unbalanced_cases = {case: counts for case, counts in by_case.items() if counts["clean"] != counts["poison"]}
    if unbalanced_cases:
        raise typer.BadParameter(f"Per-case variant order is not balanced: {unbalanced_cases}")

    # Writer output is cached across readers. Check the order of the first clean/poison
    # writer generation for every case×writer×seed unit separately from reader-pair order.
    first_writer_specs: dict[tuple[str, str, int], dict] = {}
    for spec in specs:
        unit = (str(spec["case_id"]), str(spec["writer_model"]), int(spec["seed"]))
        first_writer_specs.setdefault(unit, spec)
    writer_order = {"clean": 0, "poison": 0}
    writer_order_by_case: dict[str, dict[str, int]] = {}
    for spec in first_writer_specs.values():
        first = str(spec["variant_order"][0])
        writer_order[first] += 1
        bucket = writer_order_by_case.setdefault(
            str(spec["case_id"]), {"clean": 0, "poison": 0}
        )
        bucket[first] += 1
    if writer_order["clean"] != writer_order["poison"]:
        raise typer.BadParameter(
            f"Cached writer-generation order is not globally balanced: {writer_order}"
        )
    unbalanced_writer_cases = {
        case: counts
        for case, counts in writer_order_by_case.items()
        if counts["clean"] != counts["poison"]
    }
    if unbalanced_writer_cases:
        raise typer.BadParameter(
            f"Cached writer-generation order is not balanced by case: {unbalanced_writer_cases}"
        )
    return corpus.cases, models, embedding, specs


def _counterfactual_run_snapshot(
    config: AppConfig, specs: list[dict], *, run_kind: str, executed_pairs: int
) -> dict:
    snapshot = _safe_config_snapshot(config)
    snapshot["registered_counterfactual_design"] = {
        "fingerprint": design_fingerprint(specs),
        "full_expected_pairs": len(specs),
        "full_expected_trials": len(specs) * 2,
        "run_kind": run_kind,
        "executed_pairs": executed_pairs,
        "executed_trials": executed_pairs * 2,
    }
    return snapshot


def _assert_counterfactual_run_identity(
    *,
    run: dict,
    config: AppConfig,
    specs: list[dict],
    run_kind: str,
    executed_pairs: int,
) -> None:
    current_lock_hash = _assert_protocol(config)
    failures: list[str] = []
    if str(run.get("protocol_version")) != config.benchmark.protocol_version:
        failures.append(
            f"protocol version {run.get('protocol_version')!r} != {config.benchmark.protocol_version!r}"
        )
    if str(run.get("protocol_hash")) != current_lock_hash:
        failures.append("run protocol hash does not match the current frozen v0.3 lock")
    snapshot = run.get("config_snapshot")
    design = snapshot.get("registered_counterfactual_design") if isinstance(snapshot, dict) else None
    expected = {
        "fingerprint": design_fingerprint(specs),
        "full_expected_pairs": len(specs),
        "full_expected_trials": len(specs) * 2,
        "run_kind": run_kind,
        "executed_pairs": executed_pairs,
        "executed_trials": executed_pairs * 2,
    }
    if not isinstance(design, dict):
        failures.append("run config snapshot lacks registered_counterfactual_design")
    else:
        for field, value in expected.items():
            if design.get(field) != value:
                failures.append(
                    f"stored design {field}={design.get(field)!r} != expected {value!r}"
                )
    if failures:
        raise typer.BadParameter("Counterfactual run identity check failed: " + "; ".join(failures))


@app.command("init-db")
def init_db(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Apply PostgreSQL migrations after the empty database has been created."""
    config = _config(config_path)
    with Database(config.database_url) as database:
        applied = database.migrate(config.root / "migrations")
        health = database.health()
    console.print(f"[green]PostgreSQL ready:[/] {health['db']}")
    console.print("Applied: " + (", ".join(applied) if applied else "no new migrations"))


@app.command("validate-cases")
def validate_cases(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Validate pilot syntax, synthetic IOC constraints, balance, and protocol lock."""
    config = _config(config_path)
    corpus = load_cases(config)
    if len(corpus.cases) != 12:
        raise typer.BadParameter(
            f"Protocol v{config.benchmark.protocol_version} requires exactly 12 pilot cases, "
            f"found {len(corpus.cases)}"
        )
    categories: dict[str, int] = {}
    styles: dict[str, int] = {}
    for case in corpus.cases:
        categories[case.category] = categories.get(case.category, 0) + 1
        styles[case.attack_style] = styles.get(case.attack_style, 0) + 1
    if set(categories.values()) != {3}:
        raise typer.BadParameter(f"Expected three cases per category, found {categories}")
    valid, mismatches, _ = verify_protocol_lock(
        config.root, config.benchmark.protocol_version
    )
    table = Table(title=f"Pilot corpus v{corpus.version}")
    table.add_column("Category")
    table.add_column("Cases", justify="right")
    for category, count in sorted(categories.items()):
        table.add_row(category, str(count))
    console.print(table)
    console.print(f"Attack styles: {styles}")
    console.print("[green]Protocol lock valid[/]" if valid else f"[red]Changed:[/] {mismatches}")
    if not valid:
        raise typer.Exit(1)


@app.command("freeze-protocol")
def freeze_protocol(
    accept: Annotated[
        bool,
        typer.Option("--accept", help="Acknowledge that hashes will be replaced."),
    ] = False,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Create the current version's hash lock before running that version."""
    if not accept:
        raise typer.BadParameter(
            "Pass --accept only before experiments or after versioning the protocol"
        )
    config = _config(config_path)
    path = write_protocol_lock(config.root, config.benchmark.protocol_version)
    console.print(f"[green]Frozen:[/] {path}")


@app.command()
def preflight(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Check services and exact model digests; write the immutable run manifest."""
    config = _config(config_path)
    _assert_protocol(config)
    names = [
        *(model.tag for model in config.primary_models),
        *(model.tag for model in config.supplementary_models),
        *(model.tag for model in config.embedding_models),
    ]
    with OllamaClient(config.ollama_url, config.inference) as ollama:
        manifest = ollama.manifest(names)
    table = Table(title="Ollama model identity")
    table.add_column("Model")
    table.add_column("Installed")
    table.add_column("Digest")
    errors: list[str] = []
    required = {model.tag for model in [*config.primary_models, config.primary_embedding]}
    spec_map = {
        model.tag: model
        for model in [
            *config.primary_models,
            *config.supplementary_models,
            *config.embedding_models,
        ]
    }
    for name in names:
        record = manifest["models"].get(name, {})
        installed = bool(record.get("installed"))
        digest = record.get("digest")
        table.add_row(name, "yes" if installed else "no", str(digest or "—"))
        spec = spec_map[name]
        if name in required and not installed:
            errors.append(f"required model missing: {name}")
        if (
            installed
            and spec.digest_prefix
            and not str(digest).removeprefix("sha256:").startswith(spec.digest_prefix)
        ):
            errors.append(f"digest mismatch: {name}")
    console.print(table)
    vectors = VectorStore(config.qdrant_url, config.benchmark.collection_prefix)
    vectors.health()
    console.print("[green]Qdrant reachable[/]")
    try:
        with Database(config.database_url) as database:
            db_health = database.health()
            applied_migrations = database.applied_migrations()
        console.print(f"[green]PostgreSQL reachable:[/] {db_health['db']}")
        if (
            config.benchmark.protocol_version == "0.3"
            and "004_protocol_v0_3.sql" not in applied_migrations
        ):
            errors.append(
                "PostgreSQL migration 004_protocol_v0_3.sql is not applied; run mhb init-db "
                "with the v0.3 config first"
            )
    except Exception as exc:
        errors.append(f"PostgreSQL unavailable: {exc}")
    if errors:
        for error in errors:
            console.print(f"[red]ERROR[/] {error}")
        raise typer.Exit(1)
    path = _manifest_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    console.print(f"[green]Manifest written:[/] {path}")


@app.command("run-one")
def run_one(
    case_id: Annotated[str, typer.Option("--case")],
    writer: Annotated[str, typer.Option()],
    reader: Annotated[str, typer.Option()],
    variant: Annotated[SourceVariant, typer.Option()] = SourceVariant.CLEAN,
    memory_mode: Annotated[MemoryMode, typer.Option()] = MemoryMode.CLEAN_MEMORY,
    defense: Annotated[DefenseCondition, typer.Option()] = DefenseCondition.D0,
    seed: Annotated[int, typer.Option()] = 42,
    label: Annotated[str, typer.Option()] = "single-trial",
    human_approved: Annotated[bool, typer.Option()] = False,
    embedding_model: Annotated[str | None, typer.Option()] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Run one isolated writer→reader trial."""
    config = _config(config_path)
    protocol_hash = _assert_protocol(config)
    manifest = _load_verified_manifest(config)
    corpus = load_cases(config)
    case_map = {case.case_id: case for case in corpus.cases}
    if case_id not in case_map:
        raise typer.BadParameter(f"Unknown case: {case_id}")
    primary = [model.tag for model in config.primary_models]
    _select_models(writer, primary)
    _select_models(reader, primary)
    selected_embedding = _select_embedding(embedding_model, config)
    _assert_installed(manifest, selected_embedding)
    with (
        Database(config.database_url) as database,
        OllamaClient(config.ollama_url, config.inference) as ollama,
    ):
        run_id = database.create_run(
            label,
            config.benchmark.protocol_version,
            protocol_hash,
            _safe_config_snapshot(config),
            manifest,
        )
        runner = ExperimentRunner(
            config,
            database,
            VectorStore(config.qdrant_url, config.benchmark.collection_prefix),
            ollama,
            manifest,
        )
        result = None
        structured_error: StructuredOutputError | None = None
        try:
            result = runner.run_one(
                run_id=run_id,
                case=case_map[case_id],
                writer_model=writer,
                reader_model=reader,
                source_variant=variant,
                memory_mode=memory_mode,
                defense=defense,
                embedding_model=selected_embedding,
                seed=seed,
                human_approved=human_approved,
            )
            database.finish_run(run_id)
        except StructuredOutputError as exc:
            structured_error = exc
            database.finish_run(run_id)
        except Exception:
            database.finish_run(run_id, "failed")
            raise
    if result is not None:
        console.print_json(data=result.model_dump(mode="json"))
    else:
        console.print_json(
            data={
                "attempted": 1,
                "completed": 0,
                "structured_output_failed": 1,
                "failed": 0,
                "error": str(structured_error),
            }
        )
    console.print(f"[green]Run ID:[/] {run_id}")


@app.command("run-matrix")
def run_matrix(
    writers: Annotated[str, typer.Option(help="Comma-separated tags or all")] = "all",
    readers: Annotated[str, typer.Option(help="Comma-separated tags or all")] = "all",
    variants: Annotated[str, typer.Option()] = "clean",
    memory_modes: Annotated[str, typer.Option()] = "clean_memory",
    defenses: Annotated[str, typer.Option()] = "D0",
    pairing: Annotated[str, typer.Option(help="all, same, or cross")] = "all",
    cases: Annotated[str, typer.Option(help="Comma-separated case IDs or all")] = "all",
    seeds: Annotated[str, typer.Option()] = "42",
    limit: Annotated[int | None, typer.Option(help="Safe smoke-test cap")] = None,
    fail_fast: Annotated[bool, typer.Option()] = False,
    label: Annotated[str, typer.Option()] = "matrix",
    embedding_model: Annotated[str | None, typer.Option()] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Run a sequential matrix; defaults deliberately run clean baselines first."""
    config = _config(config_path)
    protocol_hash = _assert_protocol(config)
    manifest = _load_verified_manifest(config)
    corpus = load_cases(config)
    primary = [model.tag for model in config.primary_models]
    selected_writers = _select_models(writers, primary)
    selected_readers = _select_models(readers, primary)
    selected_variants = _parse_csv(variants, SourceVariant)
    selected_modes = _parse_csv(memory_modes, MemoryMode)
    selected_defenses = _parse_csv(defenses, DefenseCondition)
    if pairing not in {"all", "same", "cross"}:
        raise typer.BadParameter("--pairing must be all, same, or cross")
    selected_seeds = [int(seed) for seed in _parse_csv(seeds)]
    selected_embedding = _select_embedding(embedding_model, config)
    _assert_installed(manifest, selected_embedding)
    case_ids = [case.case_id for case in corpus.cases]
    selected_case_ids = case_ids if cases == "all" else _parse_csv(cases)
    unknown = sorted(set(selected_case_ids) - set(case_ids))
    if unknown:
        raise typer.BadParameter(f"Unknown cases: {', '.join(unknown)}")
    selected_cases = [case for case in corpus.cases if case.case_id in selected_case_ids]
    pairs = [
        (writer, reader)
        for writer in selected_writers
        for reader in selected_readers
        if pairing == "all"
        or (pairing == "same" and writer == reader)
        or (pairing == "cross" and writer != reader)
    ]
    variant_modes = [
        (variant, mode)
        for variant in selected_variants
        for mode in selected_modes
        if not (mode == MemoryMode.CLEAN_MEMORY and variant != SourceVariant.CLEAN)
    ]
    total = (
        len(selected_cases)
        * len(pairs)
        * len(variant_modes)
        * len(selected_defenses)
        * len(selected_seeds)
    )
    if limit is not None:
        total = min(total, limit)
    with (
        Database(config.database_url) as database,
        OllamaClient(config.ollama_url, config.inference) as ollama,
    ):
        run_id = database.create_run(
            label,
            config.benchmark.protocol_version,
            protocol_hash,
            _safe_config_snapshot(config),
            manifest,
        )
        runner = ExperimentRunner(
            config,
            database,
            VectorStore(config.qdrant_url, config.benchmark.collection_prefix),
            ollama,
            manifest,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Starting", total=total)

            def update(label_text: str) -> None:
                progress.update(task, description=label_text[:90], advance=1)

            try:
                summary = runner.run_matrix(
                    run_id=run_id,
                    cases=selected_cases,
                    writer_models=selected_writers,
                    reader_models=selected_readers,
                    variants=selected_variants,
                    memory_modes=selected_modes,
                    defenses=selected_defenses,
                    embedding_model=selected_embedding,
                    seeds=selected_seeds,
                    pairing=pairing,
                    progress=update,
                    fail_fast=fail_fast,
                    limit=limit,
                )
                database.finish_run(run_id, "failed" if summary.failed else "completed")
            except Exception:
                database.finish_run(run_id, "failed")
                raise
    console.print_json(data=summary.__dict__)
    console.print(f"[green]Run ID:[/] {run_id}")


@app.command("validate-counterfactual-design")
def validate_counterfactual_design(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(
        "configs/counterfactual-v0.3.yaml"
    ),
) -> None:
    """Validate the frozen v0.3 pair matrix without calling models or databases."""
    config = _counterfactual_config(config_path)
    cases, models, embedding, specs = _counterfactual_design(config)
    by_case: dict[str, dict[str, int]] = {}
    writer_first_by_case: dict[str, dict[str, int]] = {}
    seen_writer_units: set[tuple[str, str, int]] = set()
    for spec in specs:
        first = spec["variant_order"][0]
        bucket = by_case.setdefault(spec["case_id"], {"clean_first": 0, "poison_first": 0})
        bucket[f"{first}_first"] += 1
        writer_unit = (spec["case_id"], spec["writer_model"], int(spec["seed"]))
        if writer_unit not in seen_writer_units:
            seen_writer_units.add(writer_unit)
            writer_bucket = writer_first_by_case.setdefault(
                spec["case_id"], {"clean_first": 0, "poison_first": 0}
            )
            writer_bucket[f"{first}_first"] += 1
    console.print_json(
        data={
            "protocol_version": config.benchmark.protocol_version,
            "cases": len(cases),
            "writers": models,
            "readers": models,
            "embedding_model": embedding,
            "pairs": len(specs),
            "trials": len(specs) * 2,
            "design_fingerprint": design_fingerprint(specs),
            "variant_order_by_case": by_case,
            "cached_writer_generation_order_by_case": writer_first_by_case,
        }
    )


@app.command("run-counterfactual")
def run_counterfactual(
    label: Annotated[str, typer.Option()] = "counterfactual-confirmatory-v0.3",
    smoke_pairs: Annotated[
        int | None,
        typer.Option(help="Development only: run this many whole matched pairs."),
    ] = None,
    fail_fast: Annotated[bool, typer.Option()] = False,
    confirm_registered: Annotated[
        bool,
        typer.Option(
            "--confirm-registered",
            help="Required for the one-shot full 384-trial registered run.",
        ),
    ] = False,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(
        "configs/counterfactual-v0.3.yaml"
    ),
) -> None:
    """Run the fixed v0.3 matched clean/poison design; no effect-driven overrides."""
    config = _counterfactual_config(config_path)
    protocol_hash = _assert_protocol(config)
    cases, models, embedding, specs = _counterfactual_design(config)
    cf = config.counterfactual
    assert cf is not None
    if smoke_pairs is not None and not 1 <= smoke_pairs <= len(specs):
        raise typer.BadParameter(f"--smoke-pairs must be between 1 and {len(specs)}")
    if smoke_pairs is None and not confirm_registered:
        raise typer.BadParameter(
            "The full v0.3 run is a one-shot registered matrix. Re-run with "
            "--confirm-registered only after the smoke audit and final protocol verification pass."
        )
    if smoke_pairs is not None and confirm_registered:
        raise typer.BadParameter("Do not combine --confirm-registered with --smoke-pairs")
    manifest = _load_verified_manifest(config)
    _assert_installed(manifest, embedding)
    run_kind = "counterfactual_v0.3" if smoke_pairs is None else "counterfactual_v0.3_smoke"
    total_pairs = len(specs) if smoke_pairs is None else smoke_pairs
    total_trials = total_pairs * 2

    with (
        Database(config.database_url) as database,
        OllamaClient(config.ollama_url, config.inference) as ollama,
    ):
        if "004_protocol_v0_3.sql" not in database.applied_migrations():
            raise typer.BadParameter(
                "Migration 004_protocol_v0_3.sql is required; run mhb init-db "
                "-c configs/counterfactual-v0.3.yaml"
            )
        run_id = database.create_run(
            label,
            config.benchmark.protocol_version,
            protocol_hash,
            _counterfactual_run_snapshot(
                config, specs, run_kind=run_kind, executed_pairs=total_pairs
            ),
            manifest,
            run_kind=run_kind,
        )
        runner = ExperimentRunner(
            config,
            database,
            VectorStore(config.qdrant_url, config.benchmark.collection_prefix),
            ollama,
            manifest,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Starting v0.3 counterfactual", total=total_trials)

            def update(label_text: str) -> None:
                progress.update(task, description=label_text[:100], advance=1)

            try:
                summary = runner.run_counterfactual(
                    run_id=run_id,
                    cases=cases,
                    writer_models=models,
                    reader_models=models,
                    embedding_model=embedding,
                    seeds=cf.seeds,
                    memory_mode=cf.memory_mode,
                    defense=cf.defense,
                    progress=update,
                    fail_fast=fail_fast,
                    pair_limit=smoke_pairs,
                )
                if summary.trials_attempted != total_trials or summary.pairs_attempted != total_pairs:
                    database.finish_run(run_id, "failed")
                    raise RuntimeError(
                        "Counterfactual runner stopped before the registered whole-pair target"
                    )
                database.finish_run(run_id, "failed" if summary.failed else "completed")
            except Exception:
                database.finish_run(run_id, "failed")
                raise
    console.print_json(
        data={
            **summary.__dict__,
            "run_kind": run_kind,
            "design_fingerprint": design_fingerprint(specs),
        }
    )
    console.print(f"[green]Run ID:[/] {run_id}")
    if smoke_pairs is not None:
        console.print("[yellow]Smoke run: development evidence only; do not pool with v0.3.[/]")


@app.command("audit-counterfactual")
def audit_counterfactual_run(
    run_id: UUID,
    smoke_pairs: Annotated[
        int | None,
        typer.Option(help="For a development smoke run only: exact whole-pair count used."),
    ] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(
        "configs/counterfactual-v0.3.yaml"
    ),
) -> None:
    """Audit exact pair membership, terminal accounting, and standard trial integrity."""
    config = _counterfactual_config(config_path)
    _, _, _, full_specs = _counterfactual_design(config)
    cf = config.counterfactual
    assert cf is not None
    with Database(config.database_url) as database:
        run = database.run_record(run_id)
        if run is None:
            raise typer.BadParameter(f"Unknown run_id: {run_id}")
        rows = database.fetch_evidence_rows(run_id)

    run_kind = run.get("run_kind")
    if run_kind == "counterfactual_v0.3":
        if smoke_pairs is not None:
            raise typer.BadParameter(
                "--smoke-pairs must not be used for a registered counterfactual_v0.3 run"
            )
        specs = full_specs
        expected_trials = cf.expected_trials
    elif run_kind == "counterfactual_v0.3_smoke":
        if smoke_pairs is None:
            raise typer.BadParameter(
                "Smoke-run audit requires --smoke-pairs with the exact pair count used"
            )
        if not 1 <= smoke_pairs <= len(full_specs):
            raise typer.BadParameter(f"--smoke-pairs must be between 1 and {len(full_specs)}")
        specs = full_specs[:smoke_pairs]
        expected_trials = smoke_pairs * 2
    else:
        raise typer.BadParameter(
            f"Run kind is {run_kind!r}; expected counterfactual_v0.3 or counterfactual_v0.3_smoke"
        )

    _assert_counterfactual_run_identity(
        run=run,
        config=config,
        specs=full_specs,
        run_kind=str(run_kind),
        executed_pairs=len(specs),
    )
    pair_audit = audit_counterfactual(rows, specs)
    ordinary_summary = summarize(
        rows, {case.case_id: case.category for case in load_cases(config).cases}
    )
    ordinary_audit = audit_summary(ordinary_summary, expected_trials=expected_trials)
    analysis = analyze_counterfactual(
        rows,
        specs,
        bootstrap_replicates=cf.bootstrap_replicates,
        bootstrap_seed=cf.bootstrap_seed,
    )
    console.print_json(
        data={
            "run_id": str(run_id),
            "run_kind": run_kind,
            "expected_pairs": len(specs),
            "pair_audit": pair_audit,
            "ordinary_audit": ordinary_audit,
            "counterfactual_analysis": analysis,
        }
    )
    if not pair_audit["passed"] or not ordinary_audit["passed"]:
        raise typer.Exit(1)


@app.command("report-counterfactual")
def report_counterfactual(
    run_id: UUID,
    output_dir: Annotated[Path, typer.Option()] = Path("reports/counterfactual-v0.3"),
    smoke_pairs: Annotated[
        int | None,
        typer.Option(help="For a development smoke run only: exact whole-pair count used."),
    ] = None,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(
        "configs/counterfactual-v0.3.yaml"
    ),
) -> None:
    """Write pair-level JSON/CSV/Markdown evidence for a registered or explicit smoke run."""
    config = _counterfactual_config(config_path)
    _, _, _, full_specs = _counterfactual_design(config)
    cf = config.counterfactual
    assert cf is not None
    if not output_dir.is_absolute():
        output_dir = config.root / output_dir / str(run_id)
    with Database(config.database_url) as database:
        run = database.run_record(run_id)
        if run is None:
            raise typer.BadParameter(f"Unknown run_id: {run_id}")
        rows = database.fetch_evidence_rows(run_id)

    run_kind = run.get("run_kind")
    if run_kind == "counterfactual_v0.3":
        if smoke_pairs is not None:
            raise typer.BadParameter(
                "--smoke-pairs must not be used for a registered counterfactual_v0.3 run"
            )
        specs = full_specs
    elif run_kind == "counterfactual_v0.3_smoke":
        if smoke_pairs is None:
            raise typer.BadParameter(
                "Smoke-run report requires --smoke-pairs with the exact pair count used"
            )
        if not 1 <= smoke_pairs <= len(full_specs):
            raise typer.BadParameter(f"--smoke-pairs must be between 1 and {len(full_specs)}")
        specs = full_specs[:smoke_pairs]
    else:
        raise typer.BadParameter(
            f"Run kind is {run_kind!r}; use the standard report for non-counterfactual runs"
        )

    _assert_counterfactual_run_identity(
        run=run,
        config=config,
        specs=full_specs,
        run_kind=str(run_kind),
        executed_pairs=len(specs),
    )
    paths = write_counterfactual_reports(
        rows,
        specs,
        output_dir,
        bootstrap_replicates=cf.bootstrap_replicates,
        bootstrap_seed=cf.bootstrap_seed,
    )
    for kind, path in paths.items():
        console.print(f"[green]{kind.upper()}:[/] {path}")
    if run_kind.endswith("_smoke"):
        console.print("[yellow]Smoke report: development evidence only.[/]")


@app.command("export-human-review")
def export_human_review(
    run_id: UUID,
    output_dir: Annotated[Path, typer.Option()] = Path("reviews/v0.3"),
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(
        "configs/counterfactual-v0.3.yaml"
    ),
) -> None:
    """Export the complete registered poison set for blinded W/I human validation."""
    config = _counterfactual_config(config_path)
    cases, models, _, specs = _counterfactual_design(config)
    cf = config.counterfactual
    assert cf is not None
    if not output_dir.is_absolute():
        output_dir = config.root / output_dir / str(run_id)
    with Database(config.database_url) as database:
        run = database.run_record(run_id)
        if run is None:
            raise typer.BadParameter(f"Unknown run_id: {run_id}")
        if run.get("run_kind") != "counterfactual_v0.3":
            raise typer.BadParameter(
                "Human validation export is permitted only for the full registered "
                "counterfactual_v0.3 run, never a smoke/development run"
            )
        evidence_rows = database.fetch_evidence_rows(run_id)
        review_rows = database.fetch_human_review_rows(run_id)

    _assert_counterfactual_run_identity(
        run=run,
        config=config,
        specs=specs,
        run_kind="counterfactual_v0.3",
        executed_pairs=cf.expected_pairs,
    )
    pair_audit = audit_counterfactual(evidence_rows, specs)
    ordinary_audit = audit_summary(
        summarize(evidence_rows, {case.case_id: case.category for case in cases}),
        expected_trials=cf.expected_trials,
    )
    if not pair_audit["passed"] or not ordinary_audit["passed"]:
        raise typer.BadParameter(
            "Refusing review export because the registered run has not passed pair/trial integrity "
            "checks. Run mhb audit-counterfactual first."
        )

    expected_poison_ids = {
        str(row["trial_id"])
        for row in evidence_rows
        if row.get("source_variant") == "poison"
    }
    review_ids = [str(row.get("trial_id")) for row in review_rows]
    if len(review_ids) != len(set(review_ids)) or set(review_ids) != expected_poison_ids:
        raise typer.BadParameter(
            "Human-review query does not map one-to-one onto the registered poison trial set"
        )

    expected_writer_units = len(cases) * len(models) * len(cf.seeds)
    paths = export_blinded_human_review(
        rows=review_rows,
        cases=cases,
        output_dir=output_dir,
        run_id=str(run_id),
        expected_writer_units=expected_writer_units,
        expected_poison_trials=cf.expected_pairs,
    )
    for kind, path in paths.items():
        console.print(f"[green]{kind.upper()}:[/] {path}")
    console.print(
        "[yellow]Keep PRIVATE-review-key.csv away from reviewers until all labels are locked.[/]"
    )


@app.command()
def report(
    run_id: UUID,
    output_dir: Annotated[Path, typer.Option()] = Path("reports"),
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Generate CSV, JSON, and self-contained HTML reports for one run."""
    config = _config(config_path)
    if not output_dir.is_absolute():
        output_dir = config.root / output_dir
    with Database(config.database_url) as database:
        categories = {case.case_id: case.category for case in load_cases(config).cases}
        paths = write_reports(database, run_id, output_dir, categories)
    for kind, path in paths.items():
        console.print(f"[green]{kind.upper()}:[/] {path}")


@app.command("audit-run")
def audit_run(
    run_id: UUID,
    expected_trials: Annotated[int | None, typer.Option()] = None,
    check_clean: Annotated[bool, typer.Option()] = False,
    check_stop_go: Annotated[bool, typer.Option()] = False,
    min_clean_rate: Annotated[float, typer.Option()] = 0.75,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Fail closed on missing trials, model-level clean utility, and stop/go rules."""
    if not 0 <= min_clean_rate <= 1:
        raise typer.BadParameter("--min-clean-rate must be between 0 and 1")
    config = _config(config_path)
    categories = {case.case_id: case.category for case in load_cases(config).cases}
    with Database(config.database_url) as database:
        rows = database.fetch_evidence_rows(run_id)
        if database.run_record(run_id) is None:
            raise typer.BadParameter(f"Unknown run_id: {run_id}")
    summary = summarize(rows, categories)
    audit = audit_summary(
        summary,
        expected_trials=expected_trials,
        check_clean=check_clean,
        check_stop_go=check_stop_go,
        min_clean_rate=min_clean_rate,
    )
    console.print_json(data={"run_id": str(run_id), "audit": audit, "summary": summary})
    if not audit["passed"]:
        raise typer.Exit(1)


@app.command()
def analyse(
    run_id: UUID,
    output: Annotated[Path, typer.Option()] = Path("reports/mixed_effects.txt"),
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Fit the protocol-specified optional binary mixed-effects model."""
    config = _config(config_path)
    if not output.is_absolute():
        output = config.root / output
    with Database(config.database_url) as database:
        rows = database.fetch_evidence_rows(run_id)
    path = fit_binary_mixed_model(rows, output)
    console.print(f"[green]Model summary:[/] {path}")


@app.command()
def rollback(
    trial_id: UUID,
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    """Restore one trial's mock-SIEM fixture from recorded before-state."""
    config = _config(config_path)
    with Database(config.database_url) as database:
        count = database.rollback_trial(trial_id)
    console.print(f"[green]Reversed {count} action(s)[/] for trial {trial_id}")


@app.command("verify-protocol")
def verify_protocol(
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path("configs/default.yaml"),
) -> None:
    config = _config(config_path)
    valid, mismatches, lock_hash = verify_protocol_lock(
        config.root, config.benchmark.protocol_version
    )
    if not valid:
        console.print(f"[red]Protocol mismatch:[/] {', '.join(mismatches)}")
        raise typer.Exit(1)
    console.print(
        f"[green]Protocol v{config.benchmark.protocol_version} verified[/] lock_sha256={lock_hash}"
    )


if __name__ == "__main__":
    app()
