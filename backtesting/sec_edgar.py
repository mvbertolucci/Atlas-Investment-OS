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
TAXONOMY = "us-gaap"

# Tags XBRL nativos mapeados para o nome canônico do Atlas. Deliberadamente
# pequeno e só de conceitos NATIVOS para esta primeira fatia -- conceitos
# derivados (EBIT, Working Capital não existem como tag da SEC) e múltiplos
# de valuation (que exigem uma série de PREÇO, que a SEC não tem) ficam para
# um incremento futuro documentado, nunca aproximados silenciosamente aqui.
TAG_TO_FIELD = {
    "Assets": "total_assets",
    "NetIncomeLoss": "net_income",
    "Revenues": "total_revenue",
    "AssetsCurrent": "current_assets",
    "LiabilitiesCurrent": "current_liabilities",
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
    tag_to_field: dict[str, str] = TAG_TO_FIELD,
    taxonomy: str = TAXONOMY,
) -> tuple[HistoricalObservation, ...]:
    """
    Converte um subconjunto de tags XBRL nativos de um payload companyfacts
    em HistoricalObservation. Só as tags em `tag_to_field` são extraídas --
    um conceito ausente dessa lista fica simplesmente ausente, nunca
    aproximado. Cada revisão (accn) vira sua própria observação versionada;
    `available_at` usa a convenção conservadora de `available_at_from_filed`.

    Restrito a formulários 10-K/10-Q (o núcleo periódico) -- outros tipos de
    filing que carregam XBRL (ex.: exibições de 8-K) ficam de fora nesta
    fatia.
    """
    symbol = _text(symbol, "symbol").upper()
    facts = company_facts.get("facts", {}).get(taxonomy, {})
    observations: list[HistoricalObservation] = []
    seen_identities: set[tuple[str, str, str, str]] = set()

    for tag, field_name in tag_to_field.items():
        concept = facts.get(tag)
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
                identity = (symbol, field_name, str(entry["end"]), revision_id)
                if identity in seen_identities:
                    continue
                seen_identities.add(identity)

                observations.append(
                    HistoricalObservation(
                        symbol=symbol,
                        field_name=field_name,
                        value=entry["val"],
                        observed_on=entry["end"],
                        available_at=available_at_from_filed(str(entry["filed"])),
                        source=f"SEC EDGAR ({form})",
                        revision_id=revision_id,
                    )
                )

    return tuple(observations)
