"""PortfolioOptimizer: Modern Portfolio Theory optimization.

Provides mean-variance optimization using PyPortfolioOpt with
Ledoit-Wolf shrinkage for covariance estimation.
"""

import os

import pandas as pd
from pypfopt import EfficientFrontier, expected_returns, risk_models

from src.core.logging import get_logger
from src.core.settings import Settings
from src.optimization.metrics import get_advanced_stats

logger = get_logger(__name__)


class PortfolioOptimizer:
    """Mean-variance portfolio optimizer using Modern Portfolio Theory.

    Args:
        nav_data: DataFrame with dates as index and fund names as columns,
            containing historical NAV data.
        config: Application configuration (used for data export paths).
    """

    def __init__(self, nav_data: pd.DataFrame, config: Settings):
        self.nav_data = nav_data
        self.config = config
        self.mu: pd.Series | None = None
        self.S: pd.DataFrame | None = None
        self.weights: dict | None = None

    def calculate_metrics(self) -> None:
        """Calculate expected returns and covariance matrix.

        Cleans data by dropping NaN rows to find the common overlapping
        period for all funds. Uses Ledoit-Wolf shrinkage for robust
        covariance estimation.
        """
        cleaned_prices = self.nav_data.dropna()

        if cleaned_prices.empty or len(cleaned_prices) < 30:
            raise ValueError(
                "Insufficient overlapping historical data "
                "(less than 30 days) for selected funds."
            )

        # Calculate expected returns (mean historical return)
        self.mu = expected_returns.mean_historical_return(cleaned_prices)

        # Calculate covariance matrix using Ledoit-Wolf Shrinkage
        # Industry standard for robust covariance estimation.
        self.S = risk_models.CovarianceShrinkage(cleaned_prices).ledoit_wolf()

        # Cache intermediate calculation data
        try:
            os.makedirs(self.config.data_dir, exist_ok=True)
            self.mu.to_csv(
                f"{self.config.data_dir}/expected_returns.csv",
                header=["Expected Return"],
            )
            self.S.to_csv(f"{self.config.data_dir}/covariance_matrix.csv")
            self.S.corr().to_csv(f"{self.config.data_dir}/correlation_matrix.csv")
        except OSError as e:
            logger.warning("Could not save intermediate data: %s", e)

    def optimize_sharpe_ratio(
        self,
        risk_free_rate: float = 0.07,
        weight_bounds: tuple = (0, 1),
    ) -> dict:
        """Optimize for maximal Sharpe Ratio.

        Args:
            risk_free_rate: Risk-free rate (default 0.07 = 7% for India).
            weight_bounds: Tuple of (min_weight, max_weight) for each asset.
                Default is (0, 1) i.e. long-only, 0-100%.

        Returns:
            Cleaned weights dict mapping fund name to target weight.

        Raises:
            Exception: If optimization is infeasible (e.g. constraints impossible).
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        ef = EfficientFrontier(self.mu, self.S, weight_bounds=weight_bounds)

        try:
            self.weights = ef.max_sharpe(risk_free_rate=risk_free_rate)
            cleaned_weights = ef.clean_weights()
            return cleaned_weights
        except Exception:
            logger.exception("Optimization failed")
            logger.error(
                "Hint: Your constraints might be impossible to satisfy "
                "(e.g. min weights sum > 1)."
            )
            raise

    def optimize_min_volatility(self) -> dict:
        """Optimize for minimum volatility.

        Returns:
            Cleaned weights dict mapping fund name to target weight.
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        ef = EfficientFrontier(self.mu, self.S)
        self.weights = ef.min_volatility()
        cleaned_weights = ef.clean_weights()
        return cleaned_weights

    def get_portfolio_stats(self, weights: dict) -> tuple:
        """Calculate basic performance stats for a given set of weights.

        Args:
            weights: Mapping of fund name to target weight.

        Returns:
            Tuple of (expected_return, volatility, sharpe_ratio).
        """
        if self.mu is None or self.S is None:
            self.calculate_metrics()

        ef = EfficientFrontier(self.mu, self.S)
        ef.set_weights(weights)
        return ef.portfolio_performance(verbose=False)

    def get_advanced_stats(self, weights: dict) -> dict:
        """Calculate advanced risk metrics for a given set of weights.

        Delegates to :func:`src.optimization.metrics.get_advanced_stats`.

        Args:
            weights: Mapping of fund name to target weight.

        Returns:
            Dictionary of metrics: Expected Return, Volatility, Sharpe Ratio,
            Sortino Ratio, Max Drawdown, VaR (95%).
        """
        return get_advanced_stats(self.nav_data, weights)
