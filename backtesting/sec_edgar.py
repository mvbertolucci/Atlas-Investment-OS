from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.request import Request, urlopen

from backtesting.point_in_time import HistoricalObservation


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL_TEMPLATE = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)

# Nome canônico do Atlas -> tags XBRL candidatas, em ordem de prioridade,
# cada uma com sua taxonomia. Mais de uma tag por campo porque a MESMA
# empresa pode trocar de tag ao longo dos anos (ex.: "Revenues" era comum
# até ~2018, quando muitas empresas migraram para
# "RevenueFromContractWithCustomerExcludingAssessedTax" com o novo padrão de
# reconhecimento de receita) -- todas as candidatas são extraídas e
# mescladas, não apenas a primeira com dado, para não perder parte da
# história de uma empresa que atravessou essa troca. "shares_outstanding"
# normalmente vive na taxonomia "dei", não "us-gaap".
#
# Deliberadamente ainda não cobre TODOS os ~25 campos fundamentalistas do
# Atlas -- conceitos derivados que não são tag nativa da SEC (EBIT, Working
# Capital) e múltiplos de valuation (exigem uma série de PREÇO, que a SEC
# não tem) ficam para incremento futuro documentado, nunca aproximados
# silenciosamente aqui. "operating_income" é mantido com esse nome (não
# renomeado para "ebit") para que a decisão de usá-lo como proxy de EBIT
# fique explícita e visível para quem for consumir este dado.
FIELD_TAG_CANDIDATES: dict[str, tuple[tuple[str, str], ...]] = {
    "total_assets": (("us-gaap", "Assets"),),
    "net_income": (("us-gaap", "NetIncomeLoss"),),
    "total_revenue": (
        ("us-gaap", "Revenues"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "SalesRevenueNet"),
    ),
    "current_assets": (("us-gaap", "AssetsCurrent"),),
    "current_liabilities": (("us-gaap", "LiabilitiesCurrent"),),
    "gross_profit": (("us-gaap", "GrossProfit"),),
    "long_term_debt": (
        ("us-gaap", "LongTermDebtNoncurrent"),
        ("us-gaap", "LongTermDebt"),
    ),
    # Parcela circulante da dívida de longo prazo + empréstimos/notas de
    # curto prazo -- ausentes até aqui, faziam invested_capital/
    # debt_to_equity do point-in-time subestimarem a dívida total frente ao
    # "Invested Capital"/"Total Debt" que o Yahoo já reporta prontos (medido:
    # ROIC point-in-time saía sistematicamente 2-4 p.p. ACIMA do ao vivo em
    # 3 empresas reais, mesma direção nas 3 -- capital investido menor no
    # denominador). Ausente no filing (não apenas não mapeado) é tratado
    # como zero em derive_point_in_time_ratios, não como dado faltante --
    # a maioria das empresas de fato não carrega uma das duas linhas.
    "long_term_debt_current": (
        ("us-gaap", "LongTermDebtCurrent"),
    ),
    "short_term_debt": (
        ("us-gaap", "ShortTermBorrowings"),
        ("us-gaap", "DebtCurrent"),
    ),
    "retained_earnings": (
        ("us-gaap", "RetainedEarningsAccumulatedDeficit"),
    ),
    "total_liabilities": (("us-gaap", "Liabilities"),),
    "interest_expense": (("us-gaap", "InterestExpense"),),
    "operating_cash_flow": (
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ),
    "cash_and_equivalents": (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    ),
    "tax_provision": (("us-gaap", "IncomeTaxExpenseBenefit"),),
    "pretax_income": (
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ),
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
    ),
    "repurchase_of_stock": (
        ("us-gaap", "PaymentsForRepurchaseOfCommonStock"),
    ),
    "operating_income": (("us-gaap", "OperatingIncomeLoss"),),
    "shares_outstanding": (
        ("dei", "EntityCommonStockSharesOutstanding"),
        ("us-gaap", "CommonStockSharesOutstanding"),
    ),
    "capital_expenditures": (
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ),
    "depreciation_and_amortization": (
        ("us-gaap", "DepreciationDepletionAndAmortization"),
        ("us-gaap", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"),
        ("us-gaap", "Depreciation"),
    ),
    "dividends_paid": (
        ("us-gaap", "PaymentsOfDividends"),
        ("us-gaap", "PaymentsOfDividendsCommonStock"),
    ),
}

_ACCEPTED_FORM_PREFIXES = ("10-K", "10-Q")


def _text(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} não pode ser vazio.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} não pode ser vazio.")
    return text


def available_at_from_filed(filed: str) -> str:
    """
    Convenção conservadora de disponibilidade: a SEC só dá a DATA de
    arquivamento (`filed`), não um horário intradiário exato. Para nunca
    arriscar vazamento no mesmo dia, o conteúdo de um filing é tratado como
    disponível a partir da meia-noite UTC do dia SEGUINTE ao arquivamento.
    """
    filed_date = date.fromisoformat(filed)
    available = datetime.combine(
        filed_date + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return available.isoformat()


def parse_ticker_cik_map(payload: dict[str, Any]) -> dict[str, str]:
    """
    Converte o payload de `company_tickers.json` (dict de índices numéricos
    para {cik_str, ticker, title}) em um mapa ticker (maiúsculo) -> CIK
    zero-padded de 10 dígitos.
    """
    mapping: dict[str, str] = {}
    for entry in payload.values():
        ticker = _text(entry.get("ticker"), "ticker").upper()
        cik = _text(entry.get("cik_str"), "cik_str").zfill(10)
        mapping[ticker] = cik
    return mapping


def fetch_ticker_cik_map(
    *,
    user_agent: str,
    url: str = SEC_TICKERS_URL,
) -> dict[str, str]:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_ticker_cik_map(payload)


def fetch_company_facts(
    cik: str,
    *,
    user_agent: str,
    url_template: str = SEC_COMPANYFACTS_URL_TEMPLATE,
) -> dict[str, Any]:
    url = url_template.format(cik=_text(cik, "cik").zfill(10))
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_observations(
    symbol: str,
    company_facts: dict[str, Any],
    *,
    field_tag_candidates: dict[
        str, tuple[tuple[str, str], ...]
    ] = FIELD_TAG_CANDIDATES,
) -> tuple[HistoricalObservation, ...]:
    """
    Converte um subconjunto de tags XBRL nativos de um payload companyfacts
    em HistoricalObservation. Só os campos em `field_tag_candidates` são
    extraídos -- um conceito ausente dessa lista fica simplesmente ausente,
    nunca aproximado.

    Para cada campo canônico, TODAS as tags candidatas (podendo vir de
    taxonomias diferentes) são extraídas e mescladas -- não apenas a
    primeira com dado -- porque a mesma empresa pode ter usado tags
    diferentes em períodos diferentes da sua história (ex.: troca de tag de
    receita em ~2018). Cada revisão (accn) vira sua própria observação
    versionada; `available_at` usa a convenção conservadora de
    `available_at_from_filed`.

    Restrito a formulários 10-K/10-Q (o núcleo periódico) -- outros tipos de
    filing que carregam XBRL (ex.: exibições de 8-K) ficam de fora nesta
    fatia.

    Uma entrada individual cujo `end` (período) fica depois do `filed`
    (`HistoricalObservation` recusa isso -- não dá pra saber de um período
    antes de ele existir) é descartada só ELA, não a extração inteira.
    Medido contra 128 símbolos reais que falhavam na composição de
    market_cap: 78 tinham essa violação isolada num único campo (ex.:
    `total_assets` da AGM, `dividends_paid` da ALGT) que antes abortava a
    extração de TODOS os ~17 campos rastreados da mesma empresa --
    inclusive campos sem nenhum problema, como `shares_outstanding` da
    própria empresa. Isso contradizia o princípio já documentado aqui
    ("conceito ausente fica simplesmente ausente") -- um ponto de dado
    esquisito virava ausência de tudo, não só daquele ponto.
    """
    symbol = _text(symbol, "symbol").upper()
    facts_by_taxonomy = company_facts.get("facts", {})
    observations: list[HistoricalObservation] = []
    seen_identities: set[tuple[str, str, str, str]] = set()

    for field_name, candidates in field_tag_candidates.items():
        for taxonomy, tag in candidates:
            concept = facts_by_taxonomy.get(taxonomy, {}).get(tag)
            if not concept:
                continue

            for unit_entries in concept.get("units", {}).values():
                for entry in unit_entries:
                    required = ("end", "val", "filed", "accn", "form")
                    if any(key not in entry for key in required):
                        continue

                    form = str(entry["form"])
                    if not form.startswith(_ACCEPTED_FORM_PREFIXES):
                        continue

                    revision_id = str(entry["accn"])
                    identity = (
                        symbol,
                        field_name,
                        str(entry["end"]),
                        revision_id,
                    )
                    if identity in seen_identities:
                        continue
                    seen_identities.add(identity)

                    try:
                        observation = HistoricalObservation(
                            symbol=symbol,
                            field_name=field_name,
                            value=entry["val"],
                            observed_on=entry["end"],
                            available_at=available_at_from_filed(
                                str(entry["filed"])
                            ),
                            source=f"SEC EDGAR ({form}, {taxonomy}:{tag})",
                            revision_id=revision_id,
                        )
                    except ValueError:
                        # available_at antes de observed_on -- entrada
                        # isolada malformada, tratada como ausente (ver
                        # docstring); não aborta os demais campos.
                        continue
                    observations.append(observation)

    return tuple(observations)
