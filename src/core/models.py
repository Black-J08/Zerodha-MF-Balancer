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
class FundAllocation:
    """Unified representation of a fund's allocation change.

    Attributes:
        fund_name: Name of the fund.
        current_weight: Current portfolio weight (0.0 to 1.0).
        target_weight: Optimal target weight (0.0 to 1.0).
        current_value: Current market value (INR).
        target_value: Target market value (INR).
        shortfall: target_value - current_value (positive = needs capital,
            negative = excess capital available for redemption).
    """

    fund_name: str
    current_weight: float
    target_weight: float
    current_value: float
    target_value: float
    shortfall: float


@dataclass(frozen=True)
class STPTransfer:
    """A single fund-to-fund STP transfer.

    Attributes:
        source_fund: Name of the overweighted source fund (capital redeemed from).
        target_fund: Name of the underweighted target fund (capital transferred to).
        monthly_amount: Monthly transfer amount (INR).
        duration_months: Number of months for this transfer.
        total_amount: Total transfer amount over the duration (monthly × duration).
    """

    source_fund: str
    target_fund: str
    monthly_amount: float
    duration_months: int
    total_amount: float


@dataclass(frozen=True)
class SIPAllocation:
    """Monthly SIP contribution allocated to a single target fund.

    Attributes:
        target_fund: Name of the underweighted target fund.
        monthly_amount: Monthly SIP amount allocated to this fund (INR).
        percentage_of_contribution: Percentage of the total monthly SIP contribution.
    """

    target_fund: str
    monthly_amount: float
    percentage_of_contribution: float


@dataclass(frozen=True)
class LumpSumAllocation:
    """One-time lump sum allocation to a single target fund.

    Attributes:
        target_fund: Name of the underweighted target fund.
        amount: Lump sum amount allocated to this fund (INR).
        percentage_of_total: Percentage of the total lump sum amount.
    """

    target_fund: str
    amount: float
    percentage_of_total: float


@dataclass(frozen=True)
class TransferPlan:
    """Unified execution plan for STP, SIP, and Lump Sum strategies.

    Attributes:
        stp_transfers: List of fund-to-fund STP transfers (source → target).
        stp_monthly_total: Total monthly STP outflow across all transfers (INR).
        stp_duration_months: Duration in months for all STP transfers.
        sip_allocations: List of monthly SIP allocations to target funds.
        sip_monthly_total: Total monthly SIP contribution (INR).
        lump_sum_allocations: List of one-time lump sum allocations to target funds.
        lump_sum_total: Total lump sum amount required (INR).
        shortfall_warnings: Audit warnings for unfulfilled targets or missing sources.
        total_portfolio_value: Total portfolio value used as the basis (INR).
        threshold_used: Shortfall threshold used to classify sources/targets (INR).
    """

    stp_transfers: list[STPTransfer]
    stp_monthly_total: float
    stp_duration_months: int
    sip_allocations: list[SIPAllocation]
    sip_monthly_total: float
    lump_sum_allocations: list[LumpSumAllocation]
    lump_sum_total: float
    shortfall_warnings: list[str]
    total_portfolio_value: float
    threshold_used: float


@dataclass(frozen=True)
class FundExclusion:
    """A mutual fund excluded from optimization, with the reason.

    Attributes:
        fund_name: Human-readable fund name (e.g. from Zerodha holdings).
        reason: Human-readable exclusion reason (e.g. "Scheme code not found").
        detail: Optional additional validation detail (e.g. days found vs.
            required, exception type name).
    """

    fund_name: str
    reason: str
    detail: str | None = None
