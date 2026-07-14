from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Font, PatternFill

from reports.research_common import company_status

ROOT = Path(__file__).resolve().parent.parent

# (sufixo do arquivo, nome de exibição) -- mesma convenção de
# portfolio.model_portfolio._labeled_filename.
DEFAULT_SCREENERS: tuple[tuple[str, str], ...] = (
    ("", "S&P 500"),
    ("market", "Mercado Amplo"),
    ("adr", "ADR"),
)

_HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")


def _labeled_path(output_dir: Path, base_name: str, label: str) -> Path:
    if not label:
        return output_dir / base_name
    stem, _, suffix = base_name.rpartition(".")
    return output_dir / f"{stem}_{label}.{suffix}"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _summary_row(screener_name: str, ranking: dict[str, Any], portfolio: dict[str, Any] | None) -> dict[str, Any]:
    summary = ranking.get("summary", {})
    row: dict[str, Any] = {
        "Screener": screener_name,
        "Gerado em": ranking.get("generated_at"),
        "Analisados": summary.get("total_count", 0),
        "Elegíveis": summary.get("universe_eligible_count", 0),
        "Candidatos": summary.get("candidate_count", 0),
    }
    for reason, count in (summary.get("blocked_by_reason") or {}).items():
        row[f"Bloq.: {reason}"] = count
    if portfolio is not None:
        portfolio_summary = portfolio.get("summary", {})
        row["Posições na carteira"] = portfolio_summary.get("position_count", 0)
        row["Peso investido"] = portfolio_summary.get("invested_weight", 0.0)
    return row


def _companies_dataframe(ranking: dict[str, Any], screener_name: str) -> pd.DataFrame:
    rows = []
    for company in ranking.get("companies", []):
        label, _ = company_status(company)
        rows.append(
            {
                "Screener": screener_name,
                "Rank": company.get("market_rank"),
                "Símbolo": company.get("symbol"),
                "Setor": company.get("sector"),
                "Investment Score": company.get("investment_score"),
                "Opportunity Score": company.get("opportunity_score"),
                "Conviction Score": company.get("conviction_score"),
                "Confidence Score": company.get("confidence_score"),
                "Status": label,
                "Já detida": bool(company.get("already_held")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            "Rank", na_position="last", key=lambda s: s.fillna(10**9)
        ).reset_index(drop=True)
    return df


def _positions_dataframe(portfolio: dict[str, Any], screener_name: str) -> pd.DataFrame:
    rows = [
        {
            "Screener": screener_name,
            "Rank": position.get("candidate_rank"),
            "Símbolo": position.get("symbol"),
            "Nome": position.get("name"),
            "Setor": position.get("sector"),
            "Indústria": position.get("industry"),
            "Peso": position.get("target_weight"),
            "Investment Score": position.get("investment_score"),
            "Preço ref.": position.get("reference_price"),
        }
        for position in portfolio.get("positions", [])
    ]
    return pd.DataFrame(rows)


def _style_sheet(writer: pd.ExcelWriter, sheet_name: str, percent_columns: tuple[str, ...] = ()) -> None:
    worksheet = writer.sheets.get(sheet_name)
    if worksheet is None or worksheet.max_row < 1:
        return

    for cell in worksheet[1]:
        cell.font = Font(
            name=cell.font.name or "Calibri",
            size=cell.font.size or 11,
            bold=True,
            color="FFFFFF",
        )
        cell.fill = _HEADER_FILL

    headers = {cell.value: cell.column for cell in worksheet[1]}
    for header in percent_columns:
        column = headers.get(header)
        if column is None:
            continue
        for row in range(2, worksheet.max_row + 1):
            worksheet.cell(row=row, column=column).number_format = "0.0%"

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    worksheet.sheet_view.showGridLines = False

    for column_cells in worksheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter
        for cell in column_cells:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        worksheet.column_dimensions[column_letter].width = min(max_length + 2, 40)


def build_combined_workbook(
    screeners: tuple[tuple[str, str], ...],
    output_dir: Path,
    output_path: Path,
) -> Path:
    """
    Junta os 3 screeners (S&P 500, Mercado Amplo, ADR) num único workbook:
    Resumo (estatísticas por screener), Carteira Modelo (as posições
    sugeridas das 3, empilhadas com uma coluna Screener) e Todos os Itens
    (toda empresa analisada em qualquer um dos 3, mesma coisa). Lê os JSON
    já gerados por portfolio.model_portfolio -- não recalcula nada; screener
    sem coleta feita ainda é simplesmente omitido (não é erro).
    """
    summary_rows: list[dict[str, Any]] = []
    position_frames: list[pd.DataFrame] = []
    company_frames: list[pd.DataFrame] = []

    for label, screener_name in screeners:
        ranking = _load_json(_labeled_path(output_dir, "research_ranking_report.json", label))
        if ranking is None:
            continue
        portfolio = _load_json(_labeled_path(output_dir, "model_portfolio_report.json", label))

        summary_rows.append(_summary_row(screener_name, ranking, portfolio))
        company_frames.append(_companies_dataframe(ranking, screener_name))
        if portfolio is not None:
            position_frames.append(_positions_dataframe(portfolio, screener_name))

    if not summary_rows:
        raise FileNotFoundError(
            "Nenhum research_ranking_report*.json encontrado em "
            f"{output_dir} -- rode portfolio.model_portfolio primeiro."
        )

    summary_df = pd.DataFrame(summary_rows)
    positions_df = (
        pd.concat(position_frames, ignore_index=True)
        if position_frames
        else pd.DataFrame()
    )
    companies_df = (
        pd.concat(company_frames, ignore_index=True)
        if company_frames
        else pd.DataFrame()
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Resumo", index=False)
        positions_df.to_excel(writer, sheet_name="Carteira Modelo", index=False)
        companies_df.to_excel(writer, sheet_name="Todos os Itens", index=False)

        _style_sheet(writer, "Resumo", percent_columns=("Peso investido",))
        _style_sheet(writer, "Carteira Modelo", percent_columns=("Peso",))
        _style_sheet(writer, "Todos os Itens")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Junta os 3 rankings amplos (S&P 500, Mercado Amplo, ADR) num "
            "único Excel navegável -- não recalcula nada, só formata o que "
            "portfolio.model_portfolio já gerou."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "output"),
        help="Diretório onde estão os research_ranking_report*.json.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Caminho do arquivo Excel de saída. Default: "
        "<output-dir>/research_screeners_combined.xlsx.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_path = (
        Path(args.output)
        if args.output
        else output_dir / "research_screeners_combined.xlsx"
    )
    result = build_combined_workbook(DEFAULT_SCREENERS, output_dir, output_path)
    print(f"Excel combinado gerado em {result}")


if __name__ == "__main__":
    main()
