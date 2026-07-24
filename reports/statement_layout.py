"""
Ordem canônica das demonstrações financeiras.

O provedor (yfinance) devolve as linhas em ordem praticamente invertida -- a DRE
começa em "Tax Effect Of Unusual Items" e termina em "Total Revenue". Exibir
assim é ilegível: nenhuma demonstração real é lida de baixo para cima.

Este módulo declara a ordem de apresentação usada nos formulários da SEC
(10-K/10-Q): receita no topo descendo até o lucro líquido; ativo, passivo e
patrimônio líquido na sequência do balanço; caixa separado em operacional,
investimento e financiamento.

Os rótulos permanecem os originais da fonte -- são os nomes canônicos das linhas
e é assim que aparecem no filing. Só os títulos de seção são traduzidos.

Regra de segurança: **nada é descartado**. Linha que a fonte traga e que não
esteja mapeada aqui cai na seção final "Outras linhas", para que o documento
continue sendo o retrato completo do que foi coletado.
"""
from __future__ import annotations

INCOME_STATEMENT = (
    ("Receita", ("Total Revenue", "Operating Revenue")),
    (
        "Custo e lucro bruto",
        ("Cost Of Revenue", "Reconciled Cost Of Revenue", "Gross Profit"),
    ),
    (
        "Despesas operacionais",
        (
            "Research And Development",
            "Selling General And Administration",
            "Operating Expense",
            "Total Expenses",
        ),
    ),
    (
        "Resultado operacional",
        (
            "Operating Income",
            "Total Operating Income As Reported",
            "EBIT",
            "EBITDA",
            "Normalized EBITDA",
        ),
    ),
    (
        "Resultado financeiro",
        (
            "Interest Expense",
            "Interest Expense Non Operating",
            "Net Interest Income",
            "Net Non Operating Interest Income Expense",
        ),
    ),
    (
        "Outras receitas e despesas",
        (
            "Other Income Expense",
            "Other Non Operating Income Expenses",
            "Special Income Charges",
            "Gain On Sale Of Business",
            "Impairment Of Capital Assets",
            "Earnings From Equity Interest Net Of Tax",
        ),
    ),
    ("Resultado antes de impostos", ("Pretax Income",)),
    (
        "Impostos",
        ("Tax Provision", "Tax Rate For Calcs", "Tax Effect Of Unusual Items"),
    ),
    (
        "Lucro líquido",
        (
            "Net Income Continuous Operations",
            "Net Income Discontinuous Operations",
            "Net Income Including Noncontrolling Interests",
            "Minority Interests",
            "Net Income",
            "Net Income Common Stockholders",
            "Net Income From Continuing Operation Net Minority Interest",
            "Net Income From Continuing And Discontinued Operation",
            "Diluted NI Availto Com Stockholders",
            "Normalized Income",
        ),
    ),
    (
        "Por ação",
        ("Basic EPS", "Diluted EPS", "Basic Average Shares", "Diluted Average Shares"),
    ),
    (
        "Itens não recorrentes e reconciliação",
        (
            "Total Unusual Items",
            "Total Unusual Items Excluding Goodwill",
            "Reconciled Depreciation",
        ),
    ),
)

BALANCE_SHEET = (
    (
        "ATIVO — Circulante",
        (
            "Cash And Cash Equivalents",
            "Other Short Term Investments",
            "Cash Cash Equivalents And Short Term Investments",
            "Gross Accounts Receivable",
            "Allowance For Doubtful Accounts Receivable",
            "Accounts Receivable",
            "Taxes Receivable",
            "Other Receivables",
            "Receivables",
            "Raw Materials",
            "Work In Process",
            "Finished Goods",
            "Inventories Adjustments Allowances",
            "Inventory",
            "Prepaid Assets",
            "Other Current Assets",
            "Current Assets",
        ),
    ),
    (
        "ATIVO — Não circulante",
        (
            "Properties",
            "Machinery Furniture Equipment",
            "Other Properties",
            "Construction In Progress",
            "Leases",
            "Gross PPE",
            "Accumulated Depreciation",
            "Net PPE",
            "Goodwill",
            "Other Intangible Assets",
            "Goodwill And Other Intangible Assets",
            "Long Term Equity Investment",
            "Available For Sale Securities",
            "Investmentin Financial Assets",
            "Investments And Advances",
            "Non Current Deferred Taxes Assets",
            "Non Current Deferred Assets",
            "Other Non Current Assets",
            "Total Non Current Assets",
        ),
    ),
    ("ATIVO TOTAL", ("Total Assets",)),
    (
        "PASSIVO — Circulante",
        (
            "Accounts Payable",
            "Income Tax Payable",
            "Total Tax Payable",
            "Payables",
            "Current Accrued Expenses",
            "Payables And Accrued Expenses",
            "Other Current Borrowings",
            "Current Debt",
            "Current Capital Lease Obligation",
            "Current Debt And Capital Lease Obligation",
            "Current Deferred Revenue",
            "Current Deferred Liabilities",
            "Other Current Liabilities",
            "Current Liabilities",
        ),
    ),
    (
        "PASSIVO — Não circulante",
        (
            "Long Term Debt",
            "Long Term Capital Lease Obligation",
            "Long Term Debt And Capital Lease Obligation",
            "Non Current Deferred Taxes Liabilities",
            "Non Current Deferred Liabilities",
            "Other Non Current Liabilities",
            "Total Non Current Liabilities Net Minority Interest",
        ),
    ),
    ("PASSIVO TOTAL", ("Total Liabilities Net Minority Interest",)),
    (
        "PATRIMÔNIO LÍQUIDO",
        (
            "Preferred Stock",
            "Common Stock",
            "Capital Stock",
            "Additional Paid In Capital",
            "Retained Earnings",
            "Other Equity Adjustments",
            "Gains Losses Not Affecting Retained Earnings",
            "Stockholders Equity",
            "Minority Interest",
            "Total Equity Gross Minority Interest",
            "Common Stock Equity",
            "Total Capitalization",
        ),
    ),
    ("Ações", ("Share Issued", "Ordinary Shares Number")),
    (
        "Medidas derivadas",
        (
            "Working Capital",
            "Invested Capital",
            "Tangible Book Value",
            "Net Tangible Assets",
            "Capital Lease Obligations",
            "Total Debt",
            "Net Debt",
        ),
    ),
)

CASH_FLOW = (
    (
        "ATIVIDADES OPERACIONAIS",
        (
            "Net Income From Continuing Operations",
            "Depreciation And Amortization",
            "Depreciation Amortization Depletion",
            "Stock Based Compensation",
            "Deferred Income Tax",
            "Deferred Tax",
            "Asset Impairment Charge",
            "Provisionand Write Offof Assets",
            "Amortization Of Securities",
            "Unrealized Gain Loss On Investment Securities",
            "Gain Loss On Sale Of PPE",
            "Gain Loss On Sale Of Business",
            "Net Foreign Currency Exchange Gain Loss",
            "Earnings Losses From Equity Investments",
            "Operating Gains Losses",
            "Other Non Cash Items",
            "Changes In Account Receivables",
            "Change In Receivables",
            "Change In Inventory",
            "Change In Prepaid Assets",
            "Change In Account Payable",
            "Change In Payable",
            "Change In Payables And Accrued Expense",
            "Change In Other Current Liabilities",
            "Change In Working Capital",
            "Cash Flow From Continuing Operating Activities",
            "Operating Cash Flow",
        ),
    ),
    (
        "ATIVIDADES DE INVESTIMENTO",
        (
            "Capital Expenditure Reported",
            "Purchase Of PPE",
            "Sale Of PPE",
            "Net PPE Purchase And Sale",
            "Purchase Of Intangibles",
            "Net Intangibles Purchase And Sale",
            "Purchase Of Business",
            "Sale Of Business",
            "Net Business Purchase And Sale",
            "Purchase Of Investment",
            "Sale Of Investment",
            "Net Investment Purchase And Sale",
            "Net Other Investing Changes",
            "Cash Flow From Continuing Investing Activities",
            "Investing Cash Flow",
        ),
    ),
    (
        "ATIVIDADES DE FINANCIAMENTO",
        (
            "Long Term Debt Issuance",
            "Long Term Debt Payments",
            "Net Long Term Debt Issuance",
            "Net Issuance Payments Of Debt",
            "Common Stock Issuance",
            "Net Common Stock Issuance",
            "Proceeds From Stock Option Exercised",
            "Net Other Financing Charges",
            "Cash Flow From Continuing Financing Activities",
            "Financing Cash Flow",
        ),
    ),
    (
        "VARIAÇÃO DE CAIXA",
        (
            "Changes In Cash",
            "Effect Of Exchange Rate Changes",
            "Beginning Cash Position",
            "End Cash Position",
        ),
    ),
    (
        "Informação suplementar",
        (
            "Income Tax Paid Supplemental Data",
            "Interest Paid Supplemental Data",
            "Capital Expenditure",
            "Issuance Of Capital Stock",
            "Issuance Of Debt",
            "Repayment Of Debt",
            "Free Cash Flow",
        ),
    ),
)

LAYOUTS = {
    "_income_statement": INCOME_STATEMENT,
    "_balance_sheet": BALANCE_SHEET,
    "_cashflow": CASH_FLOW,
}

# Linhas de fechamento -- destacadas em negrito, como num filing.
TOTAL_LINES = frozenset({
    "Total Revenue", "Gross Profit", "Operating Income", "Pretax Income",
    "Net Income", "Net Income Common Stockholders", "EBITDA", "EBIT",
    "Basic EPS", "Diluted EPS",
    "Current Assets", "Total Non Current Assets", "Total Assets",
    "Current Liabilities", "Total Non Current Liabilities Net Minority Interest",
    "Total Liabilities Net Minority Interest", "Stockholders Equity",
    "Total Equity Gross Minority Interest",
    "Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow",
    "Changes In Cash", "End Cash Position", "Free Cash Flow",
})


def order_statement(
    statement_key: str, labels: list[str]
) -> list[tuple[str | None, str]]:
    """Devolve [(seção ou None, rótulo)] na ordem de apresentação da SEC.

    Só inclui rótulos que a fonte de fato trouxe; rótulos não mapeados vão para
    "Outras linhas" no fim, preservando o retrato completo.
    """
    layout = LAYOUTS.get(statement_key)
    available = list(labels)
    if not layout:
        return [(None, label) for label in available]

    remaining = set(available)
    ordered: list[tuple[str | None, str]] = []
    for section, lines in layout:
        present = [line for line in lines if line in remaining]
        if not present:
            continue
        for position, line in enumerate(present):
            ordered.append((section if position == 0 else None, line))
            remaining.discard(line)

    leftovers = [label for label in available if label in remaining]
    for position, label in enumerate(leftovers):
        ordered.append(("Outras linhas" if position == 0 else None, label))
    return ordered
