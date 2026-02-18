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
                        market_context=None):
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
        
        # Add Allocation Table
        total_projected = allocator_summary['Total_Projected']
        for fund, weight in optimal_weights.items():
            target_val = weight * total_projected
            md_content += f"| {fund} | {weight*100:.2f}% | ₹{target_val:,.2f} |\n"

        md_content += "\n## 3. Recommended Monthly STP Plan\n"
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
        
        md_content += "\n## 4. Execution Strategy Options\n"
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
