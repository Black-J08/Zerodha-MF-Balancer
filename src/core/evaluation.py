"""Evaluation modes and results for MF Balancer.

Defines the mode-agnostic data structures used across portfolio evaluation:

- ``EvaluationMode``: discriminates between MPT-Optimal and master-fund-based
  evaluation workflows.
- ``EvaluationResult``: mode-agnostic result of a portfolio evaluation run,
  replacing the master-fund-coupled ``AdvisoryResult``.
"""

from dataclasses import dataclass, field
from enum import Enum

from src.core.models import FundExclusion, TransferPlan


class EvaluationMode(str, Enum):
    """Portfolio evaluation mode.

    Attributes:
        MPT_OPTIMAL: Maximum-Sharpe-ratio portfolio across all eligible
            holdings, with no master fund. Total portfolio value is used as
            the capital basis.
        MASTER_FUND: Existing master-fund-based evaluation. A user-selected
            debt fund is excluded from optimization and its value is used as
            the capital basis for debt-to-equity STP transfers.
    """

    MPT_OPTIMAL = "mpt_optimal"
    MASTER_FUND = "master_fund"


@dataclass(frozen=True)
class EvaluationResult:
    """Mode-agnostic result of a portfolio evaluation run.

    Attributes:
        mode: The :class:`EvaluationMode` used for this run.
        weights: Mapping of fund name to optimal target weight (0.0 to 1.0).
        current_weights: Mapping of fund name to current value-weighted weight.
        optimized_stats: Advanced performance stats for the optimized portfolio.
        current_stats: Advanced performance stats for the current portfolio.
        transfers: Unified :class:`TransferPlan` with STP, SIP, and Lump Sum
            allocations for MPT_OPTIMAL mode, or a MASTER_FUND-compatible plan.
        summary: Summary dict with Total_Equity, Total_Capital, Total_Projected.
        report_path: Path to the generated Markdown report.
        excluded_funds: List of :class:`FundExclusion` for funds excluded from
            optimization, each with a reason and optional detail.
        valid_funds: List of fund names included in optimization.
        total_capital: Total capital used as the basis for rebalancing (INR).
        months: Planning horizon in months.
    """

    mode: EvaluationMode
    weights: dict[str, float]
    current_weights: dict[str, float]
    optimized_stats: dict | None
    current_stats: dict | None
    transfers: TransferPlan
    summary: dict
    report_path: str
    excluded_funds: list[FundExclusion] = field(default_factory=list)
    valid_funds: list[str] = field(default_factory=list)
    total_capital: float = 0.0
    months: int = 12
