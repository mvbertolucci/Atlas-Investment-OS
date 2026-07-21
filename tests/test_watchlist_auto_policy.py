from __future__ import annotations

from pathlib import Path

import pytest

from watchlist.auto_policy import WatchlistAutoPolicy, load_watchlist_auto_policy


@pytest.fixture(scope="module")
def policy() -> WatchlistAutoPolicy:
    return load_watchlist_auto_policy(Path("config/watchlist_auto.yaml"))


def test_shipped_config_is_disabled_by_default(policy: WatchlistAutoPolicy) -> None:
    """Circuit breaker: PR1 introduz o arquivo, mas o fluxo automático só
    liga quando o wiring do pipeline (PR3) estiver pronto e testado."""
    assert policy.enabled is False


def test_shipped_config_values_are_pinned(policy: WatchlistAutoPolicy) -> None:
    """Trava os valores reais de config/watchlist_auto.yaml -- mudança de
    threshold/top_n/decisions elegíveis deve ser deliberada, não silenciosa
    (mesma disciplina de tests/test_governed_config.py para os outros
    arquivos de config governada)."""
    assert policy.top_n == 30
    assert policy.qualifying_decisions == ("STRONG_BUY", "BUY", "ACCUMULATE")
    assert policy.min_confidence_score == 60.0
    assert policy.exit_investment_score_threshold == 40.0
    assert policy.protect_portfolio_holdings is True
    assert policy.protect_manual_entries is True


def test_top_n_must_be_positive(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text(
        "enabled: true\n"
        "selection: {top_n: 0, qualifying_decisions: [BUY]}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_watchlist_auto_policy(path)


def test_exit_threshold_must_be_within_0_100(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text(
        "enabled: true\n"
        "selection: {top_n: 30, qualifying_decisions: [BUY]}\n"
        "exit: {investment_score_threshold: 150.0}\n"
        "safeguards: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_watchlist_auto_policy(path)


def test_min_confidence_score_must_be_within_0_100(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text(
        "enabled: true\n"
        "selection: {top_n: 30, qualifying_decisions: [BUY], "
        "min_confidence_score: -1}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_watchlist_auto_policy(path)


def test_qualifying_decisions_cannot_be_empty(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text(
        "enabled: true\n"
        "selection: {top_n: 30, qualifying_decisions: []}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_watchlist_auto_policy(path)


def test_missing_sections_fall_back_to_in_code_defaults(tmp_path: Path) -> None:
    """selection/exit/safeguards ausentes viram {} -- as @property tipadas
    fornecem o default, mesmo padrão de SellRulesPolicy."""
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text("enabled: false\n", encoding="utf-8")

    loaded = load_watchlist_auto_policy(path)

    assert loaded.top_n == 30
    assert loaded.exit_investment_score_threshold == 40.0
    assert loaded.protect_portfolio_holdings is True
    assert loaded.protect_manual_entries is True


def test_safeguards_can_be_explicitly_disabled(tmp_path: Path) -> None:
    """Config explícito, não hardcoded -- confirma que a salvaguarda é de
    fato lida do YAML, não uma constante Python inescapável."""
    path = tmp_path / "watchlist_auto.yaml"
    path.write_text(
        "enabled: true\n"
        "selection: {top_n: 30, qualifying_decisions: [BUY]}\n"
        "exit: {investment_score_threshold: 40.0}\n"
        "safeguards: {protect_portfolio_holdings: false, protect_manual_entries: false}\n",
        encoding="utf-8",
    )

    loaded = load_watchlist_auto_policy(path)

    assert loaded.protect_portfolio_holdings is False
    assert loaded.protect_manual_entries is False
