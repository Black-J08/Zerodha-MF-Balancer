"""Unit tests for PortfolioOptimizer.

Tests mean-variance optimization, Sharpe ratio optimization,
and advanced metrics calculation.
"""

import pandas as pd
import pytest

from src.core.config import Config
from src.optimization import PortfolioOptimizer


@pytest.fixture
def sample_nav_data():
    """Create sample NAV data for testing."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    data = {
        "Fund A": pd.Series(range(100, 200), index=dates) * 1.0,
        "Fund B": pd.Series(range(50, 150), index=dates) * 1.0,
        "Fund C": pd.Series(range(200, 300), index=dates) * 1.0,
    }
    return pd.DataFrame(data)


@pytest.fixture
def config():
    """Create a test Config."""
    return Config(
        data_dir="data",
        output_dir="output",
        reports_dir="output/reports",
        kite_api_key="test_key",
        kite_api_secret="test_secret",
        kite_access_token="test_token",
    )


class TestPortfolioOptimizer:
    """Tests for PortfolioOptimizer class."""

    def test_calculate_metrics(self, sample_nav_data, config):
        """Test that calculate_metrics computes mu and S."""
        optimizer = PortfolioOptimizer(sample_nav_data, config)
        optimizer.calculate_metrics()

        assert optimizer.mu is not None
        assert optimizer.S is not None
        assert len(optimizer.mu) == 3
        assert optimizer.S.shape == (3, 3)

    def test_optimize_sharpe_ratio(self, sample_nav_data, config):
        """Test Sharpe ratio optimization returns valid weights."""
        optimizer = PortfolioOptimizer(sample_nav_data, config)
        weights = optimizer.optimize_sharpe_ratio()

        assert isinstance(weights, dict)
        assert set(weights.keys()) == {"Fund A", "Fund B", "Fund C"}
        # Weights should sum to approximately 1
        assert abs(sum(weights.values()) - 1.0) < 0.01
        # All weights should be between 0 and 1
        for w in weights.values():
            assert 0 <= w <= 1

    def test_optimize_sharpe_ratio_with_bounds(self, sample_nav_data, config):
        """Test Sharpe ratio optimization with weight bounds."""
        optimizer = PortfolioOptimizer(sample_nav_data, config)
        weights = optimizer.optimize_sharpe_ratio(
            risk_free_rate=0.07, weight_bounds=(0.1, 0.5)
        )

        assert isinstance(weights, dict)
        for w in weights.values():
            assert 0.1 <= w <= 0.5

    def test_optimize_min_volatility(self, sample_nav_data, config):
        """Test minimum volatility optimization."""
        optimizer = PortfolioOptimizer(sample_nav_data, config)
        weights = optimizer.optimize_min_volatility()

        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_get_advanced_stats(self, sample_nav_data, config):
        """Test advanced metrics calculation."""
        optimizer = PortfolioOptimizer(sample_nav_data, config)
        weights = {"Fund A": 0.4, "Fund B": 0.3, "Fund C": 0.3}
        stats = optimizer.get_advanced_stats(weights)

        assert "Expected Return" in stats
        assert "Volatility" in stats
        assert "Sharpe Ratio" in stats
        assert "Sortino Ratio" in stats
        assert "Max Drawdown" in stats
        assert "VaR (95%)" in stats

    def test_insufficient_data_raises(self, config):
        """Test that insufficient data raises ValueError."""
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        data = pd.DataFrame({"Fund A": range(10)}, index=dates)
        optimizer = PortfolioOptimizer(data, config)

        with pytest.raises(ValueError, match="Insufficient overlapping historical data"):
            optimizer.calculate_metrics()
