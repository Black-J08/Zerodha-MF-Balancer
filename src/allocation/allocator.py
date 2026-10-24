"""Allocator: STP transfer amount calculation.

Implements Target Duration Convergence STP logic:
1. Monthly Budget = Debt Capital / Remaining Months
2. Distribute budget to funds proportional to their shortfall
   (target value - current value).
"""

from src.core.logging import get_logger

logger = get_logger(__name__)


class Allocator:
    """Computes monthly STP transfer amounts from debt to equity funds.

    Args:
        current_holdings: Dict of {fund_name: current_value_INR}.
        debt_capital: Total capital available in Debt Fund (source).
        optimal_weights: Dict of {fund_name: target_weight (0.0 to 1.0)}.
        remaining_months: Number of months to deplete the debt capital.
    """

    def __init__(
        self,
        current_holdings: dict[str, float],
        debt_capital: float,
        optimal_weights: dict[str, float],
        remaining_months: int,
    ):
        self.current_holdings = current_holdings
        self.debt_capital = debt_capital
        self.optimal_weights = optimal_weights
        self.remaining_months = max(1, remaining_months)  # Avoid div by zero

    def calculate_transfers(self) -> dict[str, float]:
        """Compute monthly transfer amounts per fund.

        Implements 'Target Duration Convergence STP':
        1. Monthly Budget = Debt / Remaining Months.
        2. Distribute budget to funds proportional to their shortfall.

        Returns:
            Dict of {fund_name: monthly_transfer_amount_INR}.
        """
        # 1. Monthly Budget (Strict Deployment)
        monthly_budget = self.debt_capital / self.remaining_months

        # 2. Calculate Shortfalls
        current_equity_value = sum(self.current_holdings.values())
        total_future_value = current_equity_value + self.debt_capital

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

    def get_summary(self) -> dict:
        """Return a summary dict of the allocation.

        Returns:
            Dict with Total_Equity, Debt_Capital, Total_Projected.
        """
        return {
            "Total_Equity": sum(self.current_holdings.values()),
            "Debt_Capital": self.debt_capital,
            "Total_Projected": sum(self.current_holdings.values())
            + self.debt_capital,
        }
