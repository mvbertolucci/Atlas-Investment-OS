"""Materialidade de uma lacuna: o que ela pode, de fato, mudar (ADR-050).

Os casos abaixo são os reais medidos em 2026-07-24, não sintéticos.
"""
from __future__ import annotations

import pytest

from reports.field_materiality import (
    FieldRole,
    load_field_roles,
    materiality_note,
)


def test_field_outside_score_and_thresholds_says_only_freshness_moves() -> None:
    """37 dos 77 campos de evidência caem aqui. Hoje aparecem com o mesmo
    peso visual de um roe ausente, e são ruído contábil.

    `beta`, não `dividend_rate`: este alimenta `shareholder_yield` e portanto
    se propaga -- a primeira versão deste teste usava o exemplo errado, e a
    checagem de dependência derrubou a asserção.
    """
    note = materiality_note("beta", 1.4, sector="Industrials")

    assert "não entra no score nem em deal breaker" in note
    assert "Data Freshness" in note


def test_threshold_only_field_reports_headroom_and_direction() -> None:
    """Caso que originou o pedido: short_float do BRK-B, defasado mas a 21x
    de distância do deal breaker que ele governa."""
    note = materiality_note("short_float", 0.96, sector="Financial Services")

    assert "crescer 20.8x" in note
    assert "não entra no score" in note


def test_minimum_threshold_says_fall_not_grow() -> None:
    """altman_z é limite MÍNIMO: ele é acionado quando o valor CAI. Dizer
    'crescer' inverteria o sentido da folga."""
    note = materiality_note("altman_z", 4.14, sector="Industrials")

    assert "cair" in note
    assert "crescer" not in note


def test_sector_exemption_is_the_only_definitive_claim() -> None:
    """Isenção setorial não é estimativa de distância: é a configuração
    dizendo que o limiar não se aplica."""
    note = materiality_note("altman_z", 1.2, sector="Utilities")

    assert "isento" in note


def test_scored_field_reports_swing_ceiling_and_never_claims_irrelevance() -> None:
    """Campo pontuado mexe no percentil por construção. O teto
    (peso_fator x peso_feature x 100) é afirmável; irrelevância não é."""
    note = materiality_note("ev_ebitda", 42.16, sector="Industrials")

    assert "9.0 pontos" in note
    assert "irrelevante" not in note.lower()
    assert "não muda" not in note.lower()


def test_field_that_is_both_scored_and_gated_reports_both() -> None:
    note = materiality_note("net_debt_ebitda", 1.2, sector="Industrials")

    assert "deal breaker" in note
    assert "Investment Score" in note


def test_current_ratio_is_recognised_as_scored_despite_the_alias() -> None:
    """`current_ratio` e `current_liquidity` são o MESMO número sob dois
    nomes (COLUMN_MAP). Tratá-los como distintos faria o current_ratio
    parecer governado só por limiar, quando ele é pontuado."""
    for name in ("current_ratio", "current_liquidity"):
        note = materiality_note(name, 4.3, sector="Industrials")
        assert "Investment Score" in note, name


def test_near_the_threshold_shows_distance_without_reassurance() -> None:
    """Sem margem de 2x, mostramos a distância e calamos sobre a folga."""
    note = materiality_note("short_float", 15.0, sector="Industrials")

    assert "15" in note and "20" in note
    assert "precisaria" not in note


def test_swing_ceiling_matches_the_governed_weights() -> None:
    roles = load_field_roles()
    role = roles["ev_ebitda"]

    # valuation pesa 0.30 no modelo; ev_ebitda pesa 0.30 dentro do fator
    assert role.max_score_swing == pytest.approx(0.30 * 0.30 * 100)
    assert role.scored is True


def test_unknown_value_does_not_fabricate_a_distance() -> None:
    note = materiality_note("short_float", None, sector="Industrials")

    assert "governa um deal breaker" in note
    assert "precisaria" not in note


def test_dependency_of_a_scored_field_is_not_declared_inconsequential() -> None:
    """`total_cash` não é pontuado nem governa limiar por si, mas compõe
    `net_debt_ebitda`, que é as duas coisas. Declarar 'não muda nada' seria
    falso -- e falso na direção que tranquiliza, que é a pior."""
    note = materiality_note("total_cash", 2.1e10, sector="Industrials")

    assert "se propaga" in note
    assert "net_debt_ebitda" in note
    assert "não entra no score nem em deal breaker" not in note


def test_genuinely_inconsequential_field_still_says_so() -> None:
    """A propagação não pode virar ressalva universal: campo que de fato não
    alimenta nada segue recebendo o veredicto forte."""
    note = materiality_note("beta", 1.4, sector="Industrials")

    assert "não entra no score nem em deal breaker" in note
    assert "se propaga" not in note


def test_company_page_converts_fraction_to_points_before_comparing() -> None:
    """O limiar do deal breaker está em pontos percentuais
    (`short_float_max: 20`), mas o valor persistido é fração. Sem converter,
    o short_float do BRK-B saía como "precisaria crescer 2083x" em vez de
    20,8x -- errado por 100x, e errado na direção que tranquiliza."""
    from pathlib import Path

    from reports.company_page import render_company_page

    html = render_company_page("BRK-B", Path(__file__).resolve().parents[1])

    assert "2083" not in html
    if "short_float" in html and "crescer" in html:
        assert "crescer 20.8x" in html
