import pandas as pd
from pypfopt import EfficientFrontier
from pypfopt import risk_models
from pypfopt import expected_returns
from pypfopt import discrete_allocation

class PortfolioOptimizer:
    def __init__(self, nav_data: pd.DataFrame):
        """
        Initialize with historical NAV data.
        :param nav_data: DataFrame with dates as index and scheme codes/ISINs as columns.
        """
        self.nav_data = nav_data
        self.mu = None
        self.S = None
        self.weights = None

    def calculate_metrics(self):
        """Calculate expected returns and sample covariance."""
        # Clean Data: Drop rows with any NaN values to ensure consistent timeframe
        # This effectively finds the "Common Period" for all funds.
        cleaned_prices = self.nav_data.dropna()
        
        if cleaned_prices.empty or len(cleaned_prices) < 30:
             # If intersection is too small, we might have funds with no overlapping history
             raise ValueError("Insufficient overlapping historical data (less than 30 days) for selected funds.")

        # Calculate expected returns (mean historical return)
        self.mu = expected_returns.mean_historical_return(cleaned_prices)
        
        # Calculate covariance matrix using Ledoit-Wolf Shrinkage
        # This is the industry standard for robust covariance estimation, reducing the impact of outliers and noise.
        # It yields a "cleaner" matrix than simple sample_cov.
        self.S = risk_models.CovarianceShrinkage(cleaned_prices).ledoit_wolf()
        
        # Cache intermediate calculation data
        try:
            import os
            data_dir = "mf_balancer/data"
            os.makedirs(data_dir, exist_ok=True)
            self.mu.to_csv(f"{data_dir}/expected_returns.csv", header=["Expected Return"])
            self.S.to_csv(f"{data_dir}/covariance_matrix.csv")
            # Also save correlation matrix for easier reading
            self.S.corr().to_csv(f"{data_dir}/correlation_matrix.csv")
        except Exception as e:
            print(f"Warning: Could not save intermediate data: {e}")

    def optimize_sharpe_ratio(self, risk_free_rate=0.07, weight_bounds=(0, 1)):
        """
        Optimize for maximal Sharpe Ratio.
        :param risk_free_rate: Risk-free rate (default 7% for India).
        :param weight_bounds: Tuple of (min_weight, max_weight) for each asset.
                              Default is (0, 1) i.e. long-only, 0-100%.
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        # Initialize EfficientFrontier with custom weight bounds
        # weight_bounds can be a single pair (min, max) applied to all, 
        # or a list of pairs for specific assets.
        ef = EfficientFrontier(self.mu, self.S, weight_bounds=weight_bounds)
        
        try:
            self.weights = ef.max_sharpe(risk_free_rate=risk_free_rate)
            cleaned_weights = ef.clean_weights()
            return cleaned_weights
        except Exception as e:
            # Handle infeasible problems (e.g. min_weight=0.10 with 20 funds = 200% total)
            print(f"[bold red]Optimization Failed:[/bold red] {e}")
            print("[yellow]Hint: Your constraints might be impossible to satisfy (e.g. min weights sum > 1).[/yellow]")
            raise e

    def optimize_min_volatility(self):
        """Optimize for minimum volatility."""
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        ef = EfficientFrontier(self.mu, self.S)
        self.weights = ef.min_volatility()
        cleaned_weights = ef.get_clean_weights()
        return cleaned_weights

    def get_performance_stats(self):
        """Return (expected_return, volatility, sharpe_ratio)"""
        if self.weights is None:
            return None
        
        # We need to reconstruct EF to get performance
        ef = EfficientFrontier(self.mu, self.S)
        ef.set_weights(self.weights)
        return ef.portfolio_performance(verbose=False)
