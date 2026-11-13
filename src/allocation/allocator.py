"""Allocator: portfolio rebalancing transfer amount calculation.

Implements Target Duration Convergence rebalancing logic:
1. Monthly Budget = Total Capital / Remaining Months
2. Distribute budget to funds proportional to their shortfall
   (target value - current value).
"""

from src.core.evaluation import EvaluationMode
from src.core.logging import get_logger

logger = get_logger(__name__)


class Allocator:
    """Computes monthly rebalancing transfer amounts to reach target weights.

    Args:
        current_holdings: Dict of {fund_name: current_value_INR}.
        total_capital: Total capital available for rebalancing (INR).
        optimal_weights: Dict of {fund_name: target_weight (0.0 to 1.0)}.
        remaining_months: Number of months to deploy the capital.
    """

    def __init__(
        self,
        current_holdings: dict[str, float],
        total_capital: float,
        optimal_weights: dict[str, float],
        remaining_months: int,
    ):
        self.current_holdings = current_holdings
        self.total_capital = total_capital
        self.optimal_weights = optimal_weights
        self.remaining_months = max(1, remaining_months)  # Avoid div by zero

    def calculate_transfers(self) -> dict[str, float]:
        """Compute monthly transfer amounts per fund.

        Implements 'Target Duration Convergence Rebalancing':
        1. Monthly Budget = Total Capital / Remaining Months.
        2. Distribute budget to funds proportional to their shortfall.

        Returns:
            Dict of {fund_name: monthly_transfer_amount_INR}.
        """
        # 1. Monthly Budget (Strict Deployment)
        monthly_budget = self.total_capital / self.remaining_months

        # 2. Calculate Shortfalls
        current_equity_value = sum(self.current_holdings.values())
        total_future_value = current_equity_value + self.total_capital

        shortfalls: dict[str, float] = {}
        total_positive_shortfall = 0.0

        for fund, weight in self.optimal_weights.items():
            current_val = self.current_holdings.get(fund, 0.0)
            target_val = weight * total_future_value
            shortfall = target_val - current_val

            if shortfall > 0:
                shortfalls[fund] = shortfall
                total_positive_shortfall += shortfall
            else:
                shortfalls[fund] = 0.0

        # 3. Allocate Budget
        transfers: dict[str, float] = {}
        for fund, weight in self.optimal_weights.items():
            if total_positive_shortfall > 0:
                # Proportional allocation of the budget
                allocation_ratio = shortfalls[fund] / total_positive_shortfall
                transfer_amount = allocation_ratio * monthly_budget
            else:
                # Edge case: All funds are overweight or math weirdness.
                # Fallback to optimal weights.
                transfer_amount = weight * monthly_budget

            transfers[fund] = round(transfer_amount, 2)

        return transfers

    def get_summary(self, mode: EvaluationMode = EvaluationMode.MASTER_FUND) -> dict:
        """Return a summary dict of the allocation.

        Args:
            mode: The :class:`EvaluationMode` used. For MPT_OPTIMAL,
                ``total_capital`` already equals the full portfolio value,
                so ``Total_Projected`` must not double-count it.

        Returns:
            Dict with Total_Equity, Total_Capital, Total_Projected.
        """
        total_equity = sum(self.current_holdings.values())
        if mode == EvaluationMode.MPT_OPTIMAL:
            # In MPT_OPTIMAL mode, total_capital == total portfolio value,
            # so Total_Projected is just total_capital (no double-counting).
            total_projected = self.total_capital
        else:
            # In MASTER_FUND mode, total_capital is the master debt fund
            # value, so Total_Projected = equity + debt capital.
            total_projected = total_equity + self.total_capital

        return {
            "Total_Equity": total_equity,
            "Total_Capital": self.total_capital,
            "Total_Projected": total_projected,
        }
