from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backtesting.portfolio_validation import (
    AssetPeriodReturn,
    PortfolioRebalance,
    PortfolioValidationInput,
    PortfolioValidationManifest,
    PortfolioValidationPolicy,
    load_portfolio_validation_input,
    load_portfolio_validation_policy,
    main,
    run_portfolio_validation,
    validate_portfolio,
    write_portfolio_validation_report,
)


def _policy(**overrides) -> PortfolioValidationPolicy:
    values = {
        "name": "Test validation",
        "benchmark_symbol": "SPY",
        "periods_per_year": 12,
        "transaction_cost_bps": 10.0,
        "base_currency": "USD",
        "dividends_included": True,
    }
    values.update(overrides)
    return PortfolioValidationPolicy(**values)


def _manifest(**overrides) -> PortfolioValidationManifest:
    values = {
        "dataset_name": "Synthetic monthly validation",
        "dataset_version": "fixture-v1",
        "portfolio_source": "synthetic-rebalances",
        "return_source": "synthetic-total-returns",
        "benchmark_source": "synthetic-spy-total-returns",
        "period_convention": "close-to-close on explicit boundaries",
        "terminal_event_source": "synthetic-terminal-events",
        "atlas_code_revision": "test",
    }
    values.update(overrides)
    return PortfolioValidationManifest(**values)


def _return(
    symbol: str,
    start: str,
    end: str,
    value: float | None,
    **overrides,
) -> AssetPeriodReturn:
    values = {
        "symbol": symbol,
        "period_start": start,
        "period_end": end,
        "total_return": value,
        "source": "synthetic-total-return-fixture",
    }
    values.update(overrides)
    return AssetPeriodReturn(**values)


def test_canonical_portfolio_validation_policy_is_pinned() -> None:
    policy = load_portfolio_validation_policy("config/portfolio_validation.yaml")

    assert policy.to_dict() == {
        "name": "Atlas Monthly Portfolio Validation",
        "benchmark_symbol": "SPY",
        "periods_per_year": 12,
        "transaction_cost_bps": 10.0,
        "base_currency": "USD",
        "dividends_included": True,
    }


def test_policy_and_rebalance_reject_invalid_assumptions() -> None:
    with pytest.raises(ValueError, match="periods_per_year"):
        _policy(periods_per_year=0)
    with pytest.raises(ValueError, match="transaction_cost_bps"):
        _policy(transaction_cost_bps=-1)
    with pytest.raises(TypeError, match="booleano"):
        _policy(dividends_included="true")
    with pytest.raises(ValueError, match="soma"):
        PortfolioRebalance("2025-01-01", {"AAA": 0.6, "BBB": 0.5})
    with pytest.raises(ValueError, match="CASH"):
        PortfolioRebalance("2025-01-01", {"CASH": 1.0})


def test_return_contract_requires_explicit_terminal_treatment() -> None:
    with pytest.raises(ValueError, match="não pode inventar"):
        _return(
            "AAA",
            "2025-01-01",
            "2025-02-01",
            -0.5,
            terminal_treatment="unresolved",
        )
    with pytest.raises(ValueError, match="igual a -1"):
        _return(
            "AAA",
            "2025-01-01",
            "2025-02-01",
            -0.5,
            terminal_treatment="zero",
        )
    resolved = _return(
        "AAA",
        "2025-01-01",
        "2025-02-01",
        -1.0,
        terminal_treatment="zero",
    )
    assert resolved.total_return == -1.0


def test_complete_validation_computes_return_risk_cost_and_concentration() -> None:
    rebalances = (
        PortfolioRebalance("2025-01-01", {"AAA": 0.5, "BBB": 0.5}),
        PortfolioRebalance("2025-02-01", {"AAA": 0.5, "BBB": 0.5}),
    )
    returns = (
        _return("AAA", "2025-01-01", "2025-02-01", 0.10),
        _return("BBB", "2025-01-01", "2025-02-01", -0.10),
        _return("SPY", "2025-01-01", "2025-02-01", 0.02),
        _return("AAA", "2025-02-01", "2025-03-01", 0.20),
        _return("BBB", "2025-02-01", "2025-03-01", 0.00),
        _return("SPY", "2025-02-01", "2025-03-01", 0.02),
    )

    report = validate_portfolio(
        rebalances,
        returns,
        _policy(),
        _manifest(),
        generated_at=datetime(2025, 3, 2, tzinfo=timezone.utc),
    )

    assert report.summary is not None
    assert report.incomplete_periods == ()
    assert report.periods[0].turnover == 1.0
    assert report.periods[0].gross_return == 0.0
    assert report.periods[0].estimated_cost == 0.001
    assert report.periods[0].net_return == -0.001
    assert report.periods[1].turnover == 0.05
    assert report.periods[1].gross_return == 0.10
    assert report.periods[1].estimated_cost == 0.00005
    assert report.periods[1].net_return == pytest.approx(0.099945)
    expected_total = (1 - 0.001) * (1 + 0.099945) - 1
    expected_volatility = math.sqrt(12) * abs(0.099945 - (-0.001)) / math.sqrt(2)
    assert report.summary.total_return == pytest.approx(expected_total)
    assert report.summary.benchmark_total_return == pytest.approx(0.0404)
    assert report.summary.annualized_volatility == pytest.approx(
        expected_volatility
    )
    assert report.summary.maximum_drawdown == -0.001
    assert report.summary.average_turnover == 0.525
    assert report.summary.total_estimated_cost == 0.00105
    assert report.summary.average_position_hhi == 0.5
    assert report.summary.maximum_position_weight == 0.5
    assert report.summary.average_sector_hhi is None
    assert report.summary.maximum_sector_weight is None
    assert report.return_sources == ("synthetic-total-return-fixture",)
    assert report.to_dict()["manifest"] == _manifest().to_dict()


def test_sector_concentration_is_computed_only_from_explicit_mapping() -> None:
    rebalance = PortfolioRebalance(
        "2025-01-01",
        {"AAA": 0.4, "BBB": 0.3, "CCC": 0.3},
        sectors={"AAA": "Technology", "BBB": "Technology", "CCC": "Health"},
    )
    report = validate_portfolio(
        (rebalance,),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.0),
            _return("BBB", "2025-01-01", "2025-02-01", 0.0),
            _return("CCC", "2025-01-01", "2025-02-01", 0.0),
            _return("SPY", "2025-01-01", "2025-02-01", 0.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    assert report.summary is not None
    assert report.periods[0].sector_hhi == 0.58
    assert report.periods[0].maximum_sector_weight == 0.7
    assert report.summary.average_sector_hhi == 0.58
    assert report.summary.maximum_sector_weight == 0.7


def test_sector_contribution_matches_weighted_return_and_sums_to_gross_return() -> None:
    rebalance = PortfolioRebalance(
        "2025-01-01",
        {"AAA": 0.4, "BBB": 0.3, "CCC": 0.3},
        sectors={"AAA": "Technology", "BBB": "Technology", "CCC": "Health"},
    )
    report = validate_portfolio(
        (rebalance,),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("BBB", "2025-01-01", "2025-02-01", -0.20),
            _return("CCC", "2025-01-01", "2025-02-01", 0.05),
            _return("SPY", "2025-01-01", "2025-02-01", 0.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    period = report.periods[0]
    # Technology = 0.4*0.10 + 0.3*(-0.20) = -0.02; Health = 0.3*0.05 = 0.015
    assert period.sector_contributions == {
        "Health": pytest.approx(0.015),
        "Technology": pytest.approx(-0.02),
    }
    assert sum(period.sector_contributions.values()) == pytest.approx(
        period.gross_return
    )


def test_sector_contribution_is_none_without_complete_sector_coverage() -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 0.5, "BBB": 0.5}),),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("BBB", "2025-01-01", "2025-02-01", 0.0),
            _return("SPY", "2025-01-01", "2025-02-01", 0.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    assert report.periods[0].sector_contributions is None


def test_sector_mapping_rejects_unknown_portfolio_symbol() -> None:
    with pytest.raises(ValueError, match="símbolos da carteira"):
        PortfolioRebalance(
            "2025-01-01",
            {"AAA": 1.0},
            sectors={"BBB": "Technology"},
        )


def test_factor_exposures_rejects_unknown_symbol_and_inconsistent_factor_set() -> None:
    with pytest.raises(ValueError, match="símbolos da carteira"):
        PortfolioRebalance(
            "2025-01-01",
            {"AAA": 1.0},
            factor_exposures={"BBB": {"business": 60.0}},
        )
    with pytest.raises(ValueError, match="mesmo conjunto de fatores"):
        PortfolioRebalance(
            "2025-01-01",
            {"AAA": 0.5, "BBB": 0.5},
            factor_exposures={
                "AAA": {"business": 60.0, "valuation": 40.0},
                "BBB": {"business": 55.0},
            },
        )
    with pytest.raises(ValueError, match="objeto não vazio"):
        PortfolioRebalance(
            "2025-01-01",
            {"AAA": 1.0},
            factor_exposures={"AAA": {}},
        )


def test_weighted_average_factor_exposure_matches_hand_computed_value() -> None:
    rebalance = PortfolioRebalance(
        "2025-01-01",
        {"AAA": 0.4, "BBB": 0.6},
        factor_exposures={
            "AAA": {"business": 80.0, "valuation": 20.0},
            "BBB": {"business": 50.0, "valuation": 60.0},
        },
    )
    report = validate_portfolio(
        (rebalance,),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.0),
            _return("BBB", "2025-01-01", "2025-02-01", 0.0),
            _return("SPY", "2025-01-01", "2025-02-01", 0.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    period = report.periods[0]
    assert period.factor_exposures == {
        "business": pytest.approx(0.4 * 80.0 + 0.6 * 50.0),
        "valuation": pytest.approx(0.4 * 20.0 + 0.6 * 60.0),
    }


def test_factor_exposures_is_none_without_complete_coverage() -> None:
    rebalance = PortfolioRebalance(
        "2025-01-01",
        {"AAA": 0.5, "BBB": 0.5},
        factor_exposures={"AAA": {"business": 80.0}},
    )
    report = validate_portfolio(
        (rebalance,),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.0),
            _return("BBB", "2025-01-01", "2025-02-01", 0.0),
            _return("SPY", "2025-01-01", "2025-02-01", 0.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    assert report.periods[0].factor_exposures is None


def test_rebalance_round_trips_factor_exposures_through_dict() -> None:
    rebalance = PortfolioRebalance(
        "2025-01-01",
        {"AAA": 1.0},
        factor_exposures={"AAA": {"business": 80.0, "valuation": 20.0}},
    )
    restored = PortfolioRebalance.from_dict(rebalance.to_dict())
    assert restored == rebalance


def test_missing_return_blocks_aggregate_metrics_and_stays_visible() -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 0.5, "BBB": 0.5}),),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("SPY", "2025-01-01", "2025-02-01", 0.02),
        ),
        _policy(),
        _manifest(),
    )

    assert report.summary is None
    assert report.periods == ()
    assert report.incomplete_periods[0].reasons == ("MISSING_RETURN:BBB",)
    assert report.to_dict()["status"] == "incomplete"


def test_unresolved_delisting_blocks_metrics_without_silent_drop() -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 1.0}),),
        (
            _return(
                "AAA",
                "2025-01-01",
                "2025-02-01",
                None,
                terminal_treatment="unresolved",
            ),
            _return("SPY", "2025-01-01", "2025-02-01", -0.05),
        ),
        _policy(),
        _manifest(),
    )

    assert report.summary is None
    assert report.incomplete_periods[0].reasons == (
        "UNRESOLVED_DELISTING:AAA",
    )


def test_zero_delisting_preserves_minus_one_floor_after_costs() -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 1.0}),),
        (
            _return(
                "AAA",
                "2025-01-01",
                "2025-02-01",
                -1.0,
                terminal_treatment="zero",
            ),
            _return("SPY", "2025-01-01", "2025-02-01", -0.10),
        ),
        _policy(),
        _manifest(),
    )

    assert report.summary is not None
    assert report.periods[0].net_return == -1.0
    assert report.periods[0].terminal_events == ("AAA:zero",)
    assert report.summary.total_return == -1.0
    assert report.summary.maximum_drawdown == -1.0


def test_benchmark_total_loss_makes_relative_return_undefined() -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 1.0}),),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("SPY", "2025-01-01", "2025-02-01", -1.0),
        ),
        _policy(transaction_cost_bps=0),
        _manifest(),
    )

    assert report.summary is not None
    assert report.summary.relative_return is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"currency": "EUR"}, "RETURN_CURRENCY_MISMATCH:AAA"),
        ({"dividends_included": False}, "DIVIDEND_TREATMENT_MISMATCH:AAA"),
    ],
)
def test_return_assumption_mismatch_is_explicit(overrides, reason) -> None:
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 1.0}),),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10, **overrides),
            _return("SPY", "2025-01-01", "2025-02-01", 0.02),
        ),
        _policy(),
        _manifest(),
    )

    assert report.summary is None
    assert reason in report.incomplete_periods[0].reasons


def test_incomplete_period_prevents_later_turnover_reconstruction() -> None:
    report = validate_portfolio(
        (
            PortfolioRebalance("2025-01-01", {"AAA": 1.0}),
            PortfolioRebalance("2025-02-01", {"AAA": 1.0}),
        ),
        (
            _return("SPY", "2025-01-01", "2025-02-01", 0.01),
            _return("AAA", "2025-02-01", "2025-03-01", 0.02),
            _return("SPY", "2025-02-01", "2025-03-01", 0.01),
        ),
        _policy(),
        _manifest(),
    )

    assert report.summary is None
    assert report.incomplete_periods[0].reasons == ("MISSING_RETURN:AAA",)
    assert report.incomplete_periods[1].reasons == (
        "PRIOR_PERIOD_INCOMPLETE",
    )


def test_validation_rejects_ambiguous_period_structure() -> None:
    rebalance = PortfolioRebalance("2025-01-01", {"AAA": 1.0})
    with pytest.raises(ValueError, match="exatamente um período"):
        validate_portfolio((rebalance,), (), _policy(), _manifest())
    duplicate = _return("AAA", "2025-01-01", "2025-02-01", 0.0)
    with pytest.raises(ValueError, match="duplicado"):
        validate_portfolio(
            (rebalance,), (duplicate, duplicate), _policy(), _manifest()
        )


def test_report_serialization_is_deterministic_and_advisory(tmp_path: Path) -> None:
    generated_at = datetime(2025, 2, 2, 12, 0, tzinfo=timezone.utc)
    report = validate_portfolio(
        (PortfolioRebalance("2025-01-01", {"AAA": 1.0}),),
        (
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("SPY", "2025-01-01", "2025-02-01", 0.05),
        ),
        _policy(),
        _manifest(),
        generated_at=generated_at,
    )
    path = write_portfolio_validation_report(report, tmp_path / "validation.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload == report.to_dict()
    assert payload["generated_at"] == "2025-02-02T12:00:00+00:00"
    assert payload["advisory_only"] is True
    assert payload["status"] == "complete"
    assert "not a performance promise" in payload["performance_disclaimer"]


def _input_contract() -> PortfolioValidationInput:
    return PortfolioValidationInput(
        manifest=_manifest(),
        rebalances=(
            PortfolioRebalance(
                "2025-01-01",
                {"AAA": 1.0},
                sectors={"AAA": "Technology"},
            ),
        ),
        returns=(
            _return("AAA", "2025-01-01", "2025-02-01", 0.10),
            _return("SPY", "2025-01-01", "2025-02-01", 0.05),
        ),
    )


def test_manifest_and_versioned_input_are_required_and_roundtrip(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="dataset_name"):
        _manifest(dataset_name="")
    contract = _input_contract()
    path = tmp_path / "input.json"
    path.write_text(json.dumps(contract.to_dict()), encoding="utf-8")

    loaded = load_portfolio_validation_input(path)

    assert loaded == contract
    invalid = contract.to_dict()
    invalid["schema_version"] = 99
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_portfolio_validation_input(path)


def test_versioned_example_input_is_valid_and_clearly_synthetic() -> None:
    contract = load_portfolio_validation_input(
        "config/portfolio_validation_input.example.json"
    )

    assert contract.schema_version == 1
    assert "Synthetic" in contract.manifest.dataset_name
    assert contract.rebalances[0].sectors == {
        "AAA": "Technology",
        "BBB": "Health",
    }


def test_file_runner_writes_reproducible_report(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(
        json.dumps(_input_contract().to_dict()),
        encoding="utf-8",
    )
    generated_at = datetime(2025, 2, 2, tzinfo=timezone.utc)

    report = run_portfolio_validation(
        input_path=input_path,
        policy_path="config/portfolio_validation.yaml",
        output_path=output_path,
        generated_at=generated_at,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == report.to_dict()
    assert payload["input_schema_version"] == 1
    assert payload["manifest"]["dataset_version"] == "fixture-v1"
    assert payload["summary"]["average_sector_hhi"] == 1.0


def test_cli_runs_only_from_explicit_local_input(
    tmp_path: Path,
    capsys,
) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "report.json"
    input_path.write_text(
        json.dumps(_input_contract().to_dict()),
        encoding="utf-8",
    )

    main(
        [
            "--input",
            str(input_path),
            "--policy",
            "config/portfolio_validation.yaml",
            "--output",
            str(output_path),
        ]
    )

    assert output_path.exists()
    assert "complete" in capsys.readouterr().out
