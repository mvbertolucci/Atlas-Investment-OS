from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from reports.report_models import CompanyReport

from portfolio.validators import (
    normalize_items,
    normalize_mapping,
    normalize_non_negative_float,
    normalize_positive_float,
    normalize_score,
    normalize_symbol,
    normalize_text,
    normalize_weight,
    validate_weight_total,
)


@dataclass(frozen=True)
class Holding:
    """
    Representa uma posição individual da carteira.

    O modelo não depende de pandas e pode consumir opcionalmente
    um CompanyReport produzido pela camada de análise do Atlas.
    """

    symbol: str
    quantity: float
    average_price: float

    current_price: float | None = None
    portfolio_weight: float | None = None

    sector: str = ""
    industry: str = ""
    country: str = ""
    currency: str = "USD"
    notes: str = ""
    entry_date: date | str | None = None
    thesis: str = ""
    thesis_updated_at: date | str | None = None

    # Proveniência do universo analisado (run_all.merge_watchlist_with_portfolio):
    # "" quando desconhecida (holding ainda não ligado a uma linha do
    # DataFrame analisado), ou o valor exato daquela linha ("portfolio",
    # "watchlist", "universe"). portfolio.rebalance.build_sell_only_plan usa
    # isto para nunca agir sobre um holding cuja origem conhecida não seja
    # "portfolio" -- defesa em profundidade contra um Portfolio construído
    # incorretamente a partir de um símbolo que não é uma posição real.
    origin: str = ""

    company_report: CompanyReport | None = None

    def __post_init__(self) -> None:
        symbol = normalize_symbol(self.symbol)

        if not symbol:
            raise ValueError(
                "Holding exige um símbolo válido."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(
            self,
            "quantity",
            normalize_positive_float(
                self.quantity,
                field_name="quantity",
            ),
        )
        object.__setattr__(
            self,
            "average_price",
            normalize_non_negative_float(
                self.average_price,
                field_name="average_price",
            ),
        )
        object.__setattr__(
            self,
            "current_price",
            normalize_non_negative_float(
                self.current_price,
                field_name="current_price",
                allow_none=True,
            ),
        )
        object.__setattr__(
            self,
            "portfolio_weight",
            normalize_weight(
                self.portfolio_weight,
                field_name="portfolio_weight",
            ),
        )

        for field_name in [
            "sector",
            "industry",
            "country",
            "currency",
            "notes",
            "thesis",
            "origin",
        ]:
            value = normalize_text(
                getattr(self, field_name)
            )

            if field_name == "currency":
                value = (value or "USD").upper()

            object.__setattr__(
                self,
                field_name,
                value,
            )

        for date_field_name in ("entry_date", "thesis_updated_at"):
            raw_value = getattr(self, date_field_name)
            if isinstance(raw_value, str):
                text = raw_value.strip()
                try:
                    raw_value = date.fromisoformat(text) if text else None
                except ValueError as exc:
                    raise ValueError(
                        f"{date_field_name} deve usar o formato YYYY-MM-DD."
                    ) from exc
            if raw_value is not None and not isinstance(raw_value, date):
                raise TypeError(
                    f"{date_field_name} exige date, string ISO ou None."
                )
            object.__setattr__(self, date_field_name, raw_value)

        if (
            self.company_report is not None
            and self.company_report.symbol != self.symbol
        ):
            raise ValueError(
                "O CompanyReport deve possuir o mesmo símbolo "
                "da Holding."
            )

    @property
    def invested_value(self) -> float:
        return round(
            self.quantity * self.average_price,
            2,
        )

    @property
    def market_value(self) -> float | None:
        if self.current_price is None:
            return None

        return round(
            self.quantity * self.current_price,
            2,
        )

    @property
    def unrealized_result(self) -> float | None:
        if self.market_value is None:
            return None

        return round(
            self.market_value - self.invested_value,
            2,
        )

    @property
    def unrealized_return(self) -> float | None:
        if self.market_value is None:
            return None

        if self.invested_value <= 0:
            return None

        return round(
            (
                self.market_value
                / self.invested_value
            ) - 1.0,
            6,
        )

    @property
    def has_current_price(self) -> bool:
        return self.current_price is not None

    @property
    def has_company_report(self) -> bool:
        return self.company_report is not None

    def with_weight(
        self,
        weight: float,
    ) -> "Holding":
        return Holding(
            symbol=self.symbol,
            quantity=self.quantity,
            average_price=self.average_price,
            current_price=self.current_price,
            portfolio_weight=weight,
            sector=self.sector,
            industry=self.industry,
            country=self.country,
            currency=self.currency,
            notes=self.notes,
            entry_date=self.entry_date,
            thesis=self.thesis,
            thesis_updated_at=self.thesis_updated_at,
            origin=self.origin,
            company_report=self.company_report,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "current_price": self.current_price,
            "invested_value": self.invested_value,
            "market_value": self.market_value,
            "unrealized_result": self.unrealized_result,
            "unrealized_return": self.unrealized_return,
            "portfolio_weight": self.portfolio_weight,
            "sector": self.sector,
            "industry": self.industry,
            "country": self.country,
            "currency": self.currency,
            "notes": self.notes,
            "entry_date": (
                self.entry_date.isoformat()
                if self.entry_date is not None
                else None
            ),
            "thesis": self.thesis,
            "thesis_updated_at": (
                self.thesis_updated_at.isoformat()
                if self.thesis_updated_at is not None
                else None
            ),
            "origin": self.origin,
            "company_report": (
                self.company_report.to_dict()
                if self.company_report is not None
                else None
            ),
        }


@dataclass(frozen=True)
class Portfolio:
    """
    Representa a carteira completa.

    Cash é tratado como um componente explícito do patrimônio.
    """

    name: str
    holdings: tuple[Holding, ...] = field(
        default_factory=tuple
    )
    cash: float = 0.0
    currency: str = "BRL"
    created_at: datetime = field(
        default_factory=datetime.now
    )

    def __post_init__(self) -> None:
        name = normalize_text(self.name)

        if not name:
            raise ValueError(
                "Portfolio exige um nome válido."
            )

        holdings = tuple(self.holdings)

        for holding in holdings:
            if not isinstance(holding, Holding):
                raise TypeError(
                    "Portfolio aceita apenas objetos Holding."
                )

        symbols = [
            holding.symbol
            for holding in holdings
        ]

        if len(symbols) != len(set(symbols)):
            raise ValueError(
                "Portfolio não permite símbolos duplicados."
            )

        object.__setattr__(self, "name", name)
        object.__setattr__(
            self,
            "holdings",
            holdings,
        )
        object.__setattr__(
            self,
            "cash",
            normalize_non_negative_float(
                self.cash,
                field_name="cash",
            ),
        )
        object.__setattr__(
            self,
            "currency",
            (
                normalize_text(
                    self.currency,
                    default="BRL",
                )
                or "BRL"
            ).upper(),
        )

    @property
    def holdings_count(self) -> int:
        return len(self.holdings)

    @property
    def total_market_value(self) -> float:
        return round(
            sum(
                holding.market_value or 0.0
                for holding in self.holdings
            ),
            2,
        )

    @property
    def total_value(self) -> float:
        return round(
            self.total_market_value + self.cash,
            2,
        )

    @property
    def missing_price_symbols(self) -> tuple[str, ...]:
        return tuple(
            holding.symbol
            for holding in self.holdings
            if not holding.has_current_price
        )

    @property
    def missing_report_symbols(self) -> tuple[str, ...]:
        return tuple(
            holding.symbol
            for holding in self.holdings
            if not holding.has_company_report
        )

    @property
    def missing_thesis_symbols(self) -> tuple[str, ...]:
        """
        Símbolos com posição real (quantity > 0) sem tese registrada. Uma
        posição zerada (quantity == 0, ex.: holding em transição) não exige
        tese -- só posições vivas o motor de venda pode precisar justificar.
        """
        return tuple(
            holding.symbol
            for holding in self.holdings
            if holding.quantity > 0 and not holding.thesis
        )

    def holding(
        self,
        symbol: str,
    ) -> Holding | None:
        normalized = normalize_symbol(symbol)

        for item in self.holdings:
            if item.symbol == normalized:
                return item

        return None

    def with_calculated_weights(self) -> "Portfolio":
        total = self.total_value

        if total <= 0:
            return self

        weighted_holdings = tuple(
            holding.with_weight(
                (holding.market_value or 0.0) / total
            )
            for holding in self.holdings
        )

        return Portfolio(
            name=self.name,
            holdings=weighted_holdings,
            cash=self.cash,
            currency=self.currency,
            created_at=self.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "currency": self.currency,
            "cash": self.cash,
            "holdings_count": self.holdings_count,
            "total_market_value": self.total_market_value,
            "total_value": self.total_value,
            "missing_price_symbols": list(
                self.missing_price_symbols
            ),
            "missing_report_symbols": list(
                self.missing_report_symbols
            ),
            "missing_thesis_symbols": list(
                self.missing_thesis_symbols
            ),
            "holdings": [
                holding.to_dict()
                for holding in self.holdings
            ],
            "created_at": self.created_at.isoformat(
                timespec="seconds"
            ),
        }


@dataclass(frozen=True)
class AllocationSnapshot:
    """
    Representa uma fotografia da alocação da carteira.

    Todos os pesos usam escala decimal:
    0.25 representa 25%.
    """

    by_symbol: dict[str, float] = field(
        default_factory=dict
    )
    by_sector: dict[str, float] = field(
        default_factory=dict
    )
    by_country: dict[str, float] = field(
        default_factory=dict
    )
    by_currency: dict[str, float] = field(
        default_factory=dict
    )
    cash_weight: float = 0.0
    generated_at: datetime = field(
        default_factory=datetime.now
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_symbol",
            normalize_mapping(
                self.by_symbol,
                field_name="by_symbol",
            ),
        )
        object.__setattr__(
            self,
            "by_sector",
            normalize_mapping(
                self.by_sector,
                field_name="by_sector",
            ),
        )
        object.__setattr__(
            self,
            "by_country",
            normalize_mapping(
                self.by_country,
                field_name="by_country",
            ),
        )
        object.__setattr__(
            self,
            "by_currency",
            normalize_mapping(
                self.by_currency,
                field_name="by_currency",
            ),
        )
        object.__setattr__(
            self,
            "cash_weight",
            normalize_weight(
                self.cash_weight,
                field_name="cash_weight",
                allow_none=False,
            ),
        )

        validate_weight_total(
            {
                **self.by_symbol,
                "__cash__": self.cash_weight,
            },
            allow_empty=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_symbol": dict(self.by_symbol),
            "by_sector": dict(self.by_sector),
            "by_country": dict(self.by_country),
            "by_currency": dict(self.by_currency),
            "cash_weight": self.cash_weight,
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
        }


@dataclass(frozen=True)
class PortfolioRisk:
    """
    Representa o risco agregado da carteira.
    """

    concentration_score: float | None = None
    diversification_score: float | None = None

    largest_position_weight: float = 0.0
    top_5_weight: float = 0.0

    sector_concentration: dict[str, float] = field(
        default_factory=dict
    )
    country_concentration: dict[str, float] = field(
        default_factory=dict
    )
    currency_concentration: dict[str, float] = field(
        default_factory=dict
    )

    warnings: tuple[str, ...] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "concentration_score",
            normalize_score(
                self.concentration_score,
                field_name="concentration_score",
            ),
        )
        object.__setattr__(
            self,
            "diversification_score",
            normalize_score(
                self.diversification_score,
                field_name="diversification_score",
            ),
        )
        object.__setattr__(
            self,
            "largest_position_weight",
            normalize_weight(
                self.largest_position_weight,
                field_name="largest_position_weight",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "top_5_weight",
            normalize_weight(
                self.top_5_weight,
                field_name="top_5_weight",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "sector_concentration",
            normalize_mapping(
                self.sector_concentration,
                field_name="sector_concentration",
            ),
        )
        object.__setattr__(
            self,
            "country_concentration",
            normalize_mapping(
                self.country_concentration,
                field_name="country_concentration",
            ),
        )
        object.__setattr__(
            self,
            "currency_concentration",
            normalize_mapping(
                self.currency_concentration,
                field_name="currency_concentration",
            ),
        )
        object.__setattr__(
            self,
            "warnings",
            normalize_items(self.warnings),
        )

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concentration_score": self.concentration_score,
            "diversification_score": self.diversification_score,
            "largest_position_weight": (
                self.largest_position_weight
            ),
            "top_5_weight": self.top_5_weight,
            "sector_concentration": dict(
                self.sector_concentration
            ),
            "country_concentration": dict(
                self.country_concentration
            ),
            "currency_concentration": dict(
                self.currency_concentration
            ),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RebalanceAction:
    """
    Representa uma sugestão consultiva de rebalanceamento.
    """

    symbol: str
    action: str

    current_weight: float
    target_weight: float

    target_value: float
    trade_value: float

    reason: str
    priority: int = 100
    triggered_rules: tuple[str, ...] = field(default_factory=tuple)
    rule_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    missing_data: tuple[str, ...] = field(default_factory=tuple)
    baseline_status: str = ""
    earnings_since_last_run: bool | None = None
    score_coverage: float | None = None
    confidence: float | None = None
    legacy_flagged: bool = False

    def __post_init__(self) -> None:
        symbol = normalize_symbol(self.symbol)
        action = normalize_text(self.action).upper()
        reason = normalize_text(self.reason)

        if not symbol:
            raise ValueError(
                "RebalanceAction exige um símbolo válido."
            )

        if action not in {
            "BUY",
            "SELL",
            "HOLD",
            "TRIM",
            "REVISAR",
            "ACOMPANHAR",
        }:
            raise ValueError(
                "action deve ser BUY, SELL, HOLD, TRIM, REVISAR ou ACOMPANHAR."
            )

        if not reason:
            raise ValueError(
                "RebalanceAction exige uma justificativa."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(
            self,
            "current_weight",
            normalize_weight(
                self.current_weight,
                field_name="current_weight",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "target_weight",
            normalize_weight(
                self.target_weight,
                field_name="target_weight",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "target_value",
            normalize_non_negative_float(
                self.target_value,
                field_name="target_value",
            ),
        )

        try:
            trade_value = float(self.trade_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "trade_value deve ser numérico."
            ) from exc

        if trade_value != trade_value:
            raise ValueError(
                "trade_value não pode ser NaN."
            )

        object.__setattr__(
            self,
            "trade_value",
            round(trade_value, 2),
        )
        object.__setattr__(
            self,
            "priority",
            max(0, int(self.priority)),
        )
        object.__setattr__(
            self,
            "triggered_rules",
            normalize_items(self.triggered_rules),
        )
        object.__setattr__(
            self,
            "rule_results",
            tuple(dict(item) for item in self.rule_results),
        )
        object.__setattr__(
            self,
            "missing_data",
            normalize_items(self.missing_data),
        )
        object.__setattr__(
            self,
            "baseline_status",
            normalize_text(self.baseline_status),
        )
        object.__setattr__(
            self,
            "score_coverage",
            normalize_score(self.score_coverage, field_name="score_coverage"),
        )
        object.__setattr__(
            self,
            "confidence",
            normalize_score(self.confidence, field_name="confidence"),
        )
        object.__setattr__(
            self,
            "legacy_flagged",
            bool(self.legacy_flagged),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "current_weight": self.current_weight,
            "target_weight": self.target_weight,
            "target_value": self.target_value,
            "trade_value": self.trade_value,
            "reason": self.reason,
            "priority": self.priority,
            "triggered_rules": list(self.triggered_rules),
            "rule_results": [dict(item) for item in self.rule_results],
            "missing_data": list(self.missing_data),
            "baseline_status": self.baseline_status,
            "earnings_since_last_run": self.earnings_since_last_run,
            "score_coverage": self.score_coverage,
            "confidence": self.confidence,
            "legacy_flagged": self.legacy_flagged,
        }


@dataclass(frozen=True)
class RebalancePlan:
    """
    Representa um plano consultivo completo de rebalanceamento.
    """

    actions: tuple[RebalanceAction, ...] = field(
        default_factory=tuple
    )
    required_cash: float = 0.0
    released_cash: float = 0.0
    estimated_turnover: float = 0.0
    warnings: tuple[str, ...] = field(
        default_factory=tuple
    )
    generated_at: datetime = field(
        default_factory=datetime.now
    )

    def __post_init__(self) -> None:
        actions = tuple(self.actions)

        for action in actions:
            if not isinstance(
                action,
                RebalanceAction,
            ):
                raise TypeError(
                    "RebalancePlan aceita apenas "
                    "objetos RebalanceAction."
                )

        object.__setattr__(self, "actions", actions)
        object.__setattr__(
            self,
            "required_cash",
            normalize_non_negative_float(
                self.required_cash,
                field_name="required_cash",
            ),
        )
        object.__setattr__(
            self,
            "released_cash",
            normalize_non_negative_float(
                self.released_cash,
                field_name="released_cash",
            ),
        )
        object.__setattr__(
            self,
            "estimated_turnover",
            normalize_weight(
                self.estimated_turnover,
                field_name="estimated_turnover",
                allow_none=False,
            ),
        )
        object.__setattr__(
            self,
            "warnings",
            normalize_items(self.warnings),
        )

    @property
    def buy_actions(self) -> tuple[RebalanceAction, ...]:
        return tuple(
            action
            for action in self.actions
            if action.action == "BUY"
        )

    @property
    def sell_actions(self) -> tuple[RebalanceAction, ...]:
        return tuple(
            action
            for action in self.actions
            if action.action == "SELL"
        )

    @property
    def hold_actions(self) -> tuple[RebalanceAction, ...]:
        return tuple(
            action
            for action in self.actions
            if action.action == "HOLD"
        )

    @property
    def trim_actions(self) -> tuple[RebalanceAction, ...]:
        return tuple(
            action
            for action in self.actions
            if action.action == "TRIM"
        )

    @property
    def review_actions(self) -> tuple[RebalanceAction, ...]:
        return tuple(
            action
            for action in self.actions
            if action.action == "REVISAR"
        )

    @property
    def informational_actions(self) -> tuple[RebalanceAction, ...]:
        """ACOMPANHAR: a comparative signal worth seeing, never worth a
        decision on its own -- kept separate from `review_actions` so it
        never inflates the "needs your attention" count."""
        return tuple(
            action
            for action in self.actions
            if action.action == "ACOMPANHAR"
        )

    @property
    def net_cash_requirement(self) -> float:
        return round(
            max(
                0.0,
                self.required_cash - self.released_cash,
            ),
            2,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [
                action.to_dict()
                for action in self.actions
            ],
            "required_cash": self.required_cash,
            "released_cash": self.released_cash,
            "net_cash_requirement": (
                self.net_cash_requirement
            ),
            "estimated_turnover": (
                self.estimated_turnover
            ),
            "warnings": list(self.warnings),
            "generated_at": self.generated_at.isoformat(
                timespec="seconds"
            ),
        }
