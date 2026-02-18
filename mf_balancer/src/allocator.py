import pandas as pd
from typing import Dict, List

class Allocator:
    def __init__(self, 
                 current_holdings: Dict[str, float], 
                 debt_capital: float, 
                 optimal_weights: Dict[str, float],
                 remaining_months: int):
        """
        :param current_holdings: Dict of {Fund_Name/ISIN: Current_Value_INR}
        :param debt_capital: Total capital available in Debt Fund (Source)
        :param optimal_weights: Dict of {Fund_Name/ISIN: Target_% (0.0 to 1.0)}
        :param remaining_months: Number of months to deplete the debt capital.
        """
        self.current_holdings = current_holdings
        self.debt_capital = debt_capital
        self.optimal_weights = optimal_weights
        self.remaining_months = max(1, remaining_months) # Avoid div by zero

    def calculate_transfers(self) -> Dict[str, float]:
        """
        Implements 'Target Duration Convergence STP'.
        Logic: 
        1. Determine Monthly Budget = Debt / Remaining_Months.
        2. Distribute Budget to funds proportional to their Shortfall.
        """
        # 1. Monthly Budget (Strict Deployment)
        monthly_budget = self.debt_capital / self.remaining_months
        
        # 2. Calculate Shortfalls
        current_equity_value = sum(self.current_holdings.values())
        total_future_value = current_equity_value + self.debt_capital
        
        shortfalls = {}
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
                
        # 3. Allocator Budget
        transfers = {}
        for fund, weight in self.optimal_weights.items():
            if total_positive_shortfall > 0:
                # Proportional allocation of the budget
                allocation_ratio = shortfalls[fund] / total_positive_shortfall
                transfer_amount = allocation_ratio * monthly_budget
            else:
                # Edge case: All funds are somehow overweight (market zoomed up?) 
                # or math weirdness. Fallback to optimal weights.
                transfer_amount = weight * monthly_budget
                
            transfers[fund] = round(transfer_amount, 2)
            
        return transfers
    
    def get_summary(self):
        return {
            "Total_Equity": sum(self.current_holdings.values()),
            "Debt_Capital": self.debt_capital, 
            "Total_Projected": sum(self.current_holdings.values()) + self.debt_capital
        }
