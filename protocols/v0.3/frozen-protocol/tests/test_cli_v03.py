from pathlib import Path

import pytest
import typer

import memory_handoff_bench.cli as cli

ROOT = Path(__file__).resolve().parents[1]


def test_counterfactual_commands_require_canonical_locked_config() -> None:
    config = cli._counterfactual_config(ROOT / "configs/counterfactual-v0.3.yaml")
    assert config.benchmark.protocol_version == "0.3"
    with pytest.raises(typer.BadParameter, match="canonical config"):
        cli._counterfactual_config(ROOT / "configs/default.yaml")


def test_run_snapshot_binds_design_fingerprint_and_execution_size() -> None:
    config = cli._counterfactual_config(ROOT / "configs/counterfactual-v0.3.yaml")
    _, _, _, specs = cli._counterfactual_design(config)
    snapshot = cli._counterfactual_run_snapshot(
        config, specs, run_kind="counterfactual_v0.3", executed_pairs=192
    )
    design = snapshot["registered_counterfactual_design"]
    assert design["fingerprint"] == cli.design_fingerprint(specs)
    assert design["full_expected_pairs"] == 192
    assert design["full_expected_trials"] == 384
    assert design["executed_pairs"] == 192
    assert design["executed_trials"] == 384


def test_run_identity_rejects_design_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    config = cli._counterfactual_config(ROOT / "configs/counterfactual-v0.3.yaml")
    _, _, _, specs = cli._counterfactual_design(config)
    snapshot = cli._counterfactual_run_snapshot(
        config, specs, run_kind="counterfactual_v0.3", executed_pairs=192
    )
    run = {
        "protocol_version": "0.3",
        "protocol_hash": "LOCK-HASH",
        "config_snapshot": snapshot,
    }
    monkeypatch.setattr(cli, "_assert_protocol", lambda _: "LOCK-HASH")
    cli._assert_counterfactual_run_identity(
        run=run,
        config=config,
        specs=specs,
        run_kind="counterfactual_v0.3",
        executed_pairs=192,
    )

    run["config_snapshot"] = dict(snapshot)
    run["config_snapshot"]["registered_counterfactual_design"] = dict(
        snapshot["registered_counterfactual_design"]
    )
    run["config_snapshot"]["registered_counterfactual_design"]["fingerprint"] = "drift"
    with pytest.raises(typer.BadParameter, match="identity check failed"):
        cli._assert_counterfactual_run_identity(
            run=run,
            config=config,
            specs=specs,
            run_kind="counterfactual_v0.3",
            executed_pairs=192,
        )


def test_migration_enforces_one_registered_v03_run_per_database() -> None:
    migration = (ROOT / "migrations/004_protocol_v0_3.sql").read_text(encoding="utf-8")
    assert "uq_experiment_runs_counterfactual_v03" in migration
    assert "WHERE run_kind = 'counterfactual_v0.3'" in migration
