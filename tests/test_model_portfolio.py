from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio.model_portfolio import (
    ModelPortfolioPolicy,
    PortfolioConstructionError,
    build_from_collection,
    build_model_portfolio,
    load_model_portfolio_policy,
    write_model_portfolio_report,
)
from ranking.models import RankedCompany, RankingPolicy, RankingReport
from universe.collector import CollectionState, write_collection_state
from universe.sources import write_constituent_snapshot


def _ranking(count: int = 24) -> RankingReport:
    companies = []
    sectors = ["Technology", "Financials", "Industrials", "Health", "Energy", "Utilities"]
    for index in range(count):
        companies.append(
            RankedCompany(
                symbol=f"S{index:02d}",
                sector=sectors[index // 4],
                universe_eligible=True,
                safeguard_passed=True,
                safeguard_reasons=(),
                market_rank=index + 1,
                sector_rank=index % 4 + 1,
                candidate_rank=index + 1,
                investment_score=90.0 - index,
                opportunity_score=80.0,
                conviction_score=75.0,
                confidence_score=90.0,
                deal_breakers=(),
            )
        )
    return RankingReport(RankingPolicy("Test"), tuple(companies))


def test_canonical_model_portfolio_policy_is_pinned() -> None:
    policy = load_model_portfolio_policy("config/model_portfolio.yaml")
    assert policy.to_dict() == {
        "name": "Atlas Equal-Weight Research Portfolio",
        "target_positions": 20,
        "weighting_method": "equal",
        "max_position_weight": 0.05,
        "max_sector_weight": 0.20,
        "cash_weight": 0.0,
        "max_initial_turnover": 1.0,
    }


def test_builder_selects_ranked_candidates_under_sector_cap() -> None:
    report = build_model_portfolio(
        _ranking(),
        ModelPortfolioPolicy("Test"),
        metadata={"S00": {"name": "First", "price": 123.45}},
        universe_snapshot_date="2026-07-13",
    )
    assert len(report.positions) == 20
    assert report.invested_weight == 1.0
    assert max(report.sector_weights.values()) <= 0.20
    assert all(position.target_weight == 0.05 for position in report.positions)
    assert report.positions[0].symbol == "S00"
    assert report.positions[0].name == "First"
    assert report.positions[0].reference_price == 123.45
    assert report.to_dict()["advisory_only"] is True


def test_sector_cap_skips_higher_ranked_concentration() -> None:
    base = _ranking()
    concentrated = tuple(
        RankedCompany(
            **{
                **company.__dict__,
                "sector": "Technology" if index < 8 else company.sector,
            }
        )
        for index, company in enumerate(base.companies)
    )
    ranking = RankingReport(base.policy, concentrated)
    report = build_model_portfolio(ranking, ModelPortfolioPolicy("Test"))
    assert [item.symbol for item in report.positions[:5]] == [
        "S00", "S01", "S02", "S03", "S08"
    ]
    assert report.warnings == (
        "4 candidato(s) superior(es) ignorado(s) pelo limite setorial.",
    )


def test_insufficient_diversified_candidates_fails_explicitly() -> None:
    with pytest.raises(PortfolioConstructionError, match="Candidatos insuficientes"):
        build_model_portfolio(
            _ranking(4),
            ModelPortfolioPolicy("Test"),
        )


def test_policy_rejects_incompatible_constraints() -> None:
    with pytest.raises(ValueError, match="max_position_weight"):
        ModelPortfolioPolicy("Invalid", max_position_weight=0.04)
    with pytest.raises(ValueError, match="weighting_method"):
        ModelPortfolioPolicy("Invalid", weighting_method="score")
    with pytest.raises(ValueError, match="max_initial_turnover"):
        ModelPortfolioPolicy("Invalid", max_initial_turnover=0.50)


def test_report_writer_serializes_contract(tmp_path: Path) -> None:
    report = build_model_portfolio(_ranking(), ModelPortfolioPolicy("Test"))
    output = write_model_portfolio_report(report, tmp_path / "model.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["position_count"] == 20
    assert payload["summary"]["invested_weight"] == 1.0
    assert payload["summary"]["expected_initial_turnover"] == 1.0


def test_builder_contract_validation() -> None:
    with pytest.raises(TypeError, match="RankingReport"):
        build_model_portfolio(object(), ModelPortfolioPolicy("Test"))  # type: ignore[arg-type]


def _write_fake_collection(tmp_path: Path) -> tuple[Path, Path]:
    """
    Coleta completa mínima (2 papéis) para exercitar build_from_collection
    sem depender de rede nem de uma coleta real de milhares de tickers.
    """
    snapshot_path = tmp_path / "snapshot.csv"
    write_constituent_snapshot(
        [
            {"symbol": "AAA", "name": "Alpha Co", "snapshot_date": "2026-07-13"},
            {"symbol": "BBB", "name": "Beta Co", "snapshot_date": "2026-07-13"},
        ],
        snapshot_path,
    )

    def _observation(symbol: str, name: str) -> dict:
        return {
            "symbol": symbol,
            "name": name,
            "quote_type": "EQUITY",
            "currency": "USD",
            "country": "United States",
            "sector": "Technology",
            "industry": "Software",
            "price": 100.0,
            "market_cap": 10_000_000_000.0,
            "volume": 1_000_000.0,
        }

    state = CollectionState(
        snapshot_date="2026-07-13",
        total_constituents=2,
        created_at="2026-07-13T00:00:00+00:00",
        updated_at="2026-07-13T00:00:00+00:00",
        observations={
            "AAA": _observation("AAA", "Alpha Co"),
            "BBB": _observation("BBB", "Beta Co"),
        },
    )
    state_path = tmp_path / "state.json"
    write_collection_state(state, state_path)
    return snapshot_path, state_path


def _write_tiny_model_portfolio_policy(tmp_path: Path) -> Path:
    path = tmp_path / "model_portfolio.yaml"
    path.write_text(
        "name: Tiny Test Portfolio\n"
        "target_positions: 2\n"
        "max_position_weight: 0.6\n"
        "max_sector_weight: 1.0\n",
        encoding="utf-8",
    )
    return path


def _write_permissive_ranking_policy(tmp_path: Path) -> Path:
    """
    O ranking.yaml canônico exige confiança >= 70; os dados fictícios do
    fixture não têm fundamentos suficientes para isso. Este teste valida o
    mecanismo de override de política/rótulo, não o comportamento de
    scoring -- por isso usa um piso permissivo.
    """
    path = tmp_path / "ranking.yaml"
    path.write_text(
        "name: Permissive Test Ranking\n"
        "min_confidence_score: 0\n"
        "require_no_deal_breakers: false\n",
        encoding="utf-8",
    )
    return path


def test_build_from_collection_defaults_match_sp500_screener(
    tmp_path: Path,
) -> None:
    """Sem overrides, os nomes de saída continuam os históricos (sem sufixo)."""
    snapshot_path, state_path = _write_fake_collection(tmp_path)
    output_dir = tmp_path / "output"

    report = build_from_collection(
        state_path=state_path,
        snapshot_path=snapshot_path,
        output_dir=output_dir,
        ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
        model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
    )

    assert len(report.positions) == 2
    assert (output_dir / "research_universe_report.json").exists()
    assert (output_dir / "research_ranking_report.json").exists()
    assert (output_dir / "research_candidates.csv").exists()
    assert (output_dir / "model_portfolio_report.json").exists()
    assert (output_dir / "research_report.html").exists()
    assert "S&amp;P 500" in (output_dir / "research_report.html").read_text(
        encoding="utf-8"
    )


def _observation(symbol: str, name: str) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "quote_type": "EQUITY",
        "currency": "USD",
        "country": "United States",
        "sector": "Technology",
        "industry": "Software",
        "price": 100.0,
        "market_cap": 10_000_000_000.0,
        "volume": 1_000_000.0,
    }


def _write_collection_with_failure(
    tmp_path: Path,
    *,
    attempts: int,
) -> tuple[Path, Path]:
    """
    Coleta de 3 constituintes: 2 observados e 1 falha com ``attempts``
    tentativas registradas. Com ``attempts >= budget`` (3) a falha é
    permanente/esgotada; com ``attempts < budget`` é transitória.
    """
    snapshot_path = tmp_path / "snapshot.csv"
    write_constituent_snapshot(
        [
            {"symbol": "AAA", "name": "Alpha Co", "snapshot_date": "2026-07-13"},
            {"symbol": "BBB", "name": "Beta Co", "snapshot_date": "2026-07-13"},
            {"symbol": "CCC-W", "name": "Gamma Warrant", "snapshot_date": "2026-07-13"},
        ],
        snapshot_path,
    )
    state = CollectionState(
        snapshot_date="2026-07-13",
        total_constituents=3,
        created_at="2026-07-13T00:00:00+00:00",
        updated_at="2026-07-13T00:00:00+00:00",
        observations={
            "AAA": _observation("AAA", "Alpha Co"),
            "BBB": _observation("BBB", "Beta Co"),
        },
        failures={
            "CCC-W": {
                "attempts": attempts,
                "last_error": "Sem histórico para CCC-W",
                "updated_at": "2026-07-13T00:00:00+00:00",
            }
        },
    )
    state_path = tmp_path / "state.json"
    write_collection_state(state, state_path)
    return snapshot_path, state_path


def test_residual_failure_blocks_strict_default(tmp_path: Path) -> None:
    """Sem allow_exhausted_failures, qualquer falha residual barra (contrato histórico)."""
    snapshot_path, state_path = _write_collection_with_failure(tmp_path, attempts=3)
    with pytest.raises(PortfolioConstructionError, match="completa e sem falhas"):
        build_from_collection(
            state_path=state_path,
            snapshot_path=snapshot_path,
            output_dir=tmp_path / "output",
            universe_policy_path="config/universe_market.yaml",
            ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
            model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
        )


def test_exhausted_failure_accepted_and_recorded(tmp_path: Path) -> None:
    """Falha esgotada (attempts >= budget) é aceita e registrada no relatório."""
    snapshot_path, state_path = _write_collection_with_failure(tmp_path, attempts=3)
    output_dir = tmp_path / "output"
    report = build_from_collection(
        state_path=state_path,
        snapshot_path=snapshot_path,
        output_dir=output_dir,
        universe_policy_path="config/universe_market.yaml",
        ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
        model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
        output_label="market",
        allow_exhausted_failures=True,
        failure_attempt_budget=3,
    )
    assert len(report.positions) == 2
    assert report.excluded_failures == (("CCC-W", "Sem histórico para CCC-W"),)
    payload = json.loads(
        (output_dir / "model_portfolio_report_market.json").read_text(encoding="utf-8")
    )
    assert payload["source"]["excluded_failure_count"] == 1
    assert payload["source"]["excluded_failures"] == [
        {"symbol": "CCC-W", "reason": "Sem histórico para CCC-W"}
    ]
    assert any("permanente" in warning for warning in payload["summary"]["warnings"])


def test_transient_failure_still_blocks_when_permissive(tmp_path: Path) -> None:
    """Falha ainda retentável (attempts < budget) barra mesmo em modo permissivo."""
    snapshot_path, state_path = _write_collection_with_failure(tmp_path, attempts=1)
    with pytest.raises(PortfolioConstructionError, match="transitórias"):
        build_from_collection(
            state_path=state_path,
            snapshot_path=snapshot_path,
            output_dir=tmp_path / "output",
            universe_policy_path="config/universe_market.yaml",
            ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
            model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
            allow_exhausted_failures=True,
            failure_attempt_budget=3,
        )


def test_permissive_requires_positive_budget(tmp_path: Path) -> None:
    snapshot_path, state_path = _write_collection_with_failure(tmp_path, attempts=3)
    with pytest.raises(ValueError, match="failure_attempt_budget"):
        build_from_collection(
            state_path=state_path,
            snapshot_path=snapshot_path,
            output_dir=tmp_path / "output",
            universe_policy_path="config/universe_market.yaml",
            ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
            model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
            allow_exhausted_failures=True,
            failure_attempt_budget=None,
        )


def test_build_from_collection_labels_output_for_another_screener(
    tmp_path: Path,
) -> None:
    """
    Com um universe_policy_path diferente e um label, os arquivos de saída
    ficam distintos -- não sobrescrevem a saída do screener S&P 500.
    """
    snapshot_path, state_path = _write_fake_collection(tmp_path)
    output_dir = tmp_path / "output"

    report = build_from_collection(
        state_path=state_path,
        snapshot_path=snapshot_path,
        output_dir=output_dir,
        universe_policy_path="config/universe_market.yaml",
        ranking_policy_path=_write_permissive_ranking_policy(tmp_path),
        model_portfolio_policy_path=_write_tiny_model_portfolio_policy(tmp_path),
        output_label="market",
    )

    assert len(report.positions) == 2
    assert (output_dir / "research_universe_report_market.json").exists()
    assert (output_dir / "research_ranking_report_market.json").exists()
    assert (output_dir / "research_candidates_market.csv").exists()
    assert (output_dir / "model_portfolio_report_market.json").exists()
    assert (output_dir / "research_report_market.html").exists()
    assert "Mercado Amplo" in (
        output_dir / "research_report_market.html"
    ).read_text(encoding="utf-8")
    # Nenhum arquivo sem sufixo foi criado por essa chamada.
    assert not (output_dir / "research_universe_report.json").exists()
    assert not (output_dir / "research_candidates.csv").exists()
    assert not (output_dir / "research_report.html").exists()
