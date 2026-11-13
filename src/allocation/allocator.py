"""Allocator: portfolio rebalancing transfer amount calculation.

Implements Target Duration Convergence rebalancing logic:
1. Monthly Budget = Total Capital / Remaining Months
2. Distribute budget to funds proportional to their shortfall
   (target value - current value).

For MPT_OPTIMAL mode, provides fund-to-fund STP transfers derived
mathematically from the difference between current and optimal allocations.
"""

from src.core.evaluation import EvaluationMode
from src.core.logging import get_logger
from src.core.models import (
    FundAllocation,
    LumpSumAllocation,
    SIPAllocation,
    STPTransfer,
    TransferPlan,
)

logger = get_logger(__name__)

# Fixed shortfall threshold: 0.1% of total portfolio value
SHORTFALL_THRESHOLD_PCT = 0.001


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

    # ------------------------------------------------------------------
    # MASTER_FUND mode: existing behavior (debt fund as single source)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # MPT_OPTIMAL mode: new fund-to-fund transfer plan
    # ------------------------------------------------------------------

    def calculate_transfer_plan(
        self,
        sip_monthly_amount: float | None = None,
    ) -> TransferPlan:
        """Compute a unified transfer plan for MPT_OPTIMAL mode.

        Derives STP, SIP, and Lump Sum allocations mathematically from the
        difference between current and optimal allocations.

        Algorithm:
        1. Calculate current and target values per fund.
        2. Identify source funds (shortfall < -threshold) and target funds
           (shortfall > threshold).
        3. For STP: match source available capital to target required capital
           proportionally; apply proportional reduction if sources are
           insufficient.
        4. For SIP: distribute monthly contribution to targets proportional
           to their shortfall.
        5. For Lump Sum: one-time allocation to targets equal to their
           shortfall (after STP reduction if applicable).

        Args:
            sip_monthly_amount: Optional monthly SIP contribution amount (INR).

        Returns:
            TransferPlan with structured STP, SIP, and Lump Sum allocations.
        """
        total_value = sum(self.current_holdings.values())
        threshold = total_value * SHORTFALL_THRESHOLD_PCT

        # --- 1. Calculate FundAllocations for all funds ---
        all_fund_names = sorted(
            set(self.current_holdings.keys()).union(set(self.optimal_weights.keys()))
        )

        allocations: dict[str, FundAllocation] = {}
        sources: dict[str, float] = {}  # fund -> available amount (positive)
        targets: dict[str, float] = {}  # fund -> required amount (positive)

        for fund in all_fund_names:
            current_val = self.current_holdings.get(fund, 0.0)
            target_w = self.optimal_weights.get(fund, 0.0)
            target_val = target_w * total_value
            shortfall = target_val - current_val
            current_w = current_val / total_value if total_value > 0 else 0.0

            allocations[fund] = FundAllocation(
                fund_name=fund,
                current_weight=current_w,
                target_weight=target_w,
                current_value=current_val,
                target_value=target_val,
                shortfall=shortfall,
            )

            if shortfall < -threshold:
                sources[fund] = abs(shortfall)
            elif shortfall > threshold:
                targets[fund] = shortfall

        warnings: list[str] = []

        # --- 2. STP: fund-to-fund transfers ---
        stp_transfers: list[STPTransfer] = []
        stp_monthly_total = 0.0

        total_available = sum(sources.values())
        total_required = sum(targets.values())

        if sources and targets:
            reduction_factor = min(1.0, total_available / total_required)

            if reduction_factor < 1.0:
                warnings.append(
                    f"STP shortfall: available capital ₹{total_available:,.2f} "
                    f"is insufficient for required ₹{total_required:,.2f}; "
                    f"all target allocations reduced by "
                    f"{(1.0 - reduction_factor) * 100:.1f}%."
                )

            # For each source, distribute its available capital across all
            # targets proportionally to their required amounts.
            for source_name, source_available in sources.items():
                source_allocated = 0.0
                for target_name, target_required in targets.items():
                    # Pair allocation: source's share of this target's requirement
                    pair_allocation = (
                        source_available
                        * (target_required / total_required)
                        * reduction_factor
                    )
                    if pair_allocation > 0:
                        monthly_amount = round(pair_allocation / self.remaining_months, 2)
                        total_amount = round(monthly_amount * self.remaining_months, 2)
                        stp_transfers.append(
                            STPTransfer(
                                source_fund=source_name,
                                target_fund=target_name,
                                monthly_amount=monthly_amount,
                                duration_months=self.remaining_months,
                                total_amount=total_amount,
                            )
                        )
                        source_allocated += pair_allocation
                        stp_monthly_total += monthly_amount

                # Validate source does not exceed available
                if source_allocated > source_available + 0.01:
                    logger.warning(
                        "Source %s allocated ₹%.2f exceeds available ₹%.2f",
                        source_name,
                        source_allocated,
                        source_available,
                    )

        elif not sources:
            warnings.append(
                "No overweighted funds available for STP. "
                "All funds are at or below optimal weight."
            )
        elif not targets:
            warnings.append(
                "No underweighted funds to receive STP transfers. "
                "All funds are at or above optimal weight."
            )

        # --- 3. SIP: monthly contributions to targets ---
        sip_allocations: list[SIPAllocation] = []
        sip_monthly_total = 0.0

        if sip_monthly_amount and sip_monthly_amount > 0 and targets:
            total_target_shortfall = sum(targets.values())
            if total_target_shortfall > 0:
                for target_name, target_required in targets.items():
                    ratio = target_required / total_target_shortfall
                    monthly_alloc = ratio * sip_monthly_amount
                    pct = (monthly_alloc / sip_monthly_amount) * 100
                    sip_allocations.append(
                        SIPAllocation(
                            target_fund=target_name,
                            monthly_amount=round(monthly_alloc, 2),
                            percentage_of_contribution=round(pct, 1),
                        )
                    )
                sip_monthly_total = sip_monthly_amount

        # --- 4. Lump Sum: one-time allocations to targets ---
        lump_sum_allocations: list[LumpSumAllocation] = []
        lump_sum_total = 0.0

        if targets:
            # Lump sum needed = sum of target shortfalls (after STP reduction)
            # If STP reduction was applied, targets receive less via STP,
            # so lump sum covers the remaining gap.
            for target_name, target_required in targets.items():
                # Amount already covered by STP for this target
                stp_covered = sum(
                    t.total_amount
                    for t in stp_transfers
                    if t.target_fund == target_name
                )
                remaining_needed = max(0.0, target_required - stp_covered)
                if remaining_needed > 0:
                    lump_sum_allocations.append(
                        LumpSumAllocation(
                            target_fund=target_name,
                            amount=round(remaining_needed, 2),
                            percentage_of_total=0.0,  # computed below
                        )
                    )
                    lump_sum_total += remaining_needed

            # Compute percentages
            if lump_sum_total > 0:
                for i, alloc in enumerate(lump_sum_allocations):
                    pct = (alloc.amount / lump_sum_total) * 100
                    lump_sum_allocations[i] = LumpSumAllocation(
                        target_fund=alloc.target_fund,
                        amount=alloc.amount,
                        percentage_of_total=round(pct, 1),
                    )

        return TransferPlan(
            stp_transfers=stp_transfers,
            stp_monthly_total=round(stp_monthly_total, 2),
            stp_duration_months=self.remaining_months,
            sip_allocations=sip_allocations,
            sip_monthly_total=round(sip_monthly_total, 2),
            lump_sum_allocations=lump_sum_allocations,
            lump_sum_total=round(lump_sum_total, 2),
            shortfall_warnings=warnings,
            total_portfolio_value=total_value,
            threshold_used=threshold,
        )

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
