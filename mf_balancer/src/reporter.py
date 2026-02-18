import os
from datetime import datetime
from rich.console import Console
from rich.table import Table

class Reporter:
    def __init__(self, output_dir="mf_balancer/output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.console = Console()

    def generate_report(self, 
                        allocator_summary, 
                        optimal_weights, 
                        transfers, 
                        duration=12,
                        current_stats=None,
                        optimized_stats=None):
        """
        Generates a Markdown report and saves it.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"report_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)

        md_content = f"""# Mutual Fund Rebalancing Report
**Date**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 1. Executive Summary
| Metric | Value |
| :--- | :--- |
| **Total Portfolio Value** | ₹{allocator_summary['Total_Projected']:,.2f} |
| **Current Equity** | ₹{allocator_summary['Total_Equity']:,.2f} |
| **Debt Capital Source** | ₹{allocator_summary['Debt_Capital']:,.2f} |
| **Planning Horizon** | {duration} Months |

## 2. Optimal Allocation (MPT)
The following weights were calculated using Maximum Sharpe Ratio optimization:

| Fund | Optimal Weight | Target Value |
| :--- | :--- | :--- |
"""
        
        # Add Allocation Table Rows
        total_projected = allocator_summary['Total_Projected']
        # Sort by weight descending
        sorted_weights = dict(sorted(optimal_weights.items(), key=lambda item: item[1], reverse=True))
        
        for fund, weight in sorted_weights.items():
            if weight > 0.001: # Show only significant allocations (>0.1%)
                target_val = weight * total_projected
                md_content += f"| {fund} | {weight*100:.2f}% | ₹{target_val:,.2f} |\n"
            else:
                 pass # Skip 0% rows to keep report clean

        # --- 3. Portfolio Health Check ---
        md_content += "\n## 3. Portfolio Health Check (Current vs. Optimized)\n"
        md_content += "Here is why the optimized portfolio is mathematically superior:\n\n"

        md_content += "| Metric | Current Portfolio | Optimized Portfolio | Improvement |\n"
        md_content += "| :--- | :--- | :--- | :--- |\n"
        
        # Helper for improvement string
        def fmt_imp(val, is_risk=False):
            icon = "✅" if (val > 0 and not is_risk) or (val < 0 and is_risk) else "🔻"
            return f"{icon} {val:+.1%}" if isinstance(val, float) else f"{icon} {val:+.2f}"

        imp_ret = optimized_stats['Expected Return'] - current_stats['Expected Return']
        imp_vol = optimized_stats['Volatility'] - current_stats['Volatility']
        imp_sharpe = optimized_stats['Sharpe Ratio'] - current_stats['Sharpe Ratio']
        imp_dd = optimized_stats['Max Drawdown'] - current_stats['Max Drawdown']
        imp_sortino = optimized_stats['Sortino Ratio'] - current_stats['Sortino Ratio']

        md_content += f"| **Annual Return** | {current_stats['Expected Return']:.1%} | **{optimized_stats['Expected Return']:.1%}** | {fmt_imp(imp_ret)} |\n"
        md_content += f"| **Volatility (Risk)** | {current_stats['Volatility']:.1%} | {optimized_stats['Volatility']:.1%} | {fmt_imp(imp_vol, is_risk=True)} |\n"
        md_content += f"| **Sharpe Ratio** | {current_stats['Sharpe Ratio']:.2f} | **{optimized_stats['Sharpe Ratio']:.2f}** | {fmt_imp(imp_sharpe)} |\n"
        md_content += f"| **Max Drawdown** | {current_stats['Max Drawdown']:.1%} | {optimized_stats['Max Drawdown']:.1%} | {fmt_imp(imp_dd)} |\n"
        md_content += f"| **Sortino Ratio** | {current_stats['Sortino Ratio']:.2f} | **{optimized_stats['Sortino Ratio']:.2f}** | {fmt_imp(imp_sortino)} |\n"

        md_content += "\n> **Interpretation**:\n"
        md_content += "> *   **Higher Sharpe/Sortino** = Better return for every unit of risk taken.\n"
        md_content += "> *   **Lower Volatility/Drawdown** = Smoother ride, less crash-prone.\n"

        md_content += "\n## 4. Recommended Monthly STP Plan\n"
        md_content += "You can set up the following **Systematic Transfer Plans (STP)** to automate your investment:\n\n"
        
        md_content += "| Source (Debt) | Target (Equity) | Monthly Installment | Duration |\n| :--- | :--- | :--- | :--- |\n"
        
        total_transfer = 0
        for fund, amount in transfers.items():
            if amount > 0:
                md_content += f"| *Master Debt Fund* | {fund} | **₹{amount:,.2f}** | **{duration} Months** |\n"
                total_transfer += amount
        
        md_content += f"\n**Total Monthly Outflow**: **₹{total_transfer:,.2f}**\n"

        if total_transfer == 0:
            md_content += "\n> **Note**: No transfers needed. Equity allocation is currently overweight or on target.\n"

        # Execution Strategy Section
        remaining_debt = allocator_summary.get('Debt_Capital', 0) - (total_transfer * duration)
        
        md_content += "\n## 5. Execution Strategy Options\n"
        md_content += "You have two ways to execute this advice:\n\n"
        md_content += "### Option A: 'Set and Forget' (Static STP)\n"
        md_content += f"- **Action**: Register the STPs listed above with your broker **once**.\n"
        md_content += f"- **Outcome**: Assuming average market conditions, your portfolio will converge to optimal weights in {duration} months.\n"
        
        md_content += "\n### Option B: 'Dynamic Optimization' (Recommended)\n"
        md_content += f"- **Action**: Execute *only* this month's installment manually (or as a one-time order).\n"
        md_content += f"- **Next Step**: Run this script again **next month**.\n"
        md_content += "- **Benefit**: This allows the algorithm to adjust the transfer amounts based on market highs and lows (buying more in dips).\n"

        with open(filepath, "w") as f:
            f.write(md_content)
        
        self.console.print(f"[green]Report generated at: {filepath}[/green]")
        return filepath
