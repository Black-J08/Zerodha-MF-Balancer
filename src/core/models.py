"""Domain models for MF Balancer.

Defines the core data structures used across the application:
- ``Fund``: a mutual fund with identifying metadata
- ``Holding``: a current portfolio holding with quantity and value
- ``Portfolio``: a collection of holdings
- ``AllocationResult``: optimized portfolio weights
- ``TransferPlan``: STP transfer amounts per fund
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fund:
    """A mutual fund with identifying metadata.

    Attributes:
        name: Human-readable fund name (e.g. from Zerodha holdings).
        isin: ISIN code (unique identifier, preferred for matching).
        scheme_code: AMFI scheme code (used for NAV fetching).
        plan: Plan type (e.g. "Direct Plan", "Regular Plan").
        option: Option type (e.g. "Growth Option", "IDCW Option").
    """

    name: str
    isin: str | None = None
    scheme_code: str | None = None
    plan: str | None = None
    option: str | None = None


@dataclass(frozen=True)
class Holding:
    """A current portfolio holding.

    Attributes:
        fund: The :class:`Fund` being held.
        quantity: Number of units held.
        last_price: Most recent NAV price.
        average_price: Average purchase price.
        value: Current market value (quantity * last_price).
    """

    fund: Fund
    quantity: float
    last_price: float
    average_price: float
    value: float


@dataclass(frozen=True)
class Portfolio:
    """A collection of mutual fund holdings.

    Attributes:
        holdings: Mapping of fund name to :class:`Holding`.
        total_value: Sum of all holding values.
    """

    holdings: dict[str, Holding] = field(default_factory=dict)

    @property
    def total_value(self) -> float:
        """Total market value of all holdings."""
        return sum(h.value for h in self.holdings.values())

    @property
    def fund_names(self) -> list[str]:
        """Sorted list of fund names in the portfolio."""
        return sorted(self.holdings.keys())


@dataclass(frozen=True)
class AllocationResult:
    """Result of portfolio optimization.

    Attributes:
        weights: Mapping of fund name to target weight (0.0 to 1.0).
        expected_return: Expected annual return of the optimized portfolio.
        volatility: Expected annual volatility.
        sharpe_ratio: Sharpe ratio of the optimized portfolio.
    """

    weights: dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float


@dataclass(frozen=True)
class TransferPlan:
    """STP transfer plan from debt to equity funds.

    Attributes:
        transfers: Mapping of fund name to monthly transfer amount (INR).
        monthly_budget: Total monthly budget available for transfers.
        duration_months: Number of months to deplete debt capital.
        total_monthly_outflow: Sum of all monthly transfers.
    """

    transfers: dict[str, float]
    monthly_budget: float
    duration_months: int
    total_monthly_outflow: float
