"""Reporter: Markdown rebalancing report generation.

Generates a detailed Markdown report comparing current vs. optimized
portfolio allocation and providing a monthly STP transfer plan.
"""

import os
from datetime import datetime

from rich.console import Console

from src.core.evaluation import EvaluationMode
from src.core.logging import get_logger
from src.core.models import FundExclusion
from src.core.settings import Settings

logger = get_logger(__name__)


class Reporter:
    """Generates Markdown rebalancing reports.

    Args:
        config: Application configuration (used for output directory paths).
    """

    def __init__(self, config: Settings):
        self.config = config
        os.makedirs(self.config.reports_dir, exist_ok=True)
        self.console = Console()

    def generate_report(
        self,
        allocator_summary: dict,
        optimal_weights: dict,
        transfers: dict,
        duration: int = 12,
        current_stats: dict | None = None,
        optimized_stats: dict | None = None,
        current_weights: dict[str, float] | None = None,
        excluded_funds: list[FundExclusion] | None = None,
        mode: EvaluationMode = EvaluationMode.MASTER_FUND,
        sip_monthly_amount: float | None = None,
    ) -> str:
        """Generate a Markdown report and save it to disk.

        Args:
            allocator_summary: Summary dict from Allocator.get_summary().
            optimal_weights: Mapping of fund name to target weight.
            transfers: Mapping of fund name to monthly transfer amount (STP).
            duration: Planning horizon in months (default 12).
            current_stats: Optional current portfolio stats dict.
            optimized_stats: Optional optimized portfolio stats dict.
            current_weights: Optional mapping of fund name to current weight.
            excluded_funds: Optional list of :class:`FundExclusion` for funds
                excluded from optimization, each with a reason and detail.
            mode: The :class:`EvaluationMode` used, for mode-appropriate labels.
            sip_monthly_amount: Optional monthly SIP contribution amount (INR).
                If provided, the SIP strategy section shows fund-wise breakdown
                of how each monthly contribution is allocated.

        Returns:
            The file path of the generated report.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"report_{timestamp}.md"
        filepath = os.path.join(self.config.reports_dir, filename)

        total_projected = allocator_summary["Total_Projected"]
        total_equity = allocator_summary["Total_Equity"]

        # Mode-appropriate labels
        if mode == EvaluationMode.MPT_OPTIMAL:
            capital_label = "Total Portfolio Capital"
            capital_value = allocator_summary["Total_Capital"]
            source_label = "Total Portfolio"
        else:
            capital_label = "Debt Capital Source"
            capital_value = allocator_summary["Total_Capital"]
            source_label = "Master Debt Fund"

        # --- Pre-compute allocation data for consistency ---
        # Build union of all funds from current and optimal weights
        all_funds = sorted(
            set(current_weights or {}).union(set(optimal_weights.keys()))
        )

        allocation_rows = []
        total_shortfall = 0.0  # Additional capital needed for Lump Sum
        for fund in all_funds:
            current_w = current_weights.get(fund, 0.0) if current_weights else 0.0
            optimal_w = optimal_weights.get(fund, 0.0)
            diff = optimal_w - current_w
            current_val = current_w * total_projected
            target_val = optimal_w * total_projected
            val_diff = target_val - current_val

            if diff > 0.001:
                action = "Buy / Increase"
            elif diff < -0.001:
                action = "Sell / Decrease"
            elif optimal_w < 0.001 and current_w > 0.001:
                action = "Sell / Exit"
            else:
                action = "Hold"

            # For Lump Sum: sum of positive shortfalls (additional capital needed)
            if val_diff > 0:
                total_shortfall += val_diff

            allocation_rows.append(
                {
                    "fund": fund,
                    "current_w": current_w,
                    "optimal_w": optimal_w,
                    "diff": diff,
                    "current_val": current_val,
                    "target_val": target_val,
                    "val_diff": val_diff,
                    "action": action,
                }
            )

        # --- STP: monthly transfer breakdown from Allocator ---
        stp_rows = []
        total_stp_monthly = 0.0
        for fund, amount in sorted(
            transfers.items(), key=lambda item: item[1], reverse=True
        ):
            if amount > 0:
                stp_rows.append((fund, amount))
                total_stp_monthly += amount

        # --- SIP: fund-wise breakdown of monthly contribution ---
        sip_rows = []
        total_sip_monthly = 0.0
        if sip_monthly_amount and sip_monthly_amount > 0:
            # Distribute SIP contribution to underweighted funds proportional to shortfall
            underweighted = [
                r for r in allocation_rows if r["val_diff"] > 0
            ]
            total_underweight_shortfall = sum(r["val_diff"] for r in underweighted)
            if total_underweight_shortfall > 0:
                for row in underweighted:
                    ratio = row["val_diff"] / total_underweight_shortfall
                    monthly_alloc = ratio * sip_monthly_amount
                    sip_rows.append((row["fund"], monthly_alloc))
                total_sip_monthly = sip_monthly_amount

        # --- Lump Sum: exact additional capital needed ---
        lump_sum_needed = round(total_shortfall, 2)

        md_content = f"""# Mutual Fund Rebalancing Report
**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 1. Executive Summary
| Metric | Value |
| :--- | :--- |
| **Total Portfolio Value** | ₹{total_projected:,.2f} |
| **Current Equity** | ₹{total_equity:,.2f} |
| **{capital_label}** | ₹{capital_value:,.2f} |
| **Planning Horizon** | {duration} Months |

## 2. Portfolio Allocation Comparison (Current vs. Optimal)
Side-by-side comparison of your current portfolio allocation and the optimal
target allocation calculated using Maximum Sharpe Ratio optimization:

| Fund | Current Weight | Optimal Weight | Difference | Current Value | Target Value | Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

        for row in allocation_rows:
            diff_icon = "▲" if row["diff"] > 0 else ("▼" if row["diff"] < 0 else "▬")
            md_content += (
                f"| {row['fund']} | {row['current_w'] * 100:.2f}% | "
                f"{row['optimal_w'] * 100:.2f}% | "
                f"{diff_icon} {row['diff'] * 100:+.2f}% | "
                f"₹{row['current_val']:,.2f} | ₹{row['target_val']:,.2f} | "
                f"{row['action']} |\n"
            )

        # --- Portfolio Health Check ---
        md_content += "\n## 3. Portfolio Health Check (Current vs. Optimized)\n"
        md_content += "Here is why the optimized portfolio is mathematically superior:\n\n"

        md_content += "| Metric | Current Portfolio | Optimized Portfolio | Improvement |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"

        # Helper for improvement string
        def fmt_imp(val, is_risk=False):
            icon = "✅" if (val > 0 and not is_risk) or (val < 0 and is_risk) else "🔻"
            return f"{icon} {val:+.1%}" if isinstance(val, float) else f"{icon} {val:+.2f}"

        if current_stats and optimized_stats:
            imp_ret = optimized_stats["Expected Return"] - current_stats["Expected Return"]
            imp_vol = optimized_stats["Volatility"] - current_stats["Volatility"]
            imp_sharpe = (
                optimized_stats["Sharpe Ratio"] - current_stats["Sharpe Ratio"]
            )
            imp_dd = optimized_stats["Max Drawdown"] - current_stats["Max Drawdown"]
            imp_sortino = (
                optimized_stats["Sortino Ratio"] - current_stats["Sortino Ratio"]
            )

            md_content += f"| **Annual Return** | {current_stats['Expected Return']:.1%} | **{optimized_stats['Expected Return']:.1%}** | {fmt_imp(imp_ret)} |\n"
            md_content += f"| **Volatility (Risk)** | {current_stats['Volatility']:.1%} | {optimized_stats['Volatility']:.1%} | {fmt_imp(imp_vol, is_risk=True)} |\n"
            md_content += f"| **Sharpe Ratio** | {current_stats['Sharpe Ratio']:.2f} | **{optimized_stats['Sharpe Ratio']:.2f}** | {fmt_imp(imp_sharpe)} |\n"
            md_content += f"| **Max Drawdown** | {current_stats['Max Drawdown']:.1%} | {optimized_stats['Max Drawdown']:.1%} | {fmt_imp(imp_dd)} |\n"
            md_content += f"| **Sortino Ratio** | {current_stats['Sortino Ratio']:.2f} | **{optimized_stats['Sortino Ratio']:.2f}** | {fmt_imp(imp_sortino)} |\n"

            md_content += "\n> **Interpretation**:\n"
            md_content += "> *   **Higher Sharpe/Sortino** = Better return for every unit of risk taken.\n"
            md_content += "> *   **Lower Volatility/Drawdown** = Smoother ride, less crash-prone.\n"

        # --- Execution Strategy Options ---
        md_content += "\n## 4. Execution Strategy Options\n"
        md_content += "You have three ways to execute this advice, ordered by recommendation:\n\n"

        # --- Option 1: STP (Recommended) ---
        md_content += "### Option 1: STP (Recommended)\n"
        md_content += "- **Action**: Gradually transfer existing invested capital from funds with zero or lower-than-optimal weights into higher-weighted target funds.\n"
        md_content += f"- **Outcome**: Your portfolio converges to optimal weights over {duration} months without requiring additional capital.\n"
        md_content += "- **Why Recommended**: Uses capital you already have invested; no new money needed. Reduces concentration risk systematically.\n\n"

        md_content += "#### Monthly STP Transfer Plan\n"
        md_content += f"| Source ({source_label}) | Target Fund | Monthly Installment | Duration |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"

        for fund, amount in stp_rows:
            md_content += f"| *{source_label}* | {fund} | **₹{amount:,.2f}** | **{duration} Months** |\n"

        md_content += f"\n**Total Monthly Outflow**: **₹{total_stp_monthly:,.2f}**\n\n"

        if total_stp_monthly == 0:
            md_content += "> **Note**: No transfers needed. Allocation is currently on target.\n\n"

        # --- Option 2: SIP ---
        md_content += "### Option 2: SIP\n"
        md_content += "- **Action**: Invest additional capital periodically (e.g., monthly) to achieve the optimal allocation while retaining existing investments.\n"
        md_content += "- **Outcome**: Existing investments stay untouched; new contributions are directed to underweighted funds until the portfolio matches optimal weights.\n"
        md_content += "- **Trade-off**: Requires ongoing additional capital; convergence depends on contribution amount and frequency.\n\n"

        if sip_monthly_amount and sip_monthly_amount > 0:
            md_content += f"#### Monthly SIP Investment Plan (₹{sip_monthly_amount:,.2f}/month)\n"
            md_content += "| Target Fund | Monthly Allocation | % of Contribution |\n"
            md_content += "| :--- | :--- | :--- |\n"

            for fund, monthly_alloc in sip_rows:
                pct = (monthly_alloc / sip_monthly_amount) * 100
                md_content += f"| {fund} | **₹{monthly_alloc:,.2f}** | {pct:.1f}% |\n"

            md_content += f"\n**Total Monthly SIP**: **₹{total_sip_monthly:,.2f}**\n\n"
        else:
            md_content += "#### Monthly SIP Investment Plan\n"
            md_content += "> **Note**: No SIP monthly amount specified. Provide a monthly contribution amount to generate a fund-wise SIP plan.\n\n"

        # --- Option 3: Lump Sum ---
        md_content += "### Option 3: Lump Sum (Least Recommended)\n"
        md_content += "- **Action**: Invest additional capital upfront to immediately achieve the optimal allocation.\n"
        md_content += "- **Outcome**: Portfolio reaches optimal weights in a single transaction.\n"
        md_content += "- **Why Least Recommended**: Requires a large amount of capital at once; exposes you to market-timing risk by deploying everything at current prices.\n\n"

        md_content += "#### Lump Sum Investment Required\n"
        md_content += "| Metric | Amount |\n| :--- | :--- |\n"
        md_content += f"| **Additional Capital Needed** | **₹{lump_sum_needed:,.2f}** |\n"
        md_content += f"| **Total Portfolio After Lump Sum** | **₹{total_projected + lump_sum_needed:,.2f}** |\n\n"

        md_content += "#### Fund-wise Lump Sum Allocation\n"
        md_content += "| Target Fund | Lump Sum Amount | % of Lump Sum |\n"
        md_content += "| :--- | :--- | :--- |\n"

        if lump_sum_needed > 0:
            for row in allocation_rows:
                if row["val_diff"] > 0:
                    pct = (row["val_diff"] / lump_sum_needed) * 100
                    md_content += f"| {row['fund']} | **₹{row['val_diff']:,.2f}** | {pct:.1f}% |\n"
        else:
            md_content += "| *No additional capital needed* | *—* | *—* |\n"

        # --- Excluded Funds ---
        if excluded_funds:
            md_content += "\n## 5. Excluded Funds\n"
            md_content += "The following funds were excluded from optimization, with the reason for each exclusion:\n\n"
            md_content += "| Fund | Reason | Detail |\n| :--- | :--- | :--- |\n"
            for exclusion in excluded_funds:
                md_content += f"| {exclusion.fund_name} | {exclusion.reason} | {exclusion.detail or ''} |\n"

        with open(filepath, "w") as f:
            f.write(md_content)

        logger.info("Report generated at: %s", filepath)
        self.console.print(f"[green]Report generated at: {filepath}[/green]")
        return filepath
