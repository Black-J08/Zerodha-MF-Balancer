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

    def get_portfolio_stats(self, weights):
        """
        Calculate basic performance stats for a given set of weights.
        Returns: (expected_return, volatility, sharpe_ratio)
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()
            
        ef = EfficientFrontier(self.mu, self.S)
        ef.set_weights(weights)
        return ef.portfolio_performance(verbose=False)

    def get_advanced_stats(self, weights):
        """
        Calculate advanced risk metrics: Sortino Ratio, Max Drawdown, VaR.
        Returns: Dictionary of metrics.
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        # 1. Basic Stats
        ret, vol, sharpe = self.get_portfolio_stats(weights)
        
        # 2. Historical Portfolio Returns (reconstructed)
        # We project the weighted portfolio onto historical returns
        pct_change = self.nav_data.dropna().pct_change().dropna()
        
        # Filter pct_change to only include assets in weights (handling 0 weights correctly)
        # Weights might contain assets not in pct_change if we messed up, so intersection is key
        common_assets = list(set(weights.keys()) & set(pct_change.columns))
        
        # Normalize weights for the subset (in case some are missing, though shouldn't happen)
        # Ideally weights sum to 1. Here we assume input weights are valid for the cleaned_data.
        
        portfolio_returns = pd.Series(0, index=pct_change.index)
        for asset, weight in weights.items():
            if asset in pct_change.columns:
                portfolio_returns += pct_change[asset] * weight
        
        # 3. Sortino Ratio (Downside Risk)
        # Risk-free rate 7% annual -> ~0.027% daily? No, stick to annual for ratio
        # Sortino = (R - Rf) / Downside Deviation
        target_return = 0
        downside_returns = portfolio_returns[portfolio_returns < target_return]
        downside_deviation = downside_returns.std() * (252**0.5) # Annualized
        
        sortino = (ret - 0.07) / downside_deviation if downside_deviation != 0 else 0
        
        # 4. Max Drawdown
        cumulative_returns = (1 + portfolio_returns).cumprod()
        peak = cumulative_returns.cummax()
        drawdown = (cumulative_returns - peak) / peak
        max_drawdown = drawdown.min()
        
        # 5. Value at Risk (VaR) - 95% Confidence
        var_95 = portfolio_returns.quantile(0.05)
        
        return {
            "Expected Return": ret,
            "Volatility": vol,
            "Sharpe Ratio": sharpe,
            "Sortino Ratio": sortino,
            "Max Drawdown": max_drawdown,
            "VaR (95%)": var_95
        }
