from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from analytics.feature_audit import (
    audit_coverage,
    format_coverage_report,
    phantom_weight_summary,
)
from analytics.fundamentals import compute_fundamentals
from analytics.history import load_history as load_score_history
from analytics.history import previous_run_context
from analytics.indicators import enrich_technicals
from analytics.mapper import normalize_columns
from atlas_logger import get_logger
from health.health_check import print_health_report, run_health_check
from metrics.execution import (
    ExecutionMetrics,
    StageTimer,
    print_execution_metrics,
    save_execution_metrics,
)
from outcomes.analytics import (
    OutcomeAnalyticsReport,
    build_outcome_analytics_report,
)
from outcomes.pipeline import (
    OutcomeCaptureResult,
    OutcomeEvaluationResult,
    capture_outcome_snapshots,
    evaluate_due_outcomes,
)
from outcomes.report import write_outcome_report
from portfolio.exceptions import PortfolioError
from portfolio.loader import load_portfolio_csv
from portfolio.pipeline import (
    build_portfolio_intelligence,
    write_portfolio_report,
)
from portfolio.rebalance import SellEngineBlockedError
from portfolio.report import PortfolioReport
from portfolio.sell_rules import SellRulesPolicy, load_sell_rules_policy
from providers.yahoo import fetch_watchlist
from ranking import (
    RankingReport,
    load_ranking_policy,
    rank_companies,
    write_ranking_report,
)
from reports.atlas_report.context import build_report_context
from reports.atlas_report.one_pager import (
    compute_symbol_contributions,
    render_one_pager,
)
from reports.atlas_report.render import page_shell, render_report
from reports.atlas_report.write import write_one_pager, write_report
from reports.excel import write_latest_and_history
from reports.morning_brief import render_morning_brief, write_morning_brief
from dashboard import build_dashboard_view, write_dashboard_view
from priority import (
    PriorityReport,
    build_buy_priority,
    build_sell_priority,
    write_priority_report,
)
from reports.report_engine import build_company_reports
from scoring.investment import load_yaml, score_dataframe
from storage.history_db import HistoryDatabase
from universe import (
    UniverseReport,
    evaluate_universe,
    load_universe_policy,
    write_universe_report,
)
from watchlist import (
    WatchlistError,
    WatchlistReport,
    attach_aging,
    evaluate_watchlist_triggers,
    load_watchlist_csv,
    normalize_current_row,
    write_watchlist_report,
)


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"
LOGS = ROOT / "logs"

HISTORY_DATABASE = DATA / "atlas_history.db"
MORNING_BRIEF_FILE = OUTPUT / "morning_brief.md"
EXECUTION_METRICS_FILE = LOGS / "execution_metrics.csv"
PORTFOLIO_REPORT_FILE = OUTPUT / "portfolio_report.json"
OUTCOME_REPORT_FILE = OUTPUT / "outcome_report.json"
DASHBOARD_REPORT_FILE = OUTPUT / "dashboard.json"
PRIORITY_REPORT_FILE = OUTPUT / "priority_report.json"
RESEARCH_RANKING_REPORT_FILE = OUTPUT / "research_ranking_report.json"
UNIVERSE_REPORT_FILE = OUTPUT / "universe_report.json"
RANKING_REPORT_FILE = OUTPUT / "ranking_report.json"
WATCHLIST_REPORT_FILE = OUTPUT / "watchlist_report.json"

logger = get_logger("run_all")


def _read_status_md() -> str:
    """
    Lê STATUS.md só para extrair os alertas de conflito de motor exibidos
    no Diagnóstico do relatório -- se o arquivo não existir, o relatório
    simplesmente não mostra alertas (nunca quebra o run por isso).
    """
    status_path = ROOT / "STATUS.md"
    try:
        return status_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_settings() -> dict:
    settings_path = CONFIG / "settings.json"

    if not settings_path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {settings_path}"
        )

    return json.loads(
        settings_path.read_text(encoding="utf-8")
    )


def load_watchlist(
    settings: dict,
) -> tuple[Path, pd.DataFrame]:
    watchlist_path = ROOT / settings.get(
        "watchlist_path",
        "config/watchlist.csv",
    )

    if not watchlist_path.exists():
        raise FileNotFoundError(
            f"Watchlist não encontrada: {watchlist_path}"
        )

    watchlist = pd.read_csv(watchlist_path)

    if watchlist.empty:
        raise RuntimeError(
            f"A watchlist está vazia: {watchlist_path}"
        )

    return watchlist_path, watchlist


ORIGIN_PORTFOLIO = "portfolio"
ORIGIN_WATCHLIST = "watchlist"
ORIGIN_UNIVERSE = "universe"

# Prioridade de proveniência quando um símbolo aparece em mais de um
# universo de origem: quem já é posição real (`portfolio`) importa mais
# operacionalmente do que "só" curiosidade de pesquisa (`watchlist`) ou
# candidato descoberto num screener amplo (`universe`, ainda não wireado
# neste merge). Hierarquia, não composição: cada linha carrega um único
# rótulo, o de maior prioridade entre os universos aos quais pertence --
# mais simples de consultar (`row["origin"] == "portfolio"`) do que um
# valor composto, e suficiente para as duas garantias que a proveniência
# precisa dar: o motor sell-only nunca deve agir fora de `portfolio`, e um
# screener de compra nunca deve apresentar uma posição já existente como
# candidata nova sem marcá-la.
ORIGIN_PRIORITY = (ORIGIN_PORTFOLIO, ORIGIN_WATCHLIST, ORIGIN_UNIVERSE)


def merge_watchlist_with_portfolio(
    watchlist: pd.DataFrame,
    settings: dict,
) -> pd.DataFrame:
    """
    A watchlist (`config/watchlist.csv`) é curada manualmente -- ativos que
    o usuário se interessou em acompanhar. A carteira real
    (`config/portfolio.csv`, gitignored) é populada a partir do arquivo de
    investimentos real do usuário. Os dois são fontes distintas e nenhum
    sobrescreve o outro em disco.

    Para que o motor de rebalance sell-only tenha um `CompanyReport` de
    cada posição real (`portfolio.pipeline.enrich_portfolio_from_analysis`
    só liga um holding a um `CompanyReport` do mesmo símbolo), o universo
    efetivamente coletado/pontuado nesta run precisa incluir também os
    símbolos da carteira -- só em memória, nunca gravado de volta em
    `watchlist.csv`. Símbolos já presentes na watchlist não são duplicados.

    Toda linha do resultado carrega uma coluna `origin` (`portfolio` ou
    `watchlist`, hierarquia `portfolio > watchlist`: um símbolo presente
    nos dois ganha `portfolio`, porque "eu possuo isso" é o fato mais
    relevante para decisão do que "eu me interessei por isso"). Motores de
    decisão a jusante (sell-only, screeners de compra) usam essa coluna
    para saber por que cada linha está sendo analisada -- nunca recomputam
    a proveniência a partir do zero.

    Ausência ou erro de leitura de `portfolio.csv` não interrompe a run:
    a análise segue apenas com a watchlist, como antes de a carteira
    existir.
    """
    result = watchlist.copy()
    if "origin" not in result.columns:
        result["origin"] = ORIGIN_WATCHLIST

    portfolio_path = ROOT / settings.get(
        "portfolio_path",
        "config/portfolio.csv",
    )
    if not portfolio_path.exists():
        return result

    try:
        portfolio = load_portfolio_csv(portfolio_path)
    except PortfolioError:
        logger.warning(
            "Não foi possível ler %s para incluir a carteira no universo "
            "analisado; seguindo apenas com a watchlist.",
            portfolio_path,
        )
        return result

    portfolio_symbols = {holding.symbol for holding in portfolio.holdings}

    existing_symbols = (
        result["symbol"].astype(str).str.strip().str.upper()
    )
    result.loc[
        existing_symbols.isin(portfolio_symbols), "origin"
    ] = ORIGIN_PORTFOLIO

    already_present = set(existing_symbols)
    extra_rows = [
        {
            "symbol": holding.symbol,
            "name": holding.symbol,
            "origin": ORIGIN_PORTFOLIO,
        }
        for holding in portfolio.holdings
        if holding.symbol not in already_present
    ]
    if not extra_rows:
        return result

    return pd.concat(
        [result, pd.DataFrame(extra_rows)],
        ignore_index=True,
    )


def collect_market_data(
    settings: dict,
    watchlist: pd.DataFrame,
    *,
    failures: list[str] | None = None,
) -> pd.DataFrame:
    logger.info(
        "Iniciando coleta de dados para %s empresas.",
        len(watchlist),
    )

    # `providers.yahoo.fetch_symbol` reconstrói cada linha do zero a partir
    # do que o Yahoo devolve -- qualquer coluna extra do `watchlist` de
    # entrada (como `origin`) não sobrevive à chamada. Reanexa por símbolo
    # (não por posição: falhas de fetch são só logadas e pulam a linha, então
    # `rows` não fica necessariamente alinhado 1:1 com `watchlist`).
    origin_by_symbol = (
        {
            str(symbol).strip().upper(): origin
            for symbol, origin in zip(
                watchlist.get("symbol", []),
                watchlist.get("origin", []),
            )
        }
        if "origin" in watchlist.columns
        else {}
    )

    rows = fetch_watchlist(
        watchlist,
        period=settings.get("history_period", "2y"),
        interval=settings.get("history_interval", "1d"),
        failures=failures,
    )

    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        row["origin"] = origin_by_symbol.get(symbol, ORIGIN_WATCHLIST)

    enriched = [
        compute_fundamentals(enrich_technicals(row))
        for row in rows
    ]

    df = pd.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key != "history"
            }
            for row in enriched
        ]
    )

    if df.empty:
        raise RuntimeError(
            "Nenhum dado foi coletado. "
            "Verifique a watchlist ou a conexão."
        )

    logger.info(
        "Coleta concluída: %s empresas retornadas.",
        len(df),
    )

    return df


def build_scores(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Iniciando normalização e scoring.")

    result = normalize_columns(df)

    result = score_dataframe(
        result,
        CONFIG / "model.yaml",
        CONFIG / "deal_breakers.json",
    )

    logger.info(
        "Scoring concluído para %s empresas.",
        len(result),
    )

    return result


def audit_feature_coverage(df: pd.DataFrame) -> dict:
    """
    Mede quanto do Investment Score está alocado a features cujas colunas
    nunca chegam populadas (peso fantasma = constante 50 neutro).

    Não altera o pipeline; apenas informa e registra um aviso.
    """

    coverage = audit_coverage(
        df,
        CONFIG / "features.yaml",
        CONFIG / "model.yaml",
    )

    summary = phantom_weight_summary(coverage)

    print()
    print(format_coverage_report(coverage, summary))

    phantom_share = summary["phantom_investment_share"]

    if phantom_share > 0:
        logger.warning(
            "Peso fantasma no Investment Score: %.1f%% "
            "(features sempre neutras por falta de dados).",
            phantom_share,
        )

    return summary


def save_history_snapshot(
    df: pd.DataFrame,
    snapshot_date: str,
    model_version: str = "legacy",
) -> str:
    with HistoryDatabase(HISTORY_DATABASE) as database:
        database.save_snapshot(
            df=df,
            snapshot_date=snapshot_date,
            model_version=model_version,
        )

    logger.info(
        "Snapshot histórico salvo em %s (model_version=%s).",
        snapshot_date,
        model_version,
    )

    return snapshot_date


def save_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeCaptureResult | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        logger.info("Outcome Analytics desabilitado.")
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        result = capture_outcome_snapshots(
            database,
            df,
            decision_date=snapshot_date,
            horizons_days=settings.get(
                "outcome_horizons_days"
            ),
        )

    logger.info(
        "Outcome snapshots salvos: %s; ignorados: %s.",
        result.saved_count,
        len(result.skipped_symbols),
    )
    return result


def evaluate_outcome_decisions(
    df: pd.DataFrame,
    snapshot_date: str,
    settings: dict,
) -> OutcomeEvaluationResult | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        result = evaluate_due_outcomes(
            database,
            df,
            evaluation_date=snapshot_date,
            horizons_days=settings.get(
                "outcome_horizons_days"
            ),
        )

    logger.info(
        "Outcome results avaliados: %s; pendentes: %s; sem preço: %s.",
        result.evaluated_count,
        result.pending_count,
        len(result.missing_price_symbols),
    )
    return result


def generate_outcome_analytics(
    settings: dict,
) -> OutcomeAnalyticsReport | None:
    if not settings.get(
        "outcome_analytics_enabled",
        True,
    ):
        return None

    with HistoryDatabase(HISTORY_DATABASE) as database:
        report = build_outcome_analytics_report(
            database,
            threshold_pct=settings.get(
                "outcome_hit_threshold_pct",
                0.0,
            ),
            bucket_size=settings.get(
                "outcome_calibration_bucket_size",
                20,
            ),
        )

    write_outcome_report(
        report,
        OUTCOME_REPORT_FILE,
    )

    logger.info(
        "Outcome Analytics: %s resultados elegíveis; hit rate %s.",
        report.hit_rate.eligible_count,
        report.hit_rate.hit_rate,
    )
    return report


def generate_universe_report(
    df: pd.DataFrame,
    settings: dict,
) -> UniverseReport | None:
    """Avalia e publica o universo sem filtrar o pipeline existente."""
    if not settings.get("universe_enabled", True):
        logger.info("Market Universe desabilitado.")
        return None

    policy_path = ROOT / settings.get(
        "universe_policy_path",
        "config/universe.yaml",
    )
    policy = load_universe_policy(policy_path)
    report = evaluate_universe(df, policy)
    write_universe_report(report, UNIVERSE_REPORT_FILE)

    logger.info(
        "Market Universe: %s elegíveis de %s; cobertura média %s%%.",
        report.eligible_count,
        report.total_count,
        report.average_data_coverage_pct,
    )
    return report


def generate_ranking_report(
    df: pd.DataFrame,
    settings: dict,
    universe_report: UniverseReport | None,
) -> RankingReport | None:
    """Publica ranking diagnóstico sem recalcular scores ou decisões."""
    if not settings.get("ranking_enabled", True):
        logger.info("Analytical Ranking desabilitado.")
        return None
    if universe_report is None:
        logger.warning(
            "Analytical Ranking ignorado: Universe Report indisponível."
        )
        return None

    policy_path = ROOT / settings.get(
        "ranking_policy_path",
        "config/ranking.yaml",
    )
    policy = load_ranking_policy(policy_path)
    report = rank_companies(df, universe_report, policy)
    write_ranking_report(report, RANKING_REPORT_FILE)
    logger.info(
        "Analytical Ranking: %s candidatos de %s empresas.",
        report.candidate_count,
        report.total_count,
    )
    return report


def generate_dashboard(
    df: pd.DataFrame,
    settings: dict,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
    universe_report: UniverseReport | None = None,
    priority_report: PriorityReport | None = None,
) -> Path | None:
    """
    Emite o contrato read-only do dashboard (output/dashboard.json).

    Pura agregação das visões que o Atlas já produziu nesta execução
    (mercado, empresas, carteira, outcomes e prioridade); não recomputa nem
    altera nada. Guardado por `dashboard_enabled` (default True).
    """
    if not settings.get("dashboard_enabled", True):
        return None

    view = build_dashboard_view(
        build_company_reports(df),
        market=universe_report,
        portfolio=portfolio_report,
        outcomes=outcome_report,
        priority=priority_report,
    )

    write_dashboard_view(view, DASHBOARD_REPORT_FILE)

    logger.info(
        "Dashboard contract gerado em %s (%s empresas).",
        DASHBOARD_REPORT_FILE,
        len(view.companies),
    )
    return DASHBOARD_REPORT_FILE


def generate_priority_report(
    settings: dict,
    *,
    ranking_report: RankingReport | None,
    portfolio_report: PortfolioReport | None,
) -> tuple[Path, PriorityReport] | None:
    """
    Classificação individual de prioridade de venda (carteira atual) e de
    compra (screener, quando o universo amplo já foi coletado). Não
    distribui peso nem aplica teto de setor -- apenas ordena por qualidade.
    Guardado por priority_enabled (default True).
    """
    if not settings.get("priority_enabled", True):
        return None

    weights_by_symbol: dict[str, float] = {}
    held_symbols: frozenset[str] | None = None

    if portfolio_report is not None:
        weights_by_symbol = dict(
            portfolio_report.allocation.get("by_symbol", {})
        )
        held_symbols = frozenset(weights_by_symbol)

    sell = build_sell_priority(
        ranking_report.to_dict()["companies"] if ranking_report else (),
        held_symbols=held_symbols,
        weights_by_symbol=weights_by_symbol,
    )

    buy = None
    if RESEARCH_RANKING_REPORT_FILE.exists():
        research_data = json.loads(
            RESEARCH_RANKING_REPORT_FILE.read_text(encoding="utf-8")
        )
        buy = build_buy_priority(
            research_data["companies"],
            held_symbols=held_symbols or frozenset(),
        )

    report = PriorityReport(sell=sell, buy=buy)
    write_priority_report(report, PRIORITY_REPORT_FILE)

    logger.info(
        "Priority Report: %s holdings classificados; %s candidatos de "
        "compra disponíveis.",
        len(sell.items),
        len(buy.items) if buy is not None else 0,
    )
    return PRIORITY_REPORT_FILE, report


def generate_excel_reports(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, Path | None]:
    logger.info("Gerando relatórios Excel.")

    history_file, latest_file = write_latest_and_history(
        df,
        OUTPUT,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    logger.info(
        "Excel histórico gerado em %s.",
        history_file,
    )

    return history_file, latest_file


def generate_morning_brief(
    df: pd.DataFrame,
    portfolio_report: PortfolioReport | None = None,
    outcome_report: OutcomeAnalyticsReport | None = None,
) -> tuple[Path, str]:
    logger.info("Gerando Morning Brief.")

    brief_path = write_morning_brief(
        current_df=df,
        database_path=HISTORY_DATABASE,
        output_path=MORNING_BRIEF_FILE,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    brief_text = render_morning_brief(
        current_df=df,
        database_path=HISTORY_DATABASE,
        portfolio_report=portfolio_report,
        outcome_report=outcome_report,
    )

    logger.info(
        "Morning Brief gerado em %s.",
        brief_path,
    )

    return brief_path, brief_text



def generate_portfolio_intelligence(
    df: pd.DataFrame,
    settings: dict,
    *,
    sell_rules_policy: SellRulesPolicy | None = None,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
) -> tuple[Path, PortfolioReport] | None:
    portfolio_path = ROOT / settings.get(
        "portfolio_path",
        "config/portfolio.csv",
    )

    if not portfolio_path.exists():
        logger.info(
            "Portfolio Intelligence ignorado: arquivo não encontrado em %s.",
            portfolio_path,
        )
        return None

    logger.info(
        "Executando Portfolio Intelligence com %s.",
        portfolio_path,
    )

    try:
        report = build_portfolio_intelligence(
            portfolio_path,
            df,
            portfolio_name=settings.get("portfolio_name"),
            cash=float(settings.get("portfolio_cash", 0.0)),
            currency=settings.get("portfolio_currency", "BRL"),
            rebalance_mode=settings.get(
                "portfolio_rebalance_mode", "sell_only"
            ),
            sell_rules_policy=sell_rules_policy,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=current_run_at,
        )
    except SellEngineBlockedError as exc:
        pending = ", ".join(exc.missing_thesis_symbols)
        logger.warning(
            "Motor de venda bloqueado -- posição(ões) sem tese registrada: "
            "%s. Screener/watchlist não são afetados; preencha "
            "config/portfolio.csv (coluna 'thesis') para destravar.",
            pending,
        )
        print()
        print(
            "AVISO: motor de venda bloqueado -- posição(ões) sem tese "
            f"registrada: {pending}"
        )
        return None

    report_path = write_portfolio_report(
        report,
        PORTFOLIO_REPORT_FILE,
    )

    logger.info(
        "Portfolio Intelligence concluído em %s.",
        report_path,
    )
    return report_path, report


def generate_watchlist_report(
    df: pd.DataFrame,
    settings: dict,
    *,
    previous_by_symbol: dict | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | None = None,
) -> tuple[Path, WatchlistReport] | None:
    """
    Independente do motor de venda estar bloqueado: watchlist tracking é uma
    preocupação separada de PR-020, nunca acoplada ao estado da carteira.
    """
    watchlist_path = ROOT / settings.get(
        "watchlist_path", "config/watchlist.csv"
    )

    if not watchlist_path.exists():
        logger.info(
            "Watchlist tracking ignorado: arquivo não encontrado em %s.",
            watchlist_path,
        )
        return None

    try:
        entries = load_watchlist_csv(watchlist_path)
    except WatchlistError as exc:
        logger.warning(
            "Não foi possível avaliar triggers da watchlist: %s",
            exc,
        )
        return None

    current_by_symbol = {
        str(row.get("symbol", "")).strip().upper(): normalize_current_row(
            row.to_dict()
        )
        for _, row in df.iterrows()
        if str(row.get("symbol", "")).strip()
    }

    results = evaluate_watchlist_triggers(
        entries,
        current_by_symbol,
        previous_by_symbol=previous_by_symbol,
        baseline_status=baseline_status,
        previous_run_at=previous_run_at,
        current_run_at=current_run_at,
    )

    aging_threshold_days = int(
        settings.get("watchlist_aging_threshold_days", 180)
    )
    last_triggered_value = (
        str(current_run_at)
        if current_run_at is not None
        else datetime.now().isoformat(timespec="seconds")
    )

    with HistoryDatabase(HISTORY_DATABASE) as database:
        trigger_history = database.load_watchlist_triggers()
        results = attach_aging(
            results,
            entries,
            trigger_history=trigger_history,
            aging_threshold_days=aging_threshold_days,
        )
        for result in results:
            if result.triggered_this_run:
                database.save_watchlist_trigger(
                    result.symbol,
                    result.trigger_condition,
                    last_triggered_value,
                )

    report = WatchlistReport(results=results)
    report_path = write_watchlist_report(report, WATCHLIST_REPORT_FILE)

    logger.info(
        "Watchlist tracking: %s trigger(s) disparado(s); %s sugestão(ões) "
        "de limpeza.",
        len(report.triggered),
        len(report.cleanup_candidates),
    )
    return report_path, report


def _safe_console_text(
    value: object,
    encoding: str | None = None,
) -> str:
    text = str(value)
    target_encoding = encoding or getattr(
        sys.stdout,
        "encoding",
        None,
    )
    if not target_encoding:
        return text
    return text.encode(
        target_encoding,
        errors="replace",
    ).decode(target_encoding)


def print_console_table(df: pd.DataFrame) -> None:
    columns = [
        "symbol",
        "Investment Score",
        "Opportunity Score",
        "Opportunity Rating",
        "Conviction Score",
        "Decision Rating",
        "Suggested Action",
        "Business Score",
        "Valuation Score",
        "Financial Score",
        "Timing Score",
        "Confidence Score",
        "Risk Penalty",
        "Recommendation",
    ]

    available_columns = [
        column
        for column in columns
        if column in df.columns
    ]

    print()

    if available_columns:
        table = (
            df[available_columns]
            .head(20)
            .to_string(index=False)
        )
        print(_safe_console_text(table))
    else:
        print(
            "[AVISO] Nenhuma coluna de resumo foi encontrada."
        )

    print()


def run_ticker_mode(symbol: str, settings: dict) -> Path:
    """
    Modo --ticker SYM: gera o one-pager de um símbolo (decomposição de
    score + histórico + tese, se for uma posição real).

    O Atlas pontua CROSS-SECIONALMENTE (percentil dentro do lote analisado,
    ver docs/SCORING_MODEL.md) -- pontuar o símbolo isolado faria todo
    percentil cair no neutro 50 (pct_rank exige >=2 valores para comparar).
    Por isso este modo reaproveita o MESMO lote analisado por --full/
    --portfolio (watchlist ∪ carteira), acrescentando o símbolo pedido se
    ele ainda não estiver lá -- não é um fetch leve de 1 símbolo, é o
    mesmo custo de --portfolio, só que renderiza apenas 1 one-pager no
    final.
    """
    symbol = symbol.strip().upper()
    logger.info("Modo --ticker: analisando %s dentro do lote watchlist+carteira.", symbol)

    watchlist_path, watchlist = load_watchlist(settings)
    analysis_universe = merge_watchlist_with_portfolio(watchlist, settings)

    existing_symbols = (
        analysis_universe["symbol"].astype(str).str.strip().str.upper()
    )
    if symbol not in set(existing_symbols):
        analysis_universe = pd.concat(
            [
                analysis_universe,
                pd.DataFrame([{"symbol": symbol, "name": symbol, "origin": "ticker"}]),
            ],
            ignore_index=True,
        )

    df = collect_market_data(settings, analysis_universe)
    df = build_scores(df)

    symbol_rows = df.index[
        df["symbol"].astype(str).str.strip().str.upper() == symbol
    ]
    if len(symbol_rows) == 0:
        raise RuntimeError(
            f"Não foi possível coletar dados de mercado para {symbol}."
        )
    position = symbol_rows[0]

    investment_score = None
    if "Investment Score" in df.columns:
        try:
            investment_score = float(df.loc[position, "Investment Score"])
        except (TypeError, ValueError):
            investment_score = None

    positive, negative = compute_symbol_contributions(
        df,
        symbol,
        CONFIG / "features.yaml",
        CONFIG / "model.yaml",
    )

    score_history = load_score_history(HISTORY_DATABASE)
    if not score_history.empty and "symbol" in score_history.columns:
        score_history = score_history.loc[
            score_history["symbol"].astype(str).str.upper() == symbol
        ]

    thesis = ""
    portfolio_path = ROOT / settings.get("portfolio_path", "config/portfolio.csv")
    if portfolio_path.exists():
        try:
            holding = load_portfolio_csv(portfolio_path).holding(symbol)
            if holding is not None:
                thesis = holding.thesis
        except PortfolioError:
            logger.warning(
                "Não foi possível ler %s para buscar a tese de %s.",
                portfolio_path,
                symbol,
            )

    company_name = str(df.loc[position].get("name", "") or "").strip() or symbol
    body = render_one_pager(
        symbol=symbol,
        company_name=company_name,
        investment_score=investment_score,
        positive=positive,
        negative=negative,
        score_history=score_history,
        thesis=thesis,
    )
    html = page_shell(f"Atlas One-Pager — {symbol}", body)

    date_stamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    path = write_one_pager(html, OUTPUT, symbol, date_stamp)
    print(f"One-pager de {symbol} gerado em {path}")
    logger.info("One-pager de %s gerado em %s.", symbol, path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Atlas Decision Intelligence Platform."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Universo + funil + carteira + watchlist (default).",
    )
    mode_group.add_argument(
        "--portfolio",
        action="store_true",
        help="Só carteira + watchlist, sem funil de screener.",
    )
    parser.add_argument(
        "--ticker",
        metavar="SYM",
        default=None,
        help="Analisa só um símbolo e gera o one-pager (ex.: --ticker MSFT).",
    )
    args = parser.parse_args()

    if args.ticker:
        mode = "ticker"
    elif args.portfolio:
        mode = "portfolio"
    else:
        mode = "full"

    metrics = ExecutionMetrics()

    logger.info("Iniciando Atlas (modo=%s).", mode)

    try:
        if mode == "ticker":
            settings = load_settings()
            run_ticker_mode(args.ticker, settings)
            return

        health_report = run_health_check(ROOT)
        print_health_report(health_report)

        settings = load_settings()

        watchlist_path, watchlist = load_watchlist(
            settings
        )
        analysis_universe = merge_watchlist_with_portfolio(
            watchlist, settings
        )

        print()
        print("=" * 70)
        print("ATLAS DECISION INTELLIGENCE PLATFORM")
        print("=" * 70)
        print(f"Watchlist       : {watchlist_path}")
        if len(analysis_universe) != len(watchlist):
            print(
                f"Carteira        : +{len(analysis_universe) - len(watchlist)} "
                "símbolo(s) da carteira real incluído(s) só nesta análise "
                "(watchlist.csv não é alterado)"
            )
        print(f"History DB      : {HISTORY_DATABASE}")
        print(f"Execution log   : {LOGS / 'atlas.log'}")
        print()

        fetch_failures: list[str] = []
        with StageTimer(metrics, "download_time"):
            df = collect_market_data(
                settings,
                analysis_universe,
                failures=fetch_failures,
            )

        metrics.companies = len(df)

        with StageTimer(metrics, "scoring_time"):
            df = build_scores(df)

        feature_coverage_summary = audit_feature_coverage(df)

        if mode == "full":
            universe_report = generate_universe_report(
                df,
                settings,
            )
            ranking_report = generate_ranking_report(
                df,
                settings,
                universe_report,
            )
            broad_market_report_path = OUTPUT / "research_ranking_report_market.json"
            adr_report_path = OUTPUT / "research_ranking_report_adr.json"
        else:
            universe_report = None
            ranking_report = None
            broad_market_report_path = None
            adr_report_path = None

        # Contexto de histórico calculado ANTES de gravar o snapshot deste
        # run: "run anterior" precisa ser o run anterior de verdade, nunca
        # este mesmo run que ainda está sendo computado.
        run_at = datetime.now()
        snapshot_date = run_at.isoformat(timespec="seconds")
        model_version = (
            str(load_yaml(CONFIG / "model.yaml").get("model_version", "legacy"))
            .strip()
            or "legacy"
        )
        score_history = load_score_history(HISTORY_DATABASE)
        previous_by_symbol, baseline_status, previous_run_at = (
            previous_run_context(
                score_history,
                current_snapshot_date=snapshot_date,
                current_model_version=model_version,
            )
        )
        sell_rules_policy = load_sell_rules_policy(
            CONFIG / "sell_rules.yaml"
        )

        # Anexa a quantidade real da carteira ao df analisado só para as
        # linhas origin=portfolio (símbolos fora da carteira ficam NaN) --
        # é o único jeito de comparar "quantidade deste run" vs. "quantidade
        # do run anterior" no motor de venda sem um arquivo de estado novo.
        portfolio_path_for_snapshot = ROOT / settings.get(
            "portfolio_path", "config/portfolio.csv"
        )
        if portfolio_path_for_snapshot.exists():
            try:
                quantity_by_symbol = {
                    holding.symbol: holding.quantity
                    for holding in load_portfolio_csv(
                        portfolio_path_for_snapshot
                    ).holdings
                }
                df["quantity"] = (
                    df["symbol"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .map(quantity_by_symbol)
                )
            except PortfolioError:
                logger.warning(
                    "Não foi possível ler %s para anexar quantity ao "
                    "snapshot histórico.",
                    portfolio_path_for_snapshot,
                )

        # Anexa se o símbolo foi candidato neste run (ranking_report já
        # computado acima) -- é o único jeito de comparar "quem é candidato
        # agora" vs. "quem era candidato no run anterior" (seção SCREENER do
        # relatório) sem recalcular ranking a partir do histórico.
        if ranking_report is not None:
            candidate_by_symbol = {
                company.symbol: bool(
                    company.safeguard_passed
                    and company.candidate_rank is not None
                )
                for company in ranking_report.companies
            }
            df["is_candidate"] = (
                df["symbol"]
                .astype(str)
                .str.strip()
                .str.upper()
                .map(candidate_by_symbol)
            )

        with StageTimer(metrics, "history_time"):
            save_history_snapshot(df, snapshot_date, model_version)
            outcome_capture = save_outcome_decisions(
                df,
                snapshot_date,
                settings,
            )
            outcome_evaluation = evaluate_outcome_decisions(
                df,
                snapshot_date,
                settings,
            )
            outcome_analytics = generate_outcome_analytics(
                settings
            )

        portfolio_result = generate_portfolio_intelligence(
            df,
            settings,
            sell_rules_policy=sell_rules_policy,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=snapshot_date,
        )
        portfolio_report = (
            portfolio_result[1]
            if portfolio_result is not None
            else None
        )

        watchlist_result = generate_watchlist_report(
            df,
            settings,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=snapshot_date,
        )
        watchlist_report = (
            watchlist_result[1]
            if watchlist_result is not None
            else None
        )

        portfolio_blocked_reason = None
        if (
            portfolio_result is None
            and portfolio_path_for_snapshot.exists()
        ):
            portfolio_blocked_reason = (
                "Motor de venda bloqueado -- posição(ões) sem tese "
                "registrada (ver aviso acima)."
            )

        report_context = build_report_context(
            mode=mode,
            df=df,
            snapshot_date=snapshot_date,
            previous_run_at=previous_run_at,
            baseline_status=baseline_status,
            previous_by_symbol=previous_by_symbol,
            rebalance=(
                portfolio_report.rebalance
                if portfolio_report is not None
                else None
            ),
            portfolio_blocked_reason=portfolio_blocked_reason,
            portfolio_warnings=(
                portfolio_report.warnings
                if portfolio_report is not None
                else ()
            ),
            watchlist_report=watchlist_report,
            ranking_report=ranking_report,
            universe_report=universe_report,
            fetch_failures=tuple(fetch_failures),
            phantom_weight_pct=feature_coverage_summary.get(
                "phantom_investment_share", 0.0
            ),
            status_md_text=_read_status_md(),
            holdings=(
                portfolio_report.holdings if portfolio_report is not None else ()
            ),
            score_history=score_history,
            features_path=CONFIG / "features.yaml",
            model_path=CONFIG / "model.yaml",
            broad_market_report_path=broad_market_report_path,
            adr_report_path=adr_report_path,
        )
        atlas_report_dated, atlas_report_latest = write_report(
            render_report(report_context),
            OUTPUT,
            run_at.strftime("%Y-%m-%d"),
        )

        with StageTimer(metrics, "reports_time"):
            history_file, latest_file = (
                generate_excel_reports(
                    df,
                    portfolio_report=portfolio_report,
                    outcome_report=outcome_analytics,
                )
            )

        with StageTimer(
            metrics,
            "morning_brief_time",
        ):
            brief_file, brief_text = (
                generate_morning_brief(
                    df,
                    portfolio_report=portfolio_report,
                    outcome_report=outcome_analytics,
                )
            )

        priority_result = generate_priority_report(
            settings,
            ranking_report=ranking_report,
            portfolio_report=portfolio_report,
        )
        priority_file, priority_report = (
            priority_result
            if priority_result is not None
            else (None, None)
        )

        dashboard_file = generate_dashboard(
            df,
            settings,
            portfolio_report=portfolio_report,
            outcome_report=outcome_analytics,
            universe_report=universe_report,
            priority_report=priority_report,
        )

        print_console_table(df)

        print(_safe_console_text(brief_text))
        print()

        print("=" * 70)
        print("ARQUIVOS GERADOS")
        print("=" * 70)
        print(f"Snapshot        : {snapshot_date}")
        print(f"SQLite          : {HISTORY_DATABASE}")
        print(f"Excel histórico : {history_file}")

        if latest_file is not None:
            print(f"Latest.xlsx     : {latest_file}")
        else:
            print(
                "Latest.xlsx     : não atualizado "
                "(arquivo provavelmente aberto)"
            )

        print(f"Morning Brief   : {brief_file}")

        if outcome_capture is not None:
            print(
                "Outcome Captures: "
                f"{outcome_capture.saved_count} "
                f"({', '.join(map(str, outcome_capture.horizons_days))} dias)"
            )
            if outcome_capture.skipped_symbols:
                print(
                    "Outcome Skipped : "
                    + ", ".join(
                        outcome_capture.skipped_symbols
                    )
                )

        if outcome_evaluation is not None:
            print(
                "Outcome Results : "
                f"{outcome_evaluation.evaluated_count} avaliados; "
                f"{outcome_evaluation.pending_count} pendentes"
            )
            if outcome_evaluation.missing_price_symbols:
                print(
                    "Outcome Prices  : ausentes para "
                    + ", ".join(
                        outcome_evaluation.missing_price_symbols
                    )
                )

        if outcome_analytics is not None:
            hit_rate = outcome_analytics.hit_rate
            print(
                "Outcome Hit Rate: "
                f"{hit_rate.hit_rate if hit_rate.hit_rate is not None else '-'}% "
                f"({hit_rate.hit_count}/{hit_rate.eligible_count})"
            )
            print(f"Outcome JSON    : {OUTCOME_REPORT_FILE}")

        if dashboard_file is not None:
            print(f"Dashboard JSON  : {dashboard_file}")

        if priority_file is not None:
            print(f"Priority JSON   : {priority_file}")

        if universe_report is not None:
            print(f"Universe JSON   : {UNIVERSE_REPORT_FILE}")
            print(
                "Universe        : "
                f"{universe_report.eligible_count}/"
                f"{universe_report.total_count} elegíveis; "
                f"cobertura {universe_report.average_data_coverage_pct}%"
            )

        if ranking_report is not None:
            print(f"Ranking JSON    : {RANKING_REPORT_FILE}")
            print(
                "Ranking         : "
                f"{ranking_report.candidate_count}/"
                f"{ranking_report.total_count} candidatos"
            )

        if portfolio_result is not None:
            portfolio_file, portfolio_report = portfolio_result
            print(f"Portfolio JSON  : {portfolio_file}")
            print(
                "Portfolio Score : "
                f"{portfolio_report.summary.get('quality_score')} "
                f"({portfolio_report.summary.get('quality_rating')})"
            )
        elif (
            ROOT / settings.get("portfolio_path", "config/portfolio.csv")
        ).exists():
            print(
                "Portfolio       : motor de venda bloqueado -- posição(ões) "
                "sem tese (ver aviso acima)"
            )
        else:
            print(
                "Portfolio       : não executado "
                "(config/portfolio.csv ausente)"
            )

        if watchlist_result is not None:
            watchlist_file, watchlist_report = watchlist_result
            print(f"Watchlist JSON  : {watchlist_file}")
            print(
                "Watchlist       : "
                f"{len(watchlist_report.triggered)} trigger(s) disparado(s); "
                f"{len(watchlist_report.cleanup_candidates)} sugestão(ões) "
                "de limpeza"
            )
            for triggered in watchlist_report.triggered:
                print(f"  [TRIGGER] {triggered.symbol} -- {triggered.message}")
            for candidate in watchlist_report.cleanup_candidates:
                print(
                    f"  [LIMPEZA?] {candidate.symbol} -- {candidate.age_days} "
                    "dias sem trigger"
                )

        print(f"Atlas Report    : {atlas_report_dated}")
        print(f"Atlas Latest    : {atlas_report_latest}")

        print("=" * 70)

        save_execution_metrics(
            metrics,
            EXECUTION_METRICS_FILE,
        )

        print_execution_metrics(metrics)

        logger.info(
            "Atlas concluído com sucesso em %.2f segundos.",
            metrics.total_time(),
        )

        print(
            f"Métricas salvas : {EXECUTION_METRICS_FILE}"
        )
        print()
        print("Atlas finalizado com sucesso.")

    except SystemExit:
        logger.error(
            "Execução interrompida pelo Health Check."
        )
        raise

    except Exception:
        logger.exception(
            "Falha durante a execução do Atlas."
        )
        raise


if __name__ == "__main__":
    main()
